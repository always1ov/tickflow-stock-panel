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
_TTL_S = 20.0          # 服务端缓存: 多前端/多标签页轮询合并成同一次上游请求
_STALE_KEEP_S = 600.0  # 上游失败时旧值最多再顶 10 分钟, 之后按缺失处理


@dataclass(frozen=True)
class _Preset:
    key: str          # 稳定 id(前端选择用)
    code: str         # 新浪行情代码
    name: str         # 显示名
    kind: str         # 行格式: "int" / "hk"


# 可选指数表 —— 想加新的在这里加一行即可(独立维护的意义所在)
PRESETS: tuple[_Preset, ...] = (
    _Preset("kospi",    "int_kospi",    "韩国综合", "int"),
    _Preset("nikkei",   "int_nikkei",   "日经225",  "int"),
    _Preset("hsi",      "rt_hkHSI",     "恒生指数", "hk"),
    _Preset("dji",      "int_dji",      "道琼斯",   "int"),
    _Preset("nasdaq",   "int_nasdaq",   "纳斯达克", "int"),
    _Preset("sp500",    "int_sp500",    "标普500",  "int"),
)
_BY_KEY = {p.key: p for p in PRESETS}
DEFAULT_KEYS = ["kospi"]

_lock = threading.Lock()
_cache: dict[str, dict] = {}     # key → {..row..}
_cache_at: float = 0.0
_cache_codes: tuple[str, ...] = ()


def list_presets() -> list[dict]:
    return [{"key": p.key, "name": p.name} for p in PRESETS]


def _to_float(raw: str) -> float | None:
    try:
        v = float(raw.replace(",", "").strip())
    except (ValueError, AttributeError):
        return None
    return v


def _parse_line(preset: _Preset, payload: str) -> dict | None:
    """一行行情 → 卡片行。任何字段缺失/畸形返回 None(缺失处理, 不抛)。"""
    fields = payload.split(",")
    try:
        if preset.kind == "int":
            last, change, pct = _to_float(fields[1]), _to_float(fields[2]), _to_float(fields[3])
        elif preset.kind == "hk":
            last, change, pct = _to_float(fields[6]), _to_float(fields[7]), _to_float(fields[8])
        else:
            return None
    except IndexError:
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
    resp = httpx.get(url, headers=_HEADERS, timeout=_TIMEOUT_S)
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
    codes = tuple(p.code for p in presets)
    now = time.time()
    with _lock:
        fresh = _cache_codes == codes and (now - _cache_at) < _TTL_S
        if not fresh:
            try:
                raw = _fetch(list(codes))
                rows: dict[str, dict] = {}
                for p in presets:
                    parsed = _parse_line(p, raw.get(p.code, ""))
                    if parsed is not None:
                        parsed["updated_at"] = now
                        rows[p.key] = parsed
                if rows:
                    _set_cache(rows, now, codes)
                elif (now - _cache_at) > _STALE_KEEP_S:
                    _set_cache({}, now, codes)
            except Exception as e:  # noqa: BLE001
                logger.debug("global indices fetch failed (soft): %s", e)
                if (now - _cache_at) > _STALE_KEEP_S:
                    _set_cache({}, now, codes)
        return [dict(_cache[k]) for k in (p.key for p in presets) if k in _cache]


def _set_cache(rows: dict[str, dict], at: float, codes: tuple[str, ...]) -> None:
    global _cache, _cache_at, _cache_codes
    _cache = rows
    _cache_at = at
    _cache_codes = codes
