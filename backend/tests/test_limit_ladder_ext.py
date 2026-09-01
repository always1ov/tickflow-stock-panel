"""[fork R145] 连板梯队的扩展列(如「所属同花顺行业」)。

起因: 用户在梯队页把分组字段配成「所属同花顺行业」之后, 页面直接 500 打不开。

查下来梯队这条路自己写了一份 ext JOIN, 漏掉了全站通用路径
(`_load_ext_value_maps`)里**至关重要的两步**:
  1. 时序扩展表只取**最新分区**;
  2. JOIN 前按 symbol 去重。
而「所属同花顺行业」正是一张按日分区的时序表 —— 直接查 `ext_*` 视图会拿到
一只票 × N 个历史分区那么多行, 左连接之后梯队行数被成倍放大。

修法是**删掉那份重复实现, 改用通用路径**。这组测试守两件事:
  · 贴扩展列不许改变行数(去重这一步不能再丢);
  · 梯队里不许再出现第二份手写的 ext JOIN。
"""
from __future__ import annotations

import inspect

from app.api import screener as sc


def test_attaching_ext_columns_never_changes_row_count():
    """一只票在扩展表里有几条历史记录, 梯队里都只能是一行。

    这正是 500 的根源: 原实现直接左连接未去重的时序表, 行数被成倍放大。
    """
    rows = [{"symbol": "600000.SH", "boards": 2}, {"symbol": "000001.SZ", "boards": 1}]
    maps = {"ext_hy_ths__所属同花顺行业": {"600000.SH": "银行", "000001.SZ": "银行"}}
    out = sc._rows_with_ext(rows, maps)
    assert len(out) == len(rows)
    assert [r["ext_hy_ths__所属同花顺行业"] for r in out] == ["银行", "银行"]


def test_symbols_missing_from_the_ext_table_get_null_not_dropped():
    """扩展表里没有的票要留着并给 None —— 等价于左连接, 不能悄悄少几只。"""
    rows = [{"symbol": "600000.SH"}, {"symbol": "999999.XX"}]
    out = sc._rows_with_ext(rows, {"c__f": {"600000.SH": "银行"}})
    assert len(out) == 2
    assert out[1]["c__f"] is None


def test_no_ext_columns_is_a_passthrough():
    rows = [{"symbol": "600000.SH"}]
    assert sc._rows_with_ext(rows, {}) is rows


def test_ladder_uses_the_shared_ext_helper_not_its_own_join():
    """守住"只有一份实现"。第二份手写 JOIN 就是漏掉去重的地方。"""
    src = inspect.getsource(sc.limit_ladder)
    assert "_load_ext_value_maps" in src, "梯队必须走通用扩展列路径"
    # 只盯 ext 专有的痕迹 —— 函数里还有个正当的 prev_consec 左连接, 不能一刀切
    assert "view_name" not in src, "梯队里不许再出现手写的 ext_* 视图查询"
    assert "ext_col_name" not in src, "梯队里不许再出现手写的 ext JOIN"
    assert "_parquet_glob" not in src, "ext parquet 的读取归通用路径管"


def test_shared_helper_dedups_by_symbol():
    """通用路径本身必须去重 —— 梯队现在完全依赖它。"""
    src = inspect.getsource(sc._load_ext_value_maps)
    assert 'unique(subset=["symbol"]' in src
