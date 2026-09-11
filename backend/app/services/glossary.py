"""[fork 增强] R292 「说明」—— 六态状态与通道档位各是什么意思。

用户: 「把全景按钮改成说明或者帮助按钮, 里面是解释每个六态状态、结论状态是
什么意思」。

## 为什么在后端生成, 而不是前端写死一份

**名字和结论文案的正主在这里。** 六态那六个名字出自 `livermore.STATE_LABELS`,
十档结论的标题/怎么做/为什么出自 `keltner._VERDICTS` —— 前端誊抄一份的话, 底层
哪天改了措辞, 那份誊抄就开始说假话, 而且**没有任何东西会报错**。R203 的 27 格
速查表当初就是为这个理由做成端点的, 这里照同一条路。

**只有一样东西是这里新写的**: 每个六态状态的那句「是什么意思」。作者给的是
名字(`STATE_LABELS`)与该干什么(`STATE_ACTION`), 中间缺的正是"这个词在说什么"——
而这一层恰恰是用户点开「说明」要找的。

## 不许泄露算法

本仓库的老规矩(用户 R198 原话:「不能告诉别人具体是怎么算出来的」)。所以下面
每一句只讲**怎么读**: 说得出「一路创新高」, 说不出用了几日均线、几倍波动、
翻转阈值是多少。`test_glossary_hides_math.py` 把这个文件也扫进去了 ——
纪律管到哪儿, 守卫就得扫到哪儿(R279 那一课)。

无参数、无取数、结果恒定 —— 与 `/combo-table` 一样可以让浏览器长期缓存。
"""
from __future__ import annotations

# 六态: 「这个词在说什么」。**只讲怎么读, 不讲怎么算。**
#
# 排序按强弱, 从最强到最弱 —— 界面上就是一列, 顺序本身也是信息:
# 读的人一眼看得出这六个词是一条连续的强弱轴, 而不是六个并列的标签。
_TREND_MEANING: dict[str, str] = {
    "UT": "一路在创新高, 方向明确向上 —— 六档里最强的一档。趋势没坏就拿着。",
    "NR": "从一段下跌里反弹起来, 但还没站上前一个高点 —— 强度还没被确认, "
          "它可能是新一轮上涨的起点, 也可能只是跌途中的一次喘息。",
    "SR": "下跌途中的反弹, 而且力度比「自然回升」还弱 —— 大方向还没有变。",
    "SREA": "上涨途中的一次回落, 而且还没跌破前一个低点 —— 大方向还没有变。",
    "NREA": "从高点回落下来, 但还没跌破前一个低点 —— 弱到什么程度还没被确认, "
            "它可能只是一次洗盘, 也可能是下跌的开头。",
    "DT": "一路在创新低, 方向明确向下 —— 六档里最弱的一档。别在这里抄底。",
}

# 强 → 弱。与界面上那条状态色带同一个方向。
_TREND_ORDER = ("UT", "NR", "SR", "SREA", "NREA", "DT")


def trend_terms() -> list[dict]:
    """六态词条。名字与「该干什么」取自作者那一层, 只有释义是这里加的。"""
    from app.indicators.livermore import BULLISH, STATE_ACTION, STATE_LABELS
    out = []
    for code in _TREND_ORDER:
        cn, en = STATE_LABELS.get(code, (code, ""))
        out.append({
            "code": code,
            "title": cn,
            # 英文名留着 —— 徽标的悬停里一直有, 两处得是同一个词
            "en": en,
            "side": "多头" if code in BULLISH else "空头",
            "meaning": _TREND_MEANING.get(code, ""),
            "action": STATE_ACTION.get(code, ""),
        })
    return out


def verdict_terms() -> list[dict]:
    """通道档位词条。**整条都取自作者的表**, 一个字不改写。

    按 `rank` 从偏买到偏卖排 —— 那个次序是作者定的(「越大越偏卖」), 界面别处
    的排序也直接用它, 这里不另编一套。
    """
    from app.indicators.keltner import _VERDICTS
    rows = []
    for code, (title, action, detail, _side, tone, rank) in _VERDICTS.items():
        rows.append({"code": code, "title": title, "action": action,
                     "meaning": detail, "tone": tone, "rank": rank})
    return sorted(rows, key=lambda r: r["rank"])


def terms() -> dict:
    return {"trend": trend_terms(), "verdict": verdict_terms()}
