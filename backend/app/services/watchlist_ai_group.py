"""[fork 增强] AI 一键分组 —— 按题材把自选归拢成若干分组。

设计要点:
- **只出方案不落库**: generate 返回建议, 用户在前端确认后再调 apply,
  绝不静默改动既有分组数据。
- **原料是本地已有的概念/行业标签**(扩展数据), AI 只做归纳命名与合并,
  不需要它凭空判断个股属于什么行业 —— 降低幻觉, 也让结果可解释。
- **严格校验**: 只认自选内的代码; 同一只票被分进多组时保留第一次出现;
  未被 AI 覆盖的票留在"未分组", 如实告知数量。
"""
from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)

# 送审上限(自选通常上百只, 每只只带名称+少量标签, 单次调用足够)
_MAX_SYMBOLS = 300
# 每只票最多带几个概念标签(标签太多会淹没提示词)
_MAX_TAGS_PER_SYMBOL = 4
# AI 可创建的分组数量区间
_MIN_GROUPS, _MAX_GROUPS = 3, 12

_SYSTEM = """你是 A 股投资助理, 任务是把用户的自选股按**题材/行业主线**归拢成几个分组, 方便他分组盯盘。

规则:
1. 分组数量 3-12 个, 每组至少 2 只; 按"用户会怎么理解这批票"来分, 而不是照搬行业分类目录
2. 组名 **不超过 6 个中文字**, 要直观(如"光模块""存储芯片""半导体设备""AI算力""消费电子"); 不要用"其他""综合"这类空洞名称
3. 每只股票**只能进一个组**; 实在归不进任何主题的票就不要放进来(留空即可, 系统会归入未分组)
4. 只能使用给定列表里的股票代码, **不得编造代码**
5. 参考给定的概念/行业标签, 但可以合并同类、拆分过宽的标签

只输出一个 JSON 对象, 不要任何解释或代码块围栏:
{"groups": [{"name": "组名", "symbols": ["600487.SH", "603083.SH"], "reason": "不超过20字的归类说明"}]}"""


def _collect_tags(repo, symbols: list[str]) -> dict[str, list[str]]:
    """取每只票的概念/行业标签(本地扩展数据); 无扩展数据时返回空 dict。"""
    tags: dict[str, list[str]] = {}
    try:
        import polars as pl

        from app.services.rps_rotation import _load_concept_map_df
        for kind in ("industry", "concept"):  # 行业在前: 行业标签更稳定, 概念作补充
            map_df, _n = _load_concept_map_df(repo, kind)
            if map_df is None or map_df.is_empty() or kind not in map_df.columns:
                continue
            sub = map_df.filter(pl.col("_sym_up").is_in(symbols))
            for row in sub.select(["_sym_up", kind]).to_dicts():
                sym = str(row["_sym_up"]).upper()
                val = str(row[kind] or "").strip()
                if not val:
                    continue
                cur = tags.setdefault(sym, [])
                if val not in cur and len(cur) < _MAX_TAGS_PER_SYMBOL:
                    cur.append(val)
    except Exception as e:  # noqa: BLE001
        logger.warning("watchlist ai-group: load tags failed: %s", e)
    return tags


def build_payload(repo, entries: list[dict]) -> tuple[list[dict], dict[str, str]]:
    """构造送审清单 [{symbol, name, tags}] 与 {symbol: name} 映射。"""
    names: dict[str, str] = {}
    syms: list[str] = []
    for e in entries[:_MAX_SYMBOLS]:
        sym = str(e.get("symbol") or "").upper()
        if not sym:
            continue
        syms.append(sym)
        names[sym] = str(e.get("name") or sym)
    try:
        name_map = repo.get_name_map(syms)
        for s in syms:
            if name_map.get(s):
                names[s] = name_map[s]
    except Exception as e:  # noqa: BLE001
        logger.debug("watchlist ai-group: name map skipped: %s", e)
    tags = _collect_tags(repo, syms)
    payload = [{"symbol": s, "name": names[s], "tags": tags.get(s, [])} for s in syms]
    return payload, names


