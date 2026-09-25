"""[R343] 今日总览**融合进**模拟盘已有的卡片 —— 不新增任何区块。

用户: 「我的意思是融合进前面的卡片, 比如值得关注应用了评分系统的, 拿今天动手
是否可以排个序?类似这样的融合升级」。

R341 那一版做的是**挂一条补充带在底部**, 方向错了: 那还是"今日总览换了个位置",
不是融合。这一版把每一样东西都落进已有的位置, 补充带整个拆掉:

    市场状态  → 页头(姿态徽章 + 多空比 进副标题; 主线 R506 搬去宏观分析页)
    AI 导读   → 页头一个按钮, 正文展开在页面顶部
    数据自检  → 页面最顶, 不进任何折叠
    值得关注  → 「今天该挂什么单」里 —— 有转折的当排序键, 没转折的进折叠区

**判据的界线没有因为融合而变松, 反而更紧了**: R341 是靠"另开一块并写明来源"
划界, 这一版是靠**结构** —— 合成出来的打分候选行 `act` 由构造决定恒为 `null`,
它在结构上不可能成为一个动作。
"""
from __future__ import annotations

import re

from tests.frontend_source import code_of

FLIP = "pages/FlipPaper.tsx"
HEALTH = "components/today/TodayHealthBar.tsx"
HOOK = "lib/useSharedQueries.ts"


def _flip() -> str:
    return code_of(FLIP)


def _signal_row() -> str:
    """[R513] 行级组件的源码。原来是一个 `SignalRow`; R513 起三段各一种长相 ——
    要动手的卡片 / 持仓方块 / 盯着的密排行, 加上三者共用的标的按钮、六态那句、价格那行。
    截到下一个顶层 `function`(不按 `\n}` 截: 剥注释后跨行注释的收尾会留下裸 `}`)。"""
    code = code_of(FLIP)
    out = []
    for name in ("ActionCard", "HoldingTile", "WatchGroup", "SymbolButton", "StateLine", "PriceLine"):
        blk = code[code.index(f"function {name}("):]
        nxt = blk.find("\nfunction ", 1)
        out.append(blk if nxt < 0 else blk[:nxt])
    return "\n".join(out)


def _fn(name: str) -> str:
    code = code_of(FLIP)
    blk = code[code.index(f"function {name}("):]
    nxt = blk.find("\nfunction ", 1)
    return blk if nxt < 0 else blk[:nxt]


# ── 底线: 六态选, 打分排 ────────────────────────────────────────────────
def test_R344_名单只由六态选_前端不合成任何一行():
    """**这是整组的地基。**

    用户: 「我的本意是不看我的自选了, 打分系统针对六态选出来的进行二次排序」。

    R343 那一版往名单里塞了「打分候选」—— 打分选出来但六态没选中的票。方向是反的:
    **那正是"打分自己选票"**, 而这套系统里选票这件事只归六态。打分的位置在它后面,
    不在它旁边。
    """
    code = _flip()
    assert "<TodaySignals rows={d.today ?? []}" in code, \
        "名单必须原样来自后端那份六态信号"
    for banned in ("scoreOnly", "打分候选"):
        assert banned not in code, f"前端又在合成名单: {banned}"
    # **打分那份数据只准用来查分, 不准用来造行。** 不能简单地禁掉
    # `opportunities` —— 查分本来就要读它; 钉的是"只在建把握分索引那一处出现"。
    assert code.count("opportunities") == 1, \
        "opportunities 出现在不止一处 —— 多出来的那处多半又在拿它造行"
    conv = code[code.index("const conv = useMemo("):code.index("}, [ov])")]
    assert "opportunities" in conv, "唯一那处必须是建把握分索引的地方"


def test_R344_四档内部都按打分重排():
    """打分是**第二段**, 对六态选出来的**每一段**都生效 —— 不是只管其中一段。
    [R513] 盯着那一段按转多 / 转空再分两组, 两组各自照样走 byRank。"""
    code = _flip()
    i = code.index("const rank = (r: FlipTodaySignal)")
    blk = code[i:code.index("return (", i)]
    assert blk.strip(), "切出来是空的, 下面的断言就全是摆设"
    assert "const byRank = (rs: FlipTodaySignal[]) => rs.slice().sort((a, b) => rank(a) - rank(b))" in blk, \
        "排序得是一处实现 —— 各段各写一遍必然漂"
    for tier in ("const ordered = byRank(live)",
                 "const mineSorted = byRank(mine)",
                 "const toBull = byRank(idle.filter(",
                 "const toBear = byRank(idle.filter("):
        assert tier in blk, f"这一段没参与二次排序: {tier}"


def test_R344_打分不参与分档():
    """**界线。** 四档的边界只由六态定, 打分一分都不许掺和。"""
    code = _flip()
    pred = next(l for l in code.splitlines() if "const isLive =" in l)
    for word in ("conviction", "rank", "score", "把握"):
        assert word not in pred, f"分档判据里混进了打分: {word}"
    # 「手上这些」与「只是盯着」的边界是 held, 也不许沾打分
    for line in ("const mine = rest.filter((r) => r.held)",
                 "const idle = rest.filter((r) => !r.held)"):
        assert line in code, f"分档判据被动过: {line}"


def test_R344_只重排不增删():
    code = _flip()
    assert "rs.slice().sort(" in code, "少了 slice() —— sort 是就地改, 会改到上游 props"
    assert "?? Number.MAX_SAFE_INTEGER" in code, "拿不到名次的排本档末尾, 不是被丢掉"


# ── 融合: 不新增区块, 补充带已拆 ────────────────────────────────────────
def test_R343_补充带已经拆掉():
    """融合的标准就是**不新增区块** —— 留着那条带子等于没融合。"""
    import pathlib
    from tests.frontend_source import SRC
    assert not pathlib.Path(SRC / "components/today/TodayDigest.tsx").exists(), \
        "TodayDigest 还在 —— 它的内容已经并进各处卡片了"
    assert "TodayDigest" not in _flip()


def test_R343_模拟盘原有六块的顺序没被动过():
    code = _flip()
    body = code[code.index("export function FlipPaper"):code.index("function TodaySignals")]
    # [R358] `<Summary>` 与 `<NavChart>` 从这串里出列了 —— **不是被删掉**:
    # 用户把它们并进了筛选那张卡(「我是想合并到筛选的卡片里面」), `Summary`
    # 现在走 `extra={summary}` 这个插槽, `NavChart` 则收进 `Summary` 里的折叠区。
    # 它们各自的守卫在 `test_R358_*`。这里只管**留在主列里的那几块**次序没乱。
    # [R381] **`<Skipped>` 与 `<Orders>` 对调了一次, 是有意的。**
    #
    # 用户: 「模拟盘页面的内容需要重新排版, 合理利用显示空间」。宽屏上「现在拿着」
    # 与「成交流水」并排之后, 左列只装一块会空掉一大截(拿着 6 只 vs 流水 30 笔),
    # 所以「没做成」收进左列 —— 而左列是一个容器, 容器里的东西在 DOM 里必须连着。
    #
    # 先试过「不动 DOM, 用 col-start/row-start 摆位」, 结果右列 row-span-2 把第一行
    # 撑高、左列两块中间裂开一道四百像素的缝(跨行元素的多余高度怎么分摊不听我的)。
    #
    # **单列时的顺序因此变成 拿着 → 没做成 → 流水。** 这个代价是划算的: 「没做成」
    # 是一句话的小结, 「流水」是几十行的长表, 短的放前面本来就更好读。
    #
    # 真正有讲究的那一条**没动**: 「规则排在最后」—— 它是查证用的, 不该天天占首屏。
    # [R498] **又排了一次, 是用户选的。** 「先这样保守的改, 每个页面里面的东西重新
    # 排版」, 看过三种排法的效果图后选了「一个页面来搞定」(今天优先):
    #     信号 → [持仓 | 成绩(参数 + 六格 + 逐月 + 净值)] → [流水 | 没做成] → 规则(收起)
    # 成绩从筛选卡的插槽上搬下来, 成了主列里的一块(`{results}`); 「没做成」挪到
    # 流水右边。**「规则排在最后」那一条仍然没动。**
    # 只在 JSX 里数 —— `results` 那张卡的定义在前面, 那里的 `<ParamBar` 不算版面顺序
    jsx = body[body.index("return (\n    <div className=\"flex h-full flex-col\">"):]
    # [R499] 「有信号但没做成」整块撤掉了(用户: 「有信号没做成的就不要放出来了」)
    # [R512] **一页摞五块改成五栏**(用户指着 Minds 的分栏: 「模拟盘的内容分类整理成图片这样的
    # 表达方式」)。顺序的意思没变, 只是从「从上往下」变成「从左往右」: 分栏条的次序与 JSX 里
    # 各栏出现的次序都得是 信号 → 持仓 → 成绩 → 流水 → 规则, 规则仍在最后。
    order = ["tab === 'signals'", "tab === 'holdings'", "tab === 'results'", "tab === 'orders'", "tab === 'rules'"]
    idx = [jsx.index(t) for t in order]
    assert idx == sorted(idx), f"版面顺序被动过: {order}"
    assert jsx.index("tab === 'rules'") == max(idx), "「规则排在最后」这一条被动了"
    tabs = re.findall(r"^  (\w+): \{ title: '", code[code.index("FLIP_TABS"):code.index("export function FlipPaper")], re.M)
    assert tabs == ["signals", "holdings", "results", "orders", "rules"], f"分栏条次序被动过: {tabs}"
    assert "<NavChart" not in body, "净值图该在 Summary 的折叠区里, 不在主列"


