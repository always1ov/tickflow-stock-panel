"""[fork 增强] R34 策略回测的 AI 代跑 —— 用户不会填表, AI 来选策略、定参数、跑、判断。

与 R33 因子代跑同一形态, 只是对象换成「策略回测」:
  AI 选策略 + 定风控参数 + 选环境过滤 → 前端把配置灌进表单跑 → AI 看结果
  → 不行就换一个策略/换参数再跑 → 满意即收手给结论。

**只让 AI 碰有限的几个旋钮**
回测页有几十个输入(资金/费率/撮合/口径/策略自有参数…)。AI 只允许动这五样:
  策略、环境过滤档位、最大持仓数、最大总仓位、区间天数。
费率、撮合口径、初始资金这类属于"你的账户事实", 不该由 AI 替你改;
策略自有参数(params)更不给 —— 那是每个策略各不相同的语义, AI 盲调等于乱试。

**为什么设了轮数上限**
反复换配置直到回测好看, 就是在同一段历史上挑拣; 试的次数越多, 挑出来的越可能
是运气。所以最多 5 轮, 且提示词要求达标即收手, 并在结论里如实说明"这是历史
回测, 不代表未来", 引导用户去「验证」tab 做参数敏感性和滚动样本外。

纯函数在前(可单测), 装配在后。
"""
from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

MAX_ROUNDS = 5
REGIME_STATES = ("strong", "lean_strong", "range", "lean_weak", "weak")
POSITION_SIZINGS = ("equal", "score_weight")

_SYSTEM = """你在替一个不懂量化的用户操作「策略回测」。他不会填表, 你全权代劳。

每一轮你要么给出下一轮怎么配, 要么宣布够了并给结论。

你只能动这七样, 其余一律不许碰(费率、撮合口径、初始资金是用户的账户事实,
策略自有参数是每个策略特有的语义, 盲调等于乱试):
- strategy_id: 从给定策略清单里选一个。
- regime_states: 市场环境过滤, 从 strong / lean_strong / range / lean_weak / weak
  里选 0-5 个 —— 只在前一交易日属于所选环境时才允许入场。留空 = 不过滤。
  想只做强势环境就选 ["strong","lean_strong"]。
- max_positions: 最大同时持仓数, 3-30。
- max_exposure_pct: 最大总仓位百分比, 20-100。
- days: 回测区间长度(自然日), 180-1460。数据不够时系统会自动截断。
- holding_days: 兜底持仓天数, 2-60。策略自己有 max_hold_days 时以策略的为准,
  这个只在策略没规定时起作用。
- position_sizing: 每笔怎么分钱 —— equal(等权, 稳) 或 score_weight(按打分加权,
  信号强的多买, 波动更大)。

判定够了的标准(全部满足):
- 交易数 >= 30 (太少没有统计意义)
- 最大回撤不差于 -30%
- 总收益 > 0 且 夏普 >= 0.5
达到就收手。**不要为了更好看的数字反复换配置** —— 在同一段历史上反复挑拣,
试的次数越多挑出来的越可能是运气。

纪律:
- 只能用给定清单里的 strategy_id, 不得编造。
- 结论里必须说清: 这是历史回测, 不代表未来; 建议去「验证」tab 做参数敏感性
  和滚动样本外, 那才是检验稳健性的地方。
- 交易数少、回撤大、或收益全靠个别几笔的, 要明说, 不许只报喜。
- 不要给个股、点位、仓位的实盘建议。

只输出 JSON, 不要任何解释文字或代码块标记:
{"satisfied": true|false,
 "note": "一句话说这轮打算干什么 / 或这轮结果怎么样, 大白话给外行看",
 "conclusion": "满意时: 三五句话说清这个策略表现如何、风险在哪、下一步该干嘛; 不满意时填 null",
 "next": {"strategy_id": "xxx", "regime_states": ["strong"],
          "max_positions": 10, "max_exposure_pct": 100, "days": 730,
          "holding_days": 5, "position_sizing": "equal"}}
"""


# ---------- 纯函数 ----------

def digest_result(result: dict | None) -> dict:
    """回测结果 → 喂回给 AI 的关键指标(只留判断需要的, 净值曲线之类不带)。"""
    stats = ((result or {}).get("stats") or {}) if isinstance(result, dict) else {}

    def g(*keys):
        for k in keys:
            v = stats.get(k)
            if v is not None:
                return v
        return None

    return {
        "总收益": g("total_return"),
        "年化": g("annual_return"),
        "夏普": g("sharpe"),
        "最大回撤": g("max_drawdown"),
        "胜率": g("win_rate"),
        "交易数": g("n_trades"),
        "平均持仓天数": g("avg_duration"),
    }


