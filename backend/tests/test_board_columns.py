"""[R249] 决策台的列顺序。

用户: 「我有点乱, 是否有好办法整理好顺序调整显示和列」。

重排之后一行从左到右是: **认票 → 凭什么 → 我的账 → 别人的意见**

    标的 · 现价/涨跌  |  走势 · 结论  |  仓位 · 成本 · 浮盈  |  AI 分析 · AI 信号

原来账目三列横在「现价」与「走势」之间 —— 扫表时要连着读的两列判断被切开了。

`BOARD_COLS` 的注释从 R194 起就写着「**顺序必须与 thead 里的 <th> 一一对应**」,
可**没有任何东西在守它**: 对不上时列宽会整体错位一格, 而且看不出是哪一列的问题。
这一组就是那个守卫。
"""
from __future__ import annotations

import pathlib
import re

import pytest

_BOARD = (pathlib.Path(__file__).resolve().parents[2] / "frontend" / "src"
          / "components" / "stock-analysis" / "WatchlistDecisionBoard.tsx")


def _src() -> str:
    if not _BOARD.exists():
        pytest.skip("拿不到前端源码(只跑后端时正常)")
    return _BOARD.read_text(encoding="utf-8")


def _cols(src: str) -> list[str]:
    """BOARD_COLS 里的 label, 按声明顺序。"""
    block = src[src.index("const BOARD_COLS = ["):]
    block = block[:block.index("] as const")]
    return re.findall(r"label:\s*'([^']+)'", block)


def _headers(src: str) -> list[str]:
    """thead 里每个 <th> 的可见文字。"""
    head = src[src.index("<thead"):src.index("</thead>")]
    out = []
    for th in re.findall(r"<th\b.*?</th>", head, re.S):
        txt = th
        # 顺序要紧: 先剥 JSX 表达式(排序标记、caret), 再剥**属性值**, 最后剥标签。
        # 属性必须先剥 —— title="… > … < …" 里带着尖括号, 直接剥标签会被它骗到
        # (第一版就栽在这里)。
        for _ in range(6):                       # 表达式会嵌套, 由内向外剥几遍
            txt = re.sub(r"\{[^{}]*\}", "", txt)
        txt = re.sub(r'=\s*"[^"]*"', "", txt)     # 属性值
        txt = re.sub(r"=\s*'[^']*'", "", txt)
        txt = re.sub(r"<[^<>]*>", "", txt)        # 标签
        txt = txt.replace("&nbsp;", " ").strip()
        if txt:
            out.append(txt)
    return out


def test_列的顺序是_认票_凭什么_我的账_别人的意见():
    """这条把**顺序本身**钉住 —— 它是这次重排的全部内容, 不写下来下次就会漂回去。"""
    assert _cols(_src()) == [
        "标的", "现价/涨跌",          # 认票
        # [R277 加, R297 删] 「进度」并回「结论」了 —— 用户: 「进度列和结论列
        # 看看怎么合并」。它是结论的**刻度**(走到哪一步 / 还有没有劲), 不是
        # 第四条结论, 所以贴回它修饰的那两行, 而不是自己占一列。
        "走势", "结论",               # 凭什么(判断必须连着, 不许被账目切开)
        # [R284] 「成本」「浮盈」两列删掉(用户: 「删除掉浮盈和成本列」)——
        # 它们为 5% 的行占着 9% 的宽度(持有 8 / 自选 166)。成本**输入框**保留,
        # 挪进这一格: 它是出场线的输入, 不是展示。
        "持仓",                       # 我的账
        # [R284] 「AI 分析」整列撤掉 —— 它不是数据列, 是操作入口(胶囊 + 两个图标),
        # 并进「AI 信号」列的头一行。
        "AI 信号",                    # 别人的意见
    ]


def test_账目三列必须排在判断之后():
    """R249 之前它们在「现价」与「走势」之间。这条独立于上面那条写 ——
    就算以后列增减, **判断不许被账目切开**这条纪律也得留着。"""
    cols = _cols(_src())
    judge = max(cols.index("走势"), cols.index("结论"))   # [R297] 「进度」并进结论了
    ledger = cols.index("持仓")     # [R284] 账目从三列收成一列
    assert ledger > judge, (
        f"账目列插到判断列中间了 —— 扫表时「走势→结论」读不连贯。当前顺序: {cols}"
    )


def test_表头与_BOARD_COLS_一一对应():
    """`BOARD_COLS` 只管**列宽**(colgroup)与空表提示的 colSpan, 表头是另一处写的。
    两边对不上时整张表的列宽会错位一格, 而且看不出是哪一列的问题 ——
    这正是 R249 重排时最容易漏的一步(要同时改三处: BOARD_COLS / thead / tbody)。
    """
    src = _src()
    cols, heads = _cols(src), _headers(src)
    assert len(cols) == len(heads), (
        f"BOARD_COLS 有 {len(cols)} 列而 thead 有 {len(heads)} 个 <th>\n"
        f"  BOARD_COLS: {cols}\n  thead:      {heads}"
    )
    for i, (c, h) in enumerate(zip(cols, heads)):
        assert c == h, f"第 {i + 1} 列对不上: BOARD_COLS 是「{c}」, 表头是「{h}」"


