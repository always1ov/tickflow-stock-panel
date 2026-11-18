"""[R431] 个股弹窗第三块:「复盘」。

用户两条答复: 动作三列**两套都显示**; 状态那张表**只摆数, 不下结论**。

[R730→R749] 排版改过四轮: 8 列横向滚动表 → 上下一条线的卡片 → 日历/热力矩阵/分布三视图。
[R759] 用户: 「保持现在四列排版不变了, 里面内容布局先恢复最开始的样子, 复盘内部的排版
要排好显示出所有信息, 我还没想好怎么重做」—— 弹窗四栏不动, 复盘内部回到 R431 最初那版
三块(逐日 / 两套对比 / 六态历史); 窄列摊不开八列, 每天拆两行摊开八样信息。
[R827] 用户: 「两套买卖的对比这部分我不想要了，删了」—— 现在两块(逐日 / 六态历史)。

这里守的是内容口径与三条不变式, 不再守某一种排版的具体写法:

  1. 页头仍给旧「趋势状态」页的区间与天数(R826 起阈值进悬停);
  2. 口径说明只有 `StockReviewDialog` 里那一份原文;
  3. 只摆数, 不下结论。
"""
from tests.frontend_source import code_of

DLG = "components/StockPreviewDialog.tsx"
SEC = "components/stock-preview/ReviewSection.tsx"
OLD = "components/stock-analysis/StockReviewDialog.tsx"
FT = "components/stock-analysis/FlipTradesPanel.tsx"


def test_R431_复盘是右栏第4个视图_天数跟头部():
    """[R612] 窄屏时复盘仍是右栏顶部的第 4 个视图; [R732] ≥1536 时常驻左列。
    两处都得跟头部的 60 / 120 / 250 日走。"""
    dlg = code_of(DLG)
    assert "{ key: 'review', label: '复盘', Icon: History }" in dlg, "右栏没有复盘视图"
    tabs = dlg.index('role="tablist"')
    i = dlg.index("chartView === 'review' && !showReviewWide ? (", tabs)
    assert i < dlg.index("<ChartLevelsSection", tabs), "复盘与图表没做成同一层的分支"
    call = dlg[i:dlg.index("/>", dlg.index("<ReviewSection", i))]
    assert "days={reviewDays}" in call, "天数没跟头部的 60 / 120 / 250 日走"
    wide = dlg[dlg.index("showReviewWide && ("):]
    wide_call = wide[:wide.index("/>", wide.index("<ReviewSection"))]
    assert "days={reviewDays}" in wide_call and "compact" in wide_call, "常驻左列那一份没接上"
    assert "onClick={() => setView('review')}" not in dlg, "旧复盘页又回来了"


def test_R431_与旧复盘页同一个查询():
    assert "const q = useStockReview(symbol, days)" in code_of(SEC)
    assert "const q = useStockReview(symbol, days)" in code_of(OLD)


def test_R431_只摆数不下结论():
    """用户选的「只摆数」: 图里那列「一进这档就该走, 不抢反弹」是建议 ——
    自然回撤在上升趋势里并不算坏, 写「该走」就是多给一次卖出理由。"""
    sec = code_of(SEC)
    for word in ("该走", "该拿", "拿住", "抢反弹", "别追", "建议", "不要"):
        assert word not in sec, f"「{word}」—— 复盘块在下结论了"


def test_R431_口径与四个数的说明只有一个产地():
    """[R827] 用户: 「两套买卖的对比这部分我不想要了，删了」—— 那一块连同它引用的
    口径原文一起撤掉。口径与四个数的说明仍各只有一处产地(`StockReviewDialog` /
    `FlipTradesPanel`), 复盘栏里不该再出现第二份。"""
    old, sec, ft = code_of(OLD), code_of(SEC), code_of(FT)
    for text in ("转折次日开盘进出", "换档次日开盘进出"):
        assert old.count(text) == 1, f"原文在旧页里不止一份: {text}"
        assert text not in sec, f"复盘栏里又写了一份: {text}"
    assert "按信号进出的复利" not in sec
    assert ft.count("按信号进出的复利") == 1


