"""[R490] 全体测试共用的夹具。

单票日 K 历史缓存(`services/ohlcv_history`)按仓库对象 + 代码缓存 10 分钟。测试里每个用例
都给 `app.state.repo` 换一个假仓库, 假仓库对象被回收后 id 可能被下一个复用 —— 不清的话,
后一个用例会读到前一个用例的假数据, 测试结果取决于跑的先后。每个用例开跑前清一次。
"""
import os

import pytest

# [R610] 测试不读本地 .env：本机可能在里面写了 DATA_DIR = 真实数据目录，
# 一旦被测例当成真实目录读写，结果会随用户偏好漂移，甚至把用户文件挪走。
# 强制 DATA_DIR 的用例自己 monkeypatch，别在这里兜底。
os.environ.setdefault("TICKFLOW_ENV_FILE", os.devnull)


@pytest.fixture(autouse=True)
def _clear_ohlcv_history_cache():
    from app.services import ohlcv_history
    ohlcv_history.clear()
    yield
