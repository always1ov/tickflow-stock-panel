"""[R431] 个股弹窗第三块:「复盘」。

用户两条答复: 动作三列**两套都显示**; 状态那张表**只摆数, 不下结论**。

[R730→R748] 排版改过四轮: 8 列横向滚动表 → 上下一条线的卡片 → 日历/热力矩阵/分布三视图。
[R749] 用户: 「我感觉越搞越复杂了, 推翻整个复盘, 重做一个复盘方案实现」——
定案三块: **结论 / 权益曲线 / 逐日**。这里守的是内容口径与三条不变式,
不再守某一种排版的具体写法:

  1. 页头仍是旧「趋势状态」页那一句;
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
    old, sec, ft = code_of(OLD), code_of(SEC), code_of(FT)
    for const, text in (("FLIP_BASIS", "转折次日开盘进出"), ("VERDICT_BASIS", "换档次日开盘进出")):
        assert old.count(text) == 1 and text not in sec, f"{const} 的原文又写了第二份"
        assert f"basis={{{const}}}" in old
    # 结论条只引用那一份原文, 不自己再写一遍
    assert "title={FLIP_BASIS}" in sec
    assert ft.count("按信号进出的复利") == 1 and "按信号进出的复利" not in sec
    assert "tip={TRADE_STAT_TIPS.follow}" in sec


def test_R749_结论句与别当真的提醒同进同出():
    """数字与提醒必须同时出现: 摆出 +143% 而把「样本太少」藏起来, 那是骗人。"""
    sec = code_of(SEC)
    block = _between(sec, "function Conclusion", "function Inline(")
    assert "tradeNotes(ft)" in block
    assert "REASON_CN[ft.reason]" in block, "算不出来时要说为什么, 不能空着"
    assert "ci95(" in block, "结论句里的统计判断没接上区间"


def test_R441_对比表没有按档位买卖那一行():
    """[R441] 用户指着「按档位买卖 · 通道 +1.2% +11.8% -10.6% 1 次 ...」那一行: 「删除」。
    只删对比表那一行。(逐日表里通道的一笔笔动作 R444 随「通道档位」那一页一起撤了。)"""
    sec = code_of(SEC)
    assert "verdict_trades" not in sec and "按档位买卖" not in sec and "VERDICT_BASIS" not in sec
    assert "d.flip_trades" in sec


def test_R444_逐日复盘的字段与旧趋势状态页一致():
    """页头仍是旧「趋势状态」页那一句, 转折配对仍用同一份 `legsByFlipDate`。"""
    old, new = code_of(OLD), code_of(SEC)
    for t in ("{d.start} ~ {d.end} · {d.days} 个交易日",
              "` · 六态阈值 ${(d.threshold * 100).toFixed(0)}%${d.threshold_source !== 'default' ? `(${d.threshold_source})` : ''}`"):
        assert t in old and t in new, f"页头那一句与旧页对不上: {t}"
    assert "legsByFlipDate(d.flip_trades)" in new
    # 通道档位那一页、页签、并表时代的东西都不许回来
    for gone in ("VerdictTable", "只看换档的日子", "legsByFlipDate(d.verdict_trades)", "setTab(",
                 "TradeCells six=", "emptyText(", "ACT_TIP", "setShifted"):
        assert gone not in new, f"「{gone}」—— 用户只要趋势状态那套字段"


def _between(src: str, start: str, end: str, after: str = "") -> str:
    base = src.index(after) if after else 0
    i = src.index(start, base)
    return src[i:src.index(end, i) + len(end)]


def test_R442_换票复位():
    dlg = code_of(DLG)
    call = dlg[dlg.index("<ReviewSection"):dlg.index("/>", dlg.index("<ReviewSection"))]
    assert "key={symbol}" in call


def test_R749_只剩三块_页签与三视图都撤了():
    """用户: 「越搞越复杂了, 推翻整个复盘」—— 打开复盘不用再先选页签。"""
    sec = code_of(SEC)
    for fn in ("function Conclusion", "function EquityChart", "function DailyTable"):
        assert fn in sec, f"三块里少了 {fn}"
    for gone in ("setView(", "PILL", "ReviewCalendar", "DistPanel", "StateHistory", "TradeBars",
                 "NowCondition", "FlipStats", "HeatCell", "MiniBox", "VerdictStrip"):
        assert gone not in sec, f"「{gone}」—— 页签/三视图那一套又回来了"


def test_R749_逐日就是五列():
    sec = code_of(SEC)
    assert "grid grid-cols-[64px_minmax(0,1fr)_64px_56px_76px]" in sec, "逐日不是五列"
    for head in (">日期<", ">状态<", ">涨跌<", ">动作<", ">结果<"):
        assert head in sec, f"逐日表少了「{head[1:-1]}」这一列"


def test_R749_结果只在卖出那天落账():
    """用户: 「我表示看不懂」——
    以前买入那天就摆出这一笔的最后收益, 中间每天都跟着重复同一个数,
    卖出那天摆的反而是空头段的涨跌(跌了反而是好事)。现在只在卖出那天落账,
    与上面「每笔平均」同一口径。"""
    sec = code_of(SEC)
    assert "closed.get(leg.enter_date)" in sec
    assert "openBuy.has(leg.enter_date)" in sec
    assert "legResultCls" not in sec and "LegResult" not in sec, "又用回了按段取的那套结果"


def test_R749_权益曲线同起点同终点_灰底是空仓_圆点是买卖():
    sec = code_of(SEC)
    assert "curveOf(" in sec
    assert "hold *= r.close / base" in sec and "strat *=" in sec, "两条线不是同一段逐日净值"
    assert "r.close / origin" in sec, "曲线没从第一笔成交那天起算, 末端读数会跟结论条对不上"
    # [R750] 六态底色换成空仓灰底 —— 统计上差额来自空仓躲跌, 不是买卖点。
    assert "STATE_SHADE" not in sec, "六态底色又铺回来了"
    assert "flat: started && !inMarket" in sec and "fillOpacity={0.1}" in sec, "空仓灰底没铺上"
    assert "p.act === '买入' ? 'text-bull' : 'text-bear'" in sec, "买卖圆点没了"


def test_R750_规律与厚尾提醒都在结论之后():
    """统计量出来的三件事必须出现在页面上: 状态指不了方向、差额靠空仓、收益靠少数大赢家。"""
    sec = code_of(SEC)
    assert "forwardByState(d.rows ?? [], 5)" in sec, "六态之后的分布没接上"
    assert "function StateForward" in sec
    assert "其中 " in sec and "天空仓" in sec, "结论条没把空仓那段归因写出来"
    assert "去掉最好的" in sec and "trimmed" in sec, "厚尾提醒没跟数字一起摆出来"
    assert "中位" in sec, "右偏的收益还在用均值当主读数"
    # 规律模块要在结论之后、逐日之前
    assert sec.index("<Conclusion") < sec.index("<StateForward") < sec.index("<EquityChart")
