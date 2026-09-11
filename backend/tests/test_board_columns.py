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


def _strip_title(jsx: str) -> str:
    """剥掉 JSX 里所有 `title={...}`, 只留**印出来**的部分。

    [R310] **正则在这儿不够用。** `_headers()` 那一版用的是
    `re.sub(r"\\{[^{}]*\\}", "", …)` 反复剥几遍, 对付简单表达式够了; 而出场线
    那个 title 是**模板串套模板串**(`` `${a ? '已破' : `还差 ${b}%`}` ``),
    嵌套三层, 正则剥不干净 —— 于是断言读到的是 title 里那份复述, 把**印出来**
    的价格删掉照样绿。这是 R310 变异电池当场逼出来的。

    所以这里真的数括号配对。
    """
    out, i = [], 0
    while True:
        j = jsx.find("title={", i)
        if j == -1:
            out.append(jsx[i:])
            return "".join(out)
        out.append(jsx[i:j])
        k, depth = j + len("title={") - 1, 0
        while k < len(jsx):
            if jsx[k] == "{":
                depth += 1
            elif jsx[k] == "}":
                depth -= 1
                if depth == 0:
                    break
            k += 1
        i = k + 1


def _cell(fn: str) -> str:
    """[R310] 某个单元格组件的源码(已剥注释)。

    **这是本仓库栽得最多的那个坑的收口。** 以前每条守卫各写一遍
    `code[code.index("export function A"):code.index("export function B")]` ——
    锚在**隔壁那个组件**上。隔壁一改名、一搬家、一删除, 这些断言要么 ValueError
    (还算走运, 至少红了), 要么悄悄把范围扩到文件末尾然后**照样绿**(R261 那条
    就是这么假绿了一轮)。R310 删「怎么办」一次打掉 9 处。

    改成锚在**自己**身上: 从自己开始, 切到下一个顶层 `export function`(或文件
    末尾)。隔壁是谁、还在不在, 与这条守卫无关。
    """
    from tests.frontend_source import code_of
    code = code_of("components/stock-analysis/decision-board/cells.tsx")
    i = code.index(f"export function {fn}")
    j = code.find("\nexport function ", i + 1)
    return code[i:] if j == -1 else code[i:j]


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
        # [R306] 列名「结论」→「档位」。用户: 「结论这个名称改成位置」—— 问到
        # 「通道位置」与打分系统里 `channel_pct` 撞名时, 选了「通道档位」。
        # 界面上本来就满处是「这一档」「十档」「换档」, 它是十个档位。
        # [R307] 「档位」又拆成两列。用户: 「这一列我只想看位置, 表示位置」。
        # [R310] **「怎么办」整列删掉了。** 用户问「可以删除吗, 会有什么影响」,
        # 看过影响清单(它是五套判定的收敛层; 删了这张表只剩读数没有结论;
        # 出场线的价格会从界面上消失)之后决定: 「那就删除了怎么办」。
        # 判定层一个字没动, 接口照旧返回 `playbook` —— 只是界面不读它了。
        # 出场线那一处**已经接住**: 搬进「持仓」列, 见那一条的守卫。
        # [R308] 「档位」→「位置」。用户: 「关于位置列, 我只需要知道当前短期
        # 通道位置和短中长的轨道组合, 其他不关心」—— 那十档判定整个从这一列
        # 撤走(它在复盘的「通道档位」页里一天不落), 只剩两个原始读数。
        # **这次不撞名**: R306 那回撞名是拿「通道位置」去命名**那十档判定**,
        # 而打分系统里 `channel_pct` 早就叫这个; 现在这一列印的**就是**
        # `channel_pct` 那个读数 —— 两处指同一件事, 同名正好是对的。
        "走势", "位置",                # 凭什么(判断必须连着, 不许被账目切开)
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
    judge = max(cols.index("走势"), cols.index("位置"))
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

    [R308] 判定那一侧的「已N天」**离开了决策台** —— 那一列只剩两个位置读数,
    十档判定连同它的时长一起归复盘的「通道档位」页。于是这条的正面断言跟着
    搬家: 它在那边还印着, 而且仍写成「已N天」——**那是另一个锚点**(这一档
    结论连着多久), 与「从转折那天数起」量的不是同一段, 分开叫反而更准。
    见名词表 NOT_A_CONFLICT。

    **搬家有两种错法, 所以两头各钉一条**: 两头都留就破了 R249「同一个数不许
    有两种说法」; 两头都没有就是把一个后端还在算的数悄悄删掉(R246/R248
    在"字段静默消失"上栽过两次)。
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
    # [R308] 决策台上不许再有判定那份天数 —— 那一列已经不印判定了
    assert "已{" not in body, (
        "决策台又印起「已N天」了 —— 那一列只说位置, 判定连同它的时长在复盘页"
    )
    dlg = (root / "StockReviewDialog.tsx").read_text(encoding="utf-8")
    assert "已{now.days}天{now.capped ? '+' : ''}" in dlg, (
        "判定那份天数搬进复盘页之后就没了 —— 那是删数, 不是搬家"
    )

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

    # [R307] 「怎么办」曾经从禁用词里拿掉过 —— 那时它是一个列名。
    # [R310] 那一列删了, 于是它**回到禁用词那一侧**: 表头上不许再出现它,
    # 无论是作为列名(已经没有了)还是缀在别人头上。与 R297 对「进度」做的
    # 是同一件事 —— 守的规矩一个字没变: **表头只印列名。**
    for bad in ("贵不贵", "六态", "'价'", "涨跌'", "怎么办"):
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
    for name in ("位置", "走势", "现价/涨跌", "持仓"):
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
    # [R310] `play` 也随列消失了 —— 「怎么办」整列删掉。**判据与前面每一次
    # 逐字相同: 点不到就删。** 见 test_R310_按急迫程度排退役了而且退干净了。
    for one in ("caret('name')", "caret('changePct')", "caret('trend')",
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
    # [R310] `play` 加进来 —— 「怎么办」那一列删了, 它的表头跟着没了
    for dead in ("'close'", "'ks'", "'km'", "'kl'", "'held'", "'cost'", "'report'",
                 "'spread'", "'verdict'", "'exit'", "'confidence'", "'play'"):
        assert dead not in keys, f"排序键 {dead} 点不到却还留着"
    # 比较器里也不该还有它们的分支
    cmp_ = body[body.index("const sortedRows"):]
    cmp_ = cmp_[:cmp_.index("const arr = ")]
    for dead in ("case 'close'", "case 'ks'", "case 'verdict'", "case 'held'",
                 "case 'cost'", "case 'report'", "case 'spread'",
                 "case 'exit'", "case 'confidence'", "case 'play'"):
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
    # [R310] `play` 随列退役
    for key, why in (("urgency", "该动了: order 越小越急"),
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

    表头 title 里那句「怎么排」只有在方向对的时候才成立。说明与行为不一致时,
    **说明会赢**(用户信它), 于是排出来的表与预期相反而没人发现。

    [R310] 原来钉的是「怎么办」那一列(「按急迫程度排: 按纪律走 > …」), 那一列
    删了。**规矩一个字没变, 换到还在的那一列上**: 「AI 信号」的表头说买入排在
    最前, 而 `SIGNAL_RANK` 里买入 = 0 —— 同样只有升序才成立。

    换主语而不是删掉这条: R214 那个病(说明与接线相反)跟具体哪一列无关。
    """
    body = _board_body()
    block = body[body.index("FIRST_DIR"):]
    block = block[:block.index("}")]
    assert "signal: 'asc'" in block, (
        "AI 信号首次点击不是升序 —— 而 SIGNAL_RANK 里买入=0, 降序会把「观望」顶到最前"
    )
    # 正面配对: 那张 rank 表确实是"越小越要紧"
    rank = body[body.index("SIGNAL_RANK"):]
    rank = rank[:rank.index("}")]
    assert "buy: 0" in rank, "SIGNAL_RANK 变了, 上面那条升序的理由就不成立了"


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


# [R315 → **R316 退役**] R315 那五条(`位置列是一个数加一条轨` / `位置列是短期
# 百分比加三档轨点` / `轨外的点按在端帽上而数字照印真值` / `三个点分得出谁是谁`
# / `位置列的两块都在`)钉的都是那条横轨与轨上三个点。
#
# **用户看了实物说「更加看不懂了」。** 复盘原因: 一条 7px 高的线, 两端那两道
# 端帽在真实渲染里几乎看不见 —— 于是那条轨**没有任何刻度可言**, 而 `-3%` /
# `134%` 这种越界百分比在没有参照物时比 `6/100` 还费解。
#
# **图形不是万能药: 一个画不清楚的图, 比一句写清楚的话差得多。**
#
# 它们守的意图 ——「这个数得有参照物」「出界不许被抹平」「两块都不许消失」——
# 一条都没退, 全部换成下面这几条: 参照物从"一条轨"换成**一句话**(低于下轨
# 1.1%), 而话不需要渲染精度。


def test_R316_位置列是位置名加一句能交易的距离():
    """用户在四个方案里选的这一版:「只说短期 + 一句能交易的距离」。

    两行, 各管一件事:
      · 位置名 —— 扫 166 行时只看这一行的**颜色**(红=上轨侧, 蓝=下轨侧);
      · 离那条轨还有多远 —— **价格口径**, 能直接拿去下单的数。

    第二行换口径是这一版的要害: 不再是"通道刻度 0~100"(抽象、会越界), 而是
    价格百分比 —— 不需要先在脑子里把通道宽度换算一遍。
    """
    pos = _cell("PositionCell")
    body = pos[pos.index("return ("):]
    assert "{s ? s.pos_cn : '—'}" in body, "位置名那一行没了, 或者没有兜底"
    assert "{near.label}" in body and "{near.pct}%" in body, "离轨距离那一行没了"
    # 尺度标签、横轨、轨上的点都不许回来 —— 它们是前两版那两个毛病的症状
    for gone in (">短期<", ">短中长<", "bg-border/70", "POS_FILL"):
        assert gone not in pos, f"前两版的东西又回来了: {gone}"


def test_R316_距离口径与出场线逐字相同():
    """**这条是这一版最要紧的一条。**

    「还差多远」这件事仓库里早就有一个口径: `(线 − 现价) / 现价` ——
    出场线的 `distance_pct`、六态的翻转距离都走它(R178 立的, 后端
    `livermore_service._distance_pct` 有一份带注释的实现)。

    这一列要是自己另算一套(比如拿轨价当分母), 同一个"还差多远"在一个界面上
    就有了两种算法 —— 而两处定义同一件事必然漂, 这是本仓库反复在治的病。
    """
    pos = _cell("PositionCell")
    gap = pos[pos.index("function railGap"):] if "function railGap" in pos else ""
    if not gap:
        from tests.frontend_source import code_of
        code = code_of("components/stock-analysis/decision-board/cells.tsx")
        gap = code[code.index("function railGap"):]
    # 三条路都必须以**现价**作分母
    for expr in ("(close - b.upper) / close", "(b.lower - close) / close",
                 "(b.upper - close) / close", "(close - b.lower) / close"):
        assert expr in gap, f"缺了这一路的距离算法: {expr}"
    # 反面: 不许拿轨价当分母 —— 那就是第二套口径
    for bad in ("/ b.upper", "/ b.lower", "/ (b.upper", "/ (b.lower"):
        assert bad not in gap, f"拿轨价当分母了({bad})—— 与出场线口径就不一致了"


def test_R316_看哪条轨跟着位置名走():
    """**不另判一次。** 位置名已经说了在场的是哪条轨, 再写一套 if 判"该看上轨
    还是下轨", 就是同一个判定两处实现。

    只有「通道内」没有指定轨 —— 那时取**更近的那一条**(先撞上的就是它)。
    """
    from tests.frontend_source import code_of
    code = code_of("components/stock-analysis/decision-board/cells.tsx")
    gap = code[code.index("function railGap"):]
    assert "b.pos === 'above'" in gap and "b.pos === 'below'" in gap, (
        "破轨那两档没有跟着位置名走"
    )
    assert "up <= down ?" in gap, "「通道内」时没有取更近的那一条"


def test_R316_方向由措辞承担数字不带负号():
    """「低于下轨 -1.1%」是双重否定, 读的人要在脑子里再翻一次。

    所以数字取绝对值, 方向全交给措辞: 高出 / 低于 / 距。
    """
    from tests.frontend_source import code_of
    code = code_of("components/stock-analysis/decision-board/cells.tsx")
    gap = code[code.index("function railGap"):]
    assert "Math.abs(raw)" in gap, "数字没取绝对值 —— 会印出「低于下轨 -1.1%」"
    for word in ("'高出上轨'", "'低于下轨'", "'距上轨'", "'距下轨'"):
        assert word in gap, f"少了一种措辞: {word} —— 方向就没人承担了"


def test_R316_现价是传进来的不是从_pct_反推的():
    """`pct` 后端只留三位小数(`round(..., 3)`), 反推出来的收盘价会差几分钱。

    这一列印的是**要拿去下单的数**, 差几分钱就是错的。所以现价从行数据直接传,
    不从别的读数倒推。
    """
    pos = _cell("PositionCell")
    assert "close?: number | null" in pos, "PositionCell 没有接收现价"
    # 反面: 不许出现"拿 pct 和轨价反推收盘价"那种写法
    from tests.frontend_source import code_of
    code = code_of("components/stock-analysis/decision-board/cells.tsx")
    gap = code[code.index("function railGap"):]
    assert "b.pct" not in gap, (
        "离轨距离又拐回通道刻度去算了 —— 它该只用现价与轨价。"
        "(`railGap` 自己的返回字段也叫 `pct`, 所以这里禁的是**读 `b.pct`**, "
        "不是禁这三个字母 —— 第一版就是这么写宽了然后假红的)"
    )
    # **锚在 `<PositionCell` 那个调用点上。** 走势列(`ChannelStateCell`)也收
    # `close={r.close}`, 只查整份源码里有没有这个串, 把这一列的那个删掉照样绿
    # —— R316 变异电池当场逼出来的, 与"锚在邻居身上"是同一族的假守卫。
    board = _src()
    call = board[board.index("<PositionCell"):]
    call = call[:call.index("/>") + 2]
    assert "close={r.close}" in call, "板子没把现价递给「位置」列, 这一列永远只能印 —"


def test_R316_两行各自都有兜底():
    """行高一会儿一行一会儿两行, 166 行扫下来就是锯齿(R217 那个病)。

    算不出来时: 位置名给 `—`, 距离那一行也给 `—` —— **两行都还在**。
    """
    pos = _cell("PositionCell")
    btn = pos[pos.index("<button"):]
    btn = btn[:btn.index("</button>")]
    assert "{s ? s.pos_cn : '—'}" in btn, "位置名那一行没有兜底"
    assert "{near ? (" in btn and ") : (" in btn, "距离那一行没有兜底"
    assert btn.count("text-muted/30") == 2, (
        "两行的占位不全 —— 少一个那一行就会整个消失, 行高跟着跳"
    )


def test_R316_位置名按位置上色():
    """扫 166 行时**只看第一行的颜色**: 红 = 在上轨那一侧, 蓝 = 下轨那一侧。

    配色走共用的 `POS_TEXT` —— 与时间轴那条位置带同一份表, 不许在这里另抄
    (R308 立的规矩: 两份色表分居两地, 只改一处就会漂, 而那种漂移不报错)。
    """
    pos = _cell("PositionCell")
    body = pos[pos.index("return ("):]
    assert "POS_TEXT[s.pos]" in body, "位置名没按位置上色 —— 那就没法靠颜色扫表了"
    for local in ("bg-red-400'", "text-red-400'", "text-sky-400'"):
        assert local not in body, f"这一格自己又抄了一份色({local})—— 色表只许一处"


def test_R316_三档与组合码没丢只是进了悬停():
    """用户选的是「只说短期」, 但**只说短期不等于把别的删了**。

    三档各自的位置与距离、27 格那个组合码、R246 那份时长, 全在悬停里 ——
    产出了却没人接, 与没做是一回事(`state_run` 就这么死过一轮)。
    """
    pos = _cell("PositionCell")
    tip = pos[:pos.index("return (")]
    assert "(['s', 'm', 'l'] as const)" in tip, "悬停里没有三档各自的位置"
    assert "三档组合码" in tip, "悬停里没有 27 格那个组合码"
    assert "stateRun" in tip, "R246 那份时长又没人读了"
    assert "轨价 − 现价" in tip, "悬停没说清距离是什么口径"


def test_R310_出场线的价格还在界面上():
    """[R212 → R310] **一笔十几版之前立下的对价, 必须有人替它站着。**

    R212 用户说「止盈线这一列不要了」, 那一列撤掉时写下的交换条件是:
    「信息没丢 —— 出场线破了或逼近, 结论列会把线价写在徽标上」。

    R310 删「怎么办」时查了一遍: `r.exit` 在整张表上**零个渲染点**, 那条线
    只从 `play.price` 露过面。也就是说那一列一删, **这笔对价就没人兑现了**,
    而且不会有任何东西报错 —— 只是有一天你发现止盈线看不见了。

    所以它搬进「持仓」列。归那儿而不是别处: 出场线按**我的成本、我的持有
    天数**算, 它是「我的账」里的事, 不是「凭什么」。而且旁边那个成本输入框
    的提示写着「出场线按它算」—— 不接住它, 那句提示就成了假话。

    这条钉三件事: 印出来了 / 印的是价不只是名 / 破没破分得开。
    """
    src = _src()
    i = src.index("{r.held && r.exit && (")
    blk = src[i:src.index("\n                        )}", i)]

    # **必须先剥掉 `title`。** 那个悬停里本来就复述着线名、价格和已破/还差 ——
    # 直接读整段的话, 把**印出来的**那个价删掉断言照样绿(这是 R310 变异电池
    # 当场逼出来的, 与 `_headers()` 里"属性必须先剥"是同一个坑)。
    render = _strip_title(blk)

    assert "r.exit.line_cn" in render, "出场线只印了价没印是哪条线(止盈?止损?生命线?)"
    assert "r.exit.line.toFixed(2)" in render, (
        "出场线没印价 —— 只说「止盈线」而不给数字, 等于没说"
    )
    assert "r.exit.triggered" in render, (
        "已破与没破长得一样 —— 那是这条线最要紧的一个状态; "
        "写在 title 里不算, 扫表时看不见"
    )
    # 它必须在「持仓」那一格里, 不许飘到别处
    td = src[:i]
    assert td.rindex("<td") > td.rindex("<PositionCell"), "出场线跑到「持仓」以外的格子里了"


def test_R309_列宽加起来是一百且没有一列留空():
    """[R309] **谁拿着余量, 谁就会无声无息地长大。**

    改之前「AI 信号」写的是 `w: ''` —— 注释说得明明白白「不给宽度, 吃掉剩下的」。
    而这张表是 `table-auto`, 不给宽度 = 纯内容驱动: AI 那段不换行的理由把
    max-content 顶到多高, 这一列就有多宽。**实测吃掉约 47%, 整张表的一半。**

    加起来正好 100 之后, 想给谁加宽就必须从另一列身上明写着拿 —— 宽度成了
    一笔要记账的东西, 而不是"剩下的归谁"。
    """
    src = _src()
    blk = src[src.index("const BOARD_COLS = ["):]
    blk = blk[:blk.index("] as const")]
    ws = re.findall(r"label: '([^']+)', w: '([^']*)'", blk)
    assert len(ws) == len(_cols(src)), f"有列没被这条量到: {ws}"
    empty = [lab for lab, w in ws if not w.strip()]
    assert not empty, (
        f"这些列没写宽度, 于是谁也管不住它们能长多大: {empty}\n"
        "—— 「吃掉剩下的」正是 AI 信号那一列长成半张表的原因"
    )
    total = sum(float(w.rstrip('%')) for _, w in ws)
    assert abs(total - 100) < 1e-9, (
        f"列宽加起来是 {total}% 而不是 100% —— 差额会被浏览器按内容悄悄分掉, "
        f"分给谁取决于哪一列的文字最长\n  {ws}"
    )


def test_R309_别人的意见不许比自己的判断占得宽():
    """[R249 → R309] 列序那条纪律写的是 **认票 → 凭什么 → 我的账 → 别人的意见**。
    R249 把它钉成了**顺序**, 这条把它钉成**分量**。

    AI 信号是「别人的意见」: 它可以在场(而且删不得 —— 写信号的入口只有这张表,
    `paper_trader_run` 还在读存下来的信号), 但它**不该比我自己的判断加起来
    还宽**。R309 之前它一个人占 47%, 而判断那几列加起来才 32.5% ——
    **版面把话语权给反了**, 而且没有任何东西会因此报错。

    [R310] **这条昨天刚立, 今天就抓到了一次真事故。** 删掉「怎么办」让判断那
    一侧一下子少了 27%, 只剩 走势 + 位置; AI 原样留着 30% 就会顶到它们脸上。
    于是 AI 跟着收到 26% —— **不是我想收窄它, 是这条不变式逼的。**

    判断那一侧是**列出来的**而不是"除 AI 之外的都算": 标的/现价是认票、持仓是
    我的账, 它们再宽也不代表我对这只票有判断。
    """
    src = _src()
    blk = src[src.index("const BOARD_COLS = ["):]
    blk = blk[:blk.index("] as const")]
    got = {lab: float(w.rstrip('%'))
           for lab, w in re.findall(r"label: '([^']+)', w: '([^']+)%'", blk)}
    judge = got["走势"] + got["位置"]
    assert got["AI 信号"] < judge, (
        f"AI 信号占 {got['AI 信号']}%, 而我自己的判断三列加起来才 {judge}% —— "
        "版面把话语权给反了"
    )


def test_R309_AI_理由截到两行且全文进悬停():
    """[R217 → R253 → R255 → R307 → R309] **行高参差**这个病, 这张表一路在收:
    R217 收的是一格摞五层, R253 收的是到价预案"能挤就挤", R255/R307 收的是
    「怎么办」那一行说明。**只剩 AI 理由一直是整段不截断的** —— 一段长理由能把
    一行顶成五行, 旁边六列跟着空着。一屏扫 166 行的时候, 行高参差比少看几个字
    伤得多。

    所以它跟这张表其余每一格一个待遇: **截断 + 全文进悬停**。
    「截了却不给全文」是把话吞了, 那是另一种病, 所以两条一起钉。
    """
    src = _src()
    blk = src[src.index("{r.sig.reason && ("):]
    blk = blk[:blk.index(")}")]
    assert "line-clamp-2" in blk, (
        "AI 理由又变回整段不截断了 —— 它会一个人把行高顶起来, 旁边六列空着"
    )
    assert "title={r.sig.reason}" in blk, "截了却没给全文 —— 那是把话吞了, 不是排版"



# [R315 → **R316 退役**] `test_R315_位置列的两块都在` 钉的是「一个数 + 一条轨」
# 那个形状。轨没了, 由 `test_R316_两行各自都有兜底` 接手 —— 守的意图一个字没变:
# **两块都不许因为没数据而消失**, 否则行高一会儿一块一会儿两块, 166 行扫下来
# 就是锯齿(R217 那个病)。

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

    这一层在别处一律叫**通道档位**(`keltner.verdict` / 决策台那一列 / 复盘上方
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


def test_R258_那一列叫通道档位而且脚注指得对():
    """[R258 → R295 → R296] 守的规矩一个字没变: **同一层判定在界面上只许一个
    名字**, 而且脚注不许指着不存在的东西。变的只是它长在几张表里。

    R295 用户说「删掉这一列」, 它离开了趋势表; R296 用户说「趋势状态删除的那一
    列我需要恢复」, 它回来了 —— 于是**两张逐日表里各有一列**。这正是这条守卫
    最该盯的时刻: 两个列头并排放着, 名字差一个字就是同一样东西两个名字。
    """
    root = _BOARD.parent
    src = (root / "StockReviewDialog.tsx").read_text(encoding="utf-8")
    assert src.count(">通道档位</th>") == 2, (
        f"叫「通道档位」的列头有 {src.count('>通道档位</th>')} 个 —— 两张逐日表该各一列"
    )
    assert ">结论</th>" not in src, "有一列还叫「结论」—— 同一层判定只许一个名字"
    # 脚注曾经指着一个**已经不存在的页签**(R200 的旧名, R223 已改回「通道档位」);
    # R295 又出过一次同形状的: 那一列删掉后脚注还写着"悬停看完整卡片"。
    # R296 那一列回来了, 脚注跟着回来 —— 措辞得跟列头对上。
    assert "「通道档位」列悬停看完整卡片" in src, "趋势那页的脚注没提这一列怎么用"
    assert "切到上方的「通道档位」那一页" in src, "脚注没指向通道档位那一页"

    # [R306] **这一层在别处的名字也一起钉**。改名之后名词表能拦住
    # 「通道结论」, 但**拦不住光写「结论」两个字** —— 而「结论」不能一律禁:
    # 今日总览另有一列合法地叫「结论」(指「今天能不能下手」, 是另一层)。
    # 所以点名钉死, 这是变异测试当场逼出来的(导出那一列原来能悄悄漂回去)。
    #
    # [R308] **决策台那一列退出了这一层** —— 它现在印的是两个原始读数
    # (短期通道位置 + 三档组合码), 不是那十档判定, 所以它叫「位置」不算
    # 这一层多了个名字。反过来它**不许**再叫「档位」: 那会让人以为表上那一格
    # 就是判定, 而判定在复盘页。导出件仍导判定, 所以仍叫「档位」。
    board = _src()
    assert "{ label: '位置'," in board, "决策台那一列不叫「位置」了"
    assert "{ label: '档位'," not in board, (
        "决策台那一列又叫回「档位」—— 它印的是坐标不是判定, 同名会被读成判定"
    )
    assert "{ label: '结论'," not in board, "决策台那一列又叫回「结论」"
    # root = .../components/stock-analysis, 所以 lib/ 要往上两级
    exp = (root.parent.parent / "lib" / "decisionBoardExportColumns.ts").read_text(encoding="utf-8")
    assert "key: 'verdict', label: '档位'" in exp, (
        "导出件里那一列不叫「档位」—— 导出是拿去发给别人的, 名字漂了最难发现"
    )


# [R261 → **R310 退役**] `test_R261_走了多远那一行是统一色` 钉的是
# 「走了多远」用统一次要色、「快慢」按方向上色。**两个 `Qualifier` 随
# 「怎么办」列一起删了**(它们是那个判断的刻度, 判断没了就是没有主语的形容词),
# 于是这条没有可守的对象。
#
# 它那半条仍在的意图 ——「快慢的颜色编的是符号不是词」—— 由
# `test_R278_*`(在别处)守着后端那份判定, 更靠前也更准。
# 「这两个刻度不许漂回位置列」由 `test_R310_两个刻度随怎么办一起离场` 接手。


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
