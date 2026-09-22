"""[R343] 今日总览**融合进**模拟盘已有的卡片 —— 不新增任何区块。

用户: 「我的意思是融合进前面的卡片, 比如值得关注应用了评分系统的, 拿今天动手
是否可以排个序?类似这样的融合升级」。

R341 那一版做的是**挂一条补充带在底部**, 方向错了: 那还是"今日总览换了个位置",
不是融合。这一版把每一样东西都落进已有的位置, 补充带整个拆掉:

    市场状态  → 页头(姿态徽章 + 多空比/主线 进副标题)
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
    blk = _flip()
    blk = blk[blk.index("function SignalRow"):]
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
    """打分是**第二段**, 对六态选出来的**每一档**都生效 —— 不是只管其中一档。"""
    code = _flip()
    i = code.index("const rank = (r: FlipTodaySignal)")
    blk = code[i:code.index("return (", i)]
    assert blk.strip(), "切出来是空的, 下面的断言就全是摆设"
    assert "const byRank = (rs: FlipTodaySignal[]) => rs.slice().sort((a, b) => rank(a) - rank(b))" in blk, \
        "排序得是一处实现 —— 四档各写一遍必然漂"
    for tier in ("const ordered = byRank(live)",
                 "const mineSorted = byRank(mine)",
                 "const idleSorted = byRank(idle)"):
        assert tier in blk, f"这一档没参与二次排序: {tier}"


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
    order = ["<TodaySignals", "<Holdings", "<Skipped", "<Orders", "<Rules"]
    idx = [body.index(t) for t in order]
    assert idx == sorted(idx), f"版面顺序被动过: {order}"
    assert body.index("<Rules") == max(idx), "「规则排在最后」这一条被动了"
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
    # [R346] 主线要上色。[R421] 原品红按「全站禁止粉色」换成琥珀。
    # **停更要降级成灰并把标题改掉** —— 丢掉这一层, 一份几天前的主线会长得跟
    # 今天的一模一样, 那比不显示更糟。
    assert "text-amber-300" in head, "主线没上色(text-secondary 是灰阶不是颜色)"
    assert "mlStale ? 'text-muted' : 'text-amber-300'" in head, "停更没降级成灰"
    assert "主线(停更)" in head, "停更没在标题上说出来"
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
    row = code_of(FLIP)
    row = row[row.index("function SignalRow"):]
    assert "<ScoreCell o={c} rank={c.rank} total={c.rank_total ?? 0} />" in row


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


def test_R356_走势并进同一行_自成一列():
    """[R349 → R356] 用户: 「后面还有不少空间, 利用起来一行显示完整」。

    **R349 我把它放成第二行**, 理由是「六态那句说要不要动手, 走势说凭什么是这一只,
    挤在同一行读的人得先分清哪句是哪套」。那条理由没有错, 但**分列同样能分清** ——
    而分行的代价是行高随内容变(见下一条), 那个代价更大。

    所以现在它是**网格的第五列**: 与六态那句各占一格, 界线由栅格划, 不由换行划。
    """
    row = _row()
    assert "<TrendCell o={c} />" in row
    # 它在网格里, 不再是网格之外的第二行
    grid = row[row.index("<div className={cn("):]
    assert "<TrendCell o={c} />" in grid, "走势跑到网格外面去了 —— 那就又是第二行"
    assert "pl-[22.25rem]" not in row, "还留着第二行那套缩进"
    # 六态那句仍然在它自己的格子里, 排在走势之前
    assert row.index("已转折 · 现在是") < row.index("<TrendCell"), "顺序变了"


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


def test_R356_行高定死_不随有没有走势变():
    """**用户的第二件事**: 「每行个股行高要一样」。(R383 起是"整屏统一决定撑不撑")

    名次那一格本身有三行高(名次 / 分 / 三条维度条), 而没进候选池的票只有两行字
    —— 不定死的话, **行高就跟着"这只票有没有进候选池"变**, 一屏扫下去参差不齐。
    """
    row = _row()
    grid_cls = _grid_class(row)
    # [R366] **带上 `sm:` 前缀断言。** 手机上折成了卡片式, 行高本来就随内容 ——
    # 那儿定死反而会在只有两行字时留一截空。裸写 `"min-h-[3.5rem]"` 的话,
    # `sm:min-h-[3.5rem]` 也含着它, 断言分不出这两件事(锚是别人的子串, 又一次)。
    # [R383] **这一条现在是有条件的, 守卫跟着说清楚。**
    #
    # 立论没变 —— 「行与行一样高」。但撑行高的理由只在**真有名次**时存在:
    # 名次那一格三行高, 所以要把没名次的行也垫到同样高度。整屏一个名次都没有时
    # (用户实机就是这样: 32 行全是「没进候选池」), 每行只有两行字, 再垫到
    # 3.5rem 就是每行白送 26px —— 32 行八百多像素的滚动, 垫的是"和谁一样高"?
    #
    # 所以判据是: **撑不撑由整屏统一决定(`shape.rank`), 不是每行各自算。**
    # 后者才会真的出现"行高跟着这只票有没有进候选池变", 那正是 R356 要挡的。
    assert "shape.rank && 'sm:min-h-[3.5rem]'" in grid_cls, \
        "行高要么没了, 要么改成每行各自算 —— 后者正是 R356 挡的那件事"
    # **`items-center` 必须钉在网格那个 div 自己身上。** 只查 `"items-center" in row`
    # 是不够的 —— 动作徽标那几个 span 用的是 `inline-flex items-center`, 断言会被
    # 它们喂饱, 于是把网格上的这个类删掉守卫照样是绿的(变异电池当场抓到)。
    # 「锚太宽 = 没有锚」, 本会话第七次。
    assert "sm:items-center" in grid_cls, "内容没垂直居中, 定了高也会看着歪"


def test_R356_把右边那片空地用上():
    """[R350 → R356] R350 我加了 `max-w-[72rem]` 防止一行横贯两米;
    用户看了实机说「后面还有不少空间, 利用起来」—— 那道限宽因此撤掉,
    多出来的宽度给了走势那一列。"""
    row = _row()
    assert "max-w-[72rem]" not in row, "还限着宽, 右边那片空地没用上"
    # 六列。[R360] 名次挪到了最前(用户: 「这列内容统一放到股票名称前面」):
    #   名次 / 标的 / 动作 / 六态 / 走势 / 触发价
    # [R381] 六态那一列的上限 9rem → 16rem。**立论一个字没变**(把空地用上),
    # 只是发现还有一处没用上: 9rem 装不下「按现价会转折 —— 收盘还站在这边才算数」,
    # 左边在截字、右边那格空着六百像素。细节与变异见 test_R381_六态那句话能显示完整。
    # [R383] 这一串搬进了 `ROW_GRID`, 所以从 `_grid_class` 里查。它现在是
    # **走势有内容**时的那一套; 整屏没走势时另有一套把那一格收成 0。
    assert "sm:grid-cols-[3.5rem_minmax(9rem,11rem)_4.5rem_minmax(7rem,16rem)_minmax(0,1fr)_auto]" \
        in _grid_class(row), "宽屏那套列宽变了 —— 定宽网格是行与行对齐的前提"


def test_R356_没进候选池时走势格空着但占位():
    """格子不占位的话, 后面的触发价列会整体错开一格。

    **锚必须是代码, 不能是注释** —— `code_of()` 会把注释整片剥掉(这是它的本职:
    注释里写什么都不算数)。拿注释文字当切片锚, 切出来的要么报 `substring not
    found`, 要么是个空串而让下面的断言恒真。本会话已经在这上面栽过两次。
    """
    row = _row()
    # 空着时**格子还在**: 条件挂在 `{c && …}` 上, 而不是整个 <span> 上
    assert '{c && <TrendCell o={c} />}' in row, "走势那一格不由 c 决定渲不渲染"
    # 条件挂在 `{c && …}` 上, **不是整个 <span> 上** —— 套在外面就不占位了。
    i = row.index("{c && <TrendCell o={c} />}")
    before = row[:i]
    assert before.rstrip().endswith(">"), "走势那一格的 <span> 没包住它 —— 空着时不占位"
    # [R400] 原来这一行锚的是 `text-[11px]` —— 而那个字号只是**当时**的写法,
    # 3.2 把它换成规范档位 `text-micro` 时这条就红了, 可它要钉的"占位"一点没变。
    # 钉性质: 包住它的那个 <span> 占满走势那三列, 且不许被内容撑开。
    span_open = row[:i].rstrip()
    assert span_open.endswith(">"), "走势那一格的 <span> 没包住它 —— 空着时不占位"
    tag = span_open[span_open.rindex("<span"):]
    assert "col-span-3" in tag, f"走势那一格不再占满三列, 后面的列会整体错开: {tag}"
    assert "min-w-0" in tag, f"走势那一格会被内容撑开, 定宽网格就不成立了: {tag}"


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


def test_R350_信号行是定宽网格_不是flex():
    """列宽固定, 行与行天然对齐, 一列能扫到底。

    (R350 的起因: 原来是 flex + 触发价上一个 `ml-auto`, 宽屏上价格被甩到最右、
    中间空一条, 而各行按自己内容宽度排, 列也对不齐。**这一条立论没变**,
    只是列数从五变六 —— 见 `test_R356_把右边那片空地用上`。)
    """
    row = _row()
    assert "ml-auto" not in row, "ml-auto 会把最后一列甩到屏幕最右, 中间空一条"
    # [R366] **两处**: 窄屏那张卡片栅格 + `sm:` 起那张六列。立论没变(仍然是
    # 定宽网格而不是 flex), 只是同一个 div 上挂了两套。**不许再多**: 第三套
    # 意味着又有一个宽度区间是谁也没看过的。
    # [R383] 宽屏那套挪进了 `ROW_GRID`, 所以从「行 + 那张表」一起数。
    # 窄屏 1 套 + 宽屏 2 套(走势有/无), 共 3 套。**不许再多**: 第四套意味着
    # 又有一个宽度区间是谁也没看过的。
    # [R384] 名次那一列也能收成 0 了, 于是 `ROW_GRID` 变成 2×2 = 4 套
    # (名次有/无 × 走势有/无), 每套自带窄屏与宽屏两段。**不许再多**: 第五套
    # 意味着又有一个组合是谁也没看过的。
    cls = _grid_class(row)
    assert cls.count("sm:grid-cols-[") == 4, f"宽屏栅格不是四套: {cls.count('sm:grid-cols-[')}"
    assert cls.count("grid-cols-[") == 8, "窄屏那四段没跟着配齐(每套都要有窄屏+宽屏)"


def test_R350_名次那一格空着也占位():
    """有名次的行和没名次的行, 后面所有列都得对齐。"""
    row = _row()
    assert ") : <span />}" in row, "没名次时要留一个空占位, 不能整格不渲染"


# [R350 → **R356 退役**] `test_R350_走势行缩进对齐到状态文字那一列` 钉的是
# 走势作为**第二行**时的缩进量。R356 把它并进同一行自成一列, **那个缩进不存在了**
# —— 它没有可守的对象了, 而不是被绕过去。对齐现在由栅格保证, 见
# `test_R356_把右边那片空地用上` 里那条列宽断言。



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
    # **对照组**: 「定时个股信号」的产出仍然显示在决策台的「AI 信号」列上, 它留着。
    # 不能拿裸四个字当锚 —— 这四个字也出现在 toast 文案里(`定时个股信号已开启:...`),
    # 那样把开关整个删掉照样绿。
    #
    # [R400] 原来锚的是 `<span className="whitespace-nowrap">定时个股信号</span>`,
    # 而 3.2 把这个 label 收进了 `<Field label={…}>` —— **标记变了, 开关一点没变**。
    # 改钉那个真正不可少的东西: 这四个字必须挂在一个 checkbox 上。
    # 逐个看每一处「定时个股信号」, 只要**有一处**是挂在勾选框上的就算数 ——
    # 第一处恰好是 toast 文案(正是上面说的那个陷阱), 拿 `index()` 取会误判。
    hits = [m.start() for m in re.finditer("定时个股信号", ctrl)]
    assert hits, "这个开关有活的展示面(决策台 AI 信号列), 不该被误删"
    assert any('type="checkbox"' in ctrl[max(0, i - 900):i] for i in hits), \
        "「定时个股信号」没有一处挂在勾选框上 —— 剩下的可能只是 toast 文案"
    assert "signalAiSchedMut.mutate({" in ctrl, "开关得真的能落库"


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
    code = code_of(FLIP)
    assert "extra={cardBody}" in code, "模拟盘没把那一块接到插槽上"


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
    """
    code = code_of(FLIP)
    blk = code[code.index("{ov\n"):code.index("{q.isLoading &&")]
    assert blk.strip()
    assert "{cardBody}" in blk, "ov 拿不到时这一块没有退路, 会整块消失"
    # [R359] 退路里装的必须是**同一个** `cardBody` —— 另写一份等于两套版面,
    # 改了一边忘了另一边只有在打分那层挂掉时才看得见, 那时没人在看。
    assert blk.count("cardBody") == 2, "两条渲染路径没共用同一块内容"


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
    for inp in ("<input", "NumberField", "onChange="):
        assert inp not in head, f"页头右槽里出现了输入: {inp}"
    # 标题那一行**留在页头**, 这是用户点的名(「标题行留在外面」)。
    # 锚带上行首的换行与缩进: 光写 `titleExtra={w && (` 的话, 改名成
    # `xtitleExtra=` 照样含着这段, 断言过得去(变异电池当场打绿)。
    assert "\n        titleExtra={w && (" in head, "标题行被一起搬走了 —— 用户要它留在外面"
    assert "\n        subtitle={w" in head, "副标题(多空比/主线)也被搬走了"


