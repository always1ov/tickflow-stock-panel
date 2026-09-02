"""[fork R159] 推送焦点名单 —— 自选太多时, 决定「谁值得推送」。

用户: 「我自选个股太多了, 不知道哪些才是我真的要推送通知的」。150 只自选, 广域规则
(全市场 / 自选分组 / 板块)一命中就推, 推送变成噪音, 真正该看的反而被淹掉。

做法不是让用户逐只勾选(150 只没人勾得动), 而是**让系统按已有的决策产出自动分档**,
用户只在例外处动手(钉住 / 静音):

  持有   positions 里标了「持有」的 —— 出场线、趋势转弱, 任何时候都要推
  计划中 今日总览「值得关注」里过了门槛、分数达标显示出来的 —— 你今天/收盘打算
         动手的那几只, 到价、放量、跌破关键点都该推
  观察   其余自选 —— 只记进应用内告警列表, **不打外部渠道**

分档来自每次构建今日总览时落的一份快照(盘后管道也会跑一次, 所以每天自动刷新);
用户可对任意一只**钉住**(永远推)或**静音**(永远不推)。

**推送门只拦广域规则**: 用户给某只票单独设的规则(scope=symbols, 如点位提醒)是
明确的"我关心这只", 永远放行。总开关 push_focus_only 默认关 —— 推送行为不能
悄悄变, 用户看过名单觉得对了再打开。

**失败一律放行**(快照读不到 / 太旧 / 任何异常): 宁可多推, 不能因为一个辅助名单
把出场线告警吞掉。
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import date, datetime
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)

TIER_HELD = "held"
TIER_PLAN = "plan"
TIER_BAND = "band"     # [R161] 短期 Keltner 贴/破上下轨 —— 用户常盯的高抛低吸候选
TIER_WATCH = "watch"
TIER_LABELS = {TIER_HELD: "持有", TIER_PLAN: "计划中", TIER_BAND: "贴轨", TIER_WATCH: "观察"}
TIER_ORDER = {TIER_HELD: 0, TIER_PLAN: 1, TIER_BAND: 2, TIER_WATCH: 3}
PUSH_TIERS = frozenset({TIER_HELD, TIER_PLAN, TIER_BAND})
# 到轨判定复用 indicators/keltner 的口径(classify 的五档), 不另立阈值 ——
# 决策台「短通道」列写"贴上轨"的那天, 这里也必须是贴轨
_BAND_POS = frozenset({"above", "near_upper", "near_lower", "below"})

MODE_PIN = "pin"
MODE_MUTE = "mute"
MODES = frozenset({MODE_PIN, MODE_MUTE})

SNAPSHOT_MAX_AGE_DAYS = 7   # 快照比这更旧 → 名单失效, 推送门放行(管道停了不能连累告警)


def _snapshot_path() -> Path:
    p = settings.data_dir / "user_data" / "focus_snapshot.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _overrides_path() -> Path:
    p = settings.data_dir / "user_data" / "focus_overrides.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


# ---------------------------------------------------------------- 读写(带 mtime 缓存)
# should_push 在行情轮询线程里每条告警调一次, 不能每次都读盘。
_cache_lock = threading.Lock()
_cache: dict[str, tuple[float, object]] = {}   # path → (mtime, payload)


def _read_json(path: Path) -> dict | None:
    import json
    try:
        st = path.stat()
    except OSError:
        with _cache_lock:
            _cache.pop(str(path), None)
        return None
    with _cache_lock:
        hit = _cache.get(str(path))
        if hit and hit[0] == st.st_mtime:
            return hit[1]  # type: ignore[return-value]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            data = None
    except Exception as e:  # noqa: BLE001
        logger.warning("focus list read failed %s: %s", path.name, e)
        data = None
    with _cache_lock:
        _cache[str(path)] = (st.st_mtime, data)
    return data


def _write_json(path: Path, payload: dict) -> None:
    from app.services.json_store import atomic_write_json, lock_for
    with lock_for(path):
        atomic_write_json(path, payload)
    with _cache_lock:
        _cache.pop(str(path), None)


# ---------------------------------------------------------------- 快照


def save_snapshot(as_of: str | None, holdings: list[dict], opportunities: list[dict],
                  bands_map: dict[str, dict] | None = None) -> dict:
    """今日总览构建完时落一份分档快照。记「持有」「计划中」「贴轨」, 其余自选即观察。

    bands_map: keltner_service.channels_for_symbols 的结果 {SYMBOL: {"s": {...}, ...}};
    短期档 pos 在贴/破上下轨的进「贴轨」档(收盘口径, 与决策台同一口径)。
    内容没变就不写盘 —— /api/today 每次打开都会走到这里。
    """
    items: dict[str, dict] = {}
    for h in holdings:
        sym = str(h.get("symbol") or "").upper()
        if not sym:
            continue
        items[sym] = {
            "tier": TIER_HELD, "name": h.get("name") or sym,
            "reason": f"持有 · {h.get('stance') or '—'}",
        }
    for o in opportunities:
        sym = str(o.get("symbol") or "").upper()
        if not sym or sym in items:
            continue
        act = o.get("action") or {}
        bits = [f"把握 {o.get('score')}"]
        if act.get("label"):
            bits.append(str(act["label"]))
        items[sym] = {
            "tier": TIER_PLAN, "name": o.get("name") or sym,
            "reason": " · ".join(bits),
            "score": o.get("score"),
            "action": act.get("code"),
        }
    # [R161] 短期贴/破上下轨: 高抛低吸候选。持有 / 计划中优先级更高, 已在的不覆盖
    for sym, bands in (bands_map or {}).items():
        s = str(sym or "").upper()
        if not s or s in items:
            continue
        short = (bands or {}).get("s") or {}
        pos = short.get("pos")
        if pos not in _BAND_POS:
            continue
        pct = short.get("pct")
        pct_txt = f" {float(pct) * 100:.0f}%" if isinstance(pct, (int, float)) else ""
        items[s] = {
            "tier": TIER_BAND, "name": s,
            "reason": f"短期{short.get('pos_cn') or pos}{pct_txt}",
            "pos": pos,
        }
    payload = {"as_of": as_of, "items": items}
    prev = _read_json(_snapshot_path())
    if prev and prev.get("as_of") == as_of and prev.get("items") == items:
        return prev
    payload["generated_at"] = datetime.now().isoformat(timespec="seconds")
    _write_json(_snapshot_path(), payload)
    return payload


def load_snapshot() -> dict | None:
    return _read_json(_snapshot_path())


def snapshot_is_fresh(snap: dict | None, today: date | None = None) -> bool:
    if not snap or not snap.get("as_of"):
        return False
    try:
        d = date.fromisoformat(str(snap["as_of"])[:10])
    except ValueError:
        return False
    return ((today or date.today()) - d).days <= SNAPSHOT_MAX_AGE_DAYS


# ---------------------------------------------------------------- 覆盖(钉住 / 静音)


def load_overrides() -> dict[str, dict]:
    data = _read_json(_overrides_path()) or {}
    return {str(k).upper(): v for k, v in data.items() if isinstance(v, dict) and v.get("mode") in MODES}


def set_override(symbol: str, mode: str | None) -> dict[str, dict]:
    """mode: 'pin' / 'mute' / None(清除)。返回生效后的全部覆盖。"""
    sym = str(symbol or "").strip().upper()
    if not sym:
        raise ValueError("symbol 不能为空")
    if mode is not None and mode not in MODES:
        raise ValueError(f"mode 只能是 pin / mute / null, 收到 {mode!r}")
    from app.services.json_store import lock_for
    path = _overrides_path()
    with lock_for(path):
        cur = load_overrides()
        if mode is None:
            cur.pop(sym, None)
        else:
            cur[sym] = {"mode": mode, "updated_at": datetime.now().isoformat(timespec="seconds")}
        _write_json(path, cur)
    return cur


# ---------------------------------------------------------------- 判定


def resolve(symbol: str, snap: dict | None = None, overrides: dict | None = None) -> dict:
    """一只票的有效分档: {tier, effective, source, reason}。

    effective = 覆盖后的推送档(pin → held 档待遇, mute → watch); source 说明来自哪。
    """
    sym = str(symbol or "").upper()
    snap = load_snapshot() if snap is None else snap
    ov = (load_overrides() if overrides is None else overrides).get(sym)
    item = ((snap or {}).get("items") or {}).get(sym) or {}
    tier = item.get("tier") or TIER_WATCH
    out = {"tier": tier, "effective": tier, "source": "snapshot" if item else "default",
           "reason": item.get("reason") or "不在今日名单内"}
    if ov:
        out["override"] = ov["mode"]
        out["source"] = "override"
        out["effective"] = TIER_HELD if ov["mode"] == MODE_PIN else TIER_WATCH
    return out


def should_push(symbol: str, rule: dict | None) -> bool:
    """外部推送门。只在总开关开着时起作用; 任何不确定都放行。"""
    try:
        from app.services import preferences
        if not preferences.get_push_focus_only():
            return True
        # 用户给这只票单独设的规则 = 明确关心, 永远放行
        if rule and rule.get("scope") == "symbols":
            return True
        snap = load_snapshot()
        if not snapshot_is_fresh(snap):
            return True    # 名单过期(管道没跑) → 放行, 不能连累告警
        r = resolve(symbol, snap)
        return r["effective"] in PUSH_TIERS
    except Exception as e:  # noqa: BLE001
        logger.debug("focus should_push fallback open: %s", e)
        return True


def build_view(watch_symbols: list[str], names: dict[str, str]) -> dict:
    """监控页用的整份名单: 三档分组 + 覆盖 + 开关 + 快照时间。"""
    from app.services import preferences
    snap = load_snapshot()
    ov = load_overrides()
    items = []
    seen = set()
    for sym in [*(((snap or {}).get("items") or {}).keys()), *watch_symbols]:
        s = str(sym).upper()
        if s in seen:
            continue
        seen.add(s)
        r = resolve(s, snap, ov)
        snap_item = ((snap or {}).get("items") or {}).get(s) or {}
        items.append({
            "symbol": s,
            "name": names.get(s) or snap_item.get("name") or s,
            "tier": r["tier"], "effective": r["effective"], "override": r.get("override"),
            "reason": r["reason"], "score": snap_item.get("score"), "action": snap_item.get("action"),
        })
    order = TIER_ORDER
    items.sort(key=lambda x: (order.get(x["effective"], 9), -(x.get("score") or 0), x["symbol"]))
    counts = {t: sum(1 for x in items if x["effective"] == t) for t in order}
    return {
        "focus_only": preferences.get_push_focus_only(),
        "as_of": (snap or {}).get("as_of"),
        "generated_at": (snap or {}).get("generated_at"),
        "fresh": snapshot_is_fresh(snap),
        "counts": counts,
        "labels": TIER_LABELS,
        "items": items,
        "_ts": time.time(),
    }
