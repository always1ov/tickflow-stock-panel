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
    order = ["<TodaySignals", "<Holdings", "<Orders", "<Skipped", "<Rules"]
    idx = [body.index(t) for t in order]
    assert idx == sorted(idx), f"版面顺序被动过: {order}"
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
    # [R346] 主线用品红, 沿用今日总览那张卡的语义(那儿是 fuchsia)。
    # **停更要降级成灰并把标题改掉** —— 丢掉这一层, 一份几天前的主线会长得跟
    # 今天的一模一样, 那比不显示更糟。
    assert "text-fuchsia-300" in head, "主线没上色(text-secondary 是灰阶不是颜色)"
    assert "mlStale ? 'text-muted' : 'text-fuchsia-300'" in head, "停更没降级成灰"
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
    grid = row[row.index('<div className="grid'):]
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
    """**用户的第二件事**: 「每行个股行高要一样」。

    名次那一格本身有三行高(名次 / 分 / 三条维度条), 而没进候选池的票只有两行字
    —— 不定死的话, **行高就跟着"这只票有没有进候选池"变**, 一屏扫下去参差不齐。
    """
    row = _row()
    grid_cls = _grid_class(row)
    assert "min-h-[3.5rem]" in grid_cls, "行高没定死"
    # **`items-center` 必须钉在网格那个 div 自己身上。** 只查 `"items-center" in row`
    # 是不够的 —— 动作徽标那几个 span 用的是 `inline-flex items-center`, 断言会被
    # 它们喂饱, 于是把网格上的这个类删掉守卫照样是绿的(变异电池当场抓到)。
    # 「锚太宽 = 没有锚」, 本会话第七次。
    assert "items-center" in grid_cls, "内容没垂直居中, 定了高也会看着歪"


def test_R356_把右边那片空地用上():
    """[R350 → R356] R350 我加了 `max-w-[72rem]` 防止一行横贯两米;
    用户看了实机说「后面还有不少空间, 利用起来」—— 那道限宽因此撤掉,
    多出来的宽度给了走势那一列。"""
    row = _row()
    assert "max-w-[72rem]" not in row, "还限着宽, 右边那片空地没用上"
    # 六列: 标的 / 动作 / 名次 / 六态 / 走势 / 触发价
    assert "grid-cols-[minmax(9rem,11rem)_4.5rem_3.5rem_minmax(7rem,9rem)_minmax(0,1fr)_auto]" in row, \
        "列宽变了 —— 定宽网格是行与行对齐的前提"


def test_R356_没进候选池时走势格空着但占位():
    """格子不占位的话, 后面的触发价列会整体错开一格。

    **锚必须是代码, 不能是注释** —— `code_of()` 会把注释整片剥掉(这是它的本职:
    注释里写什么都不算数)。拿注释文字当切片锚, 切出来的要么报 `substring not
    found`, 要么是个空串而让下面的断言恒真。本会话已经在这上面栽过两次。
    """
    row = _row()
    # 空着时**格子还在**: 条件挂在 `{c && …}` 上, 而不是整个 <span> 上
    assert '<span className="min-w-0 text-[11px]">\n          {c && <TrendCell o={c} />}' in row, \
        "走势那一格要么没占位(条件套在 span 外), 要么不由 c 决定渲不渲染"


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
    """
    i = row.index('<div className="grid')
    j = row.index('"', i + len('<div className="'))
    cls = row[i + len('<div className="'):j]
    assert "grid-cols-[" in cls, "切到的不是网格那个 div"
    return cls


def test_R350_信号行是定宽网格_不是flex():
    """列宽固定, 行与行天然对齐, 一列能扫到底。

    (R350 的起因: 原来是 flex + 触发价上一个 `ml-auto`, 宽屏上价格被甩到最右、
    中间空一条, 而各行按自己内容宽度排, 列也对不齐。**这一条立论没变**,
    只是列数从五变六 —— 见 `test_R356_把右边那片空地用上`。)
    """
    row = _row()
    assert "ml-auto" not in row, "ml-auto 会把最后一列甩到屏幕最右, 中间空一条"
    assert row.count("grid-cols-[") == 1, "只该有一处列宽定义"


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
    # 锚在**那个 label 的标记**上, 不是四个字 —— 这四个字也出现在 toast 文案里
    # (`定时个股信号已开启:...`), 拿裸字符串扫的话把开关整个删掉照样绿。
    assert '<span className="whitespace-nowrap">定时个股信号</span>' in ctrl, \
        "这个开关有活的展示面(决策台 AI 信号列), 不该被误删"
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
    assert "{extra && <div" in ctrl, "插槽没渲染"
    # 组件本身仍然对模拟盘一无所知
    for leak in ("FlipPaper", "monthly", "nav", "total_ret", "max_drawdown"):
        assert leak not in ctrl, f"模拟盘的数据结构漏进了这个共用组件: {leak}"
    code = code_of(FLIP)
    assert "extra={cardBody}" in code, "模拟盘没把那一块接到插槽上"


def test_R358_插槽与筛选条在同一张卡里():
    """用户要的就是"同一张卡"。卡壳必须包着**筛选条 + 插槽**两样。

    钉的是结构而不是某个类名: 插槽那个 div 在卡壳之内、筛选条之后, 中间有条
    分隔线。(旧版的卡壳直接长在筛选条那个 flex 容器上 —— 那种写法下插槽只能
    排在卡外面, 或者被当成 flex 的又一个横排项。)
    """
    ctrl = code_of(CTRL)
    shell = '<div className="rounded-card border border-border/60 bg-surface/40">'
    assert shell in ctrl, "卡壳没有单独一层"
    seg = ctrl[ctrl.index(shell):]
    i_row = seg.index('<div className="flex flex-wrap items-center gap-2 px-4 py-2">')
    i_extra = seg.index("{extra && <div")
    assert i_row < i_extra, "插槽跑到筛选条前面去了"
    assert "border-t border-border/40" in seg[i_extra:i_extra + 200], \
        "插槽与筛选条之间没有分隔线 —— 两块东西糊成一团"


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
    assert "right={" not in head, "页头右槽还在 —— 里面那三个框该搬走了"
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
