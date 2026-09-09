"""[fork 增强] R214 分区 parquet 的并发读写 —— 整套测试约 1/3 概率随机挂的那个。

症状(跑全量测试时随机出现, 与被测逻辑无关):

    ComputeError: parquet: File out of specification: Invalid thrift: end of file
    ComputeError: parquet: File out of specification: The page header reported the wrong page size
    pyo3_runtime.PanicException: range end index 260625 out of range for slice of length 833

三条错都指向同一件事: **有人在别人读这个文件的时候把它换掉了。**
挖下去是两个各自独立的缺陷:

  ① 写 vs 写 —— `_atomic_write_parquet` 的临时文件名是**固定**的
     (`part.parquet.tmp`)。两个并发写入者会写进同一个临时文件: 大的写到一半,
     小的从头覆盖并抢先 replace, 发布出去就是半截文件。而且 `_write_lock`
     是**实例级**的, `save_index_instruments` / `save_etf_instruments` 这两个
     调用点**根本没持锁**, 靠锁堵不住。
     → 改成每次写入一个带 uuid 的唯一临时名(`EnrichedPublication.write_parquet`
       早就是这么做的), finally 清理。

  ② 读 vs 写 —— `replace_with_retry` 的注释说「Linux 的 inode 交换语义则无此
     限制」。那句话对 `os.replace` 成立, 对 `pl.read_parquet(路径)` **不成立**:
     polars 的流式读会先取 footer、再按字节区间回头取 row group, 中间**按路径
     重新取数**。替换正好插在中间, 就是新字节配旧偏移。
     → 读之前先 `open`, 把**文件对象**交给 polars。句柄钉住 inode,
       替换换的是目录项, 换不走正在读的那份。

两条都不是"理论上可能", 是**当场跑出来的**。这份测试就是那个复现脚本。
"""
import os
import threading
from pathlib import Path

import polars as pl
import pytest

from app.tickflow.repository import KlineRepository, replace_with_retry

# 「反例」用例(证明旧写法真的会炸)默认不跑, 要跑就:
#
#     TICKFLOW_RACE_REPRO=1 pytest tests/test_partition_concurrent_replace.py
#
# 两个理由:
#   · 它们断言的是「一定要发生竞态」—— **在失败方向上不确定**。抢不到那个
#     窗口就红一次, 那我就是在拿一种随机失败换掉另一种随机失败。
#   · 它们会真的把 Rust 侧打 panic, 满屏 backtrace, 正常跑测试时是纯噪音。
#
# 留在仓库里是因为它们证明了上面那两条结论不是推理出来的。最近一次实测
# (2026-09-09, polars 1.44.1, Linux):
#   固定临时名 + 按路径读 —— 4 轮共 24 次读写异常(踩踏 + File out of specification)
#   唯一临时名 + 钉住句柄 —— 4 轮共 0 次
_REPRO = pytest.mark.skipif(
    os.getenv("TICKFLOW_RACE_REPRO") != "1",
    reason="竞态反例默认不跑: 断言「必须抢到竞态」在失败方向上不确定, 且会打出 Rust panic 噪音",
)


def _big():
    return pl.DataFrame({"symbol": [f"{i:06d}" for i in range(120_000)],
                         "v": list(range(120_000))})


def _small():
    return pl.DataFrame({"symbol": ["000001"], "v": [1]})


def _hammer(tmp_path: Path, write, read, *, big_rounds=8, small_rounds=300):
    """一个大写入者 + 一个小写入者 + 一个读者, 同时打同一个文件。

    大小悬殊是关键: 只有体量差得多, "写到一半被另一份覆盖"才会稳定暴露。
    """
    out = tmp_path / "part.parquet"
    write(_small(), out)
    errors: list[tuple] = []
    done = threading.Event()

    def writer(df, n):
        for _ in range(n):
            if done.is_set():
                return
            try:
                write(df, out)
            except BaseException as e:  # noqa: BLE001  panic 是 BaseException
                errors.append(("write", type(e).__name__, str(e)[:80]))

    def reader():
        while not done.is_set():
            try:
                read(out)
            except BaseException as e:  # noqa: BLE001
                errors.append(("read", type(e).__name__, str(e)[:80]))
                done.set()

    threads = [threading.Thread(target=writer, args=(_big(), big_rounds)),
               threading.Thread(target=writer, args=(_small(), small_rounds)),
               threading.Thread(target=reader, daemon=True)]
    for t in threads:
        t.start()
    for t in threads[:2]:
        t.join()
    done.set()
    threads[2].join(timeout=5)
    leftover = sorted(p.name for p in tmp_path.iterdir() if p.name != "part.parquet")
    return errors, leftover