def parse_groups(text: str | None, valid_symbols: set[str],
                 names: dict[str, str]) -> tuple[list[dict], list[str]]:
    """解析 AI 输出为 [{name, symbols, reason}] 与未覆盖代码列表。

    校验: 只认自选内代码、同票只进第一个组、组名截断到 6 字、空组丢弃。
    纯函数(除日志), 便于单测。
    """
    from app.services.ai_json import extract_json_object

    obj = extract_json_object(text) or {}
    used: set[str] = set()
    groups: list[dict] = []
    for g in (obj.get("groups") or [])[:_MAX_GROUPS]:
        if not isinstance(g, dict):
            continue
        name = str(g.get("name") or "").strip()[:6]
        if not name:
            continue
        syms: list[str] = []
        for raw in g.get("symbols") or []:
            s = str(raw or "").strip().upper()
            if s in valid_symbols and s not in used:
                used.add(s)
                syms.append(s)
        if len(syms) < 2:  # 单只成组没有意义, 退回未分组
            for s in syms:
                used.discard(s)
            continue
        groups.append({
            "name": name,
            "symbols": syms,
            "names": [names.get(s, s) for s in syms],
            "reason": str(g.get("reason") or "").strip()[:40],
        })
    ungrouped = [s for s in valid_symbols if s not in used]
    return groups, sorted(ungrouped)


async def generate(repo, entries: list[dict]) -> dict:
    """调 AI 生成分组方案(不落库)。未配 AI / 解析失败均返回 error。"""
    from app.services.ai_provider import ai_configured, generate_ai_text

    if not ai_configured():
        return {"error": "未配置 AI —— 到设置页填 AI Key 后再试"}
    payload, names = build_payload(repo, entries)
    if len(payload) < 4:
        return {"error": "自选太少(不足 4 只), 手动分组更快"}
    try:
        text = await generate_ai_text(
            [
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            temperature=0.2,
            max_tokens=None,  # [上游标准] 不限制输出(推理模型思考计入预算)
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("watchlist ai-group failed: %s", e)
        return {"error": f"AI 调用失败: {e}"}

    groups, ungrouped = parse_groups(text, set(names), names)
    if not groups:
        snippet = (text or "").replace("\n", " ").strip()[:100]
        return {"error": f"AI 未给出可用分组(原文开头: {snippet or '空'}…)——可重试或换模型"}
    return {
        "groups": groups,
        "ungrouped": ungrouped,
        "ungrouped_names": [names.get(s, s) for s in ungrouped],
        "total": len(names),
    }


def apply(proposal_groups: list[dict], *, replace_existing: bool = False) -> dict:
    """把方案落库: 建分组(重名复用) + 逐只归组。返回统计。

    replace_existing=True 时, 先把所有自选的分组清空再按方案归组(彻底重分);
    False 时只移动方案涉及的票, 其余保持原分组不动。
    """
    from app.services import watchlist

    existing = {g["name"].casefold(): g for g in watchlist.list_groups()}
    if replace_existing:
        for entry in watchlist.list_symbols():
            if entry.get("group_id"):
                try:
                    watchlist.set_group(entry["symbol"], None)
                except (KeyError, ValueError) as e:  # noqa: PERF203
                    logger.debug("ai-group reset %s skipped: %s", entry.get("symbol"), e)

    colors = ["sky", "violet", "emerald", "amber", "rose", "cyan", "indigo",
              "lime", "orange", "teal", "fuchsia", "blue"]
    created = 0
    assigned = 0
    for i, g in enumerate(proposal_groups):
        name = str(g.get("name") or "").strip()[:6]
        syms = [str(s).upper() for s in (g.get("symbols") or [])]
        if not name or not syms:
            continue
        hit = existing.get(name.casefold())
        if hit:
            gid = hit["id"]
        else:
            try:
                _groups, group = watchlist.create_group(name, colors[i % len(colors)])
            except ValueError as e:  # 并发重名等
                logger.warning("ai-group create '%s' failed: %s", name, e)
                continue
            gid = group["id"]
            existing[name.casefold()] = group
            created += 1
        for s in syms:
            try:
                watchlist.set_group(s, gid)
                assigned += 1
            except (KeyError, ValueError) as e:  # noqa: PERF203
                logger.debug("ai-group assign %s skipped: %s", s, e)
    return {"ok": True, "groups_created": created, "symbols_assigned": assigned}