def test_R290_六态天数只印一处且是转折口径():
    """[R249 → R290] 这条守的规矩没变, 说法换了。

    R249 立的是「同一个数不许有两种说法」。R290 用户点名要换说法:
    「外面不再是显示"正在转多"这样的的字眼了, 这类词统一改成出现转折后的
    第几天」—— 于是六态天数从徽标搬到第二行, 写成「转折后第 N 天」。

    **搬家最容易出的错是搬完两头都留一份**, 那正好把 R249 那条规矩破掉。
    所以这里正反各钉一条: 第二行有, 徽标上不许再有。

    结论那一侧仍是「已N天」——**那是另一个锚点**(这一档结论连着多久), 与
    「从转折那天数起」量的不是同一段, 分开叫反而更准。见名词表 NOT_A_CONFLICT。
    """
    root = _BOARD.parent
    cells = (root / "decision-board" / "cells.tsx").read_text(encoding="utf-8")
    # 只看渲染出去的文本, 注释里复述历史说法是允许的
    body = "\n".join(ln for ln in cells.splitlines()
                     if not ln.lstrip().startswith(("//", "*", "/*")))
    assert "转折后第 {trend.duration} 天" in body, "走势列第二行没写成「转折后第 N 天」"
    assert "已{trend.duration}天" not in body, (
        "徽标上还留着一份天数 —— 同一个数印两处, 正是 R249 要防的"
    )
    assert "已{d.days}天" in body, "结论徽标那份天数没了"

    bar = (root / "TrendStateBar.tsx")
    if bar.exists():
        bar_body = "\n".join(ln for ln in bar.read_text(encoding="utf-8").splitlines()
                             if not ln.lstrip().startswith(("//", "*", "/*")))
        assert "第 <span" not in bar_body, "复盘条又写回「第 N 天」了"


def test_R250_表头只印列名不印排序目标():
    """用户: 「别搞贵不贵怎么办, 我就只想显示结论两个字」→(问到走势列时)「要」。

    原来三列在排序时会在表头缀出当前排序目标:

        结论 贵不贵     走势 六态 / 间距 / 短中长     现价/涨跌 价 / 涨跌

    那是**把内部分层摆到表头上**, 而这几列对外就叫「结论」「走势」。
    排序行为照旧(点击仍在各目标之间轮换), 说明留在悬停里, 只是不印在表头。

    **这条得直接盯源码**: `_headers()` 会把 JSX 表达式整个剥掉, 那些缀字在
    它眼里是隐形的 —— 靠它守不住。
    """
    import re

    src = _src()
    th_block = src[src.index("<thead"):src.index("</thead>")]
    # 表头里**渲染出去**的部分: 去掉注释、去掉 title 属性(那里面本来就要解释轮换)
    render = re.sub(r"\{/\*.*?\*/\}", "", th_block, flags=re.S)
    render = re.sub(r'title=(?:"[^"]*"|\{(?:[^{}]|\{[^{}]*\})*\})', "", render, flags=re.S)

    for bad in ("贵不贵", "怎么办", "六态", "'价'", "涨跌'"):
        assert bad not in render, (
            f"表头又缀上排序目标「{bad}」了 —— 用户只要列名本身"
        )
    # [R277 → R297] 「间距/进度」不再是列名了(那一列并进「结论」), 于是它回到
    # **禁用词**那一侧: 表头上不许出现它 —— 无论是缀在「走势」头上(R250 原本
    # 防的那件事), 还是缀在「结论」头上(R297 之后新的犯错方式)。
    # 守的规矩一个字没变: **表头只印列名。**
    assert "进度" not in render, "「进度」缀回表头了 —— 它已经不是一列, 表头只印列名"
    assert "间距" not in render, "「间距」缀回表头了"
    # 正面: 列名都还在
    for name in ("结论", "走势", "现价/涨跌", "持仓"):
        assert name in render, f"表头把「{name}」弄丢了"


# ===== [R251] 每列的排序 =====
#
# 用户: 「检查每列的排序, 我感觉有点不对劲」。查出三个:
#
#   ① 多目标那三列传的是**当前排序键本身**给箭头函数 —— 判等恒真, 箭头永远亮。
#      按「成本」排时四个箭头一起亮, 看不出按哪列排。
#      (R250 把表头缀字去掉之后这个 bug 才裸出来 —— 缀字之前一直在替它遮丑)
#   ② 「怎么办」首次点击是降序, 而 order 越小越急 —— **把「没事」顶到最前面**,
#      与表头 title 写的「按纪律走 > 今天就得动 > …」正好相反。
#   ③ 「AI 信号」同理 —— 把「观望」顶到最前面。
#
# ②③ 是**看不出来的错**: 表面上排了序, 排出来的却是最不该先看的那些。


def _board_body() -> str:
    """去掉注释的源码 —— 注释里复述 bug 是允许的, 不能算数。"""
    out, in_block = [], False
    for ln in _src().splitlines():
        t = ln.strip()
        if in_block:
            if "*/" in t:
                in_block = False
            continue
        if t.startswith("/*"):
            in_block = "*/" not in t
            continue
        if t.startswith("//"):
            continue
        out.append(ln)
    return "\n".join(out)


def test_R254_每列三下一圈():
    """用户: 「我也不想切换那么多下」「点击第三下就恢复原状」。

        第 1 下  最该看的在前
        第 2 下  反过来
        第 3 下  回默认(该动了)

    取代了两套并存的老写法: `toggleSort` 的"再点一下翻方向"(永远回不到默认)
    与 `TREND_SORTS` 的"轮换五个目标"(六下一圈, 而且一个方向永远点不到)。
    """
    body = _board_body()
    assert "cycleSort" in body, "没有统一的三态循环"
    for dead in ("toggleSort(", "cycleTrendSort", "TREND_SORTS"):
        assert dead not in body, f"老写法「{dead}」又回来了 —— 两套并存就是下一个 bug"
    blk = body[body.index("const cycleSort"):]
    blk = blk[:blk.index("\n\n")]
    assert "return DEFAULT_SORT" in blk, "第三下没有回默认"


def test_R254_每列只剩一个排序目标():
    """一列多个目标是「点太多下」的根 —— 走势列曾经塞了 5 个(R211 三列并一列
    时带来的), 轮换一圈要 6 下。现在一列一个, 表头的箭头也就只需要认一个键。"""
    body = _board_body()
    # [R284] held / cost / report 三个随列消失, 见 test_R254_点不到的排序键全删掉
    # [R297] `spread` 也随列消失 —— 「进度」并进「结论」, 而「结论」已经有
    # `play` 了; 一列一个目标正是这条在守的规矩。
    for one in ("caret('name')", "caret('changePct')", "caret('trend')",
                "caret('play')",
                "caret('pnl')", "caret('signal')"):
        assert one in body, f"表头少了 {one}"
    # 反面: 不许再出现多目标的写法
    assert "caret('trend', " not in body and "caret('close'" not in body, (
        "又有列挂上多个排序目标了"
    )


