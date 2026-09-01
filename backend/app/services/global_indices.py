"""[fork 增强] R99 全球指数实时 — 自成一体的独立模块。

用途: 侧栏挂境外指数看实时(R116 起只留韩国综合与纳斯达克)。
为什么独立: 境外市场有时差, 各自的交易时段/更新节奏与 A 股主链完全无关 ——
所以这里**不进**能力路由矩阵、不碰 QuoteService、不落盘, 就是一个带 TTL
缓存的只读小服务, 挂了也只影响这一块卡片(前端拿到空列表不渲染)。

[R119] 数据源改成**多家轮试**: 每个指数配一串候选 `(厂商, 代码)`, 按顺序取
第一个能出价的。这样"新浪这个代码没数"不再需要改代码结构, 换一家或换个写法
就是加一行。当前支持两家公开行情接口(都免 key):
  - sina    hq.sinajs.cn   需 Referer, GBK, 逗号分隔
  - tencent qt.gtimg.cn    GBK, `~` 分隔; `s_` 前缀是精简版

**TickFlow 为什么不在候选里**: 官方 SDK 的 `Region` 枚举写死
`Literal["CN", "US", "HK"]`(见 tickflow/generated_model.py) —— 压根没有韩国,
所以韩国综合走 TickFlow 无解, 这是数据源本身的边界不是配置问题。美股倒是
region=US + type=index 有定义, 能不能用取决于账号档位, `/tickflow-probe`
端点就是用来当场问清楚这件事的。
"""
from __future__ import annotations

import logging
import re
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx

logger = logging.getLogger(__name__)

_TIMEOUT_S = 6.0
_TTL_S = 5.0           # 服务端缓存: 多前端/多标签页轮询合并成同一次上游请求
_STALE_KEEP_S = 600.0  # 上游失败时旧值最多再顶 10 分钟, 之后按缺失处理
_FAIL_LOG_INTERVAL_S = 300.0  # 失败日志节流: 5 分钟一条 warning, 不刷屏
_last_fail_log = 0.0

# [R148] 行情自带时间戳相关
# 两家给这些指数的时间都是**北京时间**(国内行情站的惯例) —— 显式按上海时区解析,
# 不跟着服务器 TZ 走, 免得换个部署环境就整体偏几小时。
_QUOTE_TZ = ZoneInfo("Asia/Shanghai")
# 超出这个范围的时间戳当"读不出"处理(格式猜错/对方口径不同), 不参与新鲜度比较。
# 给未来留 5 分钟是容忍两边时钟小幅不同步。
_TS_FUTURE_TOL_S = 300.0
_TS_PAST_TOL_S = 36 * 3600.0
# 盘中超过这个年龄就算"卡住了" —— 界面据此提示, 不再让冻住的数看起来像刚更新的。
STALE_IN_SESSION_S = 600.0

_SINA_URL = "https://hq.sinajs.cn/list={codes}"
_SINA_HEADERS = {"Referer": "https://finance.sina.com.cn"}   # 新浪要求, 否则 403
_TENCENT_URL = "https://qt.gtimg.cn/q={codes}"


@dataclass(frozen=True)
class _Src:
    """一个候选行情来源。"""

    vendor: str       # "sina" / "tencent"
    code: str         # 该厂商的行情代码
    fmt: str = "int"  # sina: "int"(全球指数) / "hk"(港股行); tencent 忽略此字段


@dataclass(frozen=True)
class _Preset:
    key: str          # 稳定 id(前端选择用)
    sources: tuple[_Src, ...]
    name: str         # 显示名
    # [R112] 各市场交易时段(北京时间, 24h 制小数, 如 14.5=14:30)。跨零点的
    # 美股写成 start>end, 判定时按"跨日"处理。休市时上游值静止是正常的 ——
    # 界面据此显示"交易中/休市", 不让用户把静止当成故障。
    open_h: float = 0.0
    close_h: float = 24.0


