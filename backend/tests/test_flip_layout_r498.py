"""[fork R498] 转折页重新排版 —— 不动数据, 只改表达。

用户: 「先这样保守的改, 每个页面里面的东西重新排版。不动数据, 只考虑怎么改表达。
我们一页一页的改。先分析这一页有什么东西, 然后生成一张图片, 确定了再动手改」,
看过现状与三种排法(今天优先 / 驾驶舱 / 标签页)的效果图后: 「按照页面来设计一个
页面来搞定」—— 选的是单页、今天优先那一种。

实测的毛病(效果图上那几处)与这里钉住的改法:
  · 电脑首屏一半被「筛选 + 参数 + 逐月 + 六格」占掉 → 信号紧挨筛选条, 成绩挪到持仓旁边;
  · 手机上持仓表、流水表向右截断(浮盈、成交价、金额整列看不到) → 手机改成两行卡片;
  · 手机上「今天该挂什么单」被说明挤成两行、「手上这些」那一行右边的数被挤成竖排;
  · 「这套规则」一个月看不了一次, 一直占着页面底部 → 默认收起。
版面顺序、成绩卡不挂在打分那一层下面、参数条不跟着成绩消失这几条, 在
test_flip_fusion.py 的 R343 / R358 / R359 / R381 那几条里(随本次一起改了钉法)。
"""
from __future__ import annotations

from tests.frontend_source import code_of

FLIP = "pages/FlipPaper.tsx"


def _fn(name: str) -> str:
    code = code_of(FLIP)
    i = code.index(f"function {name}(")
    j = code.find("\nfunction ", i + 1)
    j2 = code.find("\nexport function ", i + 1)
    ends = [x for x in (j, j2) if x > 0]
    return code[i:min(ends)] if ends else code[i:]


def _jsx() -> str:
    code = code_of(FLIP)
    return code[code.index('return (\n    <div className="flex h-full flex-col">'):]


def test_R498_首屏给信号_筛选条后面紧跟着信号():
    """筛选条(板块/门槛/体检)只影响信号的先后与标注 —— 它该贴着信号, 不该隔着一张成绩卡。"""
    jsx = _jsx()
    i_ctrl = jsx.index("<TodayControls d={ov}")
    i_sig = jsx.index("<TodaySignals")
    i_res = jsx.index("{results}")
    assert i_ctrl < i_sig < i_res, "首屏又被成绩占了 —— 信号要紧跟在筛选条后面"
    between = jsx[i_ctrl:i_sig]
    for x in ("<Summary", "<ParamBar", "<MonthStrip", "{results}"):
        assert x not in between, f"筛选条与信号之间插进了 {x}"


def test_R498_手机上持仓是卡片_宽屏照旧是表格():
    h = _fn("Holdings")
    assert '<div className="divide-y divide-border/30 sm:hidden">' in h, "手机上没有卡片"
    assert '<div className="hidden overflow-x-auto sm:block">' in h, "表格没在手机上收起 —— 会向右截断"
    cards = h[h.index("sm:hidden"):h.index("hidden overflow-x-auto sm:block")]
    # 同一份数据、同一套字段 —— 卡片上一个都不能少
    for field in ("pct(p.pnl_pct)", "holdingDays.get(p.symbol)", "p.shares.toLocaleString()",
                  "p.cost?.toFixed(2)", "p.last.toFixed(2)", "money(p.market_value)"):
        assert field in cards, f"手机卡片丢了一个字段: {field}"
    assert "onOpen(p.symbol)" in cards, "手机卡片点了不能打开这只票"


def test_R498_手机上流水是卡片_默认10笔_宽屏照旧30笔():
    o = _fn("Orders")
    assert "rows.slice(0, 30)" in o and "rows.slice(0, 10)" in o
    cards = o[o.index('<div className="divide-y divide-border/30 sm:hidden">'):o.index("hidden overflow-x-auto sm:block")]
    assert "shownPhone.map" in cards, "手机卡片没用那 10 笔"
    for field in ("o.date", "o.delayed", "o.reason", "o.state_cn", "o.price.toFixed(2)", "money(o.amount)"):
        assert field in cards, f"手机卡片丢了一个字段: {field}"
    # 两个「展开全部」各管各的屏宽: 手机按 10 笔判断, 宽屏按 30 笔
    assert "rows.length > 30 &&" in o and "rows.length > 10 &&" in o
    assert "cursor-pointer sm:inline" in o and "cursor-pointer sm:hidden" in o, "两个展开按钮没按屏宽分开"


