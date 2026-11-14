"""[R642] R565 指标对拍进 pytest —— 指标一漂移就自动红, 不再靠人记得手动跑脚本。

`scripts/verify_r565_parity.py` 从 git 里取出 R565 时点的 `quant_macd.py` / `trend_quant.py`,
与当前实现喂同一批 K 线(真实库 + 5 组合成序列, 约 24 万个数值点)逐点比较。这里把它包成
一条普通用例(实测约 2 秒): 仓库没有对照提交(浅克隆)或本机没有真实库数据时跳过, 不误报。
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent
SCRIPT = BACKEND / 'scripts' / 'verify_r565_parity.py'
# R565 台账那一轮的提交; 指标模块自那以后应当逐点不变
REV = '0b174ac9'


def _has_rev() -> bool:
    return subprocess.run(
        ['git', 'cat-file', '-e', f'{REV}^{{commit}}'], cwd=BACKEND.parent,
        capture_output=True,
    ).returncode == 0


def test_R642_副图指标与R565逐点一致():
    if not _has_rev():
        pytest.skip(f'仓库里没有对照提交 {REV}(浅克隆?)')

    # tests/conftest.py 给整个测试进程设了 TICKFLOW_ENV_FILE=/dev/null(测试不读本地 .env)。
    # 对拍子进程要读真实数据根, 这里只对这一个子进程把该变量摘掉; 它只读 parquet, 不写。
    env = {k: v for k, v in os.environ.items() if k != 'TICKFLOW_ENV_FILE'}
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), '--rev', REV],
        cwd=BACKEND, capture_output=True, text=True, env=env,
    )
    # 脚本自己按 settings / .env 找数据根; 本机没有真实库时它明说一句再以 1 退出 —— 这里转成 skip
    if '没有真实库数据' in proc.stdout:
        pytest.skip(proc.stdout.strip().splitlines()[0])
    assert proc.returncode == 0, f'对拍不一致:\n{proc.stdout}\n{proc.stderr}'