# ---------- ① 写 vs 写: 固定临时名会踩踏 ----------

def _write_fixed_tmp(df: pl.DataFrame, out: Path) -> None:
    """R214 之前的实现 —— 留在测试里当反例, 证明这个测试真的抓得住。"""
    tmp = out.with_name(out.name + ".tmp")
    df.write_parquet(tmp)
    replace_with_retry(tmp, out)


@_REPRO
def test_固定临时名确实会踩踏_反例(tmp_path):
    """先证明这份压力测试抓得住 bug —— 否则修好了也不知道是不是运气。"""
    errors, _ = _hammer(tmp_path, _write_fixed_tmp,
                        lambda p: pl.read_parquet(p))
    assert errors, "旧实现居然没炸 —— 那这份测试就是摆设, 得加大并发再看"


def test_唯一临时名之后写入者互不踩踏(tmp_path):
    errors, leftover = _hammer(tmp_path, KlineRepository._atomic_write_parquet,
                               KlineRepository._read_parquet_pinned)
    assert not errors, f"并发读写仍然出错: {errors[:3]}"
    assert not leftover, f"残留临时文件没清干净: {leftover}"


# ---------- ② 读 vs 写: 按路径读会被替换掀翻 ----------

@_REPRO
def test_按路径读会被并发替换掀翻_反例(tmp_path):
    """polars 按路径读会中途重新取数 —— 这一条同时也是"注释写错了"的证据。"""
    errors, _ = _hammer(tmp_path, KlineRepository._atomic_write_parquet,
                        lambda p: pl.read_parquet(p))
    assert any(k == "read" for k, *_ in errors), \
        f"按路径读居然一次都没炸, 并发窗口可能太窄: {errors[:3]}"


def test_钉住句柄读不会被并发替换掀翻(tmp_path):
    errors, _ = _hammer(tmp_path, KlineRepository._atomic_write_parquet,
                        KlineRepository._read_parquet_pinned)
    assert not [e for e in errors if e[0] == "read"], \
        f"钉住句柄之后仍然读炸: {errors[:3]}"


# ---------- 读法本身的正确性 ----------

def test_钉住句柄读的返回值与直接读一致(tmp_path):
    out = tmp_path / "part.parquet"
    df = pl.DataFrame({"symbol": ["000001", "600000"], "v": [1, 2]})
    KlineRepository._atomic_write_parquet(df, out)
    assert KlineRepository._read_parquet_pinned(out).equals(pl.read_parquet(out))


def test_文件不存在时返回空表而不是抛(tmp_path):
    got = KlineRepository._read_parquet_pinned(tmp_path / "nope.parquet")
    assert got.is_empty()


def test_行数统计走的也是钉住句柄的读法(tmp_path):
    out = tmp_path / "part.parquet"
    KlineRepository._atomic_write_parquet(
        pl.DataFrame({"symbol": list("abcde"), "v": range(5)}), out)
    assert KlineRepository._partition_rows(out) == 5
    assert KlineRepository._partition_rows(tmp_path / "nope.parquet") == 0


@pytest.mark.parametrize("n", [1, 3])
def test_写失败不留临时文件(tmp_path, n):
    """写到一半抛异常时, finally 得把临时文件收掉, 不能一地垃圾。"""
    out = tmp_path / "part.parquet"

    class Boom(pl.DataFrame):
        def write_parquet(self, *a, **k):  # type: ignore[override]
            raise RuntimeError("boom")

    for _ in range(n):
        with pytest.raises(RuntimeError):
            KlineRepository._atomic_write_parquet(Boom({"a": [1]}), out)
    assert not list(tmp_path.iterdir()), sorted(p.name for p in tmp_path.iterdir())
