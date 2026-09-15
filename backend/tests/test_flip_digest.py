"""[R341] 模拟盘底部的「补充 · 今日总览」—— 浓缩带。

用户: 「模拟盘现在有的东西都不能动了, **特别是就只看六态这个逻辑**, 想把今日总览
里面的东西浓缩到模拟盘里面显示, 当作补充」, 「全都要, 尽可能节省空间」。

这组守卫里最要紧的是 `test_R341_补充区一个动作徽标都不许有`:

搬过来的「值得关注」**判据与本页主线完全不同** —— 打分三维度加权 + 三道硬门槛,
再叠 AI 优选; 而模拟盘整页的身份是「只看六态转折」。两套判据同处一页, 最大的风险
不是占地方, 是**读的人以为它们是一回事**。所以补充区一个动作词都不许渲染。

R340 刚因为同一个道理删掉了今日总览的两块(「同一屏上摆两套互相不认的离场纪律,
读的人每天要先决定信哪一个 —— 那不是信息, 是负担」)。把机会区搬过来而不划清界线,
等于把刚清掉的问题原样搬了个家。
"""
from __future__ import annotations

from tests.frontend_source import code_of

DIGEST = "components/today/TodayDigest.tsx"
FLIP = "pages/FlipPaper.tsx"
HEALTH = "components/today/TodayHealthBar.tsx"
TODAY = "pages/Today.tsx"


# ── 底线: 补充区不许长出动作 ────────────────────────────────────────────
def test_R341_补充区一个动作徽标都不许有():
    """**这一条是整组的地基。** 判据不同的东西摆在同一页, 界线必须由结构划死。"""
    code = code_of(DIGEST)
    for word in ("'买入'", "'清仓'", "'卖出'", "act ===", "ACT_BUY", "ACT_SELL"):
        assert word not in code, f"补充区出现了动作词/动作判据: {word}"
    # 连"能不能动手"这个概念都不该在这个文件里存在
    assert "actionable" not in code


def test_R341_标题上写明判据不是六态():
    """光靠"我知道它不一样"是不够的 —— 每天读它的人不知道。"""
    code = code_of(DIGEST)
    assert "不是六态转折" in code, "必须在界面上点明判据来源与本页主线不同"
    assert "只作参考" in code


# ── 模拟盘原有的东西一个字没动 ──────────────────────────────────────────
def test_R341_对模拟盘是纯插入():
    """用户: 「模拟盘现在有的东西都不能动了」。"""
    code = code_of(FLIP)
    body = code[code.index("export function FlipPaper"):code.index("function TodaySignals")]
    # 原有六块顺序一字不变, 补充带排在它们全部之后、规则之前
    order = ["<TodaySignals", "<Summary", "<NavChart", "<Holdings", "<Orders",
             "<Skipped", "<TodayDigest", "<Rules"]
    idx = [body.index(t) for t in order]
    assert idx == sorted(idx), f"版面顺序被动过: {order}"


def test_R341_模拟盘主查询没被动过():
    """模拟盘那条 useQuery 一个参数都不该因为这几次改动而变。"""
    flip = code_of(FLIP)
    blk = flip[flip.index("const q = useQuery({"):flip.index("const rules = useQuery({")]
    assert "refetchInterval: refreshEvery('derived')" in blk, "模拟盘主查询的节奏被动了"
    assert "todayOverview" not in blk, "今日总览的数据不该混进模拟盘主查询"


def test_R342_今日总览那份数据只有一处定义():
    """[R342] 调用方从两个涨到三个 —— 各写一份 `useQuery` 迟早漂。

    **同一份数据两种刷新节奏的表现是「两个页面上同一个数字不一样」**, 而两边看上去
    都"没坏", 查起来极痛苦。所以节奏收到 `useTodayOverview` 一处, 调用方只准调它。
    """
    hook = code_of("lib/useSharedQueries.ts")
    blk = hook[hook.index("export function useTodayOverview"):]
    blk = blk[:blk.index("\n}")]
    assert "queryKey: QK.todayOverview" in blk
    assert "refetchInterval: (query) =>" in blk, "刷新间隔不是按状态算的函数"
    assert "?.live" in blk and "inRealtimeWindow()" in blk, "两件事要同时看"
    assert "60_000" in blk and "60 * 60 * 1000" in blk, "两档节奏不全"

    for rel in (DIGEST, FLIP, TODAY):
        code = code_of(rel)
        assert "useTodayOverview()" in code, f"{rel} 没走共用 hook"
        assert "queryKey: QK.todayOverview" not in code, f"{rel} 自己又抄了一份查询"
    assert "refreshEvery(" not in code_of(DIGEST), \
        "别给它套模拟盘那套档位 —— 这不是模拟盘的数据"


# ── 省空间 ──────────────────────────────────────────────────────────────
def test_R341_默认收起_且收起时折叠条本身就是摘要():
    """用户: 「尽可能节省空间」。

    **不展开也要拿得到结论** —— 否则就是"给个标题让人点开才知道有没有内容",
    那省的不是空间, 是把信息藏起来了。
    """
    code = code_of(DIGEST)
    assert "storage.flipDigestOpen.get(false)" in code, "默认收起"
    assert "storage.flipDigestOpen.set(!v)" in code, "改了要落盘, 否则刷新就忘"
    head = code[code.index("aria-expanded={open}"):code.index("{open && (")]
    # **按渲染出来的那串文字断言, 不按标识符。** 变异测试逼出来的:
    # 第一版写的是 `"w.posture" in head` —— 而同一段里 `POSTURE_TONE[w.posture]`
    # 这个取色查表也含这个标识符, 于是**把徽标那行删掉照样绿**。锚太宽 = 没有锚
    # (R310/R333 收口过同一个毛病, 这是第三次)。
    for must in ("多 {w.bull} / 空 {w.bear}",
                 "转多 {w.new_bull} · 转空 {w.new_bear}",
                 "值得关注 {ops.length} 只"):
        assert must in head, f"折叠条上少了「{must}」—— 收起时就看不到这条读数了"
    # 姿态徽章: 一次用来取色, 一次是真渲染出来的值 —— 少一次就是徽章没了
    assert head.count("w.posture") >= 2, "姿态徽章没渲染(只剩取色那一处)"


def test_R341_展开区限高自滚():
    code = code_of(DIGEST)
    assert "const LIST_MAX = 'max-h-72'" in code, "值得关注可能几十只, 不限高等于没折叠"


# ── 自检条: 一处实现 ────────────────────────────────────────────────────
def test_R341_自检条拆成一处实现_两页共用():
    """同一个自检条两处各写一遍, 措辞和口径必然漂。"""
    bar = code_of(HEALTH)
    assert "export function TodayHealthBar" in bar
    for page in (TODAY, DIGEST):
        code = code_of(page)
        assert "from '@/components/today/TodayHealthBar'" in code, f"{page} 没复用那一处"
        assert "function TodayHealthBar" not in code, f"{page} 自己又写了一份"


def test_R341_自检条不进折叠():
    """「你看的数字是几天前的」这句话被折起来就失去了全部意义。"""
    code = code_of(DIGEST)
    i_bar = code.index("<TodayHealthBar")
    i_fold = code.index("aria-expanded={open}")
    assert i_bar < i_fold, "自检条必须在折叠条之外"
