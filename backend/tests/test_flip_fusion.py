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


# ── 底线: 打分候选在结构上不可能成为动作 ────────────────────────────────
def test_R343_打分候选的act由构造恒为null():
    """**这是整组的地基, 而且比 R341 那版更硬。**

    R341 靠"另开一块 + 写明来源"划界 —— 那是**约定**, 改版面时会被顺手改掉。
    这一版靠构造: 合成行的 `act` 写死 `null`, 它**在结构上不可能**变成一个动作。
    """
    code = _flip()
    blk = code[code.index("const rows = useMemo<SignalRowData[]>"):]
    blk = blk[:blk.index("\n  }, [")]
    assert "act: null" in blk, "合成的打分候选行必须写死 act: null"
    assert "scoreOnly: true" in blk
    # **变异逼出来的**: 只钉 act 不够。把 stage 改成 'flipped' 照样 act=null、
    # 照样不可动手 —— 但行上会印出「已转折 · 现在是自然回升」, 那是**睁眼说瞎话**:
    # 它压根没转折。不可动手与不说谎是两件事, 得分别钉。
    assert "stage: 'watch' as const" in blk, \
        "合成行的 stage 必须写死 watch —— 它没转折, 不许显示成转折"
    # 名单来源只有两处: 后端给的信号 + 打分候选; 不许凭空冒出第三种
    assert "d?.today ?? []" in blk
    assert "ov?.opportunities ?? []" in blk


def test_R343_打分候选不冒充转折信号():
    """它既没转折也没到触发价边上 —— 行上就得这么写, 不许看起来像个信号。"""
    row = _signal_row()
    assert "r.scoreOnly ? (" in row
    assert "打分候选" in row
    assert "本页的出手依据只有转折" in row, "必须点明它不是出手依据"
    # 这一支里不许出现动作徽标
    badge = "r.act === 'buy' ? '买入' : '清仓'"
    seg = row[row.index("r.scoreOnly ? ("):]
    assert badge not in seg


def test_R343_打分不参与能不能动手():
    """**铁律。** 把握分只碰顺序与标注, 不许碰 `isLive` 那个判据。"""
    code = _flip()
    pred = next(l for l in code.splitlines() if "const isLive =" in l)
    for word in ("conviction", "rank", "score", "把握", "scoreOnly"):
        assert word not in pred, f"出手判据里混进了打分: {word}"


# ── 排序: 一条原则, 四档都照它办 ────────────────────────────────────────
def test_R343_六态排不出来了才让打分接手():
    """要动手那一档全都转折、`gap_pct` 全是 null —— 六态没有剩余信息了。
    另外三档每行都还有「离触发价多远」, 那是六态自己的读数, 轮不到打分说话。"""
    code = _flip()
    # `return (` 在 `const rank` **之前**就出现过(FlipPaper 主体), 用它当右界会切出
    # 空串, 而空串里什么都断言不到 —— 断言在空集合上恒真, 是这个仓库栽过的坑。
    i = code.index("const rank = (r: SignalRowData)")
    blk = code[i:code.index("return (", i)]
    assert blk.strip(), "切出来是空的, 下面的断言就全是摆设"
    assert "const ordered = live.slice().sort((a, b) => rank(a) - rank(b))" in blk, \
        "要动手那一档按名次排"
    # 盯着那一档: 有距离的在前(保持后端距离序), 合成的打分候选在后
    assert "Number(!!a.scoreOnly) - Number(!!b.scoreOnly)" in blk, \
        "合成的打分候选必须落在有距离的票之后"
    assert "a.scoreOnly ? rank(a) - rank(b) : 0" in blk, \
        "只有没距离的那些才靠名次互相排 —— 有距离的保持六态给的顺序"


def test_R343_只重排不增删():
    code = _flip()
    for line in ("const ordered = live.slice().sort(", "const idleSorted = idle.slice().sort("):
        assert line in code, f"少了 slice() 或排错了对象: {line}"
    assert "?? Number.MAX_SAFE_INTEGER" in code, "拿不到名次的排末尾, 不是被丢掉"


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
    for must in ("多 ${w.bull}/空 ${w.bear}", "转多 ${w.new_bull} 转空 ${w.new_bear}"):
        assert must in head, f"副标题少了「{must}」"
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
