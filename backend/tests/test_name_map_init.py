"""[fork R497] 维表还没刷新过时查名字不能炸。

新装还没同步维表(或维表刷新抛错)时, `_name_map_cache` 从没被赋值,
`get_name_map` 第一次调用就 AttributeError —— 今日总览(转折页上的那份)整页 500。
"""
from app.tickflow.repository import DataStore, KlineRepository


def test_R497_维表没刷新过_查名字返回空而不是抛错(tmp_path):
    repo = KlineRepository(DataStore(data_dir=tmp_path))
    assert repo.get_name_map(["600000.SH"]) == {}
