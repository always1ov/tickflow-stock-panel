"""[fork 增强] R31 AI 自动挖掘 —— 拿上一轮结果反馈给 AI, 由它重配参数再跑一轮。

用户要的闭环: 跑 → AI 看结果 → 改配置 → 再跑 → …… 直到 AI 认为够好。

**为什么要锁一段终检数据**
挖掘页那 5 条门槛(Sharpe≥0.5 / 正收益折≥2/3 / 回撤≥-25% / 有效折≥2 / 成交≥60)
之所以有意义, 前提是"搜索过程没见过样本外那段"。一旦让 AI 读到样本外指标再改
配置重跑同一段, 样本外就被偷看了一次; 跑 20 轮等于用样本外挑了 20 次, 最后必然
撞上一个"过门槛"的 —— 那不是策略行, 是试的次数够多(多重检验)。自动化只会让这
件事坏得更快。

所以本模块把区间切成两段:
    [搜索窗口 ................] | [终检窗口(锁定)]
     AI 循环只在这里试, 看得到指标 |  循环全程看不到
循环结束后, 赢家在终检窗口上只跑一次 —— 那个数字才是可信的。
同时记录迭代次数: 试的次数越多, 同样的 Sharpe 越该打折, 界面要如实显示。

**与 docs/mining.md 的对齐点(不得违反)**
- §自动运行「自动任务只生成 pending 结果, 永远不会自动发布策略」——
  本循环同样绝不调 publish。选定赢家后停在那里, 等人工确认发布。
- §功能边界「不生成任意公式, 不接受 AI 自由代码」——
  AI 的输出只有"选哪些因子 id"和几个受控数值参数, 全部经白名单与夹紧。
- §保存与发布「客户端只能提交 run ID 与 candidate signature」——
  赢家一律按 signature 标识, 不靠 name(可能重名)。
- §任务与资源隔离「挖掘独占 2 个重任务槽位」—— 迭代必须严格串行, 一次一个 run。
- §自动运行「只允许 balanced 或 strict」—— 本循环沿用同一档位白名单。
- 终检不是再跑一轮挖掘(那要再花 786/1164 个交易日), 而是人工发布后对该策略
  在锁定期跑一次普通回测。

纯函数在前(可单测), 编排在后。
"""
from __future__ import annotations

import json
import logging
from datetime import date, timedelta
from typing import Any

logger = logging.getLogger(__name__)

# 终检窗口长度(自然日)。终检是"发布后跑一次普通回测", 不是再跑一轮挖掘,
# 所以不受 786/1164 根交易日的挖掘门槛约束; 一年足够给出可信的单次样本外结论。
DEFAULT_HOLDOUT_DAYS = 365
MIN_HOLDOUT_DAYS = 180
# 搜索窗口下限(自然日): balanced 需 786 个交易日 ≈ 1185 自然日, strict 需 1164 ≈ 1756。
# 这里只做粗筛把明显不够的挡在门外; 精确判定必须走 mining_preflight 的
# require_mining_availability(它按 enriched 真实交易日算), API 层负责调。
MIN_SEARCH_DAYS = {"balanced": 1185, "strict": 1756}
MAX_ITERATIONS_CAP = 20        # 硬上限: 不许无限刷样本外
DEFAULT_MAX_ITERATIONS = 8
_MAX_CANDIDATES_TO_AI = 6      # 每轮喂给 AI 的候选数, 太多会淹没重点

# [docs/mining.md §自动运行] 周度自动挖掘"只允许 balanced 或 strict"。自动循环沿用
# 同一条规矩: exploratory 结果固定为低置信度、只能存 pending 且**不能发布**,
# 让 AI 选它等于白烧一轮预算。
PROFILES = ("balanced", "strict")

_AI_SYSTEM = """你是量化因子研究员, 负责驱动一个自动挖掘循环。

系统会给你: 可用因子清单、本次搜索窗口、以及此前每一轮用了什么配置、跑出什么结果。
你的任务是判断"够好了没有", 不够就给出下一轮的配置。

判定够好的门槛(与系统一致, 必须全部满足):
- 有效折 >= 2
- 正收益折占比 >= 0.67
- 样本外 Sharpe >= 0.5
- 最大回撤不差于 -0.25
- 成交笔数 >= 60
- 档位只能是 balanced 或 strict(exploratory 结果不能发布, 选它等于白跑)

重要纪律:
1. 你看到的是**搜索窗口**的指标。系统另外锁了一段终检数据你永远看不到,
   循环结束后赢家会在那上面跑一次定生死。所以不要为了凑数字而堆因子 ——
   在搜索窗口过拟合出来的东西, 终检一跑就现原形。
2. 每多迭代一轮, 同样的指标可信度就低一分。若某轮已经稳稳达标, 立刻收手,
   不要为了"再好一点"继续刷。
3. 因子要挑不同类的(动量/均线乖离/成交量/波动/资金…)。同类堆一起是虚假多样性,
   系统的相关性过滤会把它们剔掉, 白费预算。
4. 只能使用给定清单里的因子 id, 不得编造。系统不接受任何公式、权重、方向或代码 ——
   你的输出只有"选哪些因子"和几个受控数值参数, 其余一律由系统按自己的口径计算。
5. 你的判断不会自动发布任何策略。选定赢家后仍需人工确认发布, 这一步你无权代劳。

只输出 JSON, 不要任何解释文字或代码块标记:
{"satisfied": true|false,
 "verdict": "一两句话说清这轮结果怎么样, 大白话",
 "pick": "满意时填选中候选的 signature(原样照抄, 不要改写), 不满意填 null",
 "next": {"factor_names": ["id1","id2",...],
          "budget_profile": "balanced|strict",
          "max_combination_factors": 2-4,
          "beam_width": 4-32,
          "correlation_threshold": 0.5-0.95},
 "reason": "不满意时说清下一轮为什么这么改; 满意时填 null"}
"""


