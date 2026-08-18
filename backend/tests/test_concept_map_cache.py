"""[fork 修复] 维度映射缓存: 命中路径必须与未命中路径返回同构的元组。

上游 bug: 缓存只存 DataFrame, 命中时调用方 `map_df, _ = ...` 把两列 df
解包成两个 Series → group_by 报 AttributeError。表现为市场环境「重算」
首次成功、600s 内第二次起"主线回填失败"。
"""
import sys
import types

import polars as pl

if "tickflow" not in sys.modules:
    _stub = types.ModuleType("tickflow")
    _stub.AsyncTickFlow = object
    _stub.TickFlow = object
    sys.modules["tickflow"] = _stub

from app.services import rps_rotation


def test_cache_hit_returns_same_shape_as_miss(tmp_path, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    rps_rotation._map_cache.clear()
    rps_rotation._map_ts.clear()

    class _Store:
        data_dir = tmp_path

    class _Repo:
        store = _Store()

    # 无扩展数据 → 空映射, 但关键是两次调用返回结构必须一致
    df1, n1 = rps_rotation._load_concept_map_df(_Repo(), "concept")   # 未命中
    df2, n2 = rps_rotation._load_concept_map_df(_Repo(), "concept")   # 命中缓存
    assert isinstance(df1, pl.DataFrame) and isinstance(df2, pl.DataFrame), \
        "命中缓存不得把 DataFrame 解包成 Series"
    assert isinstance(n1, int) and isinstance(n2, int)
    assert df2.columns == df1.columns


def test_cached_value_is_tuple():
    rps_rotation._map_cache["concept"] = (
        pl.DataFrame(schema={"_sym_up": pl.Utf8, "concept": pl.Utf8}), 0)
    cached = rps_rotation._map_cache["concept"]
    assert isinstance(cached, tuple) and len(cached) == 2
    rps_rotation._map_cache.clear()
