"""[fork 增强] R135 机会区的两个注记数据源: 策略命中 与 龙虎榜。

R134 把注记层建起来了(主线/AI/历史胜率/通道结论), 但这两项当时**只写了展示
分支, 没接数据源** —— 界面上因此永远不出现。这个模块补上, 并把两条共同的
纪律写死在一处:

  1. **只读, 不算。** 两者都读已有产出:
     · 策略命中 → ``user_data/strategy_cache.json``(策略页跑 run_all 时写的,
       含 ``today_ever_matched``: 今日曾命中的 symbol 并集);
     · 龙虎榜   → ``dragon_tiger.get_dragon_tiger``(按日缓存, fuyao 专有接口)。
     在总览接口里现算全市场策略(27 个内置策略 × 全市场历史矩阵)是几秒级的开销,
     为一个**不参与打分**的展示标付这个代价没有道理。取不到就不显示。

  2. **数据陈旧就不显示, 不显示旧的。** 与 R37 主线那条同一个原则:
     策略缓存的 as_of 与总览的 as_of 对不上 → 整个不给(那是上一交易日的命中,
     摆在今天的候选旁边是误导); 龙虎榜回退到上一期时也标出来是哪天的。

  3. **只算内置策略。** 用户明确说过"不用管我自建的策略, 参与的只用内置策略"。
     自建/AI 生成的策略数量与口径都不受控, 混进来会让"命中 5 个策略"这句话
     失去可比性。research_only 的模板同样排除。
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# 一只票最多列几个命中的策略 —— 再多标签就挤爆那一列, 也说明不了更多
MAX_HITS_PER_SYMBOL = 4


def strategy_hits(repo, engine, as_of: str | None) -> dict[str, list[str]]:
    """{SYMBOL: [内置策略中文名, ...]}。取不到/过期返回空字典。

    engine 为 StrategyEngine(可能为 None —— 引擎没初始化时静默跳过)。
    """
    if engine is None or not as_of:
        return {}
    try:
        from app.services.strategy_cache import read_cache
        cache = read_cache(repo.store.data_dir)
    except Exception as e:  # noqa: BLE001
        logger.debug("today strategy hits cache unavailable: %s", e)
        return {}
    if not cache:
        return {}
    # 缓存日与总览数据日必须一致 —— 昨天的命中摆在今天的候选旁边是误导
    if str(cache.get("as_of") or "")[:10] != str(as_of)[:10]:
        return {}

    # 内置且非研究模板的才算; 同时拿到 id → 中文名
    try:
        names = {m["id"]: (m.get("name") or m["id"])
                 for m in engine.list_strategies()
                 if m.get("source") == "builtin" and not m.get("research_only")}
    except Exception as e:  # noqa: BLE001
        logger.debug("today strategy list unavailable: %s", e)
        return {}
    if not names:
        return {}

    # today_ever_matched 是"今日曾命中"的并集 —— 盘中触发过又掉出来的也算数,
    # 这正是注记想说的("今天它进过这些策略的池子"), 不是"此刻还在池子里"
    matched = cache.get("today_ever_matched") or {}
    out: dict[str, list[str]] = {}
    for sid, syms in matched.items():
        label = names.get(sid)
        if not label or not isinstance(syms, list):
            continue
        for s in syms:
            sym = str(s).strip().upper()
            if not sym:
                continue
            hits = out.setdefault(sym, [])
            if label not in hits:
                hits.append(label)
    return {k: sorted(v)[:MAX_HITS_PER_SYMBOL] for k, v in out.items()}


def dragon_tiger_map(repo) -> dict[str, dict]:
    """{SYMBOL: {net_value, org_net_value, stale_date}}。未发布/取不到返回空。

    只取「全部」那一榜的个股条目: 机构榜与游资榜是它的子集, 三榜合并会让同一只
    票出现三次而没有新信息。净买入是正是负一起带上 —— 上榜本身是中性事实,
    净卖出上榜和净买入上榜完全是两回事, 只报"在榜"等于把方向抹掉了。
    """
    try:
        from app.services.dragon_tiger import get_dragon_tiger
        payload = get_dragon_tiger(repo.store.data_dir)
    except Exception as e:  # noqa: BLE001
        logger.debug("today dragon tiger unavailable: %s", e)
        return {}
    state = payload.get("state")
    if state not in ("ok", "fallback_prev"):
        return {}
    items = (payload.get("all") or {}).get("stock_items") or []
    stale = str(payload.get("trade_date") or "")[:10] if state == "fallback_prev" else None
    out: dict[str, dict] = {}
    for it in items:
        sym = str(it.get("thscode") or "").strip().upper()
        if not sym:
            continue
        out[sym] = {
            "net_value": it.get("net_value"),
            "org_net_value": it.get("org_net_value"),
            "stale_date": stale,
        }
    return out


def _yi(v) -> str:
    """元 → 亿元的短文案。小于一千万时退到万元, 免得满屏 0.03 亿。"""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return ""
    if abs(f) >= 1e7:
        return f"{f / 1e8:+.2f} 亿"
    return f"{f / 1e4:+.0f} 万"


def dragon_note(info: dict) -> dict:
    """龙虎榜条目 → 注记。净买入定 tone: 净卖出上榜不是利好, 不能一律标成中性。"""
    net = info.get("net_value")
    org = info.get("org_net_value")
    try:
        n = float(net) if net is not None else None
    except (TypeError, ValueError):
        n = None
    tone = "info" if n is None else "good" if n > 0 else "bad"
    label = "龙虎榜" + (f" {_yi(n)}" if n is not None else "在列")
    parts = []
    if n is not None:
        parts.append(f"当日龙虎榜净{'买入' if n > 0 else '卖出'} {_yi(n).lstrip('+-')}")
    if org is not None:
        parts.append(f"其中机构净额 {_yi(org)}")
    if info.get("stale_date"):
        parts.append(f"注意: 当日榜单尚未发布, 这是 {info['stale_date']} 那一期的数据")
    parts.append("上榜只说明当天资金关注度高, 方向要看净额正负; 不参与把握分")
    return {"key": "dragon", "tone": tone, "label": label, "text": ";".join(parts)}


def strategy_note(hits: list[str]) -> dict:
    """策略命中 → 注记。**不按命中数量给倾向**。

    命中多不等于更好: 内置策略里"均线/突破/量价"几类互相高度重叠, 一只放量突破
    的票天然会同时命中三四个, 那反映的是策略集自身的冗余而不是这只票更强。
    所以 tone 恒为 info, 只报事实。
    """
    return {
        "key": "strategy", "tone": "info",
        "label": f"内置策略命中 {len(hits)}",
        "text": "、".join(hits) + " —— 只统计内置策略(不含自建/AI 生成); "
                "策略之间口径高度重叠, 命中多不代表更强, 故不参与把握分",
    }