# 指数表 —— 想加新的在这里加一行即可(独立维护的意义所在)。
# [R116] 用户定案: 只看韩国综合与纳斯达克, 其余整行删除。
PRESETS: tuple[_Preset, ...] = (
    # 韩国 09:00-15:30 KST = 08:00-14:30 北京。
    # [R113/R119] 实测新浪 int_kospi 取不到数(其余 int_* 都正常) —— 各家对韩国
    # 综合的代码写法不一, 这里把已知的几种都列成候选逐个试。**没有一个是确认
    # 过的**, 哪个能出数要用 /api/global-indices/debug 看 raw 才知道;
    # 确认之后把能用的挪到第一位、其余删掉即可。
    _Preset("kospi", (
        _Src("sina", "int_kospi"),
        _Src("sina", "znb_KS11"),
        _Src("sina", "gb_ks11"),
        _Src("sina", "hf_KS11"),
        _Src("tencent", "int_ks11"),
        _Src("tencent", "s_int_ks11"),
    ), "韩国综合", 8.0, 14.5),
    # 美股 21:30-04:00 北京(夏令时; 冬令时晚 1 小时, 这里取并集 21.5~05.0
    # 宁可多标一小时"交易中", 也不要在真开盘时标成休市)
    # [R148] 候选顺序不再决定用谁(盘中改由行情自带时刻决定, 见 pick_candidate),
    # 这里的顺序只在**休市**时当排名用。把腾讯完整版 usIXIC 提到精简版 s_usIXIC
    # 之前: 完整版带行情时刻, 精简版不带 —— 能自证的排前面。
    _Preset("nasdaq", (
        _Src("sina", "int_nasdaq"),
        _Src("tencent", "usIXIC"),
        _Src("tencent", "s_usIXIC"),
    ), "纳斯达克", 21.5, 5.0),
)
_BY_KEY = {p.key: p for p in PRESETS}
DEFAULT_KEYS = [p.key for p in PRESETS]  # 表里就这两个, 默认全看

_lock = threading.Lock()
_cache: dict[str, dict] = {}     # key → {..row..}
_cache_at: float = 0.0
_cache_sig: tuple[str, ...] = ()


def list_presets() -> list[dict]:
    return [{"key": p.key, "name": p.name} for p in PRESETS]


def _in_session(p: _Preset, now: "datetime | None" = None) -> bool:
    """该市场此刻是否在交易时段(北京时间; 周末一律休市)。"""
    from datetime import datetime as _dt
    n = now or _dt.now()
    if n.weekday() >= 5:      # 周六日 —— 美股跨零点的周一凌晨落在周一, 不误伤
        return False
    h = n.hour + n.minute / 60
    if p.open_h <= p.close_h:
        return p.open_h <= h <= p.close_h
    return h >= p.open_h or h <= p.close_h   # 跨零点(美股)


_RE_COMPACT = re.compile(r"^\d{14}$")               # 20260901222000
_RE_DATE = re.compile(r"^(\d{4})[-/](\d{1,2})[-/](\d{1,2})$")
_RE_TIME = re.compile(r"^(\d{1,2}):(\d{2})(?::(\d{2}))?$")
_RE_DATETIME = re.compile(r"^(\d{4})[-/](\d{1,2})[-/](\d{1,2})[ T](\d{1,2}):(\d{2})(?::(\d{2}))?$")


def _epoch(dt: datetime, now: float) -> float | None:
    """北京时间 datetime → epoch 秒; 明显不合理的一律当读不出。"""
    ts = dt.replace(tzinfo=_QUOTE_TZ).timestamp()
    if ts - now > _TS_FUTURE_TOL_S or now - ts > _TS_PAST_TOL_S:
        return None
    return ts