def test_R343_市场状态并进页头_不自己占一张卡():
    code = _flip()
    head = code[code.index("<PageHeader"):code.index("<div className=\"min-h-0 flex-1")]
    assert "titleExtra={w && (" in head, "姿态是结论, 该在标题旁边"
    assert "POSTURE_TONE[w.posture]" in head
    # [R345] 副标题从模板串改成了 JSX —— **多空要分红绿**。并进页头时我一度把
    # 整行压成一条灰字: 数字还在, 但「多 81 / 空 90」这种对照**靠颜色才读得快**,
    # 全灰之后得逐字读完才知道哪边多。配色沿用今日总览那张卡的语义。
    assert '多 <span className="text-bull">{w.bull}</span>' in head, "多头数没上红"
    assert '空 <span className="text-bear">{w.bear}</span>' in head, "空头数没上绿"
    assert '转多 <span className="text-bull">{w.new_bull}</span>' in head
    assert '转空 <span className="text-bear">{w.new_bear}</span>' in head
    # [R346] 主线要上色 / [R421] 琥珀 / 停更变灰改标题 —— [R506] 主线整个搬去了宏观分析页
    # 的「现在」卡(用户: 「转折页面的那个显示主线我想搬回这里」), 那三条规矩跟着搬过去,
    # 由 test_macro_mainline_r506.py 接着守。这里只钉「页头不再有它」。
    assert "主线" not in head, "主线已经搬去宏观分析页, 转折页页头又出现了"
    # [R352] 「AI 导读」那个按钮删了(用户: 「这部分和 ai 导读都不用了」) ——
    # 这一条因此只守市场状态那部分。**顺手钉住它真的没了**, 免得哪天又被加回来
    # 却没人记得当初为什么删。
    assert "AI 导读" not in code_of(FLIP), "AI 导读已经删了, 不该再出现"


def test_R343_自检条在最顶且不进折叠():
    """「你正在看的数字是几天前的」这句话被折起来就失去了全部意义。"""
    code = _flip()
    assert "{!!ov?.health && <TodayHealthBar h={ov.health} />}" in code
    i_bar = code.index("<TodayHealthBar h=")
    i_signals = code.index("<TodaySignals")
    assert i_bar < i_signals, "自检条必须排在所有内容之前"


def test_R343_自检条一处实现_两页共用():
    """同一个自检条两处各写一遍, 措辞和口径必然漂。"""
    assert "export function TodayHealthBar" in code_of(HEALTH)
    code = code_of(FLIP)
    assert "from '@/components/today/TodayHealthBar'" in code, "模拟盘没复用那一处"
    assert "function TodayHealthBar" not in code, "模拟盘自己又写了一份"


# ── 一处定义 ────────────────────────────────────────────────────────────
def test_R343_今日总览那份数据只有一处定义():
    """同一份数据两种刷新节奏的表现是「两个页面上同一个数字不一样」, 而两边看上去
    都"没坏", 查起来极痛苦。"""
    hook = code_of(HOOK)
    blk = hook[hook.index("export function useTodayOverview"):]
    blk = blk[:blk.index("\n}")]
    assert "queryKey: QK.todayOverview" in blk
    assert "refetchInterval: (query) =>" in blk, "刷新间隔不是按状态算的函数"
    assert "?.live" in blk and "inRealtimeWindow()" in blk, "两件事要同时看"
    assert "60_000" in blk and "60 * 60 * 1000" in blk, "两档节奏不全"

    code = code_of(FLIP)
    assert "useTodayOverview()" in code, "模拟盘没走共用 hook"
    assert "queryKey: QK.todayOverview" not in code, "模拟盘自己又抄了一份查询"


def test_R343_模拟盘主查询没被动过():
    """用户: 「模拟盘现在有的东西都不能动了」。"""
    code = _flip()
    blk = code[code.index("const q = useQuery({"):code.index("const rules = useQuery({")]
    assert "refetchInterval: refreshEvery('derived')" in blk, "模拟盘主查询的节奏被动了"
    assert "todayOverview" not in blk, "今日总览的数据不该混进模拟盘主查询"


# ── [R345] 「名次」那一格整格移植 ───────────────────────────────────────
#
# 用户: 「这一列要移植」(截图是今日总览机会表的「名次」列: 名次/总数 + 把握分 +
# 三条维度条)。**不是只搬个数字** —— 那三条颜色才是它能被读懂的原因: 离开它们,
# 上面那个名次就只是个号码, 说不出"为什么是这个名次"。


def _cell() -> str:
    return code_of("components/today/ScoreCell.tsx")


def test_R345_名次那一格是一处实现_两页共用():
    """三条维度条的颜色、权重、悬停解释两处各写一遍, 哪天权重改了必然漂 ——
    而漂的表现是「两个页面对同一只票给出不同的说法」, 看上去两边都没坏。"""
    cell = _cell()
    assert "export function ScoreCell" in cell
    assert "export const DIM_META" in cell, "维度元数据也得跟着走, 否则还是两份"
    # [R351] 机会表随今日总览一起删了 —— 现在只剩模拟盘一个调用方
    code = code_of(FLIP)
    assert "from '@/components/today/ScoreCell'" in code, "模拟盘没复用那一处"
    assert "function ScoreCell" not in code, "模拟盘自己又写了一份"


def test_R345_三条维度条跟着一起搬():
    """只搬名次不搬维度条 = 搬了个号码过来。"""
    cell = _cell()
    for key, cls in (("trend", "bg-red-400"), ("volume", "bg-sky-400"), ("position", "bg-amber-400")):
        assert key in cell and cls in cell, f"少了维度 {key} 或它的颜色 {cls}"
    # 权重锚在**它真正露面的两处**: `what` 文案 + 悬停里那条公式。
    # 原来还有个 `w: '45%'` 字段, 全项目没人读 —— 变异把它改空界面一个字没变,
    # 那不是守卫有洞, 是那份数据本来就是死的(已删)。
    assert "权重 45%" in cell and "权重 30%" in cell and "权重 25%" in cell, "维度说明里少了权重"
    assert "趋势强度×45% + 量能确认×30% + 位置成本×25%" in cell, "悬停里那条公式没了"
    assert "w: '" not in cell, "又冒出一个没人读的权重字段"
    assert 'style={{ width: `${Math.max(3, Math.min(100, v))}%` }}' in cell, \
        "条长必须按分数画 —— 画成固定长度就只是装饰"


def test_R345_模拟盘行上用的就是那一格():
    # [R513] 名次那一格整格(带三条维度条)留在要动手的卡片上
    assert "<ScoreCell o={c} rank={c.rank} total={c.rank_total ?? 0} />" in _fn("ActionCard")


def test_R345_打分那份数据整条存着_不再只留几个字段():
    """三条维度条要 `dims`, 悬停要 `pct_rank` —— 只留分数与名次画不出来。"""
    code = code_of(FLIP)
    assert "new Map<string, TodayOpportunity>()" in code
    assert "m.set(o.symbol, o)" in code, "存整条, 不再挑字段"


# ── [R347] 门槛 / 体检 / 板块筛选 ───────────────────────────────────────
#
# 用户: 「门槛的东西非常重要, 体检和筛选功能也要能保留」。


CTRL = "components/today/TodayControls.tsx"


def test_R347_三样东西一处实现_两页共用():
    """近 260 行的一组控件, **手抄一遍必漂** —— 板块过滤的乐观值、门槛的分位口径、
    AI 定时那两个开关的文案, 任何一处改了另一处不改, 表现就是「两个页面对同一个
    设置说法不一样」, 而两边都不报错。"""
    ctrl = code_of(CTRL)
    assert "export function TodayControls" in ctrl
    # [R351] 今日总览删了 —— 从此只剩模拟盘一个调用方。**立论反而更要紧**:
    # 唯一的实现一旦被谁复制一份, 再也没有"另一页"会把它暴露出来。
    code = code_of(FLIP)
    assert "<TodayControls d=" in code, "模拟盘没挂上这组控件"
    assert "from '@/components/today/TodayControls'" in code
    assert "TODAY_BOARDS" not in code, "模拟盘自己又写了一份板块筛选"
    assert "ScoreLedgerDialog" not in code, "模拟盘自己又挂了一份体检弹窗"


def test_R347_三样都在():
    """门槛、体检、板块筛选 —— 少一样这次改动就没做完。"""
    ctrl = code_of(CTRL)
    assert "TODAY_BOARDS.map" in ctrl, "板块筛选没了"
    assert "<ScoreLedgerDialog" in ctrl, "体检弹窗没了"
    # **锚在真正干活的那一处, 不是标识符**: `min_hist_pct` 在这文件里出现七次
    # (toast 文案、显示值、比较……), 拿它当锚等于没有锚 —— 变异把滑块改坏照样绿。
    # 这是这个仓库第四次栽在"锚太宽"上(R310/R333/R345)。
    assert 'type="range" min={0} max={90} step={5}' in ctrl, "门槛那个滑块没了"
    assert "prefsMut.mutate({ min_hist_pct: minPct })" in ctrl, "滑块松手不落库"
    # [R133] 门槛旁边就是体检 —— 这个相邻关系是设计的一部分, 不是排版巧合。
    # 按两个按钮各自的图标定位: 文案「体检」也出现在 title 里, 拿它排序会误判。
    assert ctrl.index("<BarChart3") < ctrl.index("<SlidersHorizontal"), \
        "体检(BarChart3)必须排在门槛(SlidersHorizontal)前面"


