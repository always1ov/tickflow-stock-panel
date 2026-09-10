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
        # [R277] 从「走势」里拆出来独立成列 —— 它仍属"凭什么"那一段, 所以插在
        # 走势与结论之间。[R284] 列名「间距」→「进度」(用户: 别人看不懂)。
        "走势", "进度", "结论",       # 凭什么(判断必须连着, 不许被账目切开)
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
    judge = max(cols.index("走势"), cols.index("进度"), cols.index("结论"))
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


def test_六态天数与结论天数同一个说法():
    """同一行里两个天数。六态写「3天」而结论写「已25天」时, 读的人得先判断
    这两个数是不是一回事 —— 是的: 都是尾部连续段、都按交易日、都是「到今天还在」。

    用户: 「必须要统一表达, 不能又两种多种表述」。
    """
    root = _BOARD.parent
    cells = (root / "decision-board" / "cells.tsx").read_text(encoding="utf-8")
    # 只看渲染出去的文本, 注释里复述历史说法是允许的
    body = "\n".join(ln for ln in cells.splitlines()
                     if not ln.lstrip().startswith(("//", "*", "/*")))
    assert "已{trend.duration}天" in body, "六态徽标没用统一说法「已N天」"
    assert "已{d.days}天" in body, "结论徽标没用统一说法「已N天」"

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
    # [R277] 「间距」从禁用词里拿掉了 —— **它现在是一个列名, 不再是排序目标**。
    # 但原来的意图一个字不改: 它不许再作为分层缀在「走势」头上。
    trend_th = render[render.index("走势") - 400:render.index("走势") + 200]
    assert "进度" not in trend_th, "「进度」又缀回走势表头上了 —— 它该是独立一列"
    # 正面: 列名都还在
    for name in ("结论", "走势", "进度", "现价/涨跌", "持仓"):
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
    for one in ("caret('name')", "caret('changePct')", "caret('trend')",
                "caret('play')", "caret('spread')",
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
    # [R277] `spread` 从这张名单里拿掉了 —— **它不再点不到**: 间距独立成列之后
    # 有了自己的表头按钮。这条测的从来是"有没有够不着的死键", 不是"spread 不许
    # 存在"; 下面 `test_R277_每个排序键都够得着` 把这个意图直接测出来, 不再靠
    # 手写名单跟进(名单是要人记得改的东西, 而人不会记得)。
    # [R284] held / cost / report 加进来 —— 它们的表头随列合并/撤销消失了
    for dead in ("'close'", "'ks'", "'km'", "'kl'", "'held'", "'cost'", "'report'",
                 "'verdict'", "'exit'", "'confidence'"):
        assert dead not in keys, f"排序键 {dead} 点不到却还留着"
    # 比较器里也不该还有它们的分支
    cmp_ = body[body.index("const sortedRows"):]
    cmp_ = cmp_[:cmp_.index("const arr = ")]
    for dead in ("case 'close'", "case 'ks'", "case 'verdict'", "case 'held'",
                 "case 'cost'", "case 'report'",
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


def test_R277_间距按带符号排不按绝对值():
    """[R251 那条的形状] 表头写着「多头拉得最开在前 → 空头拉得最开在前」——
    那句话只有**带符号**才成立。

    取了绝对值的话, 一只崩得最惨的票会和一只走得最强的票并排顶在最前面, 而且
    看不出来(它确实排序了, 只是排的不是表头说的那件事)。变异验证时这一处是
    12 个里唯一没被抓到的, 所以补这一条。
    """
    body = _board_body()
    cmp_ = body[body.index("case 'spread'"):]
    cmp_ = cmp_[:cmp_.index("\n", cmp_.index("case 'spread'") + 10)]
    assert "Math.abs" not in cmp_, (
        f"间距排序取了绝对值 —— 空头拉得最开的会混进多头最强的里面: {cmp_.strip()}")
    src = _src()
    th = src[src.index("<thead"):src.index("</thead>")]
    assert "带符号" in th, "表头没说清是带符号排 —— 说明与行为得对得上"


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

    assert "flex-col items-start" in blk, "结论列没有竖排左对齐"
    assert "flex flex-wrap items-center justify-center" not in blk, (
        "两个徽标又横排回去了"
    )
    assert "whitespace-normal break-words" in blk, (
        "说明又变回单行截断了 —— AI 信号那一列的理由是整段折行的"
    )
    assert "truncate" not in blk, "说明还在用 truncate 截断"
    assert "!text-left" in blk, "竖排之后必须左对齐, 否则三行的左边缘参差不齐"


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
    assert "{trend.state_cn} 已{trend.duration}天" in blk, "方向那一行没了"
    # [R277] 成熟度**搬去 SpreadCell 了**, 走势列于是只讲方向(六态 + 三尺度对齐)。
    # 这条不再要求它出现在这一格里, 改成要求它**不在这里重复印一遍** ——
    # 同一个读数印两列, 读的人得先确认它们是不是一回事。
    assert "{ph.maturity_cn}" not in blk, (
        "成熟度又印回走势列了 —— 它现在是「间距」列的内容, 两处都印是重复"
    )
    assert "{ph.pace_cn}" not in blk, "快慢也一样, 它属于「间距」列"


def test_R277_成熟度与快慢在间距那一格里():
    """正面: 搬家不是删除。两个读数都要在新格子里真的渲染出来。

    **加速度此前在决策台上根本看不见** —— 走势列那一行写的是
    `align ? align.cn : pace_cn`, 而 `alignment()` 只要六态/位置/间距三样都在
    就返回非空(几乎永远), 于是快慢那一支轮不上; 悬停里被同一个三元顶掉。
    它只剩「结论」列悬停里的一行。这条钉住它现在有自己的位置。
    """
    root = _BOARD.parent
    cells = (root / "decision-board" / "cells.tsx").read_text(encoding="utf-8")
    body = "\n".join(ln for ln in cells.splitlines()
                     if not ln.lstrip().startswith(("//", "*", "/*", "{/*")))
    i = body.index("export function SpreadCell")
    blk = body[body.index("return (", i):]
    assert "{ph.maturity_cn}" in blk, "间距列没印成熟度"
    assert "{ph.pace_cn}" in blk, "间距列没印快慢 —— 加速度又看不见了"


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
    assert "【通道】${ph.cn}" in cells, "阶段从悬停里也没了 —— 那是删信息, 不是理顺"
    assert "该盯什么" in cells, "「该盯什么」没了"


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


def test_R258_复盘表那一列叫结论():
    root = _BOARD.parent
    src = (root / "StockReviewDialog.tsx").read_text(encoding="utf-8")
    assert ">结论</th>" in src, "复盘逐日表那一列没改成「结论」"
    # 脚注曾经指着一个**已经不存在的页签**(R200 的旧名, R223 已改回「通道结论」)
    assert "切到上方的「通道结论」" in src, "脚注还指着旧页签名"


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
    # [R277] 成熟度搬到 SpreadCell 了, 这条跟着搬 —— **守的规矩一个字没变**:
    # 成熟度是事实读数不是判断, 所以统一次要色, 不许挂条件配色。
    # 从 SpreadCell 的 `return (` 起算 —— 那一格的**悬停文案**里也提到成熟度,
    # 直接 index 会命中悬停那一处, 而这条问的是渲染出去的那一行的颜色。
    body = body[body.index("export function SpreadCell"):]
    body = body[body.index("return ("):]
    i = body.index("{ph.maturity_cn}")
    line = body[body.rindex("<span", 0, i):i]
    assert "text-muted" in line and "${" not in line, (
        f"「走了多远」那一行的颜色又变成按条件取了: {line.strip()}"
    )


def test_R261_徽标与力度仍各自按含义上色():
    """撤的是**挂错对象**的那一处配色, 不是把整列刷成一个颜色 ——
    六态徽标按状态、力度按排列层级, 那两处的颜色说的正是它们自己的意思。"""
    root = _BOARD.parent
    cells = (root / "decision-board" / "cells.tsx").read_text(encoding="utf-8")
    assert "${trendCls ?? ''}" in cells, "六态徽标的配色没了"
    assert "ph.align.level === 3 ? 'text-red-400/80'" in cells, "力度那一行的配色没了"


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