def test_R254_点不到的排序键全删掉():
    """[守则 R198] 不留没人调的死代码。

    砍掉的: close / spread / ks·km·kl / verdict —— 这几个原来靠"轮换目标"才
    够得着; exit 与 confidence 更早就**没有任何表头能选中**(止盈线那一列 R212
    撤了, 置信度 R178 换掉了), 一直是死代码。
    """
    body = _board_body()
    keys = body[body.index("type SortKey"):]
    keys = keys[:keys.index("\nconst ")]
    # [R277 → R297] `spread` 出去又回来了, **两次都是同一条判据: 点不到就删。**
    # R277 把它从名单里拿掉, 是因为那一版给了「进度」自己的表头(它不再点不到);
    # R297 那一列并进「结论」, 表头没了, 它又够不着了, 于是回到名单上。
    # 这条测的从来是"有没有够不着的死键", 不是"某个键不许存在" ——
    # `test_R277_每个排序键都够得着` 把这个意图直接测出来, 名单只是兜底。
    # [R284] held / cost / report 加进来 —— 它们的表头随列合并/撤销消失了
    for dead in ("'close'", "'ks'", "'km'", "'kl'", "'held'", "'cost'", "'report'",
                 "'spread'", "'verdict'", "'exit'", "'confidence'"):
        assert dead not in keys, f"排序键 {dead} 点不到却还留着"
    # 比较器里也不该还有它们的分支
    cmp_ = body[body.index("const sortedRows"):]
    cmp_ = cmp_[:cmp_.index("const arr = ")]
    for dead in ("case 'close'", "case 'ks'", "case 'verdict'", "case 'held'",
                 "case 'cost'", "case 'report'", "case 'spread'",
                 "case 'exit'", "case 'confidence'"):
        assert dead not in cmp_, f"比较器里还留着 {dead} 的分支"


def test_R277_每个排序键都够得着():
    """**把上一条那张手写名单换成机器核对。**

    R254 那条列的是"已知的死键", 靠人记得往里加。这次 `spread` 复活就得手动
    把它从名单里挑出来 —— 说明名单本身是要维护的东西, 而这仓库已经栽过一轮:
    R272 的注册表漏登记也是同一个形状(手写名单 + 靠自觉)。

    正确的写法是反过来: 枚举 `SortKey` 的全部取值, 逐个要求 thead 里真有一个
    `cycleSort('x')` 能选中它。这样死键**一出现就红**, 不需要谁先发现它死了。
    """
    body = _board_body()
    seg = body[body.index("type SortKey"):]
    seg = seg[:seg.index("\nconst SIGNAL_RANK")]
    keys = set(re.findall(r"'([a-zA-Z]+)'", seg))
    # [R284] 原来这里写的是 `len(keys) >= 10` —— 那是想确认"解析真的解出来了",
    # 却顺手把**键的个数**也钉住了; 列一增减就红, 而那跟这条测的东西无关。
    # 改成点名几个必然存在的键: 解析坏了它们一个都出不来, 而加减列不影响。
    assert {"urgency", "name", "signal"} <= keys, f"没解析到排序键: {keys}"
    src = _src()
    th = src[src.index("<thead"):src.index("</thead>")]
    # 默认排序键够得着 —— 它是"任一列点到第三下"回落的目标(cycleSort 的第三态),
    # 所以不需要自己的表头按钮。这条第一次跑就抓到了 `urgency`, 而它并不是死键。
    default_key = re.search(r"DEFAULT_SORT = \{ key: '([a-zA-Z]+)'", _board_body())
    assert default_key, "找不到 DEFAULT_SORT —— 这条判不了哪个键是默认的"
    reachable = {default_key.group(1)}
    unreachable = sorted(k for k in keys
                         if k not in reachable and f"cycleSort('{k}')" not in th)
    assert not unreachable, (
        f"这些排序键没有任何表头能选中, 也不是默认键, 是死代码: {unreachable}")


def test_R277_导出的快慢与屏幕同一个产地():
    """**同一句话不许有两个产地。**

    导出那一列原来自己从 `accel.level` 另算一套(accel→提速 / decel→变慢)——
    那是这次这个方向错误的**第三处**(屏幕可见行、屏幕悬停、导出件), 而且是
    最不容易发现的一处: 导出件是拿去发给别人的, 自己未必会看。

    更根本的毛病不是措辞而是**重复实现**: 两个产地必然漂移, 修了一处另一处
    照旧说反话。这条钉住它只从后端那一份读。
    """
    from tests.frontend_source import code_of
    body = code_of("lib/decisionBoardExportColumns.ts")
    i = body.index("key: 'chanState'")
    blk = body[i:body.index("},", body.index("cell:", i))]
    assert "pace_cn" in blk, "导出的快慢没走 ph.pace_cn"
    for bad in ("'提速'", "'变慢'", "'匀速'"):
        assert bad not in blk, f"导出又自己造了一套快慢措辞: {bad}"


def test_R297_按间距排退役了而且退干净了():
    """[R277 → R297] R277 那条钉的是「按间距排必须带符号」(取绝对值的话, 崩得
    最惨的票会和走得最强的票并排顶在最前面, 而且看不出来)。

    **那个排序目标随列退役了**, 于是这条改成钉"退干净": 键、比较器分支、表头
    按钮、以及表头里那句「带符号」的说明, 四处必须一起没。留下任何一处都是
    R254 反复在治的那种死代码 —— 尤其是那句说明: 它会指着一个点不到的行为。

    **退役的判据与 R254/R277 逐字相同: 点不到就删。** 那一列并进「结论」,
    而「结论」已经有 `play`(按急迫程度), 一列一个目标是 R254 立的规矩。
    """
    body = _board_body()
    assert "case 'spread'" not in body, "比较器里还留着按间距排的分支"
    assert "cycleSort('spread')" not in body, "还有表头能点到它"
    src = _src()
    th = src[src.index("<thead"):src.index("</thead>")]
    assert "带符号" not in th, "表头还留着那句说明 —— 它指着一个已经点不到的行为"


