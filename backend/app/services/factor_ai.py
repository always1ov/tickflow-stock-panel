"""[fork 增强] R32 因子批量筛选的 AI 解读。

量化研究页跑完批量筛选会吐出 61 个因子 × 5 个指标(IC 均值 / IR / IC 胜率 /
多空收益 / 多空回撤)的表。不懂的人看到一屏数字无从下手, 懂的人也要逐行扫。

两层, 与本仓其他 AI 功能一致:
  规则层(零 AI 成本): 先按 IC/IR/胜率算一个可用度分, 把明显没用的剔掉、
    按因子组去重, 得到一份短名单 —— 没配 AI 也能直接用。
  AI 层(点按钮): 只对短名单做解读 —— 哪几个真能用、哪些是同类冗余、
    当前这批数据反映的是什么样的市场、下一步该拿哪几个去挖掘。

口径提醒(与 docs/mining.md §成交和成本 一致): 多空收益是衡量因子区分能力的
理论价差, A 股不能真做空; 所以 AI 被明确要求不得把它当可执行收益来推荐。

纯函数在前(可单测), 装配在后。
"""
from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

# 可用度门槛: 低于此的因子连短名单都进不去
MIN_ABS_IC = 0.015       # |IC 均值| 太小 = 基本没有区分度
# IC 胜率在 50% ± 死区内 = 方向随机, 直接出局。用双边死区而不是单边下限, 是因为
# 反向因子的胜率天然低于 50%(值越小未来收益越高), 单边下限会把它们误杀。
WIN_RATE_DEAD_BAND = 0.05
SHORTLIST_SIZE = 12      # 送 AI 的短名单上限
PER_GROUP_CAP = 2        # 同一因子组最多留几个 —— 同组高度相关, 堆一起是虚假多样性

_AI_SYSTEM = """你是量化因子研究员。用户跑完了一批因子的批量筛选, 你要把结果讲成人话。

每个因子给你这些指标:
- IC 均值: 因子值与未来收益的截面相关性。绝对值越大区分度越强; 负值表示反向有效
  (值越小future收益越高), 反向因子照样能用, 取负号即可。
- IR: IC 的稳定性(IC 均值 / IC 标准差)。IC 高但 IR 低 = 时灵时不灵。
- IC 胜率: IC 为正的交易日占比。偏离 50% 越远方向越确定。
- 多空收益 / 多空回撤: **理论价差, 只用于衡量区分能力。A 股不能真做空,
  绝不能把它当成可执行收益来推荐。**

你的任务:
1. 挑出真正能用的 2-5 个因子, 说清为什么(要落到具体指标, 不要空话)。
2. 指出哪些是同类冗余 —— 同一组里指标接近的因子只需留一个, 全用是自欺。
3. 从这批因子的强弱格局判断当前市场偏什么风格(趋势跟随 / 均值回归 / 量能驱动),
   用大白话说, 不要术语堆砌。
4. 给下一步建议: 拿哪几个因子去「挖掘」页做组合搜索。

纪律:
- 只能引用给定清单里的因子 id, 不得编造。
- IC 高但 IR 低、或胜率贴近 50% 的, 要明说它不稳, 不能只报喜。
- 这是研究结论, 不是买卖建议; 不要给个股、点位或仓位。

只输出 JSON, 不要任何解释文字或代码块标记:
{"summary": "两三句话说清这批因子整体什么情况 + 当前市场偏什么风格",
 "picks": [{"factor": "因子id", "reason": "为什么能用, 落到指标, 50 字内"}],
 "redundant": [{"keep": "留哪个id", "drop": ["同组可以丢的id"], "reason": "30 字内"}],
 "next_step": "下一步拿哪几个去挖掘页做组合搜索, 一句话"}
"""


# ---------- 纯函数: 规则层 ----------