def test_R347_板块过滤在后端做():
    """前端筛的话会漏掉被 max_show 截掉的票 —— 你看到的"主板机会"是残缺的,
    **而你不会知道**。"""
    ctrl = code_of(CTRL)
    assert "prefsMut.mutate({ boards: next })" in ctrl, "板块必须落库让后端筛"
    assert "boardFilter.filter" in ctrl, "多选的加减逻辑没了"
    # 乐观值这一层有三处才完整: 声明 / 点下去立刻亮 / 落库或失败后撤回。
    # 只断言标识符存在的话, 删掉"立刻亮"那一处照样绿 —— 而那正是它存在的理由
    # (不亮就看起来像"点了没反应", 用户会重复点)。
    assert "setBoardDraft(next)" in ctrl, "点下去没有立刻亮 —— 乐观值这层白加了"
    assert ctrl.count("setBoardDraft(null)") >= 2, "落库成功与失败两条路都要撤回乐观值"


def test_R347_控件只作用于打分层_不碰六态名单():
    """**界线。** 门槛/筛选改的是谁拿得到名次, 不是谁在名单上。"""
    code = code_of(FLIP)
    # 名单仍然只来自后端那份六态信号
    assert "<TodaySignals rows={d.today ?? []}" in code
    # 控件吃的是今日总览那份数据, 与模拟盘主查询无关
    assert "<TodayControls d={ov}" in code, "控件必须挂在今日总览那份数据上"
    blk = code[code.index("const q = useQuery({"):code.index("const rules = useQuery({")]
    assert "prefs" not in blk and "boards" not in blk, "模拟盘主查询不该沾这些偏好"


# ── [R349] 「走势」那一格 ───────────────────────────────────────────────
#
# 用户: 「这一列也要有」(截图是今日总览机会表的「走势」列)。


TREND = "components/today/TrendCell.tsx"


def test_R349_走势那一格一处实现_两页共用():
    """「多少算多」的分界一旦抄成两份, **屏幕说「放量刚好」而导出说「量太大」**
    的那天就没法查了 —— R212 立的就是这条规矩。"""
    cell = code_of(TREND)
    assert "export function TrendCell" in cell
    assert "export function posWord" in cell and "export function volWord" in cell, \
        "分界函数得跟着组件走, 否则还是两处"
    # [R351] 机会表与那份 HTML 导出件都随今日总览一起删了 —— 转口导出那一层
    # 因此也没了(它当初存在的唯一理由就是不改导出件的 import)。
    code = code_of(FLIP)
    assert "from '@/components/today/TrendCell'" in code, "模拟盘没复用那一处"
    assert "function TrendCell" not in code, "模拟盘自己又写了一份"


def test_R349_三样读数都在():
    """位置 / 量能 / 距关键点 —— 少一样, 这一格就回答不了"凭什么是这一只"。"""
    cell = code_of(TREND)
    assert "posWord(o.channel_pct)" in cell, "位置没了"
    assert "volWord(o.vol_ratio)" in cell, "量能没了"
    assert "o.gap_pct != null" in cell, "距关键点没了"
    # 三句状态词的分界值本身
    assert "'放量刚好'" in cell and "'刚站上生命线'" in cell


# [R513] `test_R356_走势并进同一行_自成一列` 退役 —— 信号行那套定宽网格(ROW_GRID / RowShape / SignalRow)随 R513 整个删了: 用户「今日页面这个页面重做, 改的好看点, 不要折叠了」, 三段各换一种长相(卡片 / 方块 / 密排行), 不再是一张对齐的长表。新版面的守卫在 test_flip_signals_r513.py


def test_R356_走势那一格自己也是一行():
    """**行高这件事有两处**, 这是容易漏掉的那一处。

    信号行那边的 `min-h-[3.5rem]` 只管**下限**; 走势格自己若还是 `flex-col`
    (机会表时代的排法), 它会把行**撑高**, 而且只撑"进了候选池"的那些行 ——
    行高照样跟着"有没有名次"变, 用户说的第二件事等于没做。
    """
    cell = code_of(TREND)
    body = cell[cell.index("export function TrendCell"):]
    assert "flex-col" not in body, "走势格还是竖排, 会把行撑高一截"
    assert "flex flex-wrap items-center" in body, "没有横排"


# [R513] `test_R356_行高定死_不随有没有走势变` 退役 —— 信号行那套定宽网格(ROW_GRID / RowShape / SignalRow)随 R513 整个删了: 用户「今日页面这个页面重做, 改的好看点, 不要折叠了」, 三段各换一种长相(卡片 / 方块 / 密排行), 不再是一张对齐的长表。新版面的守卫在 test_flip_signals_r513.py


# [R513] `test_R356_把右边那片空地用上` 退役 —— 信号行那套定宽网格(ROW_GRID / RowShape / SignalRow)随 R513 整个删了: 用户「今日页面这个页面重做, 改的好看点, 不要折叠了」, 三段各换一种长相(卡片 / 方块 / 密排行), 不再是一张对齐的长表。新版面的守卫在 test_flip_signals_r513.py


# [R513] `test_R356_没进候选池时走势格空着但占位` 退役 —— 信号行那套定宽网格(ROW_GRID / RowShape / SignalRow)随 R513 整个删了: 用户「今日页面这个页面重做, 改的好看点, 不要折叠了」, 三段各换一种长相(卡片 / 方块 / 密排行), 不再是一张对齐的长表。新版面的守卫在 test_flip_signals_r513.py


def test_R349_走势那一格不是动作():
    cell = code_of(TREND)
    for word in ("'买入'", "'清仓'", "onClick"):
        assert word not in cell, f"走势那一格出现了动作: {word}"


# ── [R350] 版面: 定宽网格 ───────────────────────────────────────────────
#
# 用户: 「你排版不对, 中间这么多空间」。
#
# **两个毛病同一个根**: 原来是 flex + 触发价上一个 `ml-auto`。2000px 宽屏上
# `ml-auto` 把价格甩到最右边, 中间空出一大条; 而 flex 各行按自己的内容宽度排,
# **行与行之间列也对不齐** —— 「离清仓线还有 10.0%」和「还差 15.2%」起点不同,
# 眼睛得逐行重找。


def _row() -> str:
    code = code_of(FLIP)
    blk = code[code.index("function SignalRow"):]
    nxt = blk.find("\nfunction ", 1)
    out = blk if nxt < 0 else blk[:nxt]
    assert out.strip(), "切出来是空的 —— 空集合上的断言全是恒真的"
    return out


def _grid_class(row: str) -> str:
    """网格那个 div **自己**的 class 串(不含行内其它元素的)。

    行里还有好几个 `inline-flex items-center` 的徽标, 拿整行当锚去查布局类, 断言
    会被它们喂饱。要钉网格的属性, 就得先把网格那一格单独切出来。

    [R366] 这一串里现在**两套栅格并存**(窄屏卡片 / 宽屏六列), 断言要自己分清
    查的是哪一套 —— `sm:` 前缀就是分界。

    [R383] 宽屏那套**从写死变成按这一屏的形状挑**(见 `ROW_GRID`), 于是它不再
    写在 div 上, 而是由 `cn(...)` 从那张表里取。所以这里返回的是**两段拼起来**:
    行上那个 `cn(...)` 的实参 + `ROW_GRID` 那张表。合起来才是"这一行可能长的样子",
    分开看哪一段都不完整。
    """
    # **行容器也是 `cn(...)`**(它挂买卖底色), 所以不能只认 `<div className={cn(` ——
    # 那会切到外层那个, 里头一个 grid-cols 都没有。认「cn 的第一个实参就是 'grid …'」。
    m = re.search(r"<div className=\{cn\(\s*\n?\s*'grid ", row)
    assert m, "找不到网格那个 div"
    i = m.start()
    j = row.index(")}>", i)
    cls = row[i:j]
    # [R384] **栅格串一个都不在 div 上了** —— 窄屏那套也挪进了 `ROW_GRID`
    # (名次那列在窄屏同样要能收成 0)。所以只在 div 上断言「它挑了模板」,
    # 列宽本身去表里查。div 上再写死一个 `grid-cols-` 就是两个打架, 不许。
    assert "gridOf(shape)" in cls, "网格那个 div 没有去 ROW_GRID 挑模板"
    assert "grid-cols-[" not in cls, "div 上又写死了列宽 —— 会和模板给的那个打架"
    code = code_of(FLIP)
    k = code.index("const ROW_GRID = {")
    table = code[k:code.index("} as const", k)]
    assert "sm:grid-cols-[" in table, "ROW_GRID 那张表里没有宽屏栅格"
    return cls + "\n" + table


# [R513] `test_R350_信号行是定宽网格_不是flex` 退役 —— 信号行那套定宽网格(ROW_GRID / RowShape / SignalRow)随 R513 整个删了: 用户「今日页面这个页面重做, 改的好看点, 不要折叠了」, 三段各换一种长相(卡片 / 方块 / 密排行), 不再是一张对齐的长表。新版面的守卫在 test_flip_signals_r513.py