def _quote_ts(fields: list[str], now: float) -> float | None:
    """从一行行情的字段里刨出**行情自己的时刻**(epoch 秒), 刨不出返回 None。

    [R148] 这是整个多源选择的地基: 只有知道每个候选的行情时刻, 才分得清
    "这家在实时跳"和"这家还停在昨天收盘"。各家把日期/时间放在第几列并不统一
    (而且同一家不同代码都能不一样), 所以不认列号 —— 从**后往前**扫, 认得出
    哪种写法就用哪种。从后往前是因为时间戳一律在行尾, 而行首是名称和价格,
    正着扫容易把 `0.44` 之类的数字误当成别的东西。
    """
    toks = [f.strip() for f in fields]
    for tok in reversed(toks):
        if not tok:
            continue
        if _RE_COMPACT.match(tok):                    # 腾讯完整版: 20260901222000
            try:
                return _epoch(datetime.strptime(tok, "%Y%m%d%H%M%S"), now)
            except ValueError:
                continue
        m = _RE_DATETIME.match(tok)                   # 少数写法把日期时间挤在一格
        if m:
            y, mo, d, hh, mm, ss = m.groups()
            try:
                return _epoch(datetime(int(y), int(mo), int(d), int(hh), int(mm),
                                       int(ss or 0)), now)
            except ValueError:
                continue
    # 新浪 int_ 的常见写法: 日期与时间**分成两格**, 且日期在时间之前
    date_m = time_m = None
    for tok in reversed(toks):
        if time_m is None and _RE_TIME.match(tok):
            time_m = _RE_TIME.match(tok)
            continue
        if time_m is not None and _RE_DATE.match(tok):
            date_m = _RE_DATE.match(tok)
            break
    if date_m is None or time_m is None:
        return None
    y, mo, d = date_m.groups()
    hh, mm, ss = time_m.groups()
    try:
        return _epoch(datetime(int(y), int(mo), int(d), int(hh), int(mm), int(ss or 0)), now)
    except ValueError:
        return None


def _to_float(raw: str) -> float | None:
    try:
        v = float(raw.replace(",", "").replace("%", "").strip())
    except (ValueError, AttributeError):
        return None
    return v


def _parse_sina(src: _Src, payload: str) -> tuple[float, float | None, float | None] | None:
    """新浪一行 → (最新, 涨跌额, 涨跌幅%)。

    int_ 格式自适应: 标准是"名称,最新,涨跌额,涨跌幅", 但个别代码会多一列
    (如前置英文代码) —— 从头找到第一个能解析成数的字段当最新价, 紧随其后
    两个字段当涨跌额/涨跌幅, 两种排布都吃得下。
    """
    fields = payload.split(",")
    if src.fmt == "hk" and len(fields) >= 9:
        last = _to_float(fields[6])
        return (last, _to_float(fields[7]), _to_float(fields[8])) if last is not None else None
    for i in range(min(len(fields), 6)):
        v = _to_float(fields[i])
        if v is not None:
            return (
                v,
                _to_float(fields[i + 1]) if i + 1 < len(fields) else None,
                _to_float(fields[i + 2]) if i + 2 < len(fields) else None,
            )
    return None


def _parse_tencent(src: _Src, payload: str) -> tuple[float, float | None, float | None] | None:
    """腾讯一行 → (最新, 涨跌额, 涨跌幅%)。字段以 `~` 分隔, 两种排布:

      精简版(`s_` 前缀): 市场~名称~代码~最新~涨跌额~涨跌幅~成交量~成交额
      完整版:            ~名称~代码~最新~昨收~今开~…~涨跌额(31)~涨跌幅(32)~…
    """
    f = payload.split("~")
    if len(f) < 6:
        return None
    last = _to_float(f[3])
    if last is None:
        return None
    if len(f) >= 33:                    # 完整版
        return last, _to_float(f[31]), _to_float(f[32])
    return last, _to_float(f[4]), _to_float(f[5])


_PARSERS = {"sina": _parse_sina, "tencent": _parse_tencent}


