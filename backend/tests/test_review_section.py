"""[R431] 个股弹窗重做第三块:「复盘」(逐日复盘 + 两套买卖对比 + 六个状态的历史表现)。

用户两条答复: 动作三列**两套都显示**; 六个状态那张表**只摆数, 不下结论**。
"""
import re

from tests.frontend_source import code_of

DLG = "components/StockPreviewDialog.tsx"
SEC = "components/stock-preview/ReviewSection.tsx"
OLD = "components/stock-analysis/StockReviewDialog.tsx"
FT = "components/stock-analysis/FlipTradesPanel.tsx"


def test_R431_复盘块排在图表与价位之后_旧内容之前_天数跟头部():
    dlg = code_of(DLG)
    i = dlg.index("<ReviewSection")
    assert dlg.index("</ChartLevelsSection>") < i < dlg.index(
        'className="rounded border border-border/50 bg-base/30 p-3"'), "位置不对"
    call = dlg[i:dlg.index("/>", i)]
    assert "days={reviewDays}" in call, "天数没跟头部的 60 / 120 / 250 日走"
    assert "onClick={() => setView('review')}" in dlg, "旧的复盘页被删了 —— 用户说旧的先留着"


def test_R431_与旧复盘页同一个查询():
    assert "const q = useStockReview(symbol, days)" in code_of(SEC)
    assert "const q = useStockReview(symbol, days)" in code_of(OLD)


def test_R431_动作三列两套都显示_每行固定高度对齐():
    sec = code_of(SEC)
    assert "legsByFlipDate(d.flip_trades)" in sec and "legsByFlipDate(d.verdict_trades)" in sec
    assert "<TradeCells six={six.get(r.date)} ch={ch.get(r.date)} />" in sec
    assert "[['六态', six], ['通道', ch]]" in sec, "没标出是哪一套"
    assert '<span className="mr-1.5 text-micro text-muted">{src}</span>' in sec, "来源小字没画出来"
    assert "const LINE = 'flex h-5 items-center whitespace-nowrap'" in sec
    # 每一笔长什么样与旧表同一份实现
    for part in ("<LegAct leg={l} />", "<LegFill leg={l} />", "<LegResult leg={l} />"):
        assert part in sec
    ft = code_of(FT)
    cells = ft[ft.index("export function FlipTradeCells"):ft.index("export function LegAct")]
    for part in ("<LegAct leg={leg} />", "<LegFill leg={leg} />", "<LegResult leg={leg} />"):
        assert part in cells, "旧表那三格没走同一份实现"


def test_R431_两个筛选是并集():
    sec = code_of(SEC)
    assert "if (!marked && !shifted) return d.rows" in sec
    assert re.search(r"\(marked && \(r\.limit_up \|\| r\.limit_down \|\| r\.broken_limit_up \|\| !!r\.trend\?\.flipped\)\)\s*\|\| \(shifted && !!r\.verdict_flipped\)", sec)


def test_R431_只摆数不下结论():
    """用户选的「只摆数」: 图里那列「一进这档就该走, 不抢反弹」是建议 ——
    自然回撤在上升趋势里并不算坏, 写「该走」就是多给一次卖出理由。"""
    sec = code_of(SEC)
    for word in ("该走", "该拿", "拿住", "抢反弹", "别追", "建议", "不要"):
        assert word not in sec, f"「{word}」—— 复盘块在下结论了"


def test_R431_口径与四个数的说明只有一个产地():
    old, sec, ft = code_of(OLD), code_of(SEC), code_of(FT)
    for const, text in (("FLIP_BASIS", "转折次日开盘进出"), ("VERDICT_BASIS", "换档次日开盘进出")):
        assert old.count(text) == 1 and text not in sec, f"{const} 的原文又写了第二份"
        assert f"basis={{{const}}}" in old
    assert "{ name: '按转折买卖 · 六态', ft: d.flip_trades, basis: FLIP_BASIS }" in sec
    assert "{ name: '按档位买卖 · 通道', ft: d.verdict_trades, basis: VERDICT_BASIS }" in sec
    assert ft.count("按信号进出的复利") == 1 and "按信号进出的复利" not in sec
    assert "title={TRADE_STAT_TIPS.follow}" in sec