def usable_score(item: dict) -> float | None:
    """因子可用度分(0-100)。数据缺失或明显没用返回 None。

    三块: 区分度(|IC|, 50) + 稳定性(|IR|, 30) + 方向确定性(胜率偏离 50%, 20)。
    用绝对值是因为反向因子取负号照样能用, 不该因为符号被埋没。
    """
    if not isinstance(item, dict) or item.get("error"):
        return None
    ic = item.get("ic_mean")
    if not isinstance(ic, (int, float)):
        return None
    ic_abs = abs(float(ic))
    if ic_abs < MIN_ABS_IC:
        return None

    ir = item.get("ir")
    ir_abs = abs(float(ir)) if isinstance(ir, (int, float)) else 0.0
    win = item.get("ic_win_rate")
    win_dev = abs(float(win) - 0.5) if isinstance(win, (int, float)) else 0.0
    if isinstance(win, (int, float)) and win_dev < WIN_RATE_DEAD_BAND:
        return None  # 胜率贴着 50% = 方向随机, 直接出局

    return round(
        min(1.0, ic_abs / 0.05) * 50
        + min(1.0, ir_abs / 0.5) * 30
        + min(1.0, win_dev / 0.15) * 20,
        1,
    )


def shortlist(items: list[dict], *, size: int = SHORTLIST_SIZE,
              per_group: int = PER_GROUP_CAP) -> list[dict]:
    """规则层短名单: 按可用度降序, 每组最多留 per_group 个。

    同组因子(如 MA5/MA10/MA20 乖离)高度相关, 全放进去只会让 AI 在一堆近亲里
    绕圈, 也会让用户误以为"有十个有效因子"。
    """
    scored = []
    for it in items or []:
        s = usable_score(it)
        if s is None:
            continue
        scored.append({
            "factor": it.get("factor_name"),
            "label": it.get("label"),
            "group": it.get("group") or "其他",
            "可用度": s,
            "IC均值": it.get("ic_mean"),
            "IR": it.get("ir"),
            "IC胜率": it.get("ic_win_rate"),
            "多空收益(理论)": it.get("long_short_return"),
            "多空回撤(理论)": it.get("long_short_max_drawdown"),
        })
    scored.sort(key=lambda x: x["可用度"], reverse=True)

    seen: dict[str, int] = {}
    out = []
    for row in scored:
        g = row["group"]
        if seen.get(g, 0) >= per_group:
            continue
        seen[g] = seen.get(g, 0) + 1
        out.append(row)
        if len(out) >= size:
            break
    return out


def dropped_summary(items: list[dict], picked: list[dict]) -> dict:
    """被规则层剔掉的统计 —— 界面要说清"61 个里为什么只剩 12 个"。"""
    total = len([i for i in items or [] if isinstance(i, dict)])
    errored = len([i for i in items or [] if isinstance(i, dict) and i.get("error")])
    usable = len([i for i in items or [] if usable_score(i) is not None])
    kept = {p["factor"] for p in picked}
    return {
        "总数": total,
        "算失败": errored,
        "有区分度": usable,
        "进短名单": len(kept),
        "同组去重剔除": max(0, usable - len(kept)),
    }


# ---------- 纯函数: AI 出入参 ----------

def build_payload(shortlisted: list[dict], config: dict | None, stats: dict) -> dict:
    cfg = config or {}
    return {
        "样本": {
            "标的数": cfg.get("n_symbols"),
            "交易日数": cfg.get("n_dates"),
            "区间": f"{cfg.get('start') or '—'} ~ {cfg.get('end') or '—'}",
            "调仓": cfg.get("rebalance"),
            "分组数": cfg.get("n_groups"),
        },
        "规则层筛选情况": stats,
        "候选因子(已按可用度排序, 同组最多留 2 个)": shortlisted,
    }


def parse_reading(text: str, valid_factors: set[str]) -> dict:
    """解析 AI 解读; 容错各厂商格式。编造的因子 id 一律丢弃。"""
    from app.services.ai_json import extract_json_object

    obj = extract_json_object((text or "").strip()) or {}

    picks = []
    seen: set[str] = set()
    for p in (obj.get("picks") or [])[:5]:
        if not isinstance(p, dict):
            continue
        fid = str(p.get("factor") or "").strip()
        if fid not in valid_factors or fid in seen:
            continue
        seen.add(fid)
        picks.append({"factor": fid, "reason": str(p.get("reason") or "").strip()[:150]})

    redundant = []
    for r in (obj.get("redundant") or [])[:5]:
        if not isinstance(r, dict):
            continue
        keep = str(r.get("keep") or "").strip()
        drop = [str(d).strip() for d in (r.get("drop") or [])]
        drop = [d for d in drop if d in valid_factors and d != keep][:6]
        if keep not in valid_factors or not drop:
            continue
        redundant.append({"keep": keep, "drop": drop,
                          "reason": str(r.get("reason") or "").strip()[:100]})

    summary = str(obj.get("summary") or "").strip()[:500]
    next_step = str(obj.get("next_step") or "").strip()[:200]
    if not summary and not picks:
        raise ValueError(f"AI 返回无法解析为因子解读(原文开头: {(text or '')[:60]})")
    return {"summary": summary, "picks": picks, "redundant": redundant,
            "next_step": next_step}