def _parse(src: _Src, payload: str, now: float | None = None) -> dict | None:
    """一行行情 → 价格三元组字典。任何字段缺失/畸形返回 None(缺失处理, 不抛)。"""
    parser = _PARSERS.get(src.vendor)
    if parser is None or not payload.strip():
        return None
    got = parser(src, payload)
    if got is None or got[0] is None:
        return None
    last, change, pct = got
    sep = "~" if src.vendor == "tencent" else ","
    return {
        "last": last,
        "change": change,
        # 各家口径都是百分数(如 -0.38 表示 -0.38%), 转小数制与项目 change_pct 一致
        "change_pct": pct / 100.0 if pct is not None else None,
        # [R148] 行情自己的时刻(epoch 秒); 这家不给或读不出就是 None
        "quote_at": _quote_ts(payload.split(sep), now if now is not None else time.time()),
    }


def _fetch_sina(codes: list[str]) -> dict[str, str]:
    url = _SINA_URL.format(codes=",".join(codes))
    resp = httpx.get(url, headers=_SINA_HEADERS, timeout=_TIMEOUT_S, follow_redirects=True)
    resp.raise_for_status()
    out: dict[str, str] = {}
    for line in resp.content.decode("gbk", errors="replace").splitlines():
        # 形如: var hq_str_int_nasdaq="纳斯达克,22484.07,98.5,0.44";
        if "hq_str_" not in line or '"' not in line:
            continue
        head, _, rest = line.partition('"')
        payload = rest.rsplit('"', 1)[0]
        code = head.split("hq_str_", 1)[1].rstrip("=").strip()
        if payload.strip():
            out[code] = payload
    return out


def _fetch_tencent(codes: list[str]) -> dict[str, str]:
    url = _TENCENT_URL.format(codes=",".join(codes))
    resp = httpx.get(url, timeout=_TIMEOUT_S, follow_redirects=True)
    resp.raise_for_status()
    out: dict[str, str] = {}
    for line in resp.content.decode("gbk", errors="replace").splitlines():
        # 形如: v_s_usIXIC="200~纳斯达克~IXIC~22484.07~98.5~0.44~…";
        if not line.startswith("v_") or '"' not in line:
            continue
        head, _, rest = line.partition('"')
        payload = rest.rsplit('"', 1)[0]
        code = head[2:].rstrip("=").strip()
        if payload.strip():
            out[code] = payload
    return out


_FETCHERS = {"sina": _fetch_sina, "tencent": _fetch_tencent}


def _fetch_all(sources: list[_Src]) -> dict[tuple[str, str], str]:
    """按厂商分组各拉一次 → {(vendor, code): 原始 payload}。

    某一家挂了不影响另一家(分别 try) —— 多源的意义就在这。
    """
    out: dict[tuple[str, str], str] = {}
    by_vendor: dict[str, list[str]] = {}
    for s in sources:
        by_vendor.setdefault(s.vendor, []).append(s.code)
    for vendor, codes in by_vendor.items():
        fetcher = _FETCHERS.get(vendor)
        if fetcher is None:
            continue
        try:
            for code, payload in fetcher(sorted(set(codes))).items():
                out[(vendor, code)] = payload
        except Exception as e:  # noqa: BLE001 —— 单家失败降级为"这家没数"
            logger.debug("全球指数上游 %s 拉取失败: %s", vendor, e)
    return out