# [R513] `test_R350_名次那一格空着也占位` 退役 —— 信号行那套定宽网格(ROW_GRID / RowShape / SignalRow)随 R513 整个删了: 用户「今日页面这个页面重做, 改的好看点, 不要折叠了」, 三段各换一种长相(卡片 / 方块 / 密排行), 不再是一张对齐的长表。新版面的守卫在 test_flip_signals_r513.py


# ── [R352] AI 导读删掉, 连同它那个已经没有展示面的定时开关 ──────────────
#
# 用户: 「这部分和 ai 导读都不用了, 删掉」。


def test_R352_导读与它的定时开关一起消失():
    """**一个开关的展示面没了, 开关本身就得跟着走。**

    「定时导读·优选」产出两样东西 —— 导读正文与 AI 优选。优选面板随今日总览删于
    R351, 导读正文这次删; 留着那个开关就是又一个**调了不产生任何可见结果的旋钮**,
    与 R340 删掉的「回撤纪律线」一模一样。
    """
    ctrl = code_of(CTRL)
    assert "定时导读" not in ctrl, "那个开关的产出已经没有展示面了, 不该还留着"
    assert "todayAiSched" not in ctrl, "对应的 query/mutation 也该一起走"
    # [R435] 这里原来有一组**对照组**:「定时个股信号」的产出还显示在决策台的「AI 信号」
    # 列上, 所以它得留着。现在 AI 信号整套停用, 那一列没了 —— 按这条自己的立论
    # (「一个开关的展示面没了, 开关本身就得跟着走」), 它也跟着走了。
    assert "定时个股信号" not in ctrl and "signalAiSched" not in ctrl, \
        "「定时个股信号」的展示面(AI 信号列)已经撤了, 开关不该还留着"


def test_R352_前端那几个死包装也清了():
    """`todayAi` / `todayAiTrackRecord` / `todayAiSchedule*` 在前端没有任何调用方。

    命中率那条**从 R351 起就没人调了** —— 它只服务于已随今日总览删掉的优选面板。
    「没人调的代码看起来像在用」这仓库栽过太多次, 顺手清干净。
    **后端端点原样还在**, 删的只是前端那层包装。
    """
    api = code_of("lib/api.ts")
    for name in ("todayAi:", "todayAiTrackRecord:", "todayAiScheduleGet:", "todayAiScheduleSet:"):
        assert name not in api, f"前端还留着没人调的包装: {name}"
    keys = code_of("lib/queryKeys.ts")
    for name in ("todayAiSchedule:", "todayAiTrackRecord:"):
        assert name not in keys, f"queryKeys 还留着死键: {name}"


# ── [R358] 成绩与净值图并进筛选那张卡 ───────────────────────────────────
#
# 用户: 「净值走势图和这两行收益都融合到页面开头的第一个卡片里面」, 追问后明确
# 是「我是想合并到筛选的卡片里面」; 净值图「默认收起」。


def test_R358_成绩挂在筛选卡的插槽上_不是搬进那个组件():
    """**做成插槽, 不是把成绩搬进 `TodayControls`。**

    那个组件管的是"看哪些票 / 什么门槛", 对模拟盘的净值、月度收益一无所知, 也不该
    知道 —— 它当初立起来的理由就是**一处实现**(R347)。把某一页的数据结构焊进去,
    下一个用它的页面就得先绕过这段。插槽只承诺一件事: 这块东西长在同一张卡里。
    """
    ctrl = code_of(CTRL)
    assert "extra?: ReactNode" in ctrl, "没有插槽"
    # [R400] 原来锚的是 `{extra && <div` —— 3.2 把那个 div 换成了 `<CardSection>`,
    # 而"插槽渲染出来了"这件事一点没变。钉渲染本身, 不钉它当时用的是哪个标签。
    assert re.search(r"\{extra && <\w", ctrl), "插槽没渲染"
    # 组件本身仍然对模拟盘一无所知
    for leak in ("FlipPaper", "monthly", "nav", "total_ret", "max_drawdown"):
        assert leak not in ctrl, f"模拟盘的数据结构漏进了这个共用组件: {leak}"
    # [R498] 模拟盘**不再用这个插槽** —— 成绩单独成卡了(用户选的「今天优先」)。
    # 插槽本身留着(它是共用组件的通用能力, 不该因为一个页面不用了就拆), 上面那几条
    # 「组件对模拟盘一无所知」照旧钉着。这里改钉: 模拟盘调它时不传 extra。
    code = code_of(FLIP)
    call = code[code.index("<TodayControls d={ov}"):]
    call = call[:call.index("/>")]
    assert "extra=" not in call, "成绩又挂回筛选卡的插槽上了 —— R498 用户选了让首屏给信号"


def test_R358_插槽与筛选条在同一张卡里():
    """用户要的就是"同一张卡"。卡壳必须包着**筛选条 + 插槽**两样。

    钉的是结构而不是某个类名: 插槽在卡壳之内、筛选条之后, 中间有条分隔线。
    (旧版的卡壳直接长在筛选条那个 flex 容器上 —— 那种写法下插槽只能排在卡外面,
    或者被当成 flex 的又一个横排项。)

    [R400] 卡壳与分隔线都搬进了共用的 `components/ui/Card`, 所以这里改成两段查:
    **顺序**在这个文件里查, **分隔线**到那个基础件里查 —— 措辞/标签换了不该红,
    真把分隔线拿掉了才该红。
    """
    ctrl = code_of(CTRL)
    m = re.search(r"<Card [^>]*>", ctrl)
    assert m, "卡壳没有单独一层"
    seg = ctrl[m.start():]
    i_row = seg.index("flex flex-wrap items-center")
    i_extra = seg.index("{extra &&")
    assert i_row < i_extra, "插槽跑到筛选条前面去了"
    # 插槽走的必须是"卡内第二块"那个件 —— 它自带分隔线; 随便套个 div 就没有了
    assert re.search(r"\{extra && <CardSection", seg), \
        "插槽没走 CardSection —— 那条分隔线就没了, 两块东西会糊成一团"
    card = code_of("components/ui/Card.tsx")
    i_sec = card.index("export function CardSection")
    assert "border-t" in card[i_sec:i_sec + 400], \
        "CardSection 自己把分隔线弄丢了 —— 卡里那两块会糊成一团"


def test_R358_净值图默认收起():
    code = code_of(FLIP)
    assert "storage.flipNavOpen.get(false)" in code, "默认不是收起"
    assert "storage.flipNavOpen.set(!v)" in code, "折叠状态没记住"


def test_R358_折起来时连组件一起不挂载_不是藏起来():
    """**这一条挡的是一个会静默失败的坑。**

    `useECharts` 的初始化 effect 依赖数组是 `[]`, 而且 `if (!chartRef.current)
    return` —— 图表的 div 若在首次渲染时不存在, 那个 effect 就地返回, **之后
    再也不会重跑**。于是用 `hidden` / `display:none` 之类藏起来再展开, 展开后是
    一片空白: 不报错、控制台干净、数据也都在, 只是图没了。

    所以折叠必须**连 `<NavChart>` 一起不渲染**。
    """
    from tests.frontend_source import code_of as _c
    hook = _c("pages/backtest/charts/useECharts.ts")
    assert "if (!chartRef.current) return" in hook and "}, [])" in hook, \
        "这条守卫的前提变了 —— init effect 不再是一次性的, 重新想一遍"

    code = code_of(FLIP)
    sm = code[code.index("function Summary({ d }"):code.index("function Stat({ label")]
    assert sm.strip()
    assert "{navOpen && <NavChart d={d} />}" in sm, \
        "净值图不是按 navOpen 条件挂载 —— 藏起来再展开会是一片空白且不报错"
    for hide in ('hidden={', "display: 'none'", "'hidden'"):
        assert hide not in sm, f"用了藏起来的办法: {hide}"


def test_R358_折叠条与R355那条长一个样():
    """同一页上两种折叠长两个样, 读的人要认两次。"""
    code = code_of(FLIP)
    sm = code[code.index("function Summary({ d }"):code.index("function Stat({ label")]
    assert sm.strip()
    assert "navOpen && 'rotate-180'" in sm, "没沿用旋转的 ChevronDown"
    assert "{navOpen ? '收起' : '展开'}" in sm, "没沿用「收起/展开」那句"
    assert "aria-expanded={navOpen}" in sm


def test_R358_并进去之后不是卡中卡():
    """插槽里那几块自己不能再带一圈卡壳 —— 否则是一圈边框套一圈边框。"""
    code = code_of(FLIP)
    strip = code[code.index("function MonthStrip({ months }"):code.index("function Summary({ d }")]
    assert strip.strip()
    assert "rounded-card" not in strip, "逐月那一块还带着自己的卡壳"
    chart = code[code.index("function NavChart({ d }"):]
    chart = chart[:chart.index("\nfunction ")]
    assert "rounded-card" not in chart, "净值图还带着自己的卡壳"
    assert "<SectionHead" not in chart, "标题该归折叠条, 不该图里再来一个"