def test_R498_规则默认收起_记住展开状态_收起时不挂载():
    f = _fn("RulesFold")
    assert "storage.flipRulesOpen.get(false)" in f, "默认不是收起"
    assert "storage.flipRulesOpen.set(!v)" in f, "展开状态没记住"
    assert "{open && <div" in f and "<Rules r={r} d={d} />" in f, "收起时还挂着正文"
    assert "flipRulesOpen:" in code_of("lib/storage.ts")


def test_R498_规则折叠条与页上另外几条折叠长一个样():
    """同一页上几种折叠长几个样, 读的人要认几次。"""
    f = _fn("RulesFold")
    assert "open && 'rotate-180'" in f, "没沿用旋转的 ChevronDown"
    assert "duration-expand ease-smooth" in f, "旋转动效与另外几条不一致"
    assert "aria-expanded={open}" in f
    assert "transition-all" not in f, "只许过渡具体属性"


def test_R498_规则正文不带卡壳_不是卡中卡():
    r = _fn("Rules")
    assert "rounded-card" not in r and "<SectionHead" not in r, "卡壳和标题归折叠条, 正文里又来一份"
    # 七条口径一条不少(R381 的守卫钉着次序, 这里只确认搬家时没丢)
    for k in ("信号", "成交", "方向", "仓位", "标的", "不做空", "成本"):
        assert f'k="{k}"' in r


def test_R498_区块标题不被说明挤成两行():
    h = _fn("SectionHead")
    assert "shrink-0 whitespace-nowrap" in h, "标题会被说明挤成两行"
    assert "flex flex-wrap" in h, "放不下时说明没法落到下一行"


def test_R498_手上这些那一行在手机上不再挤成竖排():
    code = code_of(FLIP)
    bar = code[code.index("手上这些<span"):]
    bar = bar[:bar.index("</button>")]
    assert '<span className="hidden sm:inline"> · 跌破离场线才清仓</span>' in bar, \
        "后半句在窄屏没收掉 —— 右边那两个数会被挤成竖排"
    assert "whitespace-nowrap" in bar, "右边那两个数会被拆行"


def test_R498_成绩卡半幅时2列_1800起3列_整行时才6格():
    """xl 起成绩卡只有半幅宽。实测半幅里一行六格一格只剩一百二十来像素,
    21px 的「2026-09-23」被截成两行 —— 1440 与 1920 都是。"""
    code = code_of(FLIP)
    row = code[code.index('<section className="grid grid-cols-2 divide-x'):]
    row = row[:row.index(">")]
    for cls in ("lg:grid-cols-6", "xl:grid-cols-2", "xl:divide-y", "min-[1800px]:grid-cols-3"):
        assert cls in row, f"少了这一档: {cls}"
    assert "min-[1800px]:grid-cols-6" not in row, "半幅里一行六格会把日期截成两行"


def test_R498_没有第二块时不开两列():
    """跑不动时没有持仓、没有「没做成」时 —— 空着的那一栏等于白留一条缝。"""
    jsx = _jsx()
    assert "cn('grid gap-3', hasBody && 'xl:grid-cols-" in jsx
    assert "cn('grid gap-3', hasSkipped && 'xl:grid-cols-" in jsx
    code = code_of(FLIP)
    # 与 Skipped 自己的判据是同一条 —— 两处各写一份的话会一边说有一边不渲染
    assert "d.skipped.length > 0 || d.missing.length > 0" in code
    sk = _fn("Skipped")
    assert "if (!d.skipped.length && !d.missing.length) return null" in sk


def test_R498_逐月放不下时先露出最近的月份():
    """半幅宽时 13 个月横向滚动, 滚动条默认停在最左 —— 藏起来的恰好是最近几个月。"""
    m = _fn("MonthStrip")
    assert "useLayoutEffect(() => {" in m and "el.scrollLeft = el.scrollWidth" in m, "没滚到最近的月份"
    assert "ref={scrollRef}" in m and "overflow-x-auto" in m
    assert "scrollTo(" not in m and "behavior" not in m, "数据不加滚动动画, 瞬时定位"


def test_R498_板块按钮在手机上换行_不挤出屏幕():
    ctrl = code_of("components/today/TodayControls.tsx")
    i = ctrl.index("TODAY_BOARDS.map")
    row = ctrl[ctrl.rindex("<div className=", 0, i):i]
    assert 'className="flex flex-wrap items-center gap-g2"' in row, \
        "六个板块按钮一排在手机上放不下, 「北交所」会被挤出屏幕"
