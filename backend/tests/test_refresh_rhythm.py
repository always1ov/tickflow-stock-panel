"""[R333] 自动刷新的节奏 —— 一处定义, 页面挑档不写数。

用户: 「整个系统类似这些按钮要周期自己刷新, 不能等我手动点, 合理规格周期」。

这组守卫钉的是**规格本身**与几个关键页的接线, 不去清点全项目 45 处历史魔数 ——
那些按页迁移, 见 FORK_NOTES R333。
"""
from __future__ import annotations

import re

from tests.frontend_source import code_of

RHYTHM = "lib/refreshRhythm.ts"
BOARD = "components/stock-analysis/WatchlistDecisionBoard.tsx"
PAPER = "pages/FlipPaper.tsx"


def _table() -> dict[str, tuple[str, str]]:
    """解析档位表 → {档: (盘中, 盘后)}。"""
    code = code_of(RHYTHM)
    blk = code[code.index("const TABLE"):code.index("export function refreshEvery")]
    out = {}
    for m in re.finditer(r"(\w+): \{ open: ([^,]+), closed: ([^}]+) \}", blk):
        out[m.group(1)] = (m.group(2).strip(), m.group(3).strip())
    return out


def test_R333_四个档位齐全且盘中不慢于盘后():
    t = _table()
    assert set(t) == {"live", "derived", "slow", "static"}, f"档位对不上: {set(t)}"
    for name, (op, cl) in t.items():
        if op == "false" or cl == "false":
            continue
        assert eval(op.replace("MIN", "60000")) <= eval(cl.replace("MIN", "60000")), \
            f"{name}: 盘中不该比盘后还慢"


def test_R333_盘中盘后分开_依据是实时窗口():
    """**锚在函数体里, 不是整个文件。**

    第一版断言 `"inRealtimeWindow()" in code` —— 而 `refreshEveryWhenLive` 里
    也有一处, 所以把 `refreshEvery` 改成永远返回盘后节奏, 字符串照样在, 守卫
    照样绿。变异电池当场抓到。锚太宽 = 没有锚(R310 收口过同一个毛病)。
    """
    code = code_of(RHYTHM)
    assert "from '@/lib/marketClock'" in code, "复用 R319 那份时钟, 不重写"
    for fn in ("export function refreshEvery(", "export function refreshEveryWhenLive("):
        body = code[code.index(fn):]
        body = body[:body.index("\n}")]
        assert "inRealtimeWindow()" in body, f"{fn} 里没按实时窗口分档"
        assert "row.open" in body and "row.closed" in body, f"{fn} 只用了一档"


def test_R333_返回的是函数不是常数():
    """**给常数的话, 盘中打开的页面到收盘仍按盘中节奏轮询一整晚** ——
    定时器是挂载那一刻就定死的。"""
    code = code_of(RHYTHM)
    fn = code[code.index("export function refreshEvery("):code.index("export function refreshEveryWhenLive")]
    assert "return () => {" in fn, "必须返回函数, React Query 才会每次重新问"


def test_R333_静态档不轮询():
    t = _table()
    assert t["static"] == ("false", "false"), "词表、规则口径改了要重新部署, 轮询没意义"


def test_R333_不打开后台轮询():
    """打开 refetchIntervalInBackground 等于后台标签页整夜打接口。"""
    code = code_of(RHYTHM)
    assert "refetchIntervalInBackground" not in code or "不去打开它" in code_of(RHYTHM)


def test_R333_模拟盘自己刷_不等手动():
    code = code_of(PAPER)
    assert "refetchInterval: refreshEvery('derived')" in code, "主查询没接节奏"
    assert "refetchInterval: refreshEvery('static')" in code, "规则口径不该轮询"
    assert "rhythmHint('derived')" in code, (
        "页头要写出它在自己刷 —— 否则用户会以为数字卡住了")


def test_R333_决策台判定层自己刷():
    """行情那一侧有 SSE(watchlist-enriched 在失效列表里), 但**判定层不在**。"""
    code = code_of(BOARD)
    assert "refetchInterval: refreshEvery('derived')" in code, "六态没接 —— 它是日线派生"
    assert "refetchInterval: refreshEvery('live')" in code, "「该动了」没接 —— 它随实时价动"
    # [R435] 原来还有一条「AI 信号走 slow 档」—— 那一列随 AI 信号撤了
    assert "refetchInterval: 60 * 60 * 1000" not in code, "那个写死的一小时该换掉了"


def test_R333_六态走_derived_不走_live():
    """六态收盘落盘才翻面, 盘中不会变 —— 按分钟刷它是白烧后端。"""
    code = code_of(BOARD)
    blk = code[code.index("const trendsQ = useQuery"):]
    blk = blk[:blk.index("})")]
    assert "refreshEvery('derived')" in blk


def test_R333_该动了走_live_不走_derived():
    code = code_of(BOARD)
    blk = code[code.index("const urgencyQ = useQuery"):]
    blk = blk[:blk.index("})")]
    assert "refreshEvery('live')" in blk, "距离随实时价动, 陈旧的紧迫度会误导"


def test_R333_界面提示从规格出_不各页各写一份():
    code = code_of(RHYTHM)
    assert "export function rhythmHint" in code
    paper = code_of(PAPER)
    assert "分钟自动刷新" not in paper, "措辞不许在页面里另写一份"