def pick_candidate(p: _Preset, raw: dict, now: float, *, in_session: bool) -> dict | None:
    """[R148] 从该指数的所有候选里挑一个 —— **按行情自己的时刻挑, 不按排名挑**。

    原来的规则是"候选表里第一个能解析出数的就用"。它的致命处在于: 一家把上一次
    收盘价一直挂着不动, 也是"能解析出数"—— 于是永远轮不到后面真在跳的那家,
    界面上就是一个盘中纹丝不动的纳指。而这种故障从外面看不出来, 因为我们记的
    ``updated_at`` 是**我们抓取的时刻**, 不是行情的时刻, 永远显示"刚刚"。

    新规则分两种情形, 因为"新鲜"只在开盘时才有意义:

    - **盘中**: 谁的行情时刻最新用谁。读不出时刻的候选(如腾讯 ``s_`` 精简版
      根本不给时间)排在所有能读出时刻的后面 —— 不是因为它一定差, 而是它无法
      自证, 而此刻我们**有**能自证的候选可用。
    - **休市**: 所有人都静止, 比新鲜度没有意义, 回到候选表的排名顺序。

    时区/口径猜错的情况已经在 ``_epoch`` 兜住了(超出 ±范围一律当读不出),
    所以最坏情况是退化成原来的排名规则, 不会挑出一个更差的。
    """
    parsed: list[tuple[int, dict, _Src]] = []
    for rank, src in enumerate(p.sources):
        got = _parse(src, raw.get((src.vendor, src.code), ""), now)
        if got is not None:
            parsed.append((rank, got, src))
    if not parsed:
        return None
    if in_session:
        # 排序键: 有时刻的在前(0/1), 时刻越新越前(取负), 同分回到候选表排名
        rank, got, src = min(
            parsed,
            key=lambda t: (t[1]["quote_at"] is None, -(t[1]["quote_at"] or 0.0), t[0]),
        )
    else:
        rank, got, src = parsed[0]
    quote_at = got.get("quote_at")
    out = dict(got)
    out.update({
        "key": p.key,
        "name": p.name,
        "updated_at": now,
        "trading": in_session,
        "source": src.vendor,
        "source_code": src.code,
        # 行情多久没动了(秒)。None = 这家不给时刻, 说不出来 —— 说不出来就
        # 老实显示"说不出来", 不拿抓取时刻冒充行情时刻。
        "quote_age_s": (now - quote_at) if quote_at is not None else None,
        # 盘中却半天没更新 = 这个数已经不能信了, 前端据此收掉"实时跳动"的样子
        "stale": bool(
            in_session and quote_at is not None and (now - quote_at) > STALE_IN_SESSION_S
        ),
        # 有几个候选出了数 —— 只有一个时"挑最新"其实无从挑起, 值得在诊断里看到
        "candidates_parsed": len(parsed),
    })
    return out


def get_quotes(keys: list[str]) -> list[dict]:
    """返回所选指数的最新行(带 updated_at, epoch 秒)。

    TTL 内直接回缓存; 上游失败回旧值(最多 _STALE_KEEP_S), 再久返回空行集。
    """
    presets = [_BY_KEY[k] for k in keys if k in _BY_KEY]
    if not presets:
        return []
    sources = [s for p in presets for s in p.sources]
    sig = tuple(f"{s.vendor}:{s.code}" for s in sources)
    now = time.time()
    with _lock:
        fresh = _cache_sig == sig and (now - _cache_at) < _TTL_S
        if not fresh:
            try:
                raw = _fetch_all(sources)
                rows: dict[str, dict] = {}
                for p in presets:
                    # [R148] 挑候选的规则见 pick_candidate —— 盘中按行情时刻挑最新的
                    picked = pick_candidate(p, raw, now, in_session=_in_session(p))
                    if picked is not None:
                        rows[p.key] = picked
                if rows:
                    _set_cache(rows, now, sig)
                elif (now - _cache_at) > _STALE_KEEP_S:
                    _set_cache({}, now, sig)
            except Exception as e:  # noqa: BLE001
                global _last_fail_log
                if now - _last_fail_log > _FAIL_LOG_INTERVAL_S:
                    _last_fail_log = now
                    logger.warning("全球指数上游拉取失败(软, 卡片显示旧值/空): %s", e)
                if (now - _cache_at) > _STALE_KEEP_S:
                    _set_cache({}, now, sig)
        return [dict(_cache[k]) for k in (p.key for p in presets) if k in _cache]