def test_R358_打分那层挂了_成绩不跟着消失():
    """**两份数据是各自独立的请求。**

    筛选条吃的是今日总览那份(打分那一层), 成绩吃的是模拟盘自己那份。把成绩挂在
    `ov && ...` 里的话, 打分那一层一挂, **整段成绩跟着一起消失** —— 而它明明
    算出来了。那种消失不报错, 也看不出是哪儿出的问题。

    [R498] 成绩单独成卡之后, 这条性质换了个钉法: 成绩卡 `{results}` 在主列里
    **无条件渲染**, 它所在的那一层不看 `ov`, 也不看 `d`(跑不动时参数条仍得在)。
    """
    # [R512] 分栏之后成绩独占一栏: 那一栏只看 `tab`, 不看 `ov` 也不看 `hasBody` / `d`。
    code = code_of(FLIP)
    jsx = code[code.index('return (\n    <div className="flex h-full flex-col">'):]
    assert "{tab === 'results' && results}" in jsx, "成绩那一栏挂上了别的条件 —— 打分一挂或跑不动时它就没了"
    assert "{results}" not in jsx and jsx.count(" results}") == 1, "成绩卡没渲染, 或渲染了两份"
    assert "{tab === 'holdings' && hasBody && d && (" in jsx, "持仓该跟着正文走, 成绩卡不该"


# ── [R359] 参数条也并进那张卡 ───────────────────────────────────────────
#
# 用户: 「这两个部分整合到一个卡片放在顶部」→「参数框也并进来, 标题行留在外面」。


def test_R359_参数条不在页头了_在卡里():
    """三个框原来在**页头最右边**, 与它们算出来的数字隔着大半个屏幕 ——
    改完一个框, 眼睛要横穿整页才看得到结果变了什么。"""
    code = code_of(FLIP)
    head = code[code.index("<PageHeader"):code.index('<div className="min-h-0 flex-1')]
    assert head.strip()
    assert "NumberField" not in head, "参数框还留在页头"
    # [R365] 原来这儿还写着 `assert "right={" not in head` —— **那是禁了整个右槽,
    # 而这条守卫要护的是「那三个输入框不在页头」**。R365 往右槽放了个手动刷新
    # 按钮(用户点的名), 守卫因此红了, 而它红得没有道理: 一个刷新按钮不是参数框。
    # 锚太宽的另一个方向 —— 禁得比该禁的多。改钉真正的性质: 右槽里不许有输入。
    # [R512] 页头右槽多了分栏条, 它有 `onChange={setTab}` —— 切栏不是参数输入, 所以
    # 「onChange=」这个锚改钉参数自己的回调名。
    for inp in ("<input", "NumberField", "onCapital", "onMaxPositions", "onYears"):
        assert inp not in head, f"页头右槽里出现了输入: {inp}"
    # 标题那一行**留在页头**, 这是用户点的名(「标题行留在外面」)。
    # 锚带上行首的换行与缩进: 光写 `titleExtra={w && (` 的话, 改名成
    # `xtitleExtra=` 照样含着这段, 断言过得去(变异电池当场打绿)。
    assert "\n        titleExtra={w && (" in head, "标题行被一起搬走了 —— 用户要它留在外面"
    assert "\n        subtitle={w" in head, "副标题(多空比)也被搬走了"


def test_R359_参数条紧挨着它算出来的东西():
    """本金 / 最多持有 / 回溯**就是算出下面那些数字的那三个输入**。"""
    code = code_of(FLIP)
    # [R498] 成绩单独成卡(`results`), 参数条跟着进了这张卡, 仍排在成绩正上方
    body = code[code.index("const results = ("):code.index("const hasBody")]
    assert body.strip()
    assert body.index("<ParamBar") < body.index("{summary}"), "参数条没排在成绩上方"


def test_R359_参数条不跟着成绩一起消失():
    """**跑不动的时候正是最需要这三个框的时候。**

    `summary` 在 `d` 没有或 `reason` 非空时是 null —— 而回溯填过头、本金填成 0
    这类毛病, 修的办法就是改这三个框。把参数条塞进 `Summary` 里, 出错时它会跟着
    一起不见, 于是**没有任何办法把页面救回来**, 只能去清 localStorage。
    """
    code = code_of(FLIP)
    body = code[code.index("const results = ("):code.index("const hasBody")]
    assert body.strip()
    assert "<ParamBar" in body, "参数条不在成绩卡这一层"
    # [R498] 而且它**不在 `{summary}` 的条件里**: summary 为 null 时参数条照样渲染
    assert "summary &&" not in body and "summary ?" not in body, "参数条被包进了成绩的条件里"
    sm = code[code.index("function Summary({ d }"):code.index("function Stat({ label")]
    assert sm.strip()
    assert "<ParamBar" not in sm, "参数条嵌进了 Summary —— 跑不动时会跟着一起消失"


def test_R359_说清楚筛选不进回测():
    """板块/门槛与回测参数**并进了同一张卡**, 而它们一个进回测一个不进 ——
    这件事不说出来就没人知道, 挨着放本身就在暗示它们是一回事。

    (界线本身早有守卫: `test_R347_控件只作用于打分层_不碰六态名单`。这一条钉的
    是**界线要说给人听**, 不是界线本身。)
    """
    code = code_of(FLIP)
    bar = code[code.index("function ParamBar({"):code.index("function MonthStrip({ months }")]
    assert bar.strip()
    assert "不进这条曲线" in bar, "没告诉读的人筛选不影响回测"


# ── [R360] 名次挪到整行最前 ─────────────────────────────────────────────
#
# 用户: 「这列内容统一放到股票名称前面」。


def test_R360_名次是整行第一格_排在标的前面():
    """用户: 「这列内容统一放到股票名称前面」—— 它回答「凭什么是这一只」, 得在认票之前摆在眼前。
    [R513] 卡片上仍是名次在左、标的在右。"""
    card = _fn("ActionCard")
    assert card.index("<ScoreCell") < card.index("<SymbolButton"), "名次挪到标的后面去了"


# ── [R362] 六格并成一行 ─────────────────────────────────────────────────
#
# 用户: 「把图片显示的内容用一行显示」(截图是上排两格 + 下排四格)。


def _stat_row() -> str:
    code = code_of(FLIP)
    row = code[code.index('<section className="grid grid-cols-2 divide-x'):]
    row = row[:row.index("</section>")]
    assert row.strip() and "<Stat label=" in row, "没切到统计那一排"
    return row


def test_R362_六格一行_不是两排():
    """原来是两排: 上排两格说「当下」各占半屏 —— 一个「10 只」霸着 1000px。"""
    import re
    row = _stat_row()
    # [R512] 「现在拿着」改名「持仓」—— 与分栏上那一栏同名(一个东西一个名字)
    for label in ("持仓", "最后一天", "总收益", "最大回撤", "完整买卖", "胜率"):
        assert label in row, f"这一格掉出这一排了: {label}"
    assert len(re.findall(r"<Stat[\s>]", row)) == 6, "不是六格"
    # **整页只剩这一个统计排** —— 留着旧的那一排等于没并
    code = code_of(FLIP)
    assert code.count('<section className="grid grid-cols-2 divide-x') == 1, \
        "还有第二排统计 —— 那就不是「一行显示」"


def test_R362_当下那两格仍排在整段四格之前():
    """[R332 立论照搬] 用户每天打开先问「最近怎么样」。

    **那条次序还在, 只是不再靠换行表达** —— 六格一行, 左两格当下、右四格整段。
    """
    row = _stat_row()
    assert row.index('label="持仓"') < row.index('label="总收益"'), "次序反了"
    assert row.index('label="最后一天"') < row.index('label="总收益"')


def test_R362_窄屏照样换行():
    """六格横排在手机上一格只剩六十来像素, 数字会被压断。"""
    row = _stat_row()
    for cls in ("grid-cols-2", "sm:grid-cols-3", "lg:grid-cols-6"):
        assert cls in row, f"少了这一档断点: {cls}"
    # 换行的档位要有横线, 六格一行时**要关掉** —— 否则会在唯一那一行下面
    # 多画一条线
    assert "divide-y divide-border/30" in row and "lg:divide-y-0" in row, \
        "divide-y 没按断点收掉"


def test_R362_并成一行之后提示语没说假话():
    """「下面那一排才是整段成绩」那句话在并成一行之后是假的 —— 下面没有那一排了。

    **提示语跟着版面走**: 一句指错方向的说明比没有说明更坏, 它会让人去找一个
    不存在的东西, 而且不会有任何东西报错。
    """
    row = _stat_row()
    assert "下面那一排" not in row, "提示语还在指一个不存在的下一排"
    assert "同一行右边那四格" in row, "没告诉读的人整段成绩现在在哪儿"


# ── [R363] 标的与动作两格可点, 弹关键价位 ───────────────────────────────
#
# 用户: 「点击这两列都要能像个股分析页面那样弹出弹窗」。

LEVELS = "components/stock-analysis/LevelsDialog.tsx"
SA = "pages/StockAnalysis.tsx"


