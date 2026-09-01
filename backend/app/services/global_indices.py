"""[fork 增强] R99 全球指数实时 — 自成一体的独立模块。

用途: 侧栏挂境外指数看实时(R149 起只剩纳斯达克一只)。
为什么独立: 境外市场有时差, 各自的交易时段/更新节奏与 A 股主链完全无关 ——
所以这里**不进**能力路由矩阵、不碰 QuoteService、不落盘, 就是一个带 TTL
缓存的只读小服务, 挂了也只影响这一块卡片(前端拿到空列表不渲染)。

[R119] 数据源**多家轮试**: 每个指数配一串候选 `(厂商, 代码)`。
[R148] 挑谁不再看候选表排名, 而是看**行情自带的时刻** —— 一家把上次收盘价
挂着不动也算"能出数", 按排名挑就永远轮不到真在跳的那家(用户报的"纳指不动"
就是这么来的)。详见 `pick_candidate`。

当前支持三家:
  - tickflow 官方 SDK 直连(见下), 结构化返回, 自带毫秒级时间戳
  - sina     hq.sinajs.cn   需 Referer, GBK, 逗号分隔
  - tencent  qt.gtimg.cn    GBK, `~` 分隔; `s_` 前缀是精简版(不给时刻)

**[R149] TickFlow 现在是纳指的首选候选**。之前不放它是因为要兼顾韩国综合 ——
SDK 的 `Region` 枚举写死 `Literal["CN", "US", "HK"]`(见 generated_model.py),
压根没有韩国, 那是数据源本身的边界不是配置问题。R149 按用户要求删掉韩国之后,
这块只剩美股, 而美股 `region=US + type=index` 是有定义的, 于是回到项目本来的
"只用 TickFlow"原则, 把它排在最前面试。

关于 TickFlow 这条支路的三条自我约束:
  1. **不许让现状变差** —— 档位不给美股指数时 `_fetch_tickflow` 返回空,
     直接回落到 sina/tencent, 与 R148 之前的行为完全一致。
  2. **不烧配额** —— 只在美股交易时段调用(休市时那个数是静止的, 花配额去拿
     没有意义), 且自带 20 秒最小间隔(侧栏看境外指数不需要秒级)。
  3. **不进能力路由** —— 直接用 SDK 只读一次, 不落盘、不走 QuoteService,
     保持本模块"挂了也只坏这一张卡"的性质。

代码到底解析成 TickFlow 的哪个 symbol 不靠猜: `_tickflow_resolve` 去
`exchanges.get_instruments("US", type="index")` 里按代码根/名称找, 找到什么用
什么, 找不到就是找不到(负结果也缓存, 不反复问)。`/api/global-indices/debug`
与 `/tickflow-probe` 会把这一步的结果原样吐出来。
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

    vendor: str       # "tickflow" / "sina" / "tencent"
    code: str         # 该厂商的行情代码(tickflow 填代码根, 真实 symbol 去清单里解析)
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
    # [R150] 该市场的行情时刻**可能**用哪些时区发布, 写成"要补几小时才是北京时间"。
    # 0 永远在列(就是北京时间)。见 `_shift_quote_at` —— 只有当某个补正能把
    # 时刻拉回"确实新鲜"时才采纳, 所以多列一个候选不会凭空制造新鲜感。
    tz_shifts_h: tuple[float, ...] = (0.0,)


# 指数表 —— 想加新的在这里加一行即可(独立维护的意义所在)。
# [R149] 用户定案: 韩国综合整行删除, 只留纳斯达克。
PRESETS: tuple[_Preset, ...] = (
    # 美股 21:30-04:00 北京(夏令时; 冬令时晚 1 小时, 这里取并集 21.5~05.0
    # 宁可多标一小时"交易中", 也不要在真开盘时标成休市)
    # [R148] 候选顺序不再决定用谁(盘中改由行情自带时刻决定, 见 pick_candidate),
    # 这里的顺序只在**休市**时当排名用。排序依据是"能不能自证新鲜":
    # tickflow(毫秒时间戳) > sina/腾讯完整版(秒级时刻) > 腾讯精简版(不给时刻)。
    # [R150] 美股这一行的时刻**可能是美东当地时间** —— 用户实测卡片恒定显示
    # "延迟720分"(=12 小时整), 而北京与美东夏令时正好差 12 小时。真卡住不长
    # 这样(那个数会随时间连续变大), 恒定整数小时是时区口径不同的签名。
    # 12=夏令时(EDT, UTC-4), 13=冬令时(EST, UTC-5)。
    _Preset("nasdaq", (
        _Src("tickflow", "IXIC"),
        _Src("sina", "int_nasdaq"),
        _Src("tencent", "usIXIC"),
        _Src("tencent", "s_usIXIC"),
    ), "纳斯达克", 21.5, 5.0, (0.0, 12.0, 13.0)),
)
_BY_KEY = {p.key: p for p in PRESETS}
DEFAULT_KEYS = [p.key for p in PRESETS]  # [R149] 表里只剩纳指, 默认全看

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


def _shift_quote_at(quote_at: float | None, now: float,
                    shifts: tuple[float, ...]) -> tuple[float | None, float]:
    """[R150] 行情时刻的**时区口径**补正 → (补正后的时刻, 用了几小时)。

    起因: 纳指卡片恒定显示"延迟720分"。720 分 = 12 小时整, 而北京与美东夏令时
    正好差 12 小时 —— 这是"那家发的是当地时间, 而我按北京时间解析了"的签名,
    不是真的延迟。真卡住的数**不长这样**: 它的年龄会随时间连续变大, 不会钉在
    一个整数小时上。

    关键是**不能顺手把真故障也抹掉**。所以只有当某个补正能把时刻拉回
    "确实新鲜"(年龄 < `STALE_IN_SESSION_S`)时才采纳; 补完还差几小时的,
    说明这个补正什么也没解释, 一律按原样报。

    这条守卫让"真的冻住 12 小时"这种极端巧合也只能骗过很短一瞬: 时间一走,
    原始年龄就超过 12 小时, 补正之后不再落在新鲜区间, 卡片马上又变回延迟。
    """
    if quote_at is None:
        return None, 0.0
    best = (quote_at, 0.0)
    best_age = now - quote_at
    for h in shifts:
        if not h:
            continue
        cand = quote_at + h * 3600.0
        age = now - cand
        # 未来太多说明补过头了(比如冬夏令时挑错), 不要
        if age < -_TS_FUTURE_TOL_S:
            continue
        # 补完仍然不新鲜 = 这个补正没解释任何事, 不采纳
        if age >= STALE_IN_SESSION_S:
            continue
        if abs(age) < abs(best_age):
            best, best_age = (cand, h), age
    return best


def _to_float(raw: str) -> float | None:
    try:
        v = float(raw.replace(",", "").replace("%", "").strip())
    except (ValueError, AttributeError):
        return None
    return v


# ---------------------------------------------------------------- TickFlow 支路
# [R149] 独立于 A 股主链的一次只读 SDK 调用。三条自我约束见模块头。
_TICKFLOW_REGION = "US"
_TICKFLOW_MIN_INTERVAL_S = 20.0   # 侧栏看境外指数不需要秒级, 别拿配额换刷新率
_TF_SYMBOL_TTL_S = 6 * 3600.0     # 合约清单是静态元数据, 半天问一次绰绰有余
# 代码根 → 名称里出现任一即认(小写比对)。symbol 匹配优先, 名称是兜底。
_TF_NAME_HINTS: dict[str, tuple[str, ...]] = {
    "IXIC": ("nasdaq composite", "nasdaq comp", "纳斯达克综合", "纳斯达克"),
}
_tf_lock = threading.Lock()
_tf_at = 0.0
_tf_payloads: dict[str, dict] = {}          # 代码根 → 上次拿到的 quote
_tf_symbol: dict[str, str | None] = {}      # 代码根 → 解析出的真实 symbol(None=查过没有)
_tf_symbol_at = 0.0
_tf_last_error: str | None = None


def _tf_root(symbol: str) -> str:
    """`.IXIC.US` / `IXIC.US` / `IXIC` → `IXIC`。各家对指数加不加前导点不统一。"""
    return symbol.strip().lstrip(".").split(".", 1)[0].upper()


def _tickflow_resolve(client, roots: list[str], now: float) -> dict[str, str | None]:
    """代码根 → TickFlow 真实 symbol。**不猜代码**, 去合约清单里找。

    猜 `IXIC.US` / `.IXIC.US` / `NDX.US` 哪个对, 猜错了只会得到一个静默的空值;
    去 `get_instruments("US", type="index")` 里按代码根和名称找, 找到什么用什么,
    对方改了写法也自动跟上。负结果同样缓存 —— "这个档位没有美股指数"是个稳定
    事实, 不该每 20 秒再问一遍。
    """
    global _tf_symbol, _tf_symbol_at, _tf_last_error
    fresh = (now - _tf_symbol_at) < _TF_SYMBOL_TTL_S
    if fresh and all(r in _tf_symbol for r in roots):
        return {r: _tf_symbol[r] for r in roots}
    try:
        instruments = client.exchanges.get_instruments(
            _TICKFLOW_REGION, instrument_type="index") or []
    except Exception as e:  # noqa: BLE001 —— 档位不给/网络不通都算"这家没有"
        _tf_last_error = f"列合约失败: {type(e).__name__}: {e}"
        logger.debug("TickFlow 美股指数清单不可用: %s", e)
        return dict.fromkeys(roots)
    found: dict[str, str | None] = {}
    for root in roots:
        hit = None
        for inst in instruments:
            if not isinstance(inst, dict):
                continue
            sym = str(inst.get("symbol") or "")
            if not sym:
                continue
            if _tf_root(sym) == root:
                hit = sym
                break
        if hit is None:                      # symbol 对不上再退到名称匹配
            hints = _TF_NAME_HINTS.get(root, ())
            for inst in instruments:
                if not isinstance(inst, dict):
                    continue
                name = str(inst.get("name") or "").lower()
                if name and any(h in name for h in hints):
                    hit = str(inst.get("symbol") or "") or None
                    break
        found[root] = hit
    _tf_symbol = {**_tf_symbol, **found}
    _tf_symbol_at = now
    _tf_last_error = None if any(found.values()) else "清单里没有匹配的美股指数"
    return found


def _fetch_tickflow(codes: list[str]) -> dict[str, dict]:
    """代码根 → TickFlow quote 原样。任何一步不通都返回空 = "这家没数"。

    返回空的代价只是回落到 sina/腾讯 —— 与 R149 之前的行为完全一致, 所以
    这条支路**不可能让现状变差**, 这是敢把它排第一位的前提。
    """
    global _tf_at, _tf_payloads, _tf_last_error
    now = time.time()
    with _tf_lock:
        if (now - _tf_at) < _TICKFLOW_MIN_INTERVAL_S:
            return dict(_tf_payloads)   # 最小间隔内复用上次的, 不再打一次
        _tf_at = now
    roots = [_tf_root(c) for c in codes]
    try:
        from app.tickflow.client import get_client
        client = get_client()
    except Exception as e:  # noqa: BLE001
        _tf_last_error = f"客户端不可用: {type(e).__name__}: {e}"
        return {}
    if client is None:
        _tf_last_error = "没有配置 TickFlow key"
        return {}
    mapping = _tickflow_resolve(client, roots, now)
    symbols = [s for s in mapping.values() if s]
    if not symbols:
        return {}
    try:
        quotes = client.quotes.get(symbols=symbols) or []
    except Exception as e:  # noqa: BLE001
        _tf_last_error = f"取报价失败: {type(e).__name__}: {e}"
        logger.debug("TickFlow 美股指数报价失败: %s", e)
        return {}
    by_root: dict[str, dict] = {}
    for q in quotes:
        if not isinstance(q, dict):
            continue
        sym = str(q.get("symbol") or "")
        if sym:
            by_root[_tf_root(sym)] = q
    out = {root: by_root[root] for root in roots if root in by_root}
    with _tf_lock:
        _tf_payloads = dict(out)
    _tf_last_error = None if out else "报价里没有请求的指数"
    return out


def _parse_tickflow(src: _Src, payload) -> tuple[float, float | None, float | None] | None:
    """TickFlow quote → (最新, 涨跌额, 涨跌幅%)。

    SDK 不直接给涨跌, 给的是 `last_price` 与 `prev_close` —— 自己减。
    `prev_close` 缺或为 0 时只报最新价, 涨跌留空(宁可空着, 不编一个 0%)。
    """
    if not isinstance(payload, dict):
        return None
    last = _to_float(str(payload.get("last_price")))
    if last is None:
        return None
    prev = _to_float(str(payload.get("prev_close")))
    if prev is None or prev == 0:
        return last, None, None
    change = last - prev
    return last, change, change / prev * 100.0


def _tickflow_quote_ts(payload, now: float) -> float | None:
    """TickFlow 的 `timestamp` 是**毫秒** epoch。范围守卫与文本源一视同仁。"""
    if not isinstance(payload, dict):
        return None
    raw = payload.get("timestamp")
    try:
        ts = float(raw) / 1000.0
    except (TypeError, ValueError):
        return None
    if ts - now > _TS_FUTURE_TOL_S or now - ts > _TS_PAST_TOL_S:
        return None
    return ts


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


_PARSERS = {"sina": _parse_sina, "tencent": _parse_tencent, "tickflow": _parse_tickflow}
# [R149] 结构化厂商: payload 是 dict 而不是一行文本, 时刻另有出处
_STRUCTURED = frozenset({"tickflow"})


def _parse(src: _Src, payload, now: float | None = None) -> dict | None:
    """一行行情 → 价格三元组字典。任何字段缺失/畸形返回 None(缺失处理, 不抛)。"""
    parser = _PARSERS.get(src.vendor)
    if parser is None:
        return None
    now = now if now is not None else time.time()
    if src.vendor in _STRUCTURED:
        if not isinstance(payload, dict) or not payload:
            return None
        quote_at = _tickflow_quote_ts(payload, now)
    else:
        if not isinstance(payload, str) or not payload.strip():
            return None
        sep = "~" if src.vendor == "tencent" else ","
        quote_at = _quote_ts(payload.split(sep), now)
    got = parser(src, payload)
    if got is None or got[0] is None:
        return None
    last, change, pct = got
    return {
        "last": last,
        "change": change,
        # 各家口径都是百分数(如 -0.38 表示 -0.38%), 转小数制与项目 change_pct 一致
        "change_pct": pct / 100.0 if pct is not None else None,
        # [R148] 行情自己的时刻(epoch 秒); 这家不给或读不出就是 None
        "quote_at": quote_at,
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


_FETCHERS = {"sina": _fetch_sina, "tencent": _fetch_tencent, "tickflow": _fetch_tickflow}


def _fetch_all(sources: list[_Src]) -> dict[tuple[str, str], object]:
    """按厂商分组各拉一次 → {(vendor, code): 原始 payload}。

    某一家挂了不影响另一家(分别 try) —— 多源的意义就在这。
    payload 对文本源是一行字符串, 对结构化源(tickflow)是一个 dict。
    """
    out: dict[tuple[str, str], object] = {}
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

    [R150] 比新鲜度**之前**先做一次时区口径补正(``_shift_quote_at``) —— 否则
    一家发当地时间的源会被恒定误判成"落后 12 小时", 在这里永远排最后。
    """
    parsed: list[tuple[int, dict, _Src]] = []
    for rank, src in enumerate(p.sources):
        got = _parse(src, raw.get((src.vendor, src.code), ""), now)
        if got is None:
            continue
        shifted, shift_h = _shift_quote_at(got.get("quote_at"), now, p.tz_shifts_h)
        got["quote_at"] = shifted
        got["tz_shift_h"] = shift_h
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
    # [R149] 休市时不去打 TickFlow —— 那个数是静止的, 花配额拿它没有意义。
    # 免费源照拉(不要钱, 且休市值也要显示), 这条只针对付费支路。
    sessions = {p.key: _in_session(p) for p in presets}
    sources = [
        s for p in presets for s in p.sources
        if not (s.vendor == "tickflow" and not sessions[p.key])
    ]
    if not sources:
        return []
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
                    picked = pick_candidate(p, raw, now, in_session=sessions[p.key])
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

    def _one(p: _Preset, s: _Src) -> dict | None:
        got = _parse(s, raw.get((s.vendor, s.code), ""), now)
        if got is None:
            return None
        raw_qa = got.get("quote_at")
        qa, shift_h = _shift_quote_at(raw_qa, now, p.tz_shifts_h)
        return {
            **got,
            "quote_at": qa,
            # [R150] 补正前后都给, 免得"卡片说不延迟了"变成一句无法复核的话
            "quote_at_raw_text": (
                datetime.fromtimestamp(raw_qa, _QUOTE_TZ).strftime("%Y-%m-%d %H:%M:%S")
                if raw_qa else None
            ),
            "raw_age_s": round(now - raw_qa) if raw_qa else None,
            "tz_shift_h": shift_h,
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
            p.key: {f"{s.vendor}:{s.code}": _one(p, s) for s in p.sources}
            for p in presets
        },
        "tz_shifts_h": {p.key: list(p.tz_shifts_h) for p in presets},
        "picked": {
            p.key: pick_candidate(p, raw, now, in_session=_in_session(p))
            for p in presets
        },
        "in_session": {p.key: _in_session(p) for p in presets},
    }


