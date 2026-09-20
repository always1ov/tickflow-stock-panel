"""策略 AST 安全名单的两个**位置性**漏洞 (安全审查 run-1)。

名单本身没错, 错在只在很窄的语法位置上看:

1. 危险内建只在「直接调用」位置被拦 —— `_ev = eval` 换个名字就绕过去了。
2. `from X import a` 只校验 X, 从不看 a —— 而白名单里 `app.backtest.matrix`
   是个真模块, 它自己 `import os/shutil/json`, 于是白名单模块成了它本要排除的
   那些模块的**再导出口**。

仓库原有的两条测试只钉了最朴素的 `import os` 和 `from os import path`,
正好落在这两个漏洞之外 —— 所以这里补的是「绕法」, 不是「名单」。
"""
from __future__ import annotations

import pytest

from app.strategy.ai_generator import AIStrategyGenerator as G

LEGIT = """
META = {"id": "uf_x", "name": "x", "scoring": {}}
import polars as pl
import numpy as np
from app.indicators.keltner import KELTNER_PRESETS
from datetime import date


def filter(df, params):
    return df
"""


def test_legitimate_strategy_code_still_passes():
    """先钉住不许误伤 —— 收紧检查最容易把正常策略一起拒掉。"""
    G._validate_safety(LEGIT)


@pytest.mark.parametrize("payload", [
    "_ev = eval\n_ev('1')\n",
    "alias = exec\n",
    "_g = getattr\n_g((), '__class__')\n",
    "f = open\n",
    "handlers = [eval, exec]\n",
    "x = compile\n",
    "fn = __import__\n",
])
def test_aliasing_a_forbidden_builtin_is_rejected(payload):
    """危险内建连「被取到」都不允许, 不只是「被调用」。"""
    with pytest.raises(ValueError, match="禁止引用内建"):
        G._validate_safety(payload)


@pytest.mark.parametrize("payload", [
    "from app.backtest.matrix import os\n",
    "from app.backtest.matrix import shutil\n",
    "from app.backtest.matrix import json\n",
    "from app.backtest.matrix import hashlib, uuid\n",
    "from app.strategy.market_data import threading\n",
    "from app.indicators.keltner import time\n",
])
def test_reexported_modules_cannot_be_pulled_through_an_allowlisted_module(payload):
    """白名单模块不许当作它本要排除的模块的再导出口。"""
    with pytest.raises(ValueError, match="本身是模块"):
        G._validate_safety(payload)


def test_star_import_is_rejected_with_its_own_reason():
    with pytest.raises(ValueError, match="星号导入"):
        G._validate_safety("from polars import *\n")


def test_ordinary_symbols_from_allowlisted_modules_still_import():
    """反向那一半: 常量/函数/类不是模块, 必须照常放行。"""
    G._validate_safety("from app.indicators.keltner import KELTNER_PRESETS\n")
    G._validate_safety("from datetime import date, timedelta\n")
    G._validate_safety("from __future__ import annotations\n")


def test_the_naive_forms_the_repo_already_covered_are_still_rejected():
    """既有的两条不许因为这次收紧而失效。"""
    with pytest.raises(ValueError):
        G._validate_safety("import os\n")
    with pytest.raises(ValueError):
        G._validate_safety("from os import path\n")


def test_assigning_to_a_forbidden_name_is_not_a_reference():
    """Store 位置不算取用 —— 这是新检查的边界, 钉住免得被放宽成「见名就拒」。"""
    G._validate_safety("type = 1\n")
