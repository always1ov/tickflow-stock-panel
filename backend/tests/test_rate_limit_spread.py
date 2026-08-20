"""[fork 增强] R35 多 key 轮询的错峰与抖动。

核心不变量: 抖动只会让间隔变大, 不会变小 —— 同一个 key 两次调用的实际间隔
始终 >= 60/rpm, 所以摊开不等于偷额度。
"""
import random

import pytest

from app.tickflow.rate_limits import select_keys, shuffled_key_order, spread_delays


# ---------- 摊开 ----------

def test_first_batch_never_waits():
    """一轮总要有人先开口, 否则每轮白白多等一个间隔。"""
    d = spread_delays(14, 14, 10, rng=random.Random(1))
    assert d[0] == 0.0


def test_round_spans_the_whole_window_not_a_burst():
    """14 个 key、rpm=10(窗口 6 秒): 一轮应摊到 6 秒左右, 而不是瞬间打完。"""
    d = spread_delays(14, 14, 10, rng=random.Random(1))
    assert 6.0 <= sum(d) <= 6.0 * 1.35, f"实际 {sum(d):.2f}s"


def test_same_key_interval_never_shrinks_below_limit():
    """关键不变量: 同一 key 的两次调用间隔 >= 窗口/1, 抖动只加不减。"""
    n_keys, rpm = 14, 10
    window = 60 / rpm
    d = spread_delays(40, n_keys, rpm, rng=random.Random(2))
    # 第 i 批与第 i+n_keys 批用同一个 key(按 i//n_keys 的限速语义), 间隔是中间这段之和
    for i in range(len(d) - n_keys):
        gap = sum(d[i + 1: i + 1 + n_keys])
        assert gap >= window, f"批 {i} → {i + n_keys} 间隔 {gap:.2f}s < {window}s"


def test_delays_are_jittered_not_uniform():
    """固定间隔会和别的客户端形成同步节拍, 必须有抖动。"""
    d = spread_delays(20, 10, 10, rng=random.Random(3))[1:]
    assert len(set(d)) > 1, "所有间隔完全相同 = 没有抖动"


def test_jitter_stays_within_declared_band():
    n_keys, rpm, jitter = 8, 10, 0.35
    base = (60 / rpm) / n_keys
    d = spread_delays(50, n_keys, rpm, jitter=jitter, rng=random.Random(4))[1:]
    assert all(base <= x <= base * (1 + jitter) + 1e-6 for x in d)


def test_single_key_degrades_to_full_window():
    """单 key 时没有可摊开的对象, 间隔就是完整窗口。"""
    d = spread_delays(3, 1, 10, rng=random.Random(5))[1:]
    assert all(x >= 6.0 for x in d)


def test_edge_cases():
    assert spread_delays(0, 5, 10) == []
    assert spread_delays(3, 5, None) == [0.0, 0.0, 0.0], "无限速信息时不插入等待"
    assert spread_delays(3, 0, 10, rng=random.Random(6))[1] > 0, "key 数为 0 按 1 处理"


# ---------- key 顺序 ----------

def test_key_order_covers_every_key_each_cycle():
    """每一轮内每个 key 恰好用一次 —— 打散不等于把额度堆到某个 key 上。"""
    order = shuffled_key_order(5, 10, rng=random.Random(7))
    assert sorted(order[:5]) == [0, 1, 2, 3, 4]
    assert sorted(order[5:10]) == [0, 1, 2, 3, 4]


def test_key_order_varies_between_rounds():
    """固定 i%n 会让同一组标的永远由同一个 key 拉, 某 key 出问题时永远伤同几只。"""
    a = shuffled_key_order(8, 8, rng=random.Random(11))
    b = shuffled_key_order(8, 8, rng=random.Random(12))
    assert a != b


def test_key_order_indices_always_in_range():
    order = shuffled_key_order(3, 11, rng=random.Random(13))
    assert len(order) == 11 and all(0 <= i < 3 for i in order)


def test_key_order_edge_cases():
    assert shuffled_key_order(5, 0) == []
    assert shuffled_key_order(0, 3) == [0, 0, 0], "key 数为 0 按 1 处理"


@pytest.mark.parametrize("n_keys,n_batches", [(1, 1), (1, 5), (14, 30), (30, 7)])
def test_two_helpers_agree_on_length(n_keys, n_batches):
    assert len(spread_delays(n_batches, n_keys, 10)) == n_batches
    assert len(shuffled_key_order(n_keys, n_batches)) == n_batches


# ---------- [R35] 每轮只启用一部分 key ----------

def test_select_keys_picks_requested_count():
    got = select_keys(14, 10, rng=random.Random(21))
    assert len(got) == 10 and len(set(got)) == 10, "无放回抽样, 本轮内不重复用同一个 key"
    assert all(0 <= i < 14 for i in got)


def test_select_keys_varies_between_rounds():
    a = select_keys(14, 10, rng=random.Random(31))
    b = select_keys(14, 10, rng=random.Random(32))
    assert a != b, "每轮都该重新抽, 否则那 4 个永远闲着"


def test_select_keys_returns_all_when_disabled_or_oversized():
    assert select_keys(14, 0, rng=random.Random(41)) == list(range(14)), "0 = 全部"
    assert select_keys(14, None) == list(range(14))
    assert select_keys(14, 99) == list(range(14)), "要的比有的多就是全部"
    assert select_keys(14, -3) == list(range(14))


def test_select_keys_edge_cases():
    assert select_keys(0, 10) == []
    assert select_keys(1, 10) == [0]
    assert select_keys(5, "乱填") == list(range(5)), "非法值回落为全部"


def test_subset_leaves_quota_headroom():
    """本轮只用 10 个 key 时, 摊开的间隔按 10 算 —— 每个 key 的实际间隔更宽裕。"""
    full = spread_delays(14, 14, 10, rng=random.Random(51))
    subset = spread_delays(10, 10, 10, rng=random.Random(51))
    base_full = (60 / 10) / 14
    base_subset = (60 / 10) / 10
    assert base_subset > base_full
    assert min(subset[1:]) >= base_subset > max(full[1:]) * 0.9


@pytest.mark.parametrize("per_round", [1, 5, 10, 14])
def test_select_and_order_compose(per_round):
    """抽子集后再排批次: 下标必须落在子集长度内, 否则会索引越界。"""
    active = select_keys(14, per_round, rng=random.Random(61))
    order = shuffled_key_order(len(active), 25, rng=random.Random(62))
    assert all(0 <= i < len(active) for i in order)