# ---------- 纯函数: 窗口切分 ----------

def split_windows(start: date, end: date, *, holdout_days: int = DEFAULT_HOLDOUT_DAYS,
                  budget_profile: str = "balanced") -> dict[str, date]:
    """把区间切成 搜索窗口 + 终检窗口(锁定的尾段)。

    终检窗口是循环全程看不到的那段; 搜索窗口撑不起所选档位就直接抛错,
    不给"凑合开局"的机会 —— 否则第一轮就会被 require_mining_availability 拒掉。
    这里只按自然日粗筛, 精确判定由 API 层的 preflight 负责(它数真实交易日)。
    """
    if end <= start:
        raise ValueError("结束日期必须晚于开始日期")
    if budget_profile not in PROFILES:
        raise ValueError(f"档位只能是 {' / '.join(PROFILES)}(探索档结果不能发布)")
    holdout_days = max(MIN_HOLDOUT_DAYS, int(holdout_days))
    holdout_start = end - timedelta(days=holdout_days - 1)
    search_end = holdout_start - timedelta(days=1)
    search_days = (search_end - start).days + 1
    need = MIN_SEARCH_DAYS[budget_profile]
    if search_days < need:
        raise ValueError(
            f"{budget_profile} 档的搜索窗口需 >= {need} 天, 现在只有 {search_days} 天 —— "
            f"把开始日期往前挪, 或调小终检窗口"
        )
    return {
        "search_start": start,
        "search_end": search_end,
        "holdout_start": holdout_start,
        "holdout_end": end,
    }


# ---------- 纯函数: 结果摘要 ----------

def summarize_candidates(result: dict | None, *, limit: int = _MAX_CANDIDATES_TO_AI) -> list[dict]:
    """挖掘结果 → 喂给 AI 的精简候选列表(只留判断需要的字段)。"""
    if not isinstance(result, dict):
        return []
    out = []
    for c in (result.get("candidates") or [])[:limit]:
        if not isinstance(c, dict):
            continue
        gate = c.get("gate") or {}
        out.append({
            # [docs/mining.md §保存与发布] 赢家一律按 signature 标识, name 只给人看
            "signature": c.get("signature"),
            "name": c.get("name"),
            "定义": _definition_text(c.get("definition")),
            "达标": bool(gate.get("qualified")),
            "未达标原因": list(gate.get("reasons") or [])[:5],
            "样本外Sharpe": c.get("oos_sharpe"),
            "平均每折收益": c.get("oos_return"),
            "最大回撤": c.get("oos_max_drawdown"),
            "正收益折占比": c.get("oos_positive_fold_ratio"),
            "有效折": c.get("valid_folds"),
            "成交笔数": c.get("oos_n_trades"),
        })
    return out


def _definition_text(definition: Any) -> str:
    if not isinstance(definition, dict):
        return "—"
    names = definition.get("factor_names")
    if isinstance(names, list) and names:
        return " + ".join(str(n) for n in names[:6])
    sid = definition.get("strategy_id")
    return str(sid) if sid else "—"


def resolve_pick(pick: str | None, candidates: list[dict]) -> dict | None:
    """把 AI 的 pick 解析成候选。

    [docs/mining.md §保存与发布] 客户端只能提交 run_id + candidate signature,
    所以先按 signature 精确匹配; AI 若图省事回了 name 就退一步按 name 匹配;
    都对不上(编造/改写)就交给规则兜底, 绝不凭 AI 的字面值去构造任何定义。
    """
    if pick:
        for c in candidates:
            if str(c.get("signature") or "") == pick:
                return c
        for c in candidates:
            if str(c.get("name") or "") == pick:
                return c
    return pick_best(candidates)


def pick_best(candidates: list[dict]) -> dict | None:
    """规则兜底选优: 先看达标, 再看 Sharpe。AI 没给 pick 或给错时用这个。"""
    if not candidates:
        return None
    return max(
        candidates,
        key=lambda c: (bool(c.get("达标")), c.get("样本外Sharpe") or float("-inf")),
    )


# ---------- 纯函数: AI 出入参 ----------