def test_R359_参数条紧挨着它算出来的东西():
    """本金 / 最多持有 / 回溯**就是算出下面那些数字的那三个输入**。"""
    code = code_of(FLIP)
    body = code[code.index("const cardBody = ("):code.index("const w = ov?.weather")]
    assert body.strip()
    assert body.index("<ParamBar") < body.index("{summary}"), "参数条没排在成绩上方"


def test_R359_参数条不跟着成绩一起消失():
    """**跑不动的时候正是最需要这三个框的时候。**

    `summary` 在 `d` 没有或 `reason` 非空时是 null —— 而回溯填过头、本金填成 0
    这类毛病, 修的办法就是改这三个框。把参数条塞进 `Summary` 里, 出错时它会跟着
    一起不见, 于是**没有任何办法把页面救回来**, 只能去清 localStorage。
    """
    code = code_of(FLIP)
    body = code[code.index("const cardBody = ("):code.index("const w = ov?.weather")]
    assert body.strip()
    assert "<ParamBar" in body, "参数条不在 cardBody 这一层"
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
    """它回答的是「凭什么是这一只」—— **那个问题得在读到代码之前就摆在眼前**。

    原来它夹在动作与六态中间: 眼睛先认票、再看要不要动手, 最后才补上理由。
    现在名次先到, 一列扫下去就是一份从强到弱的名单。
    """
    row = _row()
    i_rank = row.index("{c?.rank != null ? (")
    i_sym = row.index("<SymbolCell symbol={r.symbol}")
    i_act = row.index("r.act === 'buy' ? '买入' : '清仓'")
    assert i_rank < i_sym < i_act, "名次 / 标的 / 动作 三者的次序不对"
    # 列宽也得跟着挪 —— 只换 JSX 不换栅格, 名次会去占标的那 9~11rem,
    # 而标的被挤进 3.5rem 里截成一两个字。**两处必须同时改**。
    # [R366] 两套栅格的第一列**都**得是名次那 3.5rem —— 只改一套的话, 另一个
    # 宽度区间里名次会去占标的的位置, 而那个区间没人看过。
    cols = [c for c in _grid_class(row).split() if "grid-cols-[" in c]
    assert len(cols) == 8, f"栅格不是四套(每套窄屏+宽屏两段): {cols}"
    # [R384] 第一列**要么是名次那 3.5rem, 要么是 0**(整屏一个名次都没有时它收掉)。
    # **立论没变**: 名次仍然是第一格, 挪 JSX 就必须挪栅格。加的是那个 0 ——
    # 而 `0` 恰恰只有"名次在第一列"才讲得通: 它收掉的就是名次那一列。
    for c in cols:
        body = c[c.index("grid-cols-["):]
        assert body.startswith("grid-cols-[3.5rem_") or body.startswith("grid-cols-[0_"), \
            f"第一列既不是名次那 3.5rem 也不是收掉的 0 —— JSX 挪了栅格没挪: {c}"
    # 四套里必须**两种都有** —— 只剩 3.5rem 说明收不掉了, 只剩 0 说明名次没位置了
    assert any("[3.5rem_" in c for c in cols) and any("[0_" in c for c in cols), \
        "名次那一列要么永远占着要么永远没有 —— 两种都得在"