def test_R444_页头那句与旧趋势状态页一致():
    """[R826] 用户: 「文字内容描述也要整理, 精简抓重点…用悬浮字来解释含义」——
    页头只留区间与天数, 阈值与来源搬进悬停。**信息一条没删**, 只是不再常驻。
    转折配对仍用同一份 `legsByFlipDate`。"""
    old, new = code_of(OLD), code_of(SEC)
    assert "{d.start} ~ {d.end} · {d.days} 个交易日" in old, "旧页那一句被改掉了"
    assert "{d.start} ~ {d.end} · {d.days} 日" in new, "页头不再显示区间与天数"
    assert '"六态阈值 ${(d.threshold * 100).toFixed(0)}%' in new or \
           "`六态阈值 ${(d.threshold * 100).toFixed(0)}%" in new, "阈值连悬停里都没有了"
    assert "legsByFlipDate(d.flip_trades)" in new


def test_R827_复盘回到两块_两套对比已删():
    """[R827] 用户: 「两套买卖的对比这部分我不想要了，删了」。
    现在复盘只有 逐日 / 六个状态(+ 通道证据) 两块, 对比块与它的卡片一起撤掉;
    R749 的结论条、六态规律、权益曲线也不回来。"""
    sec = code_of(SEC)
    for fn in ("function DailyCard", "function DayRow", "function HistoryCard", "function StateHistory"):
        assert fn in sec, f"复盘少了一块: {fn}"
    for gone in ("function SummaryCard", "function SystemCard", "两套买卖的对比",
                 "按转折买卖 · 六态", "按档位买卖 · 通道",
                 "setView(", "ReviewCalendar", "DistPanel", "TradeBars",
                 "NowCondition", "FlipStats", "HeatCell", "MiniBox", "VerdictStrip",
                 "function Conclusion", "function EquityChart", "function DailyTable"):
        assert gone not in sec, f"「{gone}」—— 删掉的块 / 页签 / 三视图又回来了"


def test_R759_每天两行摆齐八样信息():
    """窄列 420~460px: 第一行日期·收盘·涨跌·六态状态; 第二行通道档位·动作·成交→了结·结果。
    八样信息都必须直接可见, 不再收进悬停。"""
    sec = code_of(SEC)
    for piece in ("{r.date.slice(5)}", "{r.close.toFixed(2)}", "chgCls(r.change_pct)",
                  "trendBadgeCls(r.trend.state)", "VERDICT_CLS[r.verdict.tone]",
                  "<LegAct leg={l} />", "<LegFill leg={l} />", "<LegResult leg={l} />"):
        assert piece in sec, f"逐日少了一样: {piece}"


def test_R759_两套口径都在_六态与通道():
    """[R441] 曾按用户要求删掉「按档位买卖 · 通道」; [R759] 那一行与逐日里通道那笔
    动作一起回来; [R827] 用户把「两套对比」整块删了, **但逐日里两套动作都还在** ——
    复盘要能看见这一天六态做了什么、通道做了什么。"""
    sec = code_of(SEC)
    assert "legsByFlipDate(d.verdict_trades)" in sec, "逐日里通道那笔动作没接上"
    assert "legsByFlipDate(d.flip_trades)" in sec, "逐日里六态那笔动作没接上"
    for word in ("只看有事的日子", "只看换档的日子"):
        assert word in sec, f"筛选少了「{word}」"


def test_R759_结果按每一段取():
    """最初版的结果列是**每一段自己**的盈亏(多头真赚、空头是空仓期涨跌),
    不是卖出那天统一落账 —— R749 的落账口径随五列表一起退了。"""
    sec = code_of(SEC)
    assert "<LegResult leg={l} />" in sec and "legResultCls(l)" in sec
    assert "closed.get(leg.enter_date)" not in sec and "openBuy" not in sec


def test_R442_换票复位():
    dlg = code_of(DLG)
    call = dlg[dlg.index("<ReviewSection"):dlg.index("/>", dlg.index("<ReviewSection"))]
    assert "key={symbol}" in call
