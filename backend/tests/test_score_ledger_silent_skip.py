"""[R391/R392] 台账记不成的时候要有人知道; 体检空态要说得出为什么空。

## 这一组的由来, 连同它自己走过的弯路

用户报「体检按钮的功能失效了」—— 弹窗能开, 但报错或说台账是空的。

**第一版(R391)把病因诊断错了。** 我看到 `_build_overview` 里落台账那段只有
「条件成立」那一支有动作, 就认定"开着实时行情看盘 → 台账天天不记"是病根, 给
不成立的那几支都接上了 `_h.skip`。复审指出 [R136] 之后**日线管道落盘后会自己跑
一次 `_build_overview`** —— 那才是"每个数据日都被走到"的保底路径, 页面上这次
跳过并不会少一天样本。于是那几条上报是**把一件本来就对的常态塞进故障通道**,
只会让自检条在每个盘中日常驻一行, 而它立起来的全部理由就是"一切正常时一个像素
都不占"(R274)。R392 把那两支撤回去了。

**真正留下来的两条结论**:

1. `record_day` 自己吞异常, 失败只体现在返回值上 —— 不看返回值的话, 写盘挂了
   和写成功在界面上长得一模一样。这一条是真的静默失败, 要报。
2. 体检那个接口是**同步计算型**的(每次都补算历史收益), 却挂在默认 30 秒闸上,
   台账越厚越容易直接超时 —— 那才是用户看到的「读取台账失败」。

外加空态那段话: 它改过两轮, **两轮都是在说假话**(先是指向已删的「今日总览」,
再是我写的「这一页每打开一次就记一天」)。所以这里钉的不是某句措辞, 而是
「**指路之前先确认那条路还在**」: 已经没有的页面名不许再出现。
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from tests.frontend_source import code_of

TODAY_PY = Path(__file__).resolve().parents[1] / "app" / "api" / "today.py"
DIALOG = "components/ScoreLedgerDialog.tsx"
API_TS = "lib/api.ts"
#: R340/R351 拆掉的那一页。快照还在(仍由 `_build_overview` 产出), 页面没了 ——
#: 让用户"去打开一次今日总览"是条走不通的路。
DEAD_PAGE = "今日总览"


def _ledger_try() -> ast.Try:
    """`_build_overview` 里落台账那一段 try。"""
    tree = ast.parse(TODAY_PY.read_text(encoding="utf-8"))
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "_build_overview")
    hits = [n for n in ast.walk(fn)
            if isinstance(n, ast.Try) and "record_day" in ast.dump(n)]
    assert len(hits) == 1, f"落台账那段 try 没定位到(找到 {len(hits)} 段)"
    return hits[0]


def _called(nodes: list[ast.stmt]) -> set[str]:
    """这一段语句里调到的函数名(裸名与属性名都算)。"""
    out: set[str] = set()
    for n in nodes:
        for sub in ast.walk(n):
            if isinstance(sub, ast.Call):
                f = sub.func
                if isinstance(f, ast.Name):
                    out.add(f.id)
                elif isinstance(f, ast.Attribute):
                    out.add(f.attr)
    return out


def _skip_guards(node: ast.AST) -> list[ast.expr | None]:
    """每一次 `_h.skip(...)`, 配上**最近的那个 if** 的判据(不在 if 里配 None)。

    不能直接问外层 if「你身上有没有 skip」—— 嵌在里面那个 if 的 skip 会被算成
    外层自己的, 于是"包着一个正确内层"的外层会被误判成违规。要的是最近那一层。
    """
    out: list[ast.expr | None] = []

    def walk(n: ast.AST, guard: ast.expr | None) -> None:
        if isinstance(n, ast.ExceptHandler):
            return                       # except 里的上报是 R274 本来就要的那种
        if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                and n.func.attr == "skip"):
            out.append(guard)
        if isinstance(n, ast.If):
            for st in n.body:
                walk(st, n.test)
            for st in n.orelse:          # else 归同一个判据: 它引用的是同一批名字
                walk(st, n.test)
            return
        for child in ast.iter_child_nodes(n):
            walk(child, guard)

    walk(node, None)
    return out


# ================================================================
# 后端: 记账的返回值不许丢
# ================================================================

def test_R391_记账的返回值不许丢():
    """`record_day` 自己吞异常, 失败时只返回 `{"ok": False}`。

    不看返回值的话, 写盘挂了和写成功在界面上长得一模一样 —— 又是一次静默跳过,
    只是换了个位置。这一条**不按措辞找, 按数据流找**: 先看返回值绑给了谁,
    再看有没有哪条 if 拿它当判据并上报。
    """
    node = _ledger_try()
    bound = {
        t.id
        for st in ast.walk(node) if isinstance(st, ast.Assign)
        for t in st.targets if isinstance(t, ast.Name)
        if "record_day" in ast.unparse(st.value)
    }
    assert bound, "记账的返回值没接住 —— 写失败了也没人知道"
    checked = [
        sub for sub in ast.walk(node)
        if isinstance(sub, ast.If)
        and bound & {n.id for n in ast.walk(sub.test) if isinstance(n, ast.Name)}
        and "skip" in _called(sub.body)
    ]
    assert checked, f"接住了 {bound} 却没拿它判过 —— 写失败仍然是静默的"


def test_R392_常态不许塞进故障通道():
    """盘中不记是**常态**, 不是故障 —— [R136] 起日线管道会保底记一份。

    把它报进 `_h.skip`, 自检条就会在每个盘中日常驻一行, 而 R274 给它定的性质
    是"一切正常时一个像素都不占"。这条钉的是: 那段 try 里 `_h.skip` 的调用,
    **必须全部长在"打算记却没记成"的路径上**, 不许出现在纯粹"这次不记"的路径上。
    """
    node = _ledger_try()
    bound = {
        t.id
        for st in ast.walk(node) if isinstance(st, ast.Assign)
        for t in st.targets if isinstance(t, ast.Name)
        if "record_day" in ast.unparse(st.value)
    }
    strays = [
        "(没有任何 if 守着)" if guard is None else ast.unparse(guard)
        for guard in _skip_guards(node)
        if guard is None
        or not (bound & {n.id for n in ast.walk(guard) if isinstance(n, ast.Name)})
    ]
    assert not strays, (
        "这些分支把一件本来就对的常态报进了自检条(它只该报真出事的):\n  "
        + "\n  ".join(strays))


def test_R391_自检登记表里有台账这一项():
    """上报要有落点 —— key 没登记的话, 报出来的是个英文 key, 界面上看不懂。"""
    from app.api.today import _Health
    assert "score_ledger" in _Health.SITES


# ================================================================
# 前端: 超时档位, 与「指的路还在不在」
# ================================================================

def _code(rel: str) -> str:
    try:
        return code_of(rel)
    except OSError:
        pytest.skip("拿不到前端源码(只跑后端时正常)")


def test_R392_体检接口要走计算档超时():
    """它每次都补算历史收益(几百只日 K), 挂默认 30 秒闸的话台账越厚越容易超时,
    用户看到的就是「读取台账失败」。[R231] 当年逐个开豁免时漏的正是这一个。"""
    code = _code(API_TS)
    call = next((ln for ln in code.splitlines() if "todayScoreLedger:" in ln), None)
    assert call is not None, "todayScoreLedger 的绑定没了, 守卫的锚要跟着改"
    # 绑定跨行, 取到下一个成员为止
    seg = code.split("todayScoreLedger:", 1)[1].split("todayScoreLedgerDigest", 1)[0]
    assert "COMPUTE_REQUEST_TIMEOUT_MS" in seg, (
        "体检接口还挂在默认 30 秒闸上 —— 它是同步计算型的, 台账一厚就会超时")


def test_R392_界面上不许再指向已经拆掉的那一页():
    """**剥注释之后再扫** —— 解释「以前指的是哪一页」那几段必然要写出旧名字,
    不剥的话断言会被自己的注释喂饱(本仓库第八次)。"""
    offenders = []
    for rel in (DIALOG, "components/monitor/FocusBar.tsx"):
        for i, ln in enumerate(_code(rel).splitlines(), 1):
            if DEAD_PAGE in ln:
                offenders.append(f"{rel}:{i} {ln.strip()[:70]}")
    assert not offenders, (
        f"这些渲染文本还在让用户去开「{DEAD_PAGE}」, 而那一页已经没有了:\n  "
        + "\n  ".join(offenders))


def test_R392_空态不许许诺自检条会报好消息():
    """`TodayHealthBar` 在一切正常时**整条不渲染** —— 它只会说"没记", 说不了
    "记上了"。空态里不许再写"自检会写明这次记没记"这种反过来的话。"""
    code = _code(DIALOG)
    seg = code.split("recorded_days === 0", 1)[1].split("recorded_days > 0", 1)[0]
    assert "自检" not in seg, "空态又在许诺自检条会告诉你记上了 —— 它不会"


def test_R391_全是老口径时不许只说一句台账还是空的():
    """`legacy_days` 原来只渲染在 `recorded_days > 0` 那一支里 —— 而「攒的全是
    换口径之前的」恰恰会让 `recorded_days` 是 0, 于是唯一能解释这件事的那句话
    **正好在最需要它的时候不可达**。"""
    code = _code(DIALOG)
    empty = code.split("recorded_days === 0", 1)
    assert len(empty) == 2, "空态那一支的锚没了"
    seg = empty[1].split("recorded_days > 0", 1)[0]
    assert "legacy_days" in seg, (
        "空态里读不到 legacy_days —— 攒的全是老口径时, 用户只会看到「台账还是空的」")