def test_R277_表头上的排序目标都得是真键():
    """反向: 表头点了一个 `SortKey` 里没有的名字, 那一列点下去毫无反应 ——
    而且不报错(TypeScript 会拦住字面量, 但拼错成另一个合法键它拦不住)。"""
    body = _board_body()
    seg = body[body.index("type SortKey"):]
    seg = seg[:seg.index("\nconst SIGNAL_RANK")]
    keys = set(re.findall(r"'([a-zA-Z]+)'", seg))
    src = _src()
    th = src[src.index("<thead"):src.index("</thead>")]
    used = set(re.findall(r"cycleSort\('([a-zA-Z]+)'\)", th))
    assert not (used - keys), f"表头用了不存在的排序键: {sorted(used - keys)}"


def test_R251_越小越要紧的那几个必须升序打头():
    """`order` / `SIGNAL_RANK` 都是**越小越要紧**。首次点击给降序, 就是把最不该
    先看的顶到最前面 —— 而且看不出来, 因为它确实排序了。"""
    body = _board_body()
    block = body[body.index("FIRST_DIR"):]
    block = block[:block.index("}")]
    for key, why in (("urgency", "该动了: order 越小越急"),
                     ("play", "怎么办: 按纪律走=0, 没事=5"),
                     ("signal", "AI 信号: 买入=0, 观望=3"),
                     ("name", "标的: A → Z")):
        assert f"{key}: 'asc'" in block, f"{key} 的首次方向不是升序 —— {why}"
    for key, why in (("trend", "六态: 值取了负, 降序才是多头在前"),
                     ("changePct", "涨跌: 涨最多在前"),
                     ("pnl", "持仓: 赚最多在前")):
        assert f"{key}: 'desc'" in block, f"{key} 的首次方向不是降序 —— {why}"


def test_R251_每个排序键都定了首次方向():
    """漏一个就会 undefined —— 那一列点下去方向是随机的(实际是 undefined,
    比较时当 desc 处理), 而且悄无声息。"""
    body = _board_body()
    keys = re.findall(r"'([a-zA-Z]+)'", body[body.index("type SortKey"):body.index("\n", body.index("type SortKey") + 200)])
    block = body[body.index("FIRST_DIR"):]
    block = block[:block.index("\n  }")]
    for k in keys:
        assert re.search(rf"\b{k}: '(asc|desc)'", block), f"排序键「{k}」没定首次方向"


def test_R251_表头说的和实际做的一致():
    """[R214 的教训] 判定写对了、接线接错了, 而测试恰好只测了判定。

    「怎么办」的表头 title 写着「按急迫程度排: 按纪律走 > …」—— 那句话只有在
    升序时才成立。说明与行为不一致时, **说明会赢**(用户信它), 于是排出来的表
    与预期相反而没人发现。
    """
    src = _src()
    th = src[src.index("<thead"):src.index("</thead>")]
    assert "急迫程度排" in th, "「怎么办」的排序说明没了"
    body = _board_body()
    block = body[body.index("FIRST_DIR"):]
    assert "play: 'asc'" in block[:block.index("}")], (
        "表头说「按纪律走排最前」, 而首次点击是降序 —— 说明与行为相反"
    )


def test_R252_粘性表头必须有_z_index():
    """用户: 「怎么背后的东西也显示出来了, 层级是不是不对」。

    `position: sticky` 不带 z-index 时, 行里任何**自己造层叠上下文**的东西
    (`opacity < 1`、`transform`、`filter`…)都会画到表头上面 —— 决策台那个
    `opacity-70` 的天数徽标正是这样穿透过去的。

    这条盯**全仓所有粘性表头**, 不只决策台 —— 同一个毛病当时有三处。
    """
    import pathlib

    root = _BOARD.parents[2]            # frontend/src
    if not root.exists():
        pytest.skip("拿不到前端源码(只跑后端时正常)")
    bad = []
    for f in root.rglob("*.tsx"):
        in_block = False
        for i, ln in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            # 注释里复述这个 bug 是允许的 —— 不去注释的话守卫会被自己的说明文字
            # 骗到(第一版就栽了一次)
            t = ln.strip()
            if in_block:
                in_block = "*/" not in t
                continue
            if t.startswith(("//", "*")):
                continue
            if t.startswith(("/*", "{/*")):
                in_block = not any(x in t for x in ("*/", "*/}"))
                continue
            if "sticky top-0" in ln and not re.search(r"\bz-(\[|\d)", ln):
                bad.append(f"{f.relative_to(root)}:{i}")
    assert not bad, (
        "这些粘性表头没有 z-index, 行内容会穿透上来:\n  " + "\n  ".join(bad)
    )


def test_R252_决策台表头背景是实心的():
    """半透明表头底下是**正在划走的行** —— 让它透出来没有任何好处, 只会把
    表头读成花的。"""
    src = _src()
    head = src[src.index("<thead"):src.index(">", src.index("<thead")) + 1]
    assert "bg-surface/" not in head, f"表头背景又半透明了: {head}"
    assert "bg-surface" in head, "表头没有背景色 —— 行会直接透上来"


def test_R253_到价预案固定竖排一个一行():
    """用户: 「ai信号显示成这样换行」。

    原来是 `flex-wrap` —— 同样三个预案, 列宽够时挤成一行、不够时折成两三行,
    **每一行高度都不一样**, 一屏扫下去行与行对不齐。改成固定竖排: 行高一致,
    价位也天然对齐(方向词都是三个字 + 等宽数字)。
    """
    body = _board_body()
    i = body.index("watch_points ?? []).length > 0")
    block = body[i:i + 700]
    assert "flex flex-col" in block, "到价预案没有固定竖排"
    assert "flex-wrap" not in block, (
        "到价预案又变回「能挤就挤、挤不下才换行」了 —— 那会让每一行高度都不一样"
    )
    assert "whitespace-nowrap" in block, "单个预案自己不该再折行"