def test_R360_名次空着时照样占住第一格():
    """[R350 立论照搬] 空着不占位的话, 后面**所有**列整体左移一格 ——
    而它现在是第一格, 错开的就不只是它后面几列, 是整行。"""
    row = _row()
    assert ") : <span />}" in row, "没名次时要留一个空占位"
    # 空占位必须仍在第一格 —— 即在 SymbolCell 之前
    assert row.index(") : <span />}") < row.index("<SymbolCell symbol={r.symbol}")


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
    for label in ("现在拿着", "最后一天", "总收益", "最大回撤", "完整买卖", "胜率"):
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
    assert row.index('label="现在拿着"') < row.index('label="总收益"'), "次序反了"
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
    """[R363 → R364] 用户: 「还是别点买入了, 点「已转折 · 现在是自然回升」这样更合理」。

    **两列点开的不是同一张表**, 这正是决策台 R51 立下的规矩:

        标的那格   这只票现在贵不贵、关键价位在哪  → 关键价位(日 K)
        六态那句   这个状态是怎么走到今天的        → 逐日复盘(趋势页)

    R363 我把复盘那个入口挂在了**动作**那一格上, 还为此写了一整段"别让它看起来
    像下单按钮"的辩解。用户直接把它挪开了 —— **要辩解才站得住的设计, 多半本来
    就不该那么放**。挪到六态那句上反而更对得上内容。
    """
    row = _signal_row()
    assert row.count("onClick={() => onOpen(r.symbol, r.name)}") == 1, "标的那格的入口不止一个"
    assert row.count("onClick={() => onReview(r.symbol, r.name)}") == 1, "复盘入口不止一个"
    i_sym = row.index("<SymbolCell symbol={r.symbol}")
    i_state = row.index("已转折 · 现在是")
    i_open = row.index("onClick={() => onOpen(r.symbol, r.name)}")
    i_review = row.index("onClick={() => onReview(r.symbol, r.name)}")
    assert i_open < i_sym, "关键价位那个入口没包住标的那一格"
    assert i_sym < i_review < i_state, "复盘那个入口没包住六态那一句"