def meets_bar(digest: dict) -> bool:
    """规则层的"够好了"判定 —— 与提示词里给 AI 的标准同一套, 供兜底与前端显示。"""
    def num(key):
        v = digest.get(key)
        return float(v) if isinstance(v, (int, float)) else None

    trades, mdd = num("交易数"), num("最大回撤")
    ret, sharpe = num("总收益"), num("夏普")
    return bool(
        trades is not None and trades >= 30
        and mdd is not None and mdd >= -0.30
        and ret is not None and ret > 0
        and sharpe is not None and sharpe >= 0.5
    )


def build_payload(*, strategies: list[dict], rounds: list[dict], max_rounds: int) -> dict:
    history = []
    for r in rounds or []:
        history.append({
            "第几轮": r.get("round"),
            "用的配置": r.get("config"),
            "跑出的结果": r.get("digest"),
            "达标": r.get("passed"),
            "你当时的判断": r.get("note"),
        })
    return {
        "本轮是第几轮": len(rounds or []) + 1,
        "最多允许几轮": max_rounds,
        "可用策略": strategies,
        "历史轮次": history,
    }


def parse_plan(text: str, valid_strategies: set[str]) -> dict:
    """解析代跑计划; 容错各厂商格式。编造策略丢弃, 数值越界夹紧。"""
    from app.services.ai_json import extract_json_object

    obj = extract_json_object((text or "").strip()) or {}
    satisfied = bool(obj.get("satisfied"))
    note = str(obj.get("note") or "").strip()[:300]
    conclusion = obj.get("conclusion")
    conclusion = str(conclusion).strip()[:800] if conclusion else None

    nxt = obj.get("next")
    plan = None
    if isinstance(nxt, dict):
        sid = str(nxt.get("strategy_id") or "").strip()
        if sid in valid_strategies:
            states = [str(s).strip() for s in (nxt.get("regime_states") or [])]
            states = [s for s in dict.fromkeys(states) if s in REGIME_STATES]
            sizing = str(nxt.get("position_sizing") or "").strip()
            plan = {
                "strategy_id": sid,
                "regime_states": states,
                "max_positions": _clamp(nxt.get("max_positions"), 3, 30, 10),
                "max_exposure_pct": _clamp(nxt.get("max_exposure_pct"), 20, 100, 100),
                "days": _clamp(nxt.get("days"), 180, 1460, 730),
                "holding_days": _clamp(nxt.get("holding_days"), 2, 60, 5),
                # 编造的分钱方式一律回落等权 —— 等权是最不会出意外的那个
                "position_sizing": sizing if sizing in POSITION_SIZINGS else "equal",
            }

    if not satisfied and plan is None and not note:
        raise ValueError(f"AI 返回无法解析为回测计划(原文开头: {(text or '')[:60]})")
    return {"satisfied": satisfied, "note": note, "conclusion": conclusion, "next": plan}


def _clamp(value: Any, lo: int, hi: int, default: int) -> int:
    try:
        return max(lo, min(hi, int(value)))
    except (TypeError, ValueError):
        return default


def stop_reason(rounds: list[dict], max_rounds: int) -> str | None:
    if not rounds:
        return None
    if rounds[-1].get("satisfied"):
        return "satisfied"
    if len(rounds) >= max_rounds:
        return "exhausted"
    return None


def best_round(rounds: list[dict]) -> dict | None:
    """兜底选优: 先看达标, 再看夏普。用尽轮数时用它挑出最好的一轮。"""
    if not rounds:
        return None

    def key(r):
        d = r.get("digest") or {}
        sharpe = d.get("夏普")
        return (bool(r.get("passed")), float(sharpe) if isinstance(sharpe, (int, float)) else -1e9)

    return max(rounds, key=key)


# ---------- 装配 ----------

async def next_plan(*, strategies: list[dict], rounds: list[dict],
                    max_rounds: int = MAX_ROUNDS) -> dict:
    """要下一轮配置(或"够了")。未配 AI / 调用失败返回 {error}。"""
    from app.services.ai_provider import ai_configured, generate_ai_text

    if not ai_configured():
        return {"error": "未配置 AI"}
    valid = {str(s["id"]) for s in strategies if s.get("id")}
    payload = build_payload(strategies=strategies, rounds=rounds, max_rounds=max_rounds)
    try:
        text = await generate_ai_text(
            [
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False, default=str)},
            ],
            temperature=0.3,
            max_tokens=None,  # [上游标准] 分析类调用不限制输出
        )
        return parse_plan(text, valid)
    except Exception as e:  # noqa: BLE001
        logger.warning("backtest autopilot plan failed: %s", e)
        return {"error": f"AI 调用失败: {e}"}