def test_R255_结论列与AI信号列同一套排版():
    """用户: 「结论列也要像 ai 信号列那样排版」。

        贵不贵 已N天      ← 一行
        怎么办            ← 一行
        说明文字…         ← 整段折行, 不再单行截断

    R217 当初把这一列压成**固定两行**(徽标横排 + 说明 `truncate`), 是因为那时
    它会摞到五层、每行高度还不一样。**那个顾虑现在不成立了** —— 隔壁 AI 信号列
    R253 起就是固定竖排三行到价预案, 行高本来就由它撑着。
    """
    root = _BOARD.parent
    cells = (root / "decision-board" / "cells.tsx").read_text(encoding="utf-8")
    body = "\n".join(ln for ln in cells.splitlines()
                     if not ln.lstrip().startswith(("//", "*", "/*")))
    # 只取**渲染那一段**(从 `return (` 起)。
    # 试过用 `\n}` 收尾 —— 会停在 props 类型那个 `}) {` 上, 整段渲染代码没被检查到;
    # 换 `\n}\n` 又因为这个函数正好在文件末尾(没有末行换行)而找不到。
    # 从 `return (` 起到下一个顶层声明为止最稳。
    i = body.index("export function ConclusionCell")
    blk = body[body.index("return (", i):]
    m = re.search(r"\n(?:export )?(?:function|const) ", blk)
    if m:
        blk = blk[:m.start()]

    # [R255 → R298] **左对齐改回居中。** 用户: 「每列都居中对齐好」。
    # R255 那句理由(竖排之后居中会让三行的左边缘参差不齐)在当时是对的; R297
    # 之后前两行各自是「徽标 + 一个短词」宽度接近了, 而第三行绝大多数在一行以内,
    # 参差的前提没了。**这条守的规矩一个字没变**: 竖排, 不许再横排回去。
    # [R298 → R299] 居中的**做法**换了: 从"每行各自居中"改成"两行共用一条中轴"。
    # 用户看着截图: 「排版不好看」—— 两行宽度不一样(「候选池 已1天+」比「没事」
    # 宽出一大截), 各自居中之后四个边缘全是散的。改成两列网格: 判定靠右、
    # 刻度靠左, 中间那条缝成了一条真的竖线, 两行锁在一起。
    assert "grid-cols-[max-content_max-content]" in blk, "两行没有共用那条中轴"
    # **两行都得靠右, 所以数个数而不是"在不在"。** 只钉"在不在"的话, 把第二行
    # 那个 `justify-self-end` 拿掉照样绿 —— 而那正好就是中轴散掉的样子
    # (第一版就是这么漏的, 变异当场抓到)。
    assert blk.count("justify-self-end") == 2, (
        f"靠右的判定格有 {blk.count('justify-self-end')} 个 —— 该是两行各一, 否则中轴对不上"
    )
    assert "flex-col items-start" not in blk, "又靠左了 —— 整张表除它以外都居中"
    # 光有 `justify-center` 不够: 带 `max-w` 的块级容器不会自己居中(这一处漏了
    # 的话整格看着还是靠左 —— 最难查的那种「改了没效果」)
    assert "mx-auto grid max-w-[" in blk, "带 max-w 的容器没有 mx-auto, 整格还是靠左"
    assert "!text-left" not in blk, "还覆写着左对齐"
    # 反面照旧: 两个徽标不许又挤回同一行(那是 R217 那版, R255 拆开的)
    assert "flex flex-wrap items-center justify-center" not in blk, (
        "两个徽标又横排回去了"
    )
    assert "whitespace-normal break-words" in blk, (
        "说明又变回单行截断了 —— AI 信号那一列的理由是整段折行的"
    )
    assert "truncate" not in blk, "说明还在用 truncate 截断"


def test_R257_走势列的三行各管一件事():
    """用户: 「走势我也想重排描述, 现在的版本我觉得抓不住重点」。

    毛病是**「阶段」和「六态」在抢同一件事 —— 方向**:

        自然回升 已3天      六态说在涨
        横盘中 · 走到中段    阶段说没走          ← 打架, 而界面不提
        正在转多

    而且阶段与成熟度量的根本不是同一个东西(前者看三线重合度、后者看短长线
    间距), 于是能凑出「横盘中 · 走到中段」这种**自相矛盾**的话 ——
    见 `test_R257_横盘中确实会配上走了一段`。

    现在三行各管一件事: **方向(六态) / 走了多远(成熟度) / 还有没有劲**。
    """
    root = _BOARD.parent
    cells = (root / "decision-board" / "cells.tsx").read_text(encoding="utf-8")
    body = "\n".join(ln for ln in cells.splitlines()
                     if not ln.lstrip().startswith(("//", "*", "/*", "{/*")))
    i = body.index("export function ChannelStateCell")
    blk = body[body.index("return (", i):]

    assert "{ph.cn} · {ph.maturity_cn}" not in blk, (
        "「阶段」那个词又印回徽标上了 —— 它和六态抢方向, 而且会跟成熟度自相矛盾"
    )
    assert "{trend.state_cn}" in blk, "方向那一行没了"
    # [R277] 成熟度**搬去 SpreadCell 了**, 走势列于是只讲方向(六态 + 三尺度对齐)。
    # 这条不再要求它出现在这一格里, 改成要求它**不在这里重复印一遍** ——
    # 同一个读数印两列, 读的人得先确认它们是不是一回事。
    assert "{ph.maturity_cn}" not in blk, (
        "成熟度又印回走势列了 —— 它现在是「间距」列的内容, 两处都印是重复"
    )
    assert "{ph.pace_cn}" not in blk, "快慢也一样, 它属于「间距」列"