def test_R364_两个入口开的不是同一个弹窗():
    """合成一个弹窗的话, 这两列就白分了 —— 那正是 R51 当初要挡的事。"""
    code = code_of(FLIP)
    assert "<LevelsDialog" in code and "<StockReviewDialog" in code
    assert 'tab="trend"' in code, "复盘没落在趋势状态那一页 —— 六态那句问的是状态怎么走的"
    # 两个弹窗**各存各的 state**: 合成一个带 kind 的, "开着哪一个"与"开的是哪只票"
    # 就绑死在一起, 而它们本来是两条互不相干的路
    assert "const [levels, setLevels]" in code and "const [review, setReview]" in code


def test_R363_弹窗挂在这一层_不是每行一个():
    """三档几十上百行, 每行各挂一个就是几十上百个常驻的 AnimatePresence 与
    Esc 监听 —— 而同一时刻只可能开着一个。"""
    code = code_of(FLIP)
    assert code.count("<LevelsDialog") == 1, "弹窗挂了不止一处"
    row = _signal_row()
    assert "<LevelsDialog" not in row, "弹窗挂进了每一行"
    seg = code[code.index("function TodaySignals"):]
    assert "<LevelsDialog" in seg, "弹窗没挂在 TodaySignals 这一层"


def test_R363_点开是弹窗_不是跳走():
    """跳走之后回来, 折叠状态、滚动位置、这一屏的上下文全没了。"""
    row = _signal_row()
    for leave in ("navigate(", "href=", "window.open", "/stock-analysis?symbol="):
        assert leave not in row, f"信号行上出现了跳页: {leave}"