def tickflow_probe() -> dict:
    """[R119/R149] 用用户自己的 key 当场问清楚"纳指到底能不能走 TickFlow"。

    R149 把 TickFlow 排成纳指的首选候选之后, 这个探针要回答的就是一句话:
    **这个档位给不给美股指数报价**。给 → 侧栏那个数从此由 TickFlow 供;
    不给 → 自动回落 sina/腾讯, 与之前一模一样(所以放它在第一位是安全的)。

    输出里最该看的是 `nasdaq_resolved`(代码根 IXIC 在合约清单里对上了哪个
    symbol, null = 这个档位的清单里根本没有)与 `nasdaq_quote`(那个 symbol
    真的拿到报价没有)。纯读探针: 只列 instruments + 拉一次 quote,
    不落盘、不进任何缓存链路。
    """
    out: dict = {"regions_supported": ["CN", "US", "HK"]}
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

    # [R149] 直奔正题: 纳指这一路到底通不通
    now = time.time()
    roots = [_tf_root(s.code) for p in PRESETS for s in p.sources if s.vendor == "tickflow"]
    if roots:
        resolved = _tickflow_resolve(client, roots, now)
        out["nasdaq_resolved"] = resolved
        picked = [s for s in resolved.values() if s]
        if picked:
            try:
                quotes = client.quotes.get(symbols=picked) or []
                out["nasdaq_quote"] = quotes
                # 报价自带的时刻离现在多久 —— 这才是"能不能解决不动的问题"的答案
                out["nasdaq_quote_age_s"] = [
                    (round(now - ts) if (ts := _tickflow_quote_ts(q, now)) else None)
                    for q in quotes if isinstance(q, dict)
                ]
            except Exception as e:  # noqa: BLE001
                out["nasdaq_quote_error"] = f"{type(e).__name__}: {e}"
        else:
            out["nasdaq_quote_error"] = _tf_last_error or "合约清单里没找到纳指"
    out["ok"] = True
    return out


def _set_cache(rows: dict[str, dict], at: float, sig: tuple[str, ...]) -> None:
    global _cache, _cache_at, _cache_sig
    _cache = rows
    _cache_at = at
    _cache_sig = sig
