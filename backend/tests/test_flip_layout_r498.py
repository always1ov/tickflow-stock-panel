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
[R512] 之后改成分栏(用户: 「模拟盘的内容分类整理成图片这样的表达方式」): 规则有了自己一栏、
不再折叠; 成绩独占一栏, 六格回到一行。对应的几条在本文件里改了钉法, 注释写着 R512。
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
    """筛选条(板块/门槛/体检)只影响信号的先后与标注 —— 它该贴着信号, 不该隔着一张成绩卡。

    [R512] 分栏之后: 筛选条与信号同在「今日信号」一栏, 默认打开的就是这一栏。
    """
    jsx = _jsx()
    blk = jsx[jsx.index("{tab === 'signals' && ("):jsx.index("{tab === 'holdings'")]
    i_ctrl = blk.index("<TodayControls d={ov}")
    i_sig = blk.index("<TodaySignals")
    assert i_ctrl < i_sig, "信号要紧跟在筛选条后面"
    between = blk[i_ctrl:i_sig]
    for x in ("<Summary", "<ParamBar", "<MonthStrip", "results"):
        assert x not in between, f"筛选条与信号之间插进了 {x}"
    assert "usePageTab(FLIP_TABS, 'signals')" in code_of(FLIP), "默认打开的不是今日信号"


def test_R500_持仓是小卡片_电脑手机同一套():
    """用户: 「用小卡片显示」「或者小长方条, 你决定哪个好」—— 持仓用小卡片:
    几只到十来只, 每只最要紧的是浮盈那一个数, 卡片把它放大。"""
    h = _fn("Holdings")
    assert "<table" not in h, "持仓还是表格"
    assert "sm:hidden" not in h, "还留着手机与宽屏两套 —— 小卡片是同一套"
    assert '<div className="grid gap-2 p-3 sm:grid-cols-2 2xl:grid-cols-3">' in h
    # 同一份数据、同一套字段 —— 一个都不能少
    for field in ("pct(p.pnl_pct)", "holdingDays.get(p.symbol)", "p.shares.toLocaleString()",
                  "p.cost?.toFixed(2)", "p.last.toFixed(2)", "money(p.market_value)"):
        assert field in h, f"卡片丢了一个字段: {field}"
    assert "onOpen(p.symbol)" in h, "点卡片不能打开这只票"
    assert "rounded-btn" in h and "rounded " not in h, "卡片圆角走规范 token, 不写裸圆角"
    assert "transition-all" not in h


def test_R500_流水是小长方条_按时间一条一行_宽屏两栏列优先():
    """几十笔按时间读 —— 一笔一条, 从上往下就是时间线; 两栏用 columns(列优先), 不用 grid(行优先会打乱先后)。"""
    o = _fn("Orders")
    assert "<table" not in o, "流水还是表格"
    assert "xl:columns-2" in o and "break-inside-avoid" in o, "宽屏没排成两栏 / 一条会被拆到两栏"
    assert "grid-cols" not in o, "两栏用了 grid —— 行优先会把时间顺序打乱"
    for field in ("o.date", "o.delayed", "o.signal_date", "o.reason", "o.state_cn", "o.price.toFixed(2)",
                  "money(o.amount)", "<OrderActBadge act={o.act}"):
        assert field in o, f"条子丢了一个字段: {field}"
    # 默认条数仍按屏宽: 手机 10、宽屏 30 —— 只渲染一份, 第 11 笔起在窄屏收起
    assert "rows.slice(0, 30)" in o and "!all && i >= 10 ? 'hidden sm:flex' : 'flex'" in o
    assert "rows.length > 30 &&" in o and "rows.length > 10 &&" in o
    assert "shownPhone" not in o, "又回到两套 DOM 了"


def test_R512_规则有自己一栏_不再折叠():
    """R498 把规则默认收起, 理由是它压在长页面底下、一个月看不了一次。
    [R512] 分栏之后它有了自己一栏, 不点那一栏就不占地方, 折叠壳和记住展开状态的那条偏好一起删了。"""
    code = code_of(FLIP)
    assert "function RulesFold(" not in code and "<RulesFold" not in code, "折叠壳还在"
    assert "flipRulesOpen" not in code_of("lib/storage.ts"), "只为折叠壳服务的偏好还在"
    jsx = _jsx()
    blk = jsx[jsx.index("{tab === 'rules' && rules.data && ("):]
    blk = blk[:blk.index("</section>")]
    assert '<SectionHead title="规则"' in blk and "<Rules r={rules.data} d={d} />" in blk


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
    # [R512] 「手上这些」改名「持仓」, 与分栏同名
    code = code_of(FLIP)
    bar = code[code.index("持仓<span"):]
    bar = bar[:bar.index("</button>")]
    assert '<span className="hidden sm:inline"> · 跌破离场线才清仓</span>' in bar, \
        "后半句在窄屏没收掉 —— 右边那两个数会被挤成竖排"
    assert "whitespace-nowrap" in bar, "右边那两个数会被拆行"
    assert "手上这些" not in code, "旧名还在渲染"


def test_R512_成绩独占一栏_六格回到一行():
    """R498 时成绩卡只有半幅宽, 六格一行会把「2026-09-23」截成两行, 所以半幅排 2~3 列。
    [R512] 成绩独占一栏、整行宽, 那几档半幅断点删掉, 六格从 lg 起回到一行。
    骨架跟着同一套断点走(不然数据到位时版面跳一下)。"""
    code = code_of(FLIP)
    cls = "grid grid-cols-2 divide-x divide-y divide-border/30 overflow-hidden rounded-card border"
    rows = [code[i:code.index('">', i)] for i in range(len(code)) if code.startswith(cls, i)]
    assert len(rows) == 2, "六格与它的骨架该各有一排"
    for row in rows:
        assert "sm:grid-cols-3 lg:grid-cols-6 lg:divide-y-0" in row, row
        for gone in ("xl:grid-cols-2", "xl:divide-y", "min-[1800px]"):
            assert gone not in row, f"半幅那一档还在: {gone}"


def test_R499_有信号但没做成不再放出来():
    """用户: 「有信号没做成的就不要放出来了」。**只撤页面上那一块, 后端照旧算** ——
    skipped / missing / pending 三个字段还在接口里(模拟盘的成交顺延靠它们), 只是这一页不画。"""
    code = code_of(FLIP)
    assert "有信号但没做成" not in code, "那一块又放出来了"
    assert "function Skipped(" not in code and "<Skipped" not in code
    assert "WHY_CN" not in code and "hasSkipped" not in code, "撤干净 —— 留着没人用的翻译表会骗人"
    api = code_of("lib/api.ts")
    assert "skipped: FlipSkipped[]" in api, "接口字段不该跟着删 —— 只是页面不显示"


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