def test_R364_动作那一格根本不可点():
    """[R363 → R364] **这条守卫变强了, 不是被放松。**

    R363 钉的是「动作那一格可以点, 但不许长得像个下单按钮」—— 要靠一句 title
    和"不加按钮外观"撑着。用户看过实机后直接把入口挪走了, 于是现在钉的是最强的
    那一版: **它根本不可点**。

    理由没变, 只是更彻底: 这一格里印着「买入」两个字, 任何可点的迹象都在暗示
    "点它就下单" —— 而这一页从来不下单, 也永远不会。

    (R329 那条铁律本身另有守卫: 能不能出手只由 `actionable` 决定。这一条钉的是
    **别让它连"像个动作"都不许**。)
    """
    row = _signal_row()
    i_act = row.index("{actionable ? (")
    # 边界取**六态那一格的 `<button` 起始**, 不是那句话本身 —— 那句话在按钮
    # 里面, 拿它当界会把六态自己的 `<button ... cursor-pointer>` 一起圈进来,
    # 于是这条守卫会指着隔壁那一格喊"动作又能点了"。(第一版就是这么红的。)
    i_next = row.index('<button type="button" onClick={() => onReview')
    seg = row[i_act:i_next]
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


def test_R366_信号行窄屏折成卡片_而不是另写一份():
    """六列那条最窄也要 ≈444px, 而手机竖屏是 390px —— 横向必然撑破。

    **没有另写一份手机版的行**: 六个格子、次序、内容全都没动, 只是窄屏换一张
    三列的栅格, 靠 row-span / col-span 让它们自己落成一张卡。另写一份的代价是
    两套版面各自演化, 哪天只改了一边, 手机上看到的与电脑上不是同一件事,
    而两边都不报错。
    """
    row = _signal_row()
    cls = _grid_class(row)
    assert "grid-cols-[3.5rem_minmax(0,1fr)_auto]" in cls, "窄屏那套栅格没了"
    assert "sm:grid-cols-[" in cls, "宽屏那套栅格没了"
    # 名次竖跨两行, 六态横跨两列, 走势/触发价各占一整行 —— 这几样缺一样卡就散了
    assert "row-span-2 sm:row-span-1" in row, "名次没竖跨 —— 右边两行会挤掉它"
    assert "col-span-2 min-w-0 cursor-pointer" in row, "六态没横跨标的+动作那两列"
    assert row.count("col-span-3") == 2, "走势与触发价没各占一整行"
    # **只有一个 SignalRow** —— 没有手机版分身
    code = code_of(FLIP)
    assert code.count("function SignalRow") == 1, "又写了一份手机版的信号行"


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