def test_R363_关键价位弹窗是一处实现_两页共用():
    """它原来是 `pages/StockAnalysis.tsx` 里的私有组件(R28)。

    模拟盘要用它 —— **不在那边抄一份**: 这个弹窗里有放大态、Esc 关闭、退场动画、
    现价标签、`bare` 那一层去框。抄一份必然漂, 而漂的表现是「两个页面点同一只票
    弹出来的东西不一样」, 两边都不报错。
    """
    import re

    dlg = code_of(LEVELS)
    assert "export function LevelsDialog" in dlg
    # 那几样真本事都得跟着搬过来, 不是搬了个壳。
    #
    # **按词边界匹配, 不是裸 `in`。** 裸 `in` 挡不住改名: `setMaximizedX` 仍然
    # 含着 `setMaximized`, 断言被它喂饱 —— 变异电池当场打绿两条。这与 R359 那次
    # 的 `xtitleExtra` 是同一族毛病:**锚是别人的子串**, 本会话第二次。
    for feat in ("setMaximized", "StockLevelsPanel", "StockLevelsPriceTag",
                 "AnimatePresence"):
        assert re.search(rf"\b{feat}\b", dlg), f"搬过来的时候丢了: {feat}"
    assert "'Escape'" in dlg, "Esc 关闭丢了"

    for page in (FLIP, SA):
        code = code_of(page)
        assert "from '@/components/stock-analysis/LevelsDialog'" in code, f"{page} 没复用那一处"
        assert "function LevelsDialog" not in code, f"{page} 自己又写了一份"


def test_R364_两个可点的格子_各开各的表():
    """[R363 → R364] 两列点开的不是同一张表(决策台 R51 的规矩):

        标的那格   这只票现在贵不贵、关键价位在哪  → 关键价位(日 K)
        六态那句   这个状态是怎么走到今天的        → 逐日复盘

    [R513] 三段共用 `SymbolButton`(→ 关键价位)与 `StateLine`(→ 复盘); 持仓方块的距离条、
    盯着那行的「差 N%」说的也是状态离转折多远, 所以同样开复盘。"""
    sym = _fn("SymbolButton")
    assert sym.count("onClick={() => onOpen(r.symbol, r.name)}") == 1 and "onReview" not in sym
    assert sym.index("onClick={() => onOpen") < sym.index("<SymbolCell symbol={r.symbol}"), "关键价位入口没包住标的"
    st = _fn("StateLine")
    assert st.count("onClick={() => onReview(r.symbol, r.name)}") == 1 and "onOpen" not in st
    assert st.index("onClick={() => onReview") < st.index("已转折 · 现在是"), "复盘入口没包住六态那一句"
    for comp in ("ActionCard", "HoldingTile", "WatchGroup"):
        blk = _fn(comp)
        assert "<SymbolButton r={r} onOpen={onOpen}" in blk, f"{comp} 的标的没走共用那一格"
        assert "onOpen(r.symbol" not in blk.replace("<SymbolButton", ""), f"{comp} 另开了一个关键价位入口"


def test_R364_两个入口开的不是同一个弹窗():
    """合成一个弹窗的话, 这两列就白分了 —— 那正是 R51 当初要挡的事。"""
    code = code_of(FLIP)
    # [R427] 复盘并进了个股弹窗(用户: 「两个弹窗融合成一个」), 这边开的是它的复盘页;
    # 「关键价位」与「复盘」仍是两个入口、两份内容 —— 这条守的事没变
    assert "<LevelsDialog" in code and "<StockPreviewDialog" in code
    # [R479] 旧复盘页(和它的「趋势状态」页签)删了, 'review' 入口打开即定位到新「复盘」块
    assert 'initialView="review"' in code, "复盘入口没指定落在复盘 —— 六态那句问的是状态怎么走的"
    # 两个弹窗**各存各的 state**: 合成一个带 kind 的, "开着哪一个"与"开的是哪只票"
    # 就绑死在一起, 而它们本来是两条互不相干的路
    assert "const [levels, setLevels]" in code and "const [review, setReview]" in code


def test_R363_弹窗挂在这一层_不是每行一个():
    """三段上百行, 每行各挂一个就是上百个常驻的 AnimatePresence 与 Esc 监听 —— 而同一时刻只可能开着一个。"""
    code = code_of(FLIP)
    assert code.count("<LevelsDialog") == 1, "弹窗挂了不止一处"
    assert "<LevelsDialog" not in _signal_row(), "弹窗挂进了每一行"
    seg = code[code.index("function TodaySignals"):code.index("function ZoneHead")]
    assert "<LevelsDialog" in seg, "弹窗没挂在 TodaySignals 这一层"


def test_R363_点开是弹窗_不是跳走():
    """跳走之后回来, 折叠状态、滚动位置、这一屏的上下文全没了。"""
    row = _signal_row()
    for leave in ("navigate(", "href=", "window.open", "/stock-analysis?symbol="):
        assert leave not in row, f"信号行上出现了跳页: {leave}"


def test_R364_动作那一格根本不可点():
    """这一格里印着「买入」两个字, 任何可点的迹象都在暗示「点它就下单」—— 而这一页从来不下单。
    [R513] 动作徽标在卡片右上角, 仍然是个 span。"""
    card = _fn("ActionCard")
    i_act = card.index("{buy || sell ? (")
    seg = card[i_act:card.index("<StateLine", i_act)]
    assert seg.strip() and "'买入'" in seg, "切出来的不是动作那一格"
    for clickable in ("<button", "onClick", "cursor-pointer", "role=\"button\""):
        assert clickable not in seg, f"动作那一格又变得能点了: {clickable}"


# ── [R365] 手动刷新按钮 ─────────────────────────────────────────────────
#
# 用户: 「除了自动定时我还要手动按钮有时候我想看实时情况会点一下」。


def test_R365_有手动刷新_而且自动那一档没被动过():
    """**「除了自动定时」** —— 手动是补一条路, 不是替掉节奏。"""
    code = code_of(FLIP)
    assert "const refreshAll = () =>" in code, "没有手动刷新"
    assert "refetchInterval: refreshEvery('derived')" in code, "自动那一档被动了"
    # **两个分支各有一句**: 天气拿到了走 JSX 那支, 没拿到走后面那句模板串。
    # 只断言"出现过"的话, 删掉其中一支照样绿 —— 另一支把断言喂饱了(变异电池
    # 当场打绿)。而删掉的那一支正是**常态那一支**。
    assert code.count("rhythmHint('derived')") == 2, \
        "副标题那句节奏说明少了一支 —— 天气拿到/拿不到, 两种情形都得说"


def test_R365_两个查询一起重取_不是只刷半页():
    """这一页的数字来自**两份互不相干的请求**:

        模拟盘那份   回测 + 今日信号(带实时叠加层)
        今日总览那份 打分 / 多空比 / 主线 / 自检条

    只刷其中一个的话, 按钮上写着「刷新」而实际只刷了半页 —— 而另外半页看上去
    也没坏, **没有任何东西会提示你它是旧的**。
    """
    code = code_of(FLIP)
    # 切到行尾就够 —— 它是个一行的函数。
    # (别拿 `\n\n` 当界: `code_of` 会把注释剥掉并把空行压掉, 那个界根本不存在,
    #  第一版就是这么 `ValueError: substring not found` 的。)
    i = code.index("const refreshAll = () =>")
    fn = code[i:code.index("\n", i)]
    assert "q.refetch()" in fn, "模拟盘那份没重取"
    assert "today.refetch()" in fn, "今日总览那份没重取"


def test_R365_在飞就禁用_且转起来():
    """模拟盘那一趟是几百只票的六态 + 一整轮回测, 秒级。不禁的话连点几下就是
    几趟全量重算堆在后端。"""
    code = code_of(FLIP)
    assert "const refreshing = q.isFetching || today.isFetching" in code, \
        "在飞的判据没把两份都算上"
    head = code[code.index("<PageHeader"):code.index('<div className="min-h-0 flex-1')]
    assert head.strip()
    assert "disabled={refreshing}" in head, "在飞时没禁用"
    assert "refreshing && 'animate-spin'" in head, "在飞时没有转起来 —— 点了像没反应"


def test_R365_按钮在页头_挨着那句节奏说明():
    """副标题那句说的是「它自己什么时候刷」, 这个按钮回答「我现在就要刷」。"""
    code = code_of(FLIP)
    head = code[code.index("<PageHeader"):code.index('<div className="min-h-0 flex-1')]
    assert head.strip()
    assert "onClick={refreshAll}" in head, "刷新按钮不在页头"
    # 它是个按钮, 不是又一个输入框 —— 右槽当初就是为了腾掉参数框才空出来的(R359)
    for inp in ("<input", "NumberField"):
        assert inp not in head, f"页头右槽里又出现了输入: {inp}"


# ── [R366] 手机端: PWA 壳 + 模拟盘窄屏版 ────────────────────────────────
#
# 用户: 「有没有办法做个 app 手机也能用」→「手机端我只需要模拟盘页面和模拟盘
# 里面的那两个弹窗, 只看这三个」。

SW = "../public/sw.js"


def _pub(rel: str) -> str:
    import pathlib
    from tests.frontend_source import SRC
    return (pathlib.Path(SRC).parent / "public" / rel).read_text(encoding="utf-8")


def test_R366_service_worker_一个字节都不缓存API():
    """**这条是这次改动里最要紧的一条。**

    这一页的数字 5 分钟一刷, 盘中更是实时叠加层。把 `/api/**` 缓存下来, 手机上
    就会看到几小时前的价格与信号 —— 而**它长得和新的一模一样**, 没有任何东西会
    告诉你它是旧的。这正是自检条(R343)一直在防的事, 不能让 SW 从背后绕过去。
    """
    sw = _pub("sw.js")
    assert "if (url.pathname.startsWith('/api/')) return" in sw, \
        "SW 没有把 /api/ 整个放行 —— 一旦缓存, 手机上会看到假装是今天的旧数字"
    # 放行必须发生在**任何一条缓存分支之前**
    i_api = sw.index("startsWith('/api/')")
    for later in ("caches.open(STATIC)", "caches.open(SHELL)", "caches.match(req)"):
        assert i_api < sw.index(later), f"/api/ 的放行排在了 {later} 后面"