def test_R297_成熟度与快慢并进结论那一格且各自贴住它修饰的那一行():
    """[R277 → R297] 正面: **合并不是删除**, 两个读数都得在新格子里真的渲染出来。

    **加速度此前在决策台上根本看不见** —— 走势列那一行写的是
    `align ? align.cn : pace_cn`, 而 `alignment()` 只要六态/位置/间距三样都在
    就返回非空(几乎永远), 于是快慢那一支轮不上; 悬停里被同一个三元顶掉。
    R277 给了它一个位置, R297 换了个位置, 这条一路钉住它没再消失。

    **顺序是这次合并的全部内容, 所以一并钉住**:
      · 成熟度贴着**结论徽标**那一行 —— 它与「已N天」是同一个问题的两把尺
        (走了多久 / 走了多远), 都在回答"到什么程度了";
      · 快慢贴着**怎么办**那一行 —— 它是前瞻的那一半, 「该止盈了·正在放慢」
        与「该止盈了·还在加速」是两句不同的话。
    对调的话两行都读不通, 而且不会有任何东西报错。
    """
    from tests.frontend_source import code_of
    code = code_of("components/stock-analysis/decision-board/cells.tsx")
    blk = code[code.index("export function ConclusionCell"):]
    blk = blk[blk.index("return ("):]
    assert "ph?.maturity_cn" in blk, "结论列没印成熟度 —— 合并把它弄丢了"
    assert "ph?.pace_cn" in blk, "结论列没印快慢 —— 加速度又看不见了"
    assert blk.index("<VerdictInner") < blk.index("ph?.maturity_cn") < blk.index("<PlaybookInner"), (
        "成熟度没有贴着结论徽标那一行"
    )
    assert blk.index("<PlaybookInner") < blk.index("ph?.pace_cn"), (
        "快慢没有贴着「怎么办」那一行"
    )


def test_R297_合并后结论列吃掉了进度那一列的宽度():
    """**R283 那一课**: 「结论」一直被挤的真原因不是列宽, 是**内容的 `max-w` 上限**
    低于列宽 —— 那一版列宽 18% 在常见视口上有 300px 出头, 内容却被硬卡在 240px,
    光加列宽一点用都没有。**两者得一起动。**

    R297 往这一列里加了两个读数, 如果只删掉「进度」那一列而不抬这两个数, 就是
    把 R283 那个 bug 原样重犯一遍。所以正反各钉一条:
      · 列宽真的涨了(吃掉「进度」原来那 5.5% 的大半);
      · 内容上限不再是瓶颈 —— 它得比列宽在常见视口上折算出来的像素还宽。
    """
    src = _src()
    blk = src[src.index("const BOARD_COLS = ["):]
    blk = blk[:blk.index("] as const")]
    m = re.search(r"label: '结论', w: '(\d+(?:\.\d+)?)%'", blk)
    assert m, "「结论」那一列没有宽度了"
    pct = float(m.group(1))
    assert pct >= 21, f"「结论」列宽还是 {pct}% —— 并进来两个读数却没给它宽度"

    root = _BOARD.parent
    cells = (root / "decision-board" / "cells.tsx").read_text(encoding="utf-8")
    cap = re.search(r"(?:flex|grid) max-w-\[(\d+(?:\.\d+)?)rem\]", cells)
    assert cap, "结论列内容的 max-w 上限没了"
    rem = float(cap.group(1))
    # 常见视口按 1400px 表宽折算 —— R283 就是在这个量级上撞到上限的
    assert rem * 16 >= 1400 * pct / 100, (
        f"内容上限 {rem}rem({rem * 16:.0f}px)低于列宽 {pct}%(约 {1400 * pct / 100:.0f}px)"
        " —— 又变成 R283 那个「加了列宽也没用」的局面"
    )


def test_R297_合并没有把结论列摞成五行():
    """**这条是那次合并唯一真正的风险守卫。**

    直接把「进度」两行摞到「结论」下面就是五行 —— 那正是 R217 撤过的病
    (「原来这一列会摞到五层…每行高度还不一样, 上一行的尾巴挂到下一行的表头
    底下, 行与行糊成一片」)。**病根是行数与行高参差, 不是每行的内容量**,
    所以两个读数得**并进已有的行**, 而不是各占一行。

    钉法: 那个纵向 flex 容器的直接子节点必须仍是**三个**(结论行 / 怎么办行 /
    说明行)。多一个就是摞上去了。
    """
    from tests.frontend_source import code_of
    code = code_of("components/stock-analysis/decision-board/cells.tsx")
    blk = code[code.index("export function ConclusionCell"):]
    outer = blk[blk.index("grid max-w-["):]
    outer = outer[:outer.index("</div>")]
    # 顶层子节点 = 缩进恰好 8 空格的**开**标签(容器本身缩进 6, 嵌套的更深)。
    # 收尾标签 `</span>` 也落在这个缩进上, 得排掉 —— 不排的话会数多, 而数多
    # 恰好就是这条要防的那件事, 会给出一条看着像真的假警报(第一版就是)。
    top = [ln.strip() for ln in outer.splitlines()
           if (ln.startswith("        <") and not ln.startswith("        </"))
           or ln.startswith("        {")]
    # [R299] 版面从"三个纵向子节点"换成两列网格, 于是**格子数**变成 5:
    # 行1 两格(判定 / 刻度)、行2 两格、行3 一格跨两列。行数还是三行 ——
    # 换算关系写在这儿, 免得下次看到 5 以为又摞上去了。
    assert len(top) == 5, f"结论列的格子数变了(该是 2+2+1), 现在是 {len(top)}: {top}"
    assert "col-span-2" in outer, "第三行没有跨两列 —— 它会被塞进判定那一列里"


def test_R277_走势列不再回退到快慢():
    """那个 `align ? align : pace_cn` 的回退基本走不到(见上一条), 属于
    「写在那儿、看着像在用、其实轮不上」—— 与 R210 路 C、R214 规则②、
    R215 ③ 同一族。快慢搬走之后更不该留着: 留着就是同一读数印两列。
    """
    # **必须先剥注释。** 这条第一次跑就红了, 而红的原因是我在那一行上面写的
    # 说明里复述了 `ph.pace_cn` —— 本仓库第七次「断言被自己的注释喂饱」,
    # 这次是反向(该消失的字眼被注释顶着不消失)。用共用的块级剥注释工具。
    from tests.frontend_source import code_of
    code = code_of("components/stock-analysis/decision-board/cells.tsx")
    blk = code[code.index("export function ChannelStateCell"):]
    assert "ph.pace_cn" not in blk, "走势列又回退到快慢了"