def test_R381_六态那句话能显示完整():
    """9rem = 144px 装不下「按现价会转折 —— 收盘还站在这边才算数」, 盘中越线
    那几行一直被截成「…收盘还...」 —— 而截掉的正是这一档唯一要说的话。

    **仍然是定宽列, 不是 `1fr`**: 行与行要对齐, 这是 R350 定的。
    """
    from tests.frontend_source import code_of
    code = code_of("pages/FlipPaper.tsx")
    assert "sm:grid-cols-[3.5rem_minmax(9rem,11rem)_4.5rem_minmax(7rem,16rem)_minmax(0,1fr)_auto]" in code, \
        "六态那一列的宽度被改回去了(或整条栅格被动过)"
    # 窄屏那条一个字没动 —— R366 的卡片式布局靠它
    assert "grid-cols-[3.5rem_minmax(0,1fr)_auto]" in code, "窄屏栅格被动了"


def test_R381_现在拿着与成交流水在宽屏并排():
    """两张都是 `min-w-[640px]` 的窄表, 各占一整行时右边一半是空的。

    断点 1560 是算出来的: 内容区 ≈ 视口 − 侧栏 224 − 留白 32, 两列 640 + 12
    的间隙要 1292 → 视口 ≥ 1548。**窄了也不会坏** —— 两张表自带
    `overflow-x-auto`, 最坏是卡片内部出现横向滚动条。
    """
    from tests.frontend_source import code_of
    code = code_of("pages/FlipPaper.tsx")
    i = code.index("<TodaySignals")
    blk = code[i:code.index("<Rules", i)]
    assert blk.strip()
    assert "min-[1560px]:grid-cols-2" in blk, "并排那层栅格没了"
    # 左列装两块(拿着 + 没做成), 右列装流水 —— 左列只装一块的话会空掉一大截
    left = blk[blk.index('className="min-w-0 space-y-3"'):]
    left = left[:left.index("</div>")]
    assert "<Holdings" in left and "<Skipped" in left, "左列没把「没做成」收进来"
    assert "<Orders" not in left, "流水跑到左列去了"


def test_R381_规则与没做成都改成多列():
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

    skipped = code[code.index("function Skipped("):]
    skipped = skipped[:skipped.index("\nfunction ")]
    assert skipped.strip()
    # **列数只到 2**: 这一块活在半幅左列里, 而 sm:/xl: 量的是视口不是它自己的宽度
    assert "sm:grid-cols-2" in skipped, "没做成那几条没排成两列"
    assert "grid-cols-3" not in skipped and "grid-cols-4" not in skipped, \
        "列数又往上加了 —— 它在半幅列里, 视口断点在这儿是假的"


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