def debug_fetch(keys: list[str]) -> dict:
    """诊断用: 直连上游一次, 返回每个候选的原始 payload 与解析结果(不进缓存)。

    卡片空白时打开这个看是哪一步断了 —— raw 里那个代码是空的 = 这家没有这个
    指数(换代码), raw 有值但 parsed 是 null = 字段排布和解析器对不上(改解析)。

    [R148] 数字**不动**时也看这里: 每个候选多了 `quote_at_text`(行情自己说的
    时刻)与 `age_s`(它离现在多久)。盘中某家的 age_s 是几小时 = 那家把上次收盘
    挂着不动; `picked` 告诉你最后用了谁、为什么。`age_s` 是 null = 这家不给
    时刻, 无从判断新不新。
    """
    presets = [_BY_KEY[k] for k in keys if k in _BY_KEY] or list(PRESETS)
    sources = [s for p in presets for s in p.sources]
    raw = _fetch_all(sources)
    now = time.time()

    def _one(s: _Src) -> dict | None:
        got = _parse(s, raw.get((s.vendor, s.code), ""), now)
        if got is None:
            return None
        qa = got.get("quote_at")
        return {
            **got,
            "quote_at_text": (
                datetime.fromtimestamp(qa, _QUOTE_TZ).strftime("%Y-%m-%d %H:%M:%S")
                if qa else None
            ),
            "age_s": round(now - qa) if qa else None,
        }

    return {
        "ok": True,
        "now": datetime.fromtimestamp(now, _QUOTE_TZ).strftime("%Y-%m-%d %H:%M:%S"),
        "candidates": [f"{s.vendor}:{s.code}" for s in sources],
        "raw": {f"{v}:{c}": payload for (v, c), payload in raw.items()},
        "parsed": {
            p.key: {f"{s.vendor}:{s.code}": _one(s) for s in p.sources}
            for p in presets
        },
        "picked": {
            p.key: pick_candidate(p, raw, now, in_session=_in_session(p))
            for p in presets
        },
        "in_session": {p.key: _in_session(p) for p in presets},
    }


def tickflow_probe() -> dict:
    """[R119] 用用户自己的 TickFlow key 问清楚"境外指数到底能不能走 TickFlow"。

    SDK 的 Region 枚举只有 CN/US/HK —— 韩国不用问了, 没有。这里问的是美股:
    账号档位能不能列出 region=US 的指数、拿不拿得到它的实时报价。
    纯读探针: 只列 instruments + 拉一次 quote, 不落盘、不进任何缓存链路。
    """
    out: dict = {"regions_supported": ["CN", "US", "HK"], "korea": False}
    try:
        from app.tickflow.client import get_client
        client = get_client()
    except Exception as e:  # noqa: BLE001
        return {**out, "ok": False, "error": f"TickFlow 客户端不可用: {e}"}
    if client is None:
        return {**out, "ok": False, "error": "没有配置 TickFlow key"}

    try:
        out["exchanges"] = client.exchanges.list()
    except Exception as e:  # noqa: BLE001
        out["exchanges_error"] = f"{type(e).__name__}: {e}"
    try:
        us_index = client.exchanges.get_instruments("US", instrument_type="index") or []
        out["us_index_count"] = len(us_index)
        out["us_index_sample"] = us_index[:20]
        symbols = [i.get("symbol") for i in us_index[:5] if isinstance(i, dict) and i.get("symbol")]
        if symbols:
            out["quote_probe_symbols"] = symbols
            out["quote_probe"] = client.quotes.get(symbols=symbols)
    except Exception as e:  # noqa: BLE001
        out["us_index_error"] = f"{type(e).__name__}: {e}"
    out["ok"] = True
    return out


def _set_cache(rows: dict[str, dict], at: float, sig: tuple[str, ...]) -> None:
    global _cache, _cache_at, _cache_sig
    _cache = rows
    _cache_at = at
    _cache_sig = sig