def test_R257_阶段的说明必须留在悬停里():
    """撤的是**徽标上那个词**, 不是这一层的判定 —— 阶段的 `why` 与「该盯什么」
    照旧要给得出来, 否则就是把信息删了而不是理顺了。"""
    root = _BOARD.parent
    cells = (root / "decision-board" / "cells.tsx").read_text(encoding="utf-8")
    # [R298] 这两句话**收成了一处产地**(`phaseLines`)。原来走势列写
    # `【通道】${ph.cn} —— ${ph.why}`、结论列写 `【${ph.cn}】${ph.why}` ——
    # 同两句、两个格式、两个产地, 与 R296 撤 `LiveStrip` 是同一类。
    # 这条守的规矩一个字没变(阶段的 why 与「该盯什么」必须还给得出来),
    # 只是锚点从"走势列那个字面量"换成"那一处产地 + 两列都在用它"。
    assert "function phaseLines" in cells, "阶段那两句没有唯一产地"
    assert "${ph.cn}】${ph.why}" in cells, "阶段从悬停里也没了 —— 那是删信息, 不是理顺"
    assert "该盯什么" in cells, "「该盯什么」没了"
    from tests.frontend_source import code_of
    code = code_of("components/stock-analysis/decision-board/cells.tsx")
    assert code.count("phaseLines(ph)") == 2, (
        f"用到 phaseLines 的地方有 {code.count('phaseLines(ph)')} 处 —— 该是走势列与结论列各一"
    )
    assert "【通道】" not in code, "又有人另写了一份阶段文案"


def test_R257_横盘中确实会配上走了一段():
    """把这次改动的**依据**钉住: 阶段与成熟度是两个量, 真的能凑出自相矛盾的话。

    哪天底层改了让它们不再打架, 这条会红 —— 那时就该回头看看徽标上要不要
    把阶段加回来。
    """
    from itertools import product

    from app.indicators import keltner_geometry as kg
    got = set()
    for sp in [x / 10 for x in range(-80, 81, 2)]:
        for a1, o in product((-0.5, 0.0, 0.5), (0.0, 0.5, 0.9, 1.0)):
            ph = kg.phase({"spread": sp, "accel": {"a1": a1}, "compress": o},
                          {"compress_days": 30})
            if ph and ph["cn"] == "横盘中":
                got.add(ph["maturity_cn"])
    assert got - {"刚起步"}, (
        "「横盘中」现在只配「刚起步」了 —— 两者不再打架, "
        "可以回头考虑把阶段加回徽标"
    )


def test_R258_界面上不再出现贵不贵():
    """用户: 「别用这么傻逼的描述」(指着复盘表那个「贵不贵」列头)。

    这一层在别处一律叫**通道结论**(`keltner.verdict` / 决策台那一列 / 复盘上方
    那个页签 / 复盘统计口径), 只有几处自己起了个口语名字。一个东西两个名字,
    读的人得先确认它们是不是一回事。

    扫的是**渲染出去的文本** —— 注释里复述历史说法是允许的。
    """
    root = _BOARD.parents[2]            # frontend/src
    if not root.exists():
        pytest.skip("拿不到前端源码(只跑后端时正常)")
    bad = []
    for f in list(root.rglob("*.tsx")) + list(root.rglob("*.ts")):
        in_block = False
        for i, ln in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            t = ln.strip()
            if in_block:
                in_block = not any(x in t for x in ("*/", "*/}"))
                continue
            if t.startswith(("//", "*")):
                continue
            if t.startswith(("/*", "{/*")):
                in_block = not any(x in t for x in ("*/", "*/}"))
                continue
            if "贵不贵" in ln:
                bad.append(f"{f.relative_to(root)}:{i}")
    assert not bad, "这些地方还印着「贵不贵」:\n  " + "\n  ".join(bad)


def test_R258_那一列叫通道结论而且脚注指得对():
    """[R258 → R295 → R296] 守的规矩一个字没变: **同一层判定在界面上只许一个
    名字**, 而且脚注不许指着不存在的东西。变的只是它长在几张表里。

    R295 用户说「删掉这一列」, 它离开了趋势表; R296 用户说「趋势状态删除的那一
    列我需要恢复」, 它回来了 —— 于是**两张逐日表里各有一列**。这正是这条守卫
    最该盯的时刻: 两个列头并排放着, 名字差一个字就是同一样东西两个名字。
    """
    root = _BOARD.parent
    src = (root / "StockReviewDialog.tsx").read_text(encoding="utf-8")
    assert src.count(">通道结论</th>") == 2, (
        f"叫「通道结论」的列头有 {src.count('>通道结论</th>')} 个 —— 两张逐日表该各一列"
    )
    assert ">结论</th>" not in src, "有一列还叫「结论」—— 同一层判定只许一个名字"
    # 脚注曾经指着一个**已经不存在的页签**(R200 的旧名, R223 已改回「通道结论」);
    # R295 又出过一次同形状的: 那一列删掉后脚注还写着"悬停看完整卡片"。
    # R296 那一列回来了, 脚注跟着回来 —— 措辞得跟列头对上。
    assert "「通道结论」列悬停看完整卡片" in src, "趋势那页的脚注没提这一列怎么用"
    assert "切到上方的「通道结论」那一页" in src, "脚注没指向通道结论那一页"