# ---------- 装配 ----------

async def generate(result: dict) -> dict:
    """批量筛选结果 → {shortlist, stats, ai}。未配 AI 时仍返回规则层短名单。"""
    items = (result or {}).get("results") or []
    picked = shortlist(items)
    stats = dropped_summary(items, picked)
    base = {"shortlist": picked, "stats": stats}
    if not picked:
        return {**base, "error": "没有因子通过规则层门槛 —— 这批因子在该区间都没有区分度"}

    from app.services.ai_provider import ai_configured, generate_ai_text
    if not ai_configured():
        return {**base, "error": "未配置 AI(短名单仍可用)"}

    cfg = dict((result or {}).get("config") or {})
    cfg.setdefault("n_symbols", (result or {}).get("n_symbols"))
    cfg.setdefault("n_dates", (result or {}).get("n_dates"))
    try:
        text = await generate_ai_text(
            [
                {"role": "system", "content": _AI_SYSTEM},
                {"role": "user", "content": json.dumps(
                    build_payload(picked, cfg, stats), ensure_ascii=False, default=str)},
            ],
            temperature=0.2,
            max_tokens=None,  # [上游标准] 分析类调用不限制输出
        )
        ai = parse_reading(text, {str(p["factor"]) for p in picked})
    except Exception as e:  # noqa: BLE001
        logger.warning("factor ai reading failed: %s", e)
        return {**base, "error": f"AI 调用失败: {e}"}
    return {**base, "ai": ai}


# ================================================================
# [R33] AI 代跑 —— 用户不会填表, 那就让 AI 来填、来跑、来判断
# ================================================================
#
# 与 R32「AI 解读」的区别: 解读是跑完之后帮你读; 代跑是**从头到尾替你操作** ——
# 选因子、定参数、跑、看结果、不行就换一批再跑, 直到它认为可以。
#
# 这里只出"下一步该怎么配"和"够了没有", 实际跑批量筛选仍走原来的 /factor/batch,
# 前端把每轮配置灌进表单再调用 —— 用户能亲眼看到它在操作, 而不是黑箱。
#
# 与挖掘 autopilot 的关键差别: 批量筛选是描述性统计(算 IC/IR), 不是带通过/否决
# 门槛的策略验证, 也没有 786 根交易日的硬门槛, 几秒就能跑完。所以这里不需要锁
# 终检窗口 —— 但也因此**它的结论只是"值得进一步研究", 不是"验证过的策略"**,
# 提示词里要求 AI 如实这么说。

MAX_PLAN_ROUNDS = 5
_PLAN_REBALANCE = ("daily", "weekly", "monthly")

_PLAN_SYSTEM = """你在替一个不懂量化的用户操作「因子批量筛选」。他不会填表, 你全权代劳。

每一轮你要么给出下一轮怎么配, 要么宣布够了并给结论。

可调的只有三样:
- factor_names: 从给定清单里挑 8-16 个因子。**必须跨组挑**(动量/均线偏离/超买超卖/
  趋势/波动率/量价/价格位置…), 同组挑 1-2 个就够 —— 同组高度相关, 堆一起是白费。
- rebalance: daily / weekly / monthly。短周期因子(5日动量、量比)配 daily 或 weekly;
  中长周期因子(60日动量、MA60乖离)配 monthly。
- n_groups: 2-10, 常用 5。标的少时用小一点(3), 免得每组太少没有统计意义。

判定够了的标准: 至少有 2 个因子的 |IC 均值| >= 0.02 且 IC 胜率偏离 50% 超过 5 个点。
达到就收手, 不要为了更好看的数字反复刷 —— 试的次数越多, 挑出来的越可能是运气。

纪律:
- 只能用给定清单里的因子 id, 不得编造。
- 批量筛选算的是 IC/IR 这类描述性统计, **不是经过验证的策略**。结论里必须说清
  这只是"值得进一步研究的方向", 让用户拿去挖掘页做组合搜索和样本外验证。
- 多空收益是理论价差, A 股不能真做空, 不得当成可执行收益来说。
- 不要给个股、点位、仓位建议。

只输出 JSON, 不要任何解释文字或代码块标记:
{"satisfied": true|false,
 "note": "一句话说这轮打算干什么 / 或这轮结果怎么样, 大白话给外行看",
 "conclusion": "满意时: 三五句话说清哪几个因子有效、当前市场偏什么风格、下一步该干嘛; 不满意时填 null",
 "next": {"factor_names": ["id1", ...], "rebalance": "daily|weekly|monthly", "n_groups": 5}}
"""


