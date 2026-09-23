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


def test_R441_对比表没有按档位买卖那一行():
    """[R441] 用户指着「按档位买卖 · 通道 +1.2% +11.8% -10.6% 1 次 ...」那一行: 「删除」。
    只删对比表那一行; 逐日表里通道的一笔笔动作是旧表原有内容, 留着(R440)。"""
    sec = code_of(SEC)
    summary = sec[sec.index("function SummaryCard"):sec.index("function SystemRow")]
    assert "verdict_trades" not in summary and "按档位买卖" not in summary and "VERDICT_BASIS" not in sec
    assert "{ name: '按转折买卖 · 六态', ft: d.flip_trades, basis: FLIP_BASIS }" in summary
    assert "legsByFlipDate(d.verdict_trades)" in sec, "逐日表里通道那一笔笔动作不该跟着删"


def _strip_class(src: str) -> str:
    """去掉所有 className=...(字符串或花括号表达式), 再把空白压成一格 —— 剩下的就是「内容」"""
    out, i = [], 0
    while True:
        j = src.find("className=", i)
        if j == -1:
            out.append(src[i:])
            break
        out.append(src[i:j])
        k = j + len("className=")
        if src[k] == '"':
            k = src.index('"', k + 1) + 1
        else:                                   # {...}: 按花括号配对, 模板串里的 ${} 也成对
            depth = 0
            while True:
                c = src[k]
                depth += c == "{"
                depth -= c == "}"
                k += 1
                if depth == 0:
                    break
        i = k
    flat = re.sub(r"\s+", " ", "".join(out))
    # code_of 去掉 JSX 注释 {/* ... */} 后会留下一个孤立的「}」, 两边都清掉
    flat = re.sub(r"(?<= )\}(?= )", "", flat)
    flat = re.sub(r"\s+", " ", flat)
    return re.sub(r"\s+(/?>)", r"\1", flat)


def _between(src: str, start: str, end: str, after: str = "") -> str:
    base = src.index(after) if after else 0
    i = src.index(start, base)
    return src[i:src.index(end, i) + len(end)]


def _pieces(src: str, view: str) -> list[str]:
    """一页逐日表的三样: 筛选开关、表、脚注"""
    button = _between(src, "<button", "</button>", after=view)
    table = _between(src, "<table", "</table>", after=view)
    tail = src[src.index("</table>", src.index(view)):]
    foot = tail[tail.index("<div"):tail.index("</div>", tail.index("<div")) + len("</div>")]
    return [_strip_class(x) for x in (button, table, foot)]


def test_R442_逐日复盘是旧两张表_去掉样式后逐字一样():
    """[R442] 用户: 「逐日复盘并没有和之前一模一样」(之前一句: 「可以保留样式, 但是内容必须和
    以前一模一样, 不多也不少」)。R431 并过表, R440 只换回了原话, 并表本身多出了东西。
    现在是旧的两张表、页签切换: 两张表连同各自的筛选开关、脚注, 去掉 className 后必须与旧页逐字一样。"""
    old, new = code_of(OLD), code_of(SEC)
    for old_view, new_view in (("function TrendView(", "function TrendTable("),
                               ("function VerdictView(", "function VerdictTable(")):
        for o, n in zip(_pieces(old, old_view), _pieces(new, new_view)):
            assert o == n, f"{new_view} 与旧页不一样:\n新: {n}\n旧: {o}"
    # 两页的数据源与旧页一样: 趋势那页吃按转折买卖、通道那页吃按档位买卖
    assert "legsByFlipDate(d.flip_trades)" in new[new.index("function TrendTable("):new.index("function VerdictTable(")]
    assert "legsByFlipDate(d.verdict_trades)" in new[new.index("function VerdictTable("):]
    # 筛选与旧页同一个判据
    assert "r.limit_up || r.limit_down || r.broken_limit_up || r.trend?.flipped" in new
    assert "const rows = onlyMarked ? d.rows.filter((r) => r.verdict_flipped) : d.rows" in new
    # 页签、页头那一行与旧页同一句
    for t in ("([['trend', '趋势状态'], ['verdict', '通道档位']] as const)",
              "{d.start} ~ {d.end} · {d.days} 个交易日",
              "{tab === 'trend' && ` · 六态阈值 ${(d.threshold * 100).toFixed(0)}%${d.threshold_source !== 'default' ? `(${d.threshold_source})` : ''}`}",
              "initialTab === 'trend' ? 'trend' : 'verdict'"):
        assert t in old and t in new, f"「{t}」与旧页对不上"
    # 并表时代的东西不许回来
    for gone in ("TradeCells six=", "[['六态', six], ['通道', ch]]", "emptyText(", "ACT_TIP", "setShifted"):
        assert gone not in new, f"「{gone}」是并表时的东西"


def test_R442_换票复位_先看哪一页跟着入口():
    dlg = code_of(DLG)
    call = dlg[dlg.index("<ReviewSection"):dlg.index("/>", dlg.index("<ReviewSection"))]
    assert "key={symbol}" in call and "tab={reviewTab}" in call