def test_R366_只缓存带哈希的构建产物():
    """文件名带内容哈希 = 改了就是新名字, 所以"缓存优先"永远不会给出过期的东西。

    不带哈希的东西(比如 index.html)**不许缓存优先** —— 那会把人钉死在旧版本上。
    """
    sw = _pub("sw.js")
    assert "/assets/" in sw and "isHashedAsset" in sw
    nav = sw[sw.index("req.mode === 'navigate'"):]
    assert "await fetch(req)" in nav, "页面外壳不是网络优先"
    assert nav.index("await fetch(req)") < nav.index("caches.match"), \
        "页面外壳成了缓存优先 —— 会把人钉死在旧版本上"


def test_R366_manifest_直接开到模拟盘():
    """用户: 「手机端我只需要模拟盘页面」—— 从主屏图标点进去就该是它,
    不必先落到首页再点两下。"""
    import json
    m = json.loads(_pub("manifest.webmanifest"))
    assert m["start_url"] == "/lots", "主屏图标没直接开到模拟盘"
    assert m["display"] == "standalone", "不是独立窗口 —— 那就还是个网页"
    sizes = {i["sizes"] for i in m["icons"]}
    assert {"192x192", "512x512"} <= sizes, "缺 Android 要的图标尺寸"
    assert any(i.get("purpose") == "maskable" for i in m["icons"]), \
        "没有 maskable 图标 —— Android 各家裁切形状不同, 会把图形切掉一圈"


def test_R366_iOS那几样单独挂在html上():
    """**iOS 不认 manifest 里的 icons**, 也不认 display —— 各有各的 meta。"""
    import pathlib
    from tests.frontend_source import SRC
    html = (pathlib.Path(SRC).parent / "index.html").read_text(encoding="utf-8")
    assert 'rel="apple-touch-icon"' in html, "iOS 主屏图标没挂"
    assert 'name="apple-mobile-web-app-capable" content="yes"' in html, "iOS 全屏没开"
    assert 'rel="manifest"' in html


def test_R366_要么不用cover_要么得真有安全区内边距():
    """**这一条钉的是一对东西必须成对出现。**

    第一版我在 viewport 上加了 `viewport-fit=cover`, 注释里还写着「内容自己躲开
    安全区(见 index.css 的 env(safe-area-*))」—— 而那段 CSS 根本不存在。加了
    cover 却不配内边距, 内容会钻到刘海与 Home 条底下, **而在没有刘海的机器上
    一切正常**, 所以平时看不出来。

    现在的选择是不加 cover(iOS 自己会内缩)。哪天真要铺到边, 这条守卫会逼着
    同时把安全区内边距也写上。

    (顺带记一笔第一版守卫怎么漏的: 它写 `assert "viewport-fit=cover" in html`,
     **而我自己那条注释里就有这几个字** —— 把 meta 删掉照样绿, 断言被注释喂饱。
     这是本会话第二次栽在"注释喂饱断言"上, 所以这里查的是 `<meta` 那一行本身。)
    """
    import pathlib
    import re
    from tests.frontend_source import SRC
    html = (pathlib.Path(SRC).parent / "index.html").read_text(encoding="utf-8")
    bare = re.sub(r"<!--.*?-->", "", html, flags=re.S)      # 注释说了不算
    meta = re.search(r'<meta name="viewport"[^>]*>', bare)
    assert meta, "viewport 那一行没了"
    if "viewport-fit=cover" in meta.group(0):
        css = (pathlib.Path(SRC) / "index.css").read_text(encoding="utf-8")
        assert "env(safe-area-inset" in css,             "用了 viewport-fit=cover 却没有安全区内边距 —— 内容会钻到刘海底下"


def test_R366_开发时不注册SW():
    """vite dev 的模块不带哈希, 缓存住会得到「改了代码没反应」这种最难查的现象。"""
    code = code_of("main.tsx")
    assert "import.meta.env.PROD" in code, "开发环境也注册了 SW"
    assert "navigator.serviceWorker.register('/sw.js')" in code


# [R513] `test_R366_信号行窄屏折成卡片_而不是另写一份` 退役 —— 信号行那套定宽网格(ROW_GRID / RowShape / SignalRow)随 R513 整个删了: 用户「今日页面这个页面重做, 改的好看点, 不要折叠了」, 三段各换一种长相(卡片 / 方块 / 密排行), 不再是一张对齐的长表。新版面的守卫在 test_flip_signals_r513.py


def test_R366_窄屏断点走共用那一个_不另立一套():
    """两套断点会在某个宽度上互相打架, 而且**不报错** —— 只是那个宽度区间里
    版面是谁也没看过的样子。"""
    dlg = code_of("components/stock-analysis/LevelsDialog.tsx")
    assert "useIsDesktop" in dlg, "弹窗自己造了个断点"
    assert "matchMedia" not in dlg and "innerWidth" not in dlg, \
        "弹窗绕开共用 hook 自己量宽度"


def test_R366_根目录那几个文件按原样发_不落进SPA兜底():
    """**这一条挡的是一个整串都不报错的失败。**

    `/assets/**` 有自己的挂载, 而 `sw.js` / `manifest.webmanifest` / 图标 /
    `favicon.svg` 都在 dist 根 —— 它们原本会被 SPA 兜底回一份 index.html:

        · register('/sw.js') 拿到 text/html → 注册失败
        · /manifest.webmanifest 解析失败 → **整个「添加到主屏」就没了**
        · 图标全是 HTML

    而这一串**一个错都不会报到眼前**: 页面照常打开, 只是装不成 app。

    用真的 dist 目录跑一遍(没构建过就跳过), 逐个断言拿到的是真文件而不是 HTML。
    """
    import pathlib

    import pytest
    from fastapi.testclient import TestClient

    from app.config import settings

    static = pathlib.Path(settings.static_dir)
    if not (static / "index.html").exists():
        pytest.skip("前端没构建, 这条要真的 dist 才跑得了")

    from app.main import app
    with TestClient(app) as c:
        for path, ctype, needle in (
            ("/sw.js", "javascript", b"startsWith('/api/')"),
            ("/manifest.webmanifest", "manifest+json", b'"start_url"'),
            ("/icon-192.png", "image/png", b"\x89PNG"),
            ("/apple-touch-icon.png", "image/png", b"\x89PNG"),
            ("/favicon.svg", "image/svg", b"<svg"),
        ):
            r = c.get(path)
            assert r.status_code == 200, f"{path} 拿不到"
            assert ctype in r.headers["content-type"], \
                f"{path} 的类型是 {r.headers['content-type']} —— 多半被兜底成了 index.html"
            assert needle in r.content, f"{path} 的内容不对"

        # sw.js 不许被缓存住 —— 它自己就是更新机制
        assert "no-cache" in c.get("/sw.js").headers.get("cache-control", "")

        # 认不出的路径仍然回 index.html(React Router 接管)
        spa = c.get("/lots")
        assert "text/html" in spa.headers["content-type"]

        # **越界要挡住**: ../ 不许摸到 dist 外面去。
        #
        # 两处讲究, 第一版两处都写错了, 于是把 `relative_to` 那道检查删掉守卫
        # 照样绿(变异电池打出来的):
        #
        #   ① **`/../x` 到不了 handler** —— Starlette 会先把它规范成 `/x`。
        #      真能把 `../` 送进来的是**编码过的** `..%2f` / `%2e%2e`。
        #   ② 路径得**真的逃得出去**。第一版用的是 `../app/main.py`, 而 static
        #      是 `frontend/dist`, 往上一层是 `frontend/app/…` —— 那个目录根本
        #      不存在, 于是照样落到兜底, 看上去"挡住了"。
        #      要逃出去得是 `../../backend/app/main.py`。
        escape = "/..%2f..%2fbackend%2fapp%2fmain.py"
        r = c.get(escape)
        assert b"spa_fallback" not in r.content, f"路径穿越没挡住: {escape}"
        assert "text/html" in r.headers["content-type"], "越界的请求该落到 SPA 兜底"


# ── [R381] 重新排版:把宽屏上空着的那半边用起来 ──────────────────────────
#
# 用户: 「模拟盘页面的内容需要重新排版, 合理利用显示空间」。
#
# **这一轮是拿真数据看出来的, 不是拿空页面猜的。** 本地这套没有行情 Key, 直接
# 开页面是空的 —— 空页面上"哪儿浪费"全看不见。所以用 Playwright 把
# `/api/flip-paper` 拦下来喂一份像样的假数据(9 条信号 / 6 只持仓 / 46 笔流水 /
# 23 次没做成 / 12 个月), 在 1366/1600/1920/390 四个宽度上各看一遍。
#
# 看出来三处, 都是**只改版面不改内容**:
#   ① 六态那一列被 9rem 截字, 右边那格却空着六百像素
#   ② 「现在拿着」与「成交流水」各占一整行, 两张都是 min-w-[640px] 的窄表
#   ③ 「这套规则」七条竖着排, 「有信号但没做成」也是一条一行


# [R513] `test_R381_六态那句话能显示完整` 退役 —— 信号行那套定宽网格(ROW_GRID / RowShape / SignalRow)随 R513 整个删了: 用户「今日页面这个页面重做, 改的好看点, 不要折叠了」, 三段各换一种长相(卡片 / 方块 / 密排行), 不再是一张对齐的长表。新版面的守卫在 test_flip_signals_r513.py


