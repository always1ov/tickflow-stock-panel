"""[R325] 启动装配的接线守卫 —— 每一步的调用与定义, 参数个数必须对得上。

R318 把 336 行的 `_application_lifespan` 拆成 24 个具名步骤, 其中
`_init_strategy_engine` 调用处写了三个参数、定义只收两个 —— **应用一启动就
TypeError, 整个后端起不来**(用户: 「报错打不开了」)。而 3900 条测试没有一条
真的跑 lifespan(跑一遍要 DataStore、探测数据源、起一堆后台线程), 所以全绿。

这里不起应用, 只做一件便宜的事: 把 `_application_lifespan` / `_shutdown_services`
/ `lifespan` 三个装配函数的源码解析成 AST, 找出其中对本模块 `_xxx` 步骤函数的
每一次调用, 用 `inspect.signature().bind()` 核对实参个数与形参匹配。参数个数
错了在这里红, 不必等到部署。
"""
from __future__ import annotations

import ast
import inspect

import app.main as main_module

ASSEMBLY = ("_application_lifespan", "_shutdown_services", "lifespan")


def _step_calls(fn_name: str) -> list[ast.Call]:
    src = inspect.getsource(getattr(main_module, fn_name))
    tree = ast.parse(src)
    out: list[ast.Call] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            target = getattr(main_module, node.func.id, None)
            if inspect.isfunction(target) and target.__module__ == main_module.__name__:
                out.append(node)
    return out


def test_R325_装配函数里每一步的实参个数与定义匹配():
    checked = 0
    problems: list[str] = []
    for fn_name in ASSEMBLY:
        for call in _step_calls(fn_name):
            target = getattr(main_module, call.func.id)
            sig = inspect.signature(target)
            args = [object()] * (len(call.args))
            kwargs = {kw.arg: object() for kw in call.keywords if kw.arg}
            try:
                sig.bind(*args, **kwargs)
            except TypeError as e:
                problems.append(f"{fn_name}: {call.func.id}{sig} 被调成 {len(args)} 个位置参数 → {e}")
            checked += 1
    assert not problems, "\n".join(problems)
    assert checked >= 20, f"只核对了 {checked} 处 —— 装配步骤应该有二十多步, 是不是解析漏了"


def test_R325_策略引擎那一步收的是_repo_不再从_app_state_绕():
    src = inspect.getsource(main_module._init_strategy_engine)
    assert "repo: KlineRepository" in src.splitlines()[0]
    assert "app.state.repo" not in src, "同一函数里别人都直接收 repo, 这里不该绕道 app.state"