def test_R385_分界线是每一行进没进候选池():
    """**R383/R384 的判据("整屏一行都没有才收")被实机打脸。**

    用户那一屏 32 行里 3 行有名次与走势、29 行两样都没有 —— 于是 3 行把 29 行
    全拖住: 29 行陪着撑 56px 的行高、陪着空出 `1fr` 那一整列走势。
    **混着才是常态**, "整屏"那个判据几乎永远不成立。

    而这两类行本来就该分开: `conv` 只收 `rank != null` 的, 走势也只在有 `c` 时
    渲染 —— **名次与走势永远同进同出**。这条守卫先把那个前提钉住, 再钉分组。
    """
    code = code_of(FLIP)
    # 前提: conv 只收有名次的 —— 这是"两样同进同出"的来源
    i = code.index("const conv = useMemo(")
    blk = code[i:code.index("}, [ov])", i)]
    assert "if (o.rank == null) continue" in blk, \
        "conv 收了没名次的条目 —— 那么「名次与走势同进同出」就不成立了, 分组的前提没了"
    row = _row()
    assert "{c && <TrendCell o={c} />}" in row, "走势不再由 c 决定 —— 同上"

    sig = _signals()
    assert "const FULL: RowShape = { rank: true, trend: true }" in sig, "进了候选池那一组的形状没了"
    assert "const PLAIN: RowShape = { rank: false, trend: false }" in sig, "没进那一组的形状没了"
    # 分组判据就是 conviction.has, 不掺别的
    i = sig.index("const renderRows = (list: FlipTodaySignal[]) => {")
    blk = sig[i:sig.index("\n  }", i)]
    assert blk.strip()
    assert "list.filter((r) => conviction.has(r.symbol))" in blk, "上半组不是「进了候选池」"
    assert "list.filter((r) => !conviction.has(r.symbol))" in blk, "下半组不是「没进候选池」"
    assert "shape={FULL}" in blk and "shape={PLAIN}" in blk, "两组没各用各的形状"
    # 没进的那一组不传 c —— 传了就会去渲染走势, 而它那一列已经收成 0
    assert re.search(r"<SignalRow r=\{r\} shape=\{PLAIN\}", blk), \
        "没进候选池那一组还在传 c —— 走势那一列已经收成 0, 渲染出来会溢出"


def test_R385_三段都走同一个分组函数():
    """三段各写一遍的话, 「要动手」分了组而「只是盯着」没分, 同一张卡里两种版面。"""
    sig = _signals()
    for seg in ("renderRows(ordered)", "renderRows(mineSorted)", "renderRows(idleSorted)"):
        assert seg in sig, f"少了 {seg}"
    assert sig.count("<SignalRow") == 2, \
        "SignalRow 不是只在 renderRows 里渲染了两处(进/没进各一处) —— 有人又在别处单独渲染"


def test_R385_没进候选池那组排三列():
    """行只剩 标的/动作/六态 ≈560px, 宽屏上排三列; 1180 起先排两列。"""
    sig = _signals()
    assert "min-[1180px]:grid min-[1180px]:grid-cols-2" in sig, "两列那一档没了"
    assert "min-[1560px]:grid-cols-3" in sig, "三列那一档没了"
    # 竖缝: 两列时左列画, 三列时前两列画、最右不画
    assert "i % 2 === 0 && 'min-[1180px]:border-r" in sig, "两列的竖缝没了"
    assert "(i + 1) % 3 === 0 && 'min-[1560px]:border-r-0'" in sig, "三列时最右一列还在画竖缝"


def test_R384_名次那列在没进候选池那一组里收成0():
    """同一句话说 32 遍不是信息是噪音 —— 它该在区块标题上说一次。

    (名字里原来写的是"整屏没名次" —— [R385] 判据改成按行分组之后那个说法不成立了,
    现在是"没进候选池那一组"。**四套模板本身一个字没动**, 变的是谁来挑。)

    **收成 0 而不是不渲染那一格**: 窄屏那套卡片版面(R366)靠 `row-span-2` /
    `col-span-3` 把六个格子折成一张卡, 抽掉一格整套跨行跨列全要重算。
    """
    code = code_of(FLIP)
    i = code.index("const ROW_GRID = {")
    table = code[i:code.index("} as const", i)]
    assert table.strip()
    # **逐条切出来查, 不是在整张表里找一次。**
    # 第一版写成 `for key in (...)` 里两次断言同一个字符串 —— 与 key 无关,
    # 于是只改回其中一条照样绿(变异 M1 当场抓到)。「锚太宽 = 没有锚」。
    entries = dict(re.findall(r"'([a-z ]*)': '([^']+)'", table))
    assert set(entries) == {"rank trend", "rank", "trend", ""}, f"四套键对不上: {sorted(entries)}"
    for key in ("trend", ""):          # 没名次的那两套
        v = entries[key]
        assert "grid-cols-[0_minmax(0,1fr)_auto]" in v, f"{key!r} 那套窄屏没收掉名次列"
        assert "sm:grid-cols-[0_minmax(9rem,11rem)_" in v, f"{key!r} 那套宽屏没收掉名次列"
    for key in ("rank trend", "rank"):  # 有名次的那两套要占住 3.5rem
        v = entries[key]
        assert "grid-cols-[3.5rem_minmax(0,1fr)_auto]" in v, f"{key!r} 那套窄屏把名次列收掉了"
        assert "sm:grid-cols-[3.5rem_minmax(9rem,11rem)_" in v, f"{key!r} 那套宽屏把名次列收掉了"
    row = _row()
    # 0 宽的格子里不许再写字 —— 会溢出到隔壁
    assert "actionable && shape.rank ? (" in row, \
        "整屏没名次时还在往 0 宽的格子里写「没进候选池」"


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


