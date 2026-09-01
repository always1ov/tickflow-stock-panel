"""[fork 增强] R99 全球指数实时 — 自成一体的独立模块。

用途: 侧栏挂几个境外指数(韩综指/日经/恒生/美股三大)看实时。
为什么独立: TickFlow 与 fuyao 都是纯 A 股源, 给不了境外指数; 且境外市场
有时差, 各自的交易时段/更新节奏与 A 股主链完全无关 —— 所以这里**不进**
能力路由矩阵、不碰 QuoteService、不落盘, 就是一个带 TTL 缓存的只读小服务,
挂了也只影响这一块卡片(前端拿到空列表不渲染)。

数据源: 新浪财经公开行情接口(hq.sinajs.cn, 免 key, 需带 Referer)。
GBK 编码, 两种行格式:
  - int_  全球指数: "指数名, 最新价, 涨跌额, 涨跌幅%"
  - rt_hk 港股:     "代码, 名称, 开盘, 昨收, 最高, 最低, 最新, 涨跌额, 涨跌幅%, ..."
字段顺序由 preset 表逐个钉死, 解析失败按缺失处理(不抛)。

时差处理: 不做时段门控 —— 各市场休市时上游值天然静止, 卡片带 updated_at
供前端标注新鲜度; 请求由前端轮询驱动 + 服务端 TTL 合并, 没人看就零请求。
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)

_URL = "https://hq.sinajs.cn/list={codes}"
_HEADERS = {"Referer": "https://finance.sina.com.cn"}  # 新浪要求, 否则 403
_TIMEOUT_S = 6.0
_TTL_S = 5.0           # 服务端缓存: 多前端/多标签页轮询合并成同一次上游请求
_STALE_KEEP_S = 600.0  # 上游失败时旧值最多再顶 10 分钟, 之后按缺失处理
_FAIL_LOG_INTERVAL_S = 300.0  # 失败日志节流: 5 分钟一条 warning, 不刷屏
_last_fail_log = 0.0


@dataclass(frozen=True)
class _Preset:
    key: str          # 稳定 id(前端选择用)
    codes: tuple[str, ...]   # [R113] 新浪行情代码**候选**: 逐个试, 用第一个有数据的
    name: str         # 显示名
    kind: str         # 行格式: "int" / "hk"
    # [R112] 各市场交易时段(北京时间, 24h 制小数, 如 14.5=14:30)。跨零点的
    # 美股写成 start>end, 判定时按"跨日"处理。休市时上游值静止是正常的 ——
    # 界面据此显示"交易中/休市", 不让用户把静止当成故障。
    open_h: float = 0.0
    close_h: float = 24.0


# 可选指数表 —— 想加新的在这里加一行即可(独立维护的意义所在)
PRESETS: tuple[_Preset, ...] = (
    # 韩国 09:00-15:30 KST = 08:00-14:30 北京。
    # [R113] int_kospi 实测取不到数(其余 int_* 都正常) —— 新浪对韩国综合的
    # 代码不止一种写法, 这里列出已知几种候选逐个试, 免得靠猜来回改。
    _Preset("kospi",  ("int_kospi", "gb_ks11", "znb_KS11", "hf_KS11"), "韩国综合", "int", 8.0, 14.5),
    # 日本 09:00-15:00 JST = 08:00-14:00 北京(午休不细分, 只判大时段)
    _Preset("nikkei", ("int_nikkei",), "日经225",  "int", 8.0, 14.0),
    # 港股 09:30-16:00 = 北京同时区
    _Preset("hsi",    ("rt_hkHSI", "int_hangseng"), "恒生指数", "hk", 9.5, 16.0),
    # 美股 21:30-04:00 北京(夏令时; 冬令时晚 1 小时, 这里取并集 21.5~05.0
    # 宁可多标一小时"交易中", 也不要在真开盘时标成休市)
    _Preset("dji",    ("int_dji",),    "道琼斯",   "int", 21.5, 5.0),
    _Preset("nasdaq", ("int_nasdaq",), "纳斯达克", "int", 21.5, 5.0),
    _Preset("sp500",  ("int_sp500",),  "标普500",  "int", 21.5, 5.0),
)
_BY_KEY = {p.key: p for p in PRESETS}
DEFAULT_KEYS = ["kospi", "nasdaq"]  # 用户定案: 只留韩国综合与纳斯达克

_lock = threading.Lock()
_cache: dict[str, dict] = {}     # key → {..row..}
_cache_at: float = 0.0
_cache_codes: tuple[str, ...] = ()


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


def _to_float(raw: str) -> float | None:
    try:
        v = float(raw.replace(",", "").replace("%", "").strip())
    except (ValueError, AttributeError):
        return None
    return v


def _parse_line(preset: _Preset, payload: str) -> dict | None:
    """一行行情 → 卡片行。任何字段缺失/畸形返回 None(缺失处理, 不抛)。

    int_ 格式自适应: 标准是"名称,最新,涨跌额,涨跌幅", 但个别代码会多一列
    (如前置英文代码) —— 从头找到第一个能解析成数的字段当最新价, 紧随其后
    两个字段当涨跌额/涨跌幅, 两种排布都吃得下。
    """
    fields = payload.split(",")
    last = change = pct = None
    if preset.kind == "hk" and len(fields) < 9:
        # 该候选返回的不是港股行格式(如回落到 int_hangseng), 按 int 解析
        preset = _Preset(preset.key, preset.codes, preset.name, "int", preset.open_h, preset.close_h)
    if preset.kind == "int":
        for i in range(min(len(fields), 6)):
            v = _to_float(fields[i])
            if v is not None:
                last = v
                change = _to_float(fields[i + 1]) if i + 1 < len(fields) else None
                pct = _to_float(fields[i + 2]) if i + 2 < len(fields) else None
                break
    elif preset.kind == "hk":
        try:
            last, change, pct = _to_float(fields[6]), _to_float(fields[7]), _to_float(fields[8])
        except IndexError:
            return None
    else:
        return None
    if last is None:
        return None
    return {
        "key": preset.key,
        "name": preset.name,
        "last": last,
        "change": change,
        # 新浪口径为百分数(如 -0.38 表示 -0.38%), 转小数制与项目 change_pct 口径一致
        "change_pct": pct / 100.0 if pct is not None else None,
    }


def _fetch(codes: list[str]) -> dict[str, str]:
    """拉一批代码 → {code: 原始 payload}。网络/编码问题抛给调用方统一处理。"""
    url = _URL.format(codes=",".join(codes))
    resp = httpx.get(url, headers=_HEADERS, timeout=_TIMEOUT_S, follow_redirects=True)
    resp.raise_for_status()
    text = resp.content.decode("gbk", errors="replace")
    out: dict[str, str] = {}
    for line in text.splitlines():
        # 形如: var hq_str_int_kospi="韩国KOSPI,3200.12,-12.34,-0.38";
        if "hq_str_" not in line or '"' not in line:
            continue
        head, _, rest = line.partition('"')
        payload = rest.rsplit('"', 1)[0]
        code = head.split("hq_str_", 1)[1].rstrip("=").strip()
        if payload.strip():
            out[code] = payload
    return out


def get_quotes(keys: list[str]) -> list[dict]:
    """返回所选指数的最新行(带 updated_at, epoch 秒)。

    TTL 内直接回缓存; 上游失败回旧值(最多 _STALE_KEEP_S), 再久返回空行集。
    """
    presets = [_BY_KEY[k] for k in keys if k in _BY_KEY]
    if not presets:
        return []
    codes = tuple(c for p in presets for c in p.codes)
    now = time.time()
    with _lock:
        fresh = _cache_codes == codes and (now - _cache_at) < _TTL_S
        if not fresh:
            try:
                raw = _fetch(list(codes))
                rows: dict[str, dict] = {}
                for p in presets:
                    # 逐个候选代码试, 用第一个能解析出价格的
                    parsed = None
                    for c in p.codes:
                        parsed = _parse_line(p, raw.get(c, ""))
                        if parsed is not None:
                            parsed["source_code"] = c
                            break
                    if parsed is not None:
                        parsed["updated_at"] = now
                        parsed["trading"] = _in_session(p)
                        rows[p.key] = parsed
                if rows:
                    _set_cache(rows, now, codes)
                elif (now - _cache_at) > _STALE_KEEP_S:
                    _set_cache({}, now, codes)
            except Exception as e:  # noqa: BLE001
                global _last_fail_log
                if now - _last_fail_log > _FAIL_LOG_INTERVAL_S:
                    _last_fail_log = now
                    logger.warning("全球指数上游拉取失败(软, 卡片显示旧值/空): %s", e)
                if (now - _cache_at) > _STALE_KEEP_S:
                    _set_cache({}, now, codes)
        return [dict(_cache[k]) for k in (p.key for p in presets) if k in _cache]


def debug_fetch(keys: list[str]) -> dict:
    """诊断用: 直连上游一次, 返回原始 payload 与逐行解析结果(不进缓存)。"""
    presets = [_BY_KEY[k] for k in keys if k in _BY_KEY] or list(PRESETS)
    codes = [c for p in presets for c in p.codes]
    try:
        raw = _fetch(codes)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"{type(e).__name__}: {e}", "codes": codes}
    return {
        "ok": True,
        "codes": codes,
        "raw": raw,
        "parsed": {
            p.key: {c: _parse_line(p, raw.get(c, "")) for c in p.codes}
            for p in presets
        },
    }


def _set_cache(rows: dict[str, dict], at: float, codes: tuple[str, ...]) -> None:
    global _cache, _cache_at, _cache_codes
    _cache = rows
    _cache_at = at
    _cache_codes = codes