def build_payload(*, factor_catalog: list[dict], windows: dict, iterations: list[dict],
                  max_iterations: int, asset_type: str) -> dict:
    """组装送审 payload。历史轮次全带上 —— 这就是"拿上次结果反馈"的载体。"""
    history = []
    for it in iterations:
        history.append({
            "第几轮": it.get("iteration"),
            "用的配置": it.get("config"),
            "跑出的候选": it.get("candidates"),
            "运行状态": it.get("status"),
            "你当时的判断": (it.get("ai") or {}).get("verdict"),
        })
    return {
        "品种": asset_type,
        "搜索窗口": {"start": str(windows["search_start"]), "end": str(windows["search_end"])},
        "终检窗口": "已锁定, 你看不到也不该猜 —— 循环结束后赢家在那上面跑一次定生死",
        "本轮是第几轮": len(iterations) + 1,
        "最多允许几轮": max_iterations,
        "可用因子": factor_catalog,
        "历史轮次": history,
    }


def parse_plan(text: str, valid_factors: set[str]) -> dict:
    """解析 AI 计划; 容错各厂商格式。配置越界一律夹紧, 编造的因子直接丢。

    返回 {satisfied, verdict, pick, next: {...} | None, reason}。
    """
    from app.services.ai_json import extract_json_object

    obj = extract_json_object((text or "").strip()) or {}
    satisfied = bool(obj.get("satisfied"))
    verdict = str(obj.get("verdict") or "").strip()[:300]
    pick = obj.get("pick")
    pick = str(pick).strip()[:120] if pick else None
    reason = obj.get("reason")
    reason = str(reason).strip()[:300] if reason else None

    nxt = obj.get("next")
    plan = None
    if isinstance(nxt, dict):
        names = [str(n).strip() for n in (nxt.get("factor_names") or [])]
        names = [n for n in dict.fromkeys(names) if n in valid_factors][:48]
        if names:
            profile = str(nxt.get("budget_profile") or "").strip()
            plan = {
                "factor_names": names,
                "budget_profile": profile if profile in PROFILES else "balanced",
                "max_combination_factors": _clamp_int(nxt.get("max_combination_factors"), 2, 4, 4),
                "beam_width": _clamp_int(nxt.get("beam_width"), 4, 32, 12),
                "correlation_threshold": _clamp_float(
                    nxt.get("correlation_threshold"), 0.5, 0.95, 0.75),
            }

    if not satisfied and plan is None and not verdict:
        raise ValueError(f"AI 返回无法解析为挖掘计划(原文开头: {(text or '')[:60]})")
    return {"satisfied": satisfied, "verdict": verdict, "pick": pick,
            "next": plan, "reason": reason}


def _clamp_int(value: Any, lo: int, hi: int, default: int) -> int:
    try:
        return max(lo, min(hi, int(value)))
    except (TypeError, ValueError):
        return default


def _clamp_float(value: Any, lo: float, hi: float, default: float) -> float:
    try:
        return round(max(lo, min(hi, float(value))), 4)
    except (TypeError, ValueError):
        return default


def stop_reason(iterations: list[dict], max_iterations: int) -> str | None:
    """该收手了吗? 返回停止原因, None = 可以继续。"""
    if not iterations:
        return None
    last = iterations[-1]
    if (last.get("ai") or {}).get("satisfied"):
        return "satisfied"
    if len(iterations) >= max_iterations:
        return "exhausted"
    return None


def confidence_note(iteration_count: int) -> str:
    """迭代次数 → 可信度提示。试的次数越多, 同样的指标越该打折。"""
    if iteration_count <= 1:
        return "仅 1 轮, 未反复挑拣, 搜索窗口指标基本可信"
    if iteration_count <= 3:
        return f"已试 {iteration_count} 轮, 搜索窗口指标略有挑拣成分, 以终检结果为准"
    if iteration_count <= 8:
        return f"已试 {iteration_count} 轮, 搜索窗口指标明显被挑拣过, 只看终检结果"
    return f"已试 {iteration_count} 轮, 搜索窗口指标已无参考价值, 终检不过就整轮作废"


# ---------- 装配 ----------

async def next_plan(*, factor_catalog: list[dict], windows: dict, iterations: list[dict],
                    max_iterations: int, asset_type: str) -> dict:
    """调 AI 要下一轮配置(或"够好了")。未配 AI / 调用失败返回 {error}。"""
    from app.services.ai_provider import ai_configured, generate_ai_text

    if not ai_configured():
        return {"error": "未配置 AI"}
    valid = {str(f["id"]) for f in factor_catalog if f.get("id")}
    payload = build_payload(factor_catalog=factor_catalog, windows=windows,
                            iterations=iterations, max_iterations=max_iterations,
                            asset_type=asset_type)
    try:
        text = await generate_ai_text(
            [
                {"role": "system", "content": _AI_SYSTEM},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False, default=str)},
            ],
            temperature=0.3,
            max_tokens=None,  # [上游标准] 分析类调用不限制输出
        )
        return parse_plan(text, valid)
    except Exception as e:  # noqa: BLE001
        logger.warning("mining autopilot plan failed: %s", e)
        return {"error": f"AI 调用失败: {e}"}