def test_R431_数字与别当真的提醒同进同出():
    sec = code_of(SEC)
    row = sec[sec.index("function SystemRow"):sec.index("function factOf")]
    assert "const notes = tradeNotes(ft)" in row
    assert "REASON_CN[ft.reason]" in row, "算不出来时要说为什么, 不能空着"


def test_R431_当前状态那一行高亮_没出现过的也占一行():
    sec = code_of(SEC)
    assert "s.current && 'bg-warning/[0.08]'" in sec
    assert "if (s.n === 0) return `这 ${days} 天没出现过`" in sec
    assert "TREND_FILL[s.key]" in sec, "状态色没用时间轴那一份"


def _flat(src: str) -> str:
    return re.sub(r"\s+", " ", src)


# 旧「趋势状态」「通道档位」两张逐日表里, 读的人看得到的每一句(表头、悬停、开关、空表、脚注、阈值)
_OLD_DAILY_TEXTS = [
    ">日期<", ">收盘<", ">涨跌<", ">六态状态<", ">通道档位<", ">动作<", ">成交 → 了结<", ">结果<",
    "当天三档通道合起来给出的那一句结论, 悬停看完整卡片",
    "成交日与成交价 → 了结日与了结价, 都是开盘价",
    "多头段是真赚到的; 空头段是空仓期间股价的涨跌, 不是你的盈亏",
    "按转折买卖: 这次转折的次日开盘该干什么",
    "按档位买卖: 这次换档的次日开盘该干什么",
    "只留下有涨跌停、或趋势翻转的那些天 —— 其余日子状态没变, 复盘时没有信息",
    "只留下档位换过的那些天 —— 其余日子档位没变, 复盘时没有信息",
    "只看有事的日子", "只看换档的日子",
    "这段时间里没有涨跌停, 状态也没翻转过", "这段时间里档位一次都没换过",
    "← 转折", "这天六态状态发生了翻转", "← 换档", "这天通道档位换了一档",
    "三档都在中部", 'note="收盘口径"', "<LimitTag r={r} />", "SUB_STATE_TIP",
    "{r.trend.state_cn} 第 {r.trend.day} 天",
    "收盘口径, 与决策台「趋势」列同一个状态机、同一个阈值(含你自己调过的那个)。",
    "「通道档位」列悬停看完整卡片 —— 与决策台「档位」列是同一张。一律按收盘算, 用的是同一套通道。",
    '历史是按<b className="text-secondary">当前</b>复权价重新算的 —— 期间除过权的话, '
    "同一天今天算出来的通道会和当时屏幕上略有出入, 复盘看的是形态与节奏。",
    "六态阈值 ", "(d.threshold * 100).toFixed(0)}%", "? `(${d.threshold_source})` : ''",
]


def test_R440_逐日复盘内容与旧两张表一模一样():
    """[R440] 用户: 「逐日复盘可以保留样式, 但是内容必须和以前一模一样, 不多也不少」。
    旧两张表里读得到的每一句, 新表里逐字都要有(不少); R431 自己改写过的那几句不许再出现(不多)。"""
    old, new = _flat(code_of(OLD)), _flat(code_of(SEC))
    for t in _OLD_DAILY_TEXTS:
        t = _flat(t)
        assert t in old, f"旧页里没有「{t}」—— 这份清单抄错了"
        assert t in new, f"新逐日复盘少了旧表里的「{t}」"
    for t in ("六态转折的那些天", "只留下通道档位换过的那些天", "没有这类日子", "两列同源",
              "前面的小字说明是哪一套", "(现在是 "):
        assert t not in new, f"「{t}」是 R431 自己改写的, 旧表里没有"
    # 列与旧表一样多: 六态表的 8 列 ∪ 通道表的 7 列 = 同样这 8 个表头, 一列不多
    daily = new[new.index("function DailyCard"):new.index("function TrendCell")]
    assert len(re.findall(r"<th\b", daily)) == 8