def build_plan_payload(*, factor_catalog: list[dict], rounds: list[dict],
                       max_rounds: int, sample: dict | None = None) -> dict:
    """送审 payload: 因子清单 + 历次配置与结果(这就是"拿上次结果反馈"的载体)。"""
    history = []
    for r in rounds or []:
        history.append({
            "第几轮": r.get("round"),
            "用的配置": r.get("config"),
            "跑出的因子表现(已按可用度排序)": r.get("shortlist"),
            "规则层筛选情况": r.get("stats"),
            "你当时的判断": r.get("note"),
        })
    return {
        "样本": sample or {},
        "本轮是第几轮": len(rounds or []) + 1,
        "最多允许几轮": max_rounds,
        "可用因子": factor_catalog,
        "历史轮次": history,
    }


def parse_plan(text: str, valid_factors: set[str]) -> dict:
    """解析代跑计划; 容错各厂商格式。编造因子丢弃, 参数越界夹紧。"""
    from app.services.ai_json import extract_json_object

    obj = extract_json_object((text or "").strip()) or {}
    satisfied = bool(obj.get("satisfied"))
    note = str(obj.get("note") or "").strip()[:300]
    conclusion = obj.get("conclusion")
    conclusion = str(conclusion).strip()[:800] if conclusion else None

    nxt = obj.get("next")
    plan = None
    if isinstance(nxt, dict):
        names = [str(n).strip() for n in (nxt.get("factor_names") or [])]
        names = [n for n in dict.fromkeys(names) if n in valid_factors][:32]
        if names:
            reb = str(nxt.get("rebalance") or "").strip()
            try:
                groups = max(2, min(10, int(nxt.get("n_groups"))))
            except (TypeError, ValueError):
                groups = 5
            plan = {
                "factor_names": names,
                "rebalance": reb if reb in _PLAN_REBALANCE else "weekly",
                "n_groups": groups,
            }

    if not satisfied and plan is None and not note:
        raise ValueError(f"AI 返回无法解析为代跑计划(原文开头: {(text or '')[:60]})")
    return {"satisfied": satisfied, "note": note, "conclusion": conclusion, "next": plan}


def round_digest(result: dict) -> dict:
    """一轮批量筛选结果 → 喂回给 AI 的摘要(复用规则层短名单与漏斗)。"""
    items = (result or {}).get("results") or []
    picked = shortlist(items)
    return {"shortlist": picked, "stats": dropped_summary(items, picked)}


def plan_stop_reason(rounds: list[dict], max_rounds: int) -> str | None:
    """该收手了吗。"""
    if not rounds:
        return None
    if rounds[-1].get("satisfied"):
        return "satisfied"
    if len(rounds) >= max_rounds:
        return "exhausted"
    return None


async def next_plan(*, factor_catalog: list[dict], rounds: list[dict],
                    max_rounds: int = MAX_PLAN_ROUNDS,
                    sample: dict | None = None) -> dict:
    """要下一轮配置(或"够了")。未配 AI / 调用失败返回 {error}。"""
    from app.services.ai_provider import ai_configured, generate_ai_text

    if not ai_configured():
        return {"error": "未配置 AI"}
    valid = {str(f["id"]) for f in factor_catalog if f.get("id")}
    payload = build_plan_payload(factor_catalog=factor_catalog, rounds=rounds,
                                 max_rounds=max_rounds, sample=sample)
    try:
        text = await generate_ai_text(
            [
                {"role": "system", "content": _PLAN_SYSTEM},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False, default=str)},
            ],
            temperature=0.3,
            max_tokens=None,  # [上游标准] 分析类调用不限制输出
        )
        return parse_plan(text, valid)
    except Exception as e:  # noqa: BLE001
        logger.warning("factor autopilot plan failed: %s", e)
        return {"error": f"AI 调用失败: {e}"}