def test_R381_R512_宽屏上不让窄块独占半屏_分栏后各占整行():
    """R381 的立论: **宽屏上别让一张窄表独占一整行、右边空一半** —— 当时的解法是并排。

    [R498] 并排的对象换成持仓 | 成绩。[R512] 分栏之后每一栏只有一块, 并排没有对象了,
    立论换个方向落地: 成绩独占整行时, 六格回到一行(不再按半幅排成 2~3 列),
    持仓卡片与流水两栏照旧铺满宽屏。
    """
    from tests.frontend_source import code_of
    code = code_of("pages/FlipPaper.tsx")
    jsx = code[code.index('return (\n    <div className="flex h-full flex-col">'):]
    assert "xl:grid-cols-[minmax(0,1.25fr)_minmax(0,1fr)]" not in jsx, "分栏之后还留着并排的两列 —— 一栏里只有一块"
    assert "{tab === 'orders' && hasBody && d && <Orders orders={d.orders} />}" in jsx, "流水该独占一栏"
    row = code[code.index('<section className="grid grid-cols-2 divide-x'):]
    row = row[:row.index(">")]
    assert "lg:grid-cols-6" in row and "xl:grid-cols-2" not in row, "成绩独占整行了, 六格还按半幅排"


def test_R381_规则改成多列():
    """七条「标签 + 一行值」竖着排在 1600px 上, 每行右边空掉三分之二,
    还把下面的东西挤出首屏。**口径一个字没改, 只是换了排法。**"""
    from tests.frontend_source import code_of
    code = code_of("pages/FlipPaper.tsx")

    rules = code[code.index("function Rules("):]
    rules = rules[:rules.index("\nfunction ")]
    assert rules.strip()
    assert "md:grid-cols-2 2xl:grid-cols-3" in rules, "规则没排成多列"
    # 七条一条不少, 次序也没动 —— 这是查证用的清单, 顺序本身是信息
    for k in ("信号", "成交", "方向", "仓位", "标的", "不做空", "成本"):
        assert f'k="{k}"' in rules, f"规则少了一条: {k}"
    assert rules.index('k="信号"') < rules.index('k="成交"') < rules.index('k="方向"'), \
        "规则的次序被打乱了"
    # 「成本」那条最长, 多列时独占一整行
    assert "md:col-span-2 2xl:col-span-3" in rules, "「成本」没独占整行, 会把行高撑成两倍"

    # [R499] 「没做成」那一块整个撤了, 它那一半守卫随之退场(见 test_flip_layout_r498 的 R499 那条)


# ── [R383] 没内容的列不该占宽 ────────────────────────────────────────────
#
# 用户(第二次说了): 「不是叫你重新排版模拟盘页面吗, 怎么一点都变化」。
#
# **R381 那一轮我拿自己造的假数据改的, 而那份假数据恰好把真问题遮住了。**
# 用户实机是 32 行全「已转折」、全「没进候选池」、`flip_price` 为 null ——
# 于是 R381 改的三处在他那一屏上一处都看不见(六态加宽只对「盘中越线」有效,
# 另外两处全在折叠线以下)。照着他的数据形状量了一遍才看见真的浪费:
#
#     行宽 1688 · 走势那一格独占 1068 而且是空的(63%) · 行高被 min-h 撑着 56
#
# R356 定下定宽网格的立论是「行与行天然对齐」—— 那条立论要的是**行与行之间**
# 对齐, 不是某一列必须占住某个绝对宽度。所以: 整屏都没有的那一列, 宽度给 0。


def _signals() -> str:
    code = code_of(FLIP)
    blk = code[code.index("function TodaySignals"):]
    out = blk[:blk.index("\nfunction ", 1)]
    assert out.strip()
    return out


# [R513] `test_R385_分界线是每一行进没进候选池` 退役 —— 信号行那套定宽网格(ROW_GRID / RowShape / SignalRow)随 R513 整个删了: 用户「今日页面这个页面重做, 改的好看点, 不要折叠了」, 三段各换一种长相(卡片 / 方块 / 密排行), 不再是一张对齐的长表。新版面的守卫在 test_flip_signals_r513.py


# [R513] `test_R385_三段都走同一个分组函数` 退役 —— 信号行那套定宽网格(ROW_GRID / RowShape / SignalRow)随 R513 整个删了: 用户「今日页面这个页面重做, 改的好看点, 不要折叠了」, 三段各换一种长相(卡片 / 方块 / 密排行), 不再是一张对齐的长表。新版面的守卫在 test_flip_signals_r513.py


# [R513] `test_R385_没进候选池那组排三列` 退役 —— 信号行那套定宽网格(ROW_GRID / RowShape / SignalRow)随 R513 整个删了: 用户「今日页面这个页面重做, 改的好看点, 不要折叠了」, 三段各换一种长相(卡片 / 方块 / 密排行), 不再是一张对齐的长表。新版面的守卫在 test_flip_signals_r513.py


# [R513] `test_R384_名次那列在没进候选池那一组里收成0` 退役 —— 信号行那套定宽网格(ROW_GRID / RowShape / SignalRow)随 R513 整个删了: 用户「今日页面这个页面重做, 改的好看点, 不要折叠了」, 三段各换一种长相(卡片 / 方块 / 密排行), 不再是一张对齐的长表。新版面的守卫在 test_flip_signals_r513.py


def test_R384_那句话改在标题上说一次():
    """从行里撤掉的东西必须在别处说出来, 否则就是悄悄少了一条信息。

    [R385] 判据从「整屏都没有」换成「有几行没有」—— 混着才是常态, 前者几乎
    永远不成立。所以标题上**报个数**, 而不是一句"都没进"。
    """
    sig = _signals()
    assert "unscored ? `${unscored} 只没进候选池` : null" in sig, \
        "「没进候选池」从行里撤了, 但标题上没补上 —— 那条信息就这么没了"
    assert "const unscored = rows.length - rows.filter((r) => conviction.has(r.symbol)).length" in sig, \
        "那个数不是从全部行算的"


# [R513] `test_R384_行留白跟着名次走` 退役 —— 信号行那套定宽网格(ROW_GRID / RowShape / SignalRow)随 R513 整个删了: 用户「今日页面这个页面重做, 改的好看点, 不要折叠了」, 三段各换一种长相(卡片 / 方块 / 密排行), 不再是一张对齐的长表。新版面的守卫在 test_flip_signals_r513.py


# [R513] `test_R384_网格类只有一个产地` 退役 —— 信号行那套定宽网格(ROW_GRID / RowShape / SignalRow)随 R513 整个删了: 用户「今日页面这个页面重做, 改的好看点, 不要折叠了」, 三段各换一种长相(卡片 / 方块 / 密排行), 不再是一张对齐的长表。新版面的守卫在 test_flip_signals_r513.py


# ── [R386] 列数要把触发价算进去 ──────────────────────────────────────────
#
# 用户截图: 「手上这些」那一档里, 触发价压到了右边一列的字上(「现 46.23深科技」)。
#
# **R385 我按「标的 176 + 动作 72 + 六态 112~256 + 间距」≈560px 定的三列, 漏了
# 触发价** —— 它是 `auto` + `whitespace-nowrap`, 有值时要 ~175px, 一行实际要
# ~740px, 塞进 539px 的格子就溢出。
#
# 教训与 R385 同一条, 而且是同一个错犯第二次:
# **`shape.trend` 为假并不意味着触发价也没有。** 名次与走势同进同出(`conv` 只收
# 有名次的), 而**触发价是第三个独立的东西** —— 「手上这些」那一档每行都有它,
# 「要动手」那一档反而没有(转折已成, 不再有待触发的线)。
#
# 这个 bug **断言 class 串是抓不到的** —— 类名全都在, 只是算术错了。真正抓到它
# 的是拿真浏览器量 `scrollWidth > clientWidth`。复现脚本的做法记在 FORK_NOTES
# R386 里: 拦 `/api/flip-paper` 喂一档有触发价的持仓行, 在 7 个宽度上逐行量。


# [R513] `test_R386_列数把触发价算进去了` 退役 —— 信号行那套定宽网格(ROW_GRID / RowShape / SignalRow)随 R513 整个删了: 用户「今日页面这个页面重做, 改的好看点, 不要折叠了」, 三段各换一种长相(卡片 / 方块 / 密排行), 不再是一张对齐的长表。新版面的守卫在 test_flip_signals_r513.py


# [R513] `test_R386_触发价按这一组算_不是整屏` 退役 —— 信号行那套定宽网格(ROW_GRID / RowShape / SignalRow)随 R513 整个删了: 用户「今日页面这个页面重做, 改的好看点, 不要折叠了」, 三段各换一种长相(卡片 / 方块 / 密排行), 不再是一张对齐的长表。新版面的守卫在 test_flip_signals_r513.py


# [R513] `test_R386_触发价那一格仍然不换行` 退役 —— 信号行那套定宽网格(ROW_GRID / RowShape / SignalRow)随 R513 整个删了: 用户「今日页面这个页面重做, 改的好看点, 不要折叠了」, 三段各换一种长相(卡片 / 方块 / 密排行), 不再是一张对齐的长表。新版面的守卫在 test_flip_signals_r513.py