def test_R384_行留白跟着名次走():
    """名次那一格是三行高, 留白撑着才不挤; 没名次时行只有两行字,
    `py-2.5`(上下各 10px)在 40px 的栅格上占掉三分之一。"""
    row = _row()
    assert "shape.rank ? 'py-2.5' : 'py-1.5'" in row, "行留白没跟着 shape 走"


def test_R384_网格类只有一个产地():
    """div 上写死一个、模板再给一个, 同一个元素上就有两个 `grid-cols-` ——
    **而 CSS 里谁赢取决于样式表里谁排后面, 不是 class 串里谁排后面**。
    那种冲突不报错, 只表现为「某些情况下列宽莫名其妙」。(这条是数 grid-cols
    条数时当场抓到的, 不是想出来的。)"""
    row = _row()
    m = re.search(r"<div className=\{cn\(\s*\n?\s*'grid ", row)
    assert m
    head = row[m.start():row.index(")}>", m.start())]
    assert "grid-cols-[" not in head, "网格那个 div 上又写死了列宽"
    assert "gridOf(shape)" in head, "没去 ROW_GRID 挑模板"


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


def test_R386_列数把触发价算进去了():
    """没触发价 ≈560px → 1180 起两列、1560 起三列;
    有触发价 ≈740px → 1560 起两列, **三列直接放弃**(要 ≥2560 的视口)。"""
    sig = _signals()
    i = sig.index("const plainCols = (hasPrice: boolean) =>")
    blk = sig[i:sig.index("const plainCell", i)]
    assert blk.strip()
    assert "hasPrice" in blk, "列数没看触发价"
    # 有触发价那一支: 只到两列, 且断点是 1560(不是 1180)
    assert "'min-[1560px]:grid min-[1560px]:grid-cols-2'" in blk, \
        "有触发价时不是「1560 起两列」"
    hi = blk[blk.index("?"):blk.index(":", blk.index("?"))]
    assert "grid-cols-3" not in hi, "有触发价还排三列 —— 那正是撑破格子的那一版"
    # 没触发价那一支照旧三列 —— 不能因为修这个 bug 把另一支也降级
    lo = blk[blk.index(":", blk.index("?")):]
    assert "min-[1560px]:grid-cols-3" in lo, "没触发价那一支的三列被顺手砍了"


def test_R386_触发价按这一组算_不是整屏():
    """「要动手」那档没有触发价(转折已成), 「手上这些」那档每行都有 ——
    两档因此列数不同。按整屏算的话, 一档有触发价就把另一档也拖成两列。"""
    sig = _signals()
    i = sig.index("const renderRows = (list: FlipTodaySignal[]) => {")
    blk = sig[i:sig.index("\n  }", i)]
    assert "const plainHasPrice = plain.some((r) => r.flip_price != null)" in blk, \
        "触发价不是从这一组的行里算的"
    assert "plainCols(plainHasPrice)" in blk and "plainCell(i, plainHasPrice)" in blk, \
        "算出来的 plainHasPrice 没真的用上"


def test_R386_触发价那一格仍然不换行():
    """`whitespace-nowrap` 是它宽度需求的来源 —— 去掉它「触发 45.85 · 现 46.23」
    会在窄格里折行, 行高就跟着这一格变, 而 R356 定的是「每行个股行高要一样」。
    所以它不许换行, 该让**列数**去适应它, 不是反过来。"""
    row = _row()
    i = row.index("触发 {r.flip_price.toFixed(2)}")
    head = row[:i]
    j = head.rindex("<span className=")
    assert "whitespace-nowrap" in head[j:], "触发价那一格可以换行了 —— 行高会跟着它变"
