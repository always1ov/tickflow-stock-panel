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
TODAY = "pages/Today.tsx"
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
    order = ["<TodaySignals", "<Summary", "<NavChart", "<Holdings", "<Orders", "<Skipped", "<Rules"]
    idx = [body.index(t) for t in order]
    assert idx == sorted(idx), f"版面顺序被动过: {order}"


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
    assert "AI 导读" in head, "AI 导读也收进页头"


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
    for page in (TODAY, FLIP):
        code = code_of(page)
        assert "from '@/components/today/TodayHealthBar'" in code, f"{page} 没复用那一处"
        assert "function TodayHealthBar" not in code, f"{page} 自己又写了一份"


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

    for rel in (FLIP, TODAY):
        code = code_of(rel)
        assert "useTodayOverview()" in code, f"{rel} 没走共用 hook"
        assert "queryKey: QK.todayOverview" not in code, f"{rel} 自己又抄了一份查询"


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
    for page in (FLIP, "components/today/OpportunityTable.tsx"):
        code = code_of(page)
        assert "from '@/components/today/ScoreCell'" in code, f"{page} 没复用那一处"
        assert "function ScoreCell" not in code, f"{page} 自己又写了一份"


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
