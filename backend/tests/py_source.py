"""[R328] 读 Python 源码的共用工具 —— 给那几组「扫自己代码」的守卫用。

## 为什么值得单独拿出来

`tests/frontend_source.py` 的开头写着: 这个仓库发生过五次「断言被自己的注释
喂饱」。那份工具收口了**前端**那一侧。

Python 这一侧同样栽 —— 而且就在同一个会话里连栽两次:

  R327  守卫断言 `flip_portfolio` 的函数体里不许出现 `BULLISH`,
        而模块 docstring 里正好写着「不在这里重写一遍 `state in BULLISH`」
  R328  守卫断言 `_names` 里不许出现 `list_symbols`,
        而它的 docstring 里正好写着「第一版写的是 `watchlist.list_symbols()`」

两次都是同一个形状: **断言查的那个标识符, 正好也写在解释它为什么不该出现的
那段文字里。** 越是把理由写清楚, 越容易踩。

所以: 一处实现, 一处修。
"""
from __future__ import annotations

import ast
import inspect
import textwrap
from types import FunctionType, ModuleType


def _strip_docstring(body: list[ast.stmt]) -> list[ast.stmt]:
    if (body and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)):
        return body[1:]
    return body


def body_of(fn: FunctionType) -> str:
    """一个函数的**代码**, 不含它的 docstring。

    注释本来就不进 AST, docstring 是唯一会混进来的说明文字 —— 掐掉它之后
    断言看到的就只剩真正的代码。
    """
    tree = ast.parse(textwrap.dedent(inspect.getsource(fn)))
    node = next(n for n in ast.walk(tree)
                if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef))
    return "\n".join(ast.unparse(n) for n in _strip_docstring(node.body))


def code_of(mod: ModuleType) -> str:
    """整个模块的**代码**, 剥掉模块 docstring 与每个函数/类自己的 docstring。"""
    tree = ast.parse(inspect.getsource(mod))
    tree.body = _strip_docstring(tree.body)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            node.body = _strip_docstring(node.body)
    return ast.unparse(tree)