def test_R261_走了多远那一行是统一色():
    """用户: 「趋势列的描述都没有统一颜色, 有些是白色字体」。

    **这是 R257 留下的错**: 那一版把文字从「阶段」换成了「走了多远」(成熟度),
    却忘了换配色 —— 颜色仍按阶段码取, 于是同一句「走到中段」在上升中的票上是
    红的、在下跌中的票上是绿的、在横盘中的票上是近白的(`text-secondary`)。
    **颜色在说阶段, 文字在说走了多远, 两码事。**

    成熟度是一句事实读数, 不是判断, 所以统一给次要色。
    """
    root = _BOARD.parent
    cells = (root / "decision-board" / "cells.tsx").read_text(encoding="utf-8")
    body = "\n".join(ln for ln in cells.splitlines()
                     if not ln.lstrip().startswith(("//", "*", "/*", "{/*")))

    assert "PHASE_TEXT" not in body, (
        "「阶段配色」那张表又回来了 —— 它按**已经不显示的东西**给文字上色"
    )
    # [R277 → R297] 成熟度先搬到 SpreadCell、再并进 ConclusionCell, 这条一路跟着搬
    # —— **守的规矩一个字没变**: 成熟度是事实读数不是判断, 所以统一次要色,
    # 不许挂条件配色。快慢正相反(R278): 它**是**判断(在往多头还是空头变),
    # 所以按 `level` 上色 —— 两者用的是同一个 `Qualifier`, 差别只在传不传 `cls`。
    body = body[body.index("export function ConclusionCell"):]
    body = body[body.index("return ("):]
    def _tag(mark: str) -> str:
        """含 `mark` 的那一整个 `<Qualifier … />` —— **必须切到 `/>`**:
        `cls=` 写在 `text=` 的下一行, 只切到属性名那里的话它永远看不见
        (第一版就是这么错的, 本仓库这个坑的又一次)。"""
        i = body.index(mark)
        return body[body.rindex("<Qualifier", 0, i):body.index("/>", i) + 2]

    assert "cls=" not in _tag("ph?.maturity_cn"), (
        "「走了多远」挂上条件配色了 —— 它该走 Qualifier 的默认次要色"
    )
    # 反面配对: 快慢必须**有** cls —— 两个都统一次要色的话, 「跌得更急」与
    # 「跌势在缓」会变成同一个颜色, 那才是真的丢信息。
    assert "PACE_CLS" in _tag("ph?.pace_cn"), "快慢没按方向上色 —— 加速与减速会变成同一个颜色"


def test_R261_徽标与第二行仍各自按含义上色():
    """撤的是**挂错对象**的那一处配色, 不是把整列刷成一个颜色。

    [R290] 第二行从「三尺度对齐」换成「转折后第 N 天」之后, 那一行的配色跟着
    换了对象: 原来按 `align.level` 分四档, 现在只分**今天是不是转折日** ——
    因为这一行现在讲的就是这件事。规矩没变: 颜色必须说这一行自己的意思。
    """
    root = _BOARD.parent
    cells = (root / "decision-board" / "cells.tsx").read_text(encoding="utf-8")
    assert "${trendCls ?? ''}" in cells, "六态徽标的配色没了"
    # [R291] 转折那天点亮成一枚芯片(边框+底色+琥珀字), 平常是同尺寸的透明框 ——
    # 同一个盒子只换颜色, 所以行高一格都不跳。守的规矩没变: 这一行的颜色
    # 必须说这一行自己的意思(今天是不是转折)。
    assert "border-amber-400/45 bg-amber-400/10 font-medium text-amber-300" in cells, (
        "转折那天没点亮 —— 那一行该是琥珀芯片, 与复盘逐日表那个标记同色"
    )
    assert "'border-transparent text-muted'" in cells, (
        "平常那天的透明框没了 —— 没有它, 转折行会比别的行高一截"
    )


def test_R286_走势列显示今天是不是转折():
    """用户: 「走势这一列还要显示今天是不是转折, 我在趋势状态那部分发现了这个参数」。

    复盘的逐日表上转折那天挂着「← 转折」, 而决策台的走势列只有「已N天」——
    同一件事在一个页面上标出来、在另一个页面上要读的人自己从天数里推。
    """
    from tests.frontend_source import code_of
    code = code_of("components/stock-analysis/decision-board/cells.tsx")
    blk = code[code.index("export function ChannelStateCell"):]
    blk = blk[blk.index("return ("):]
    assert "trend?.flipped" in blk or "trend.flipped" in blk, (
        "走势列没读转折读数 —— 转折标记根本不会亮"
    )
    assert "转折" in blk, "走势列没把「转折」两个字印出来"


def test_R286_转折的词与复盘那边一致():
    """AGENTS.md 规则 12: 同一件事在两个页面上必须是同一个词。

    复盘逐日表用的是「转折」+ 琥珀色。决策台这一格换成「刚翻转」「拐点」之类,
    读的人就得先确认这两处说的是不是一回事 —— 这正是 R279 整理术语时的原话。
    """
    from tests.frontend_source import code_of
    cells = code_of("components/stock-analysis/decision-board/cells.tsx")
    review = code_of("components/stock-analysis/StockReviewDialog.tsx")
    blk = cells[cells.index("export function ChannelStateCell"):]
    blk = blk[blk.index("return ("):]

    assert "转折" in review, "场景没搭对: 复盘那边的「转折」不见了"
    for banned in ("刚翻转", "拐点", "变盘", "反转日"):
        assert banned not in blk, f"走势列用了「{banned}」而复盘用「转折」—— 同一件事两个词"
    assert "amber" in blk[blk.index("转折") - 400:blk.index("转折")], (
        "转折标记没用琥珀色 —— 复盘那边用的是 amber, 两处该同色"
    )


def test_R286_转折不在前端自己推():
    """`flipped` 与 `duration == 1` 恒等(后端 `test_R286_转折与已1天恒等` 钉住),
    正因为恒等, 前端**更不该**自己再推一遍: 两处各算各的, 哪天有一处漏改就
    开始各说各话。这一格只许读后端给的那个读数。
    """
    from tests.frontend_source import code_of
    code = code_of("components/stock-analysis/decision-board/cells.tsx")
    blk = code[code.index("export function ChannelStateCell"):]
    blk = blk[blk.index("return ("):]
    for derived in ("duration === 1", "duration == 1", "duration <= 1"):
        assert derived not in blk, (
            f"走势列自己从 `{derived}` 推转折了 —— 该读后端的 flipped"
        )
