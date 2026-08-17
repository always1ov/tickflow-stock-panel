"""[fork 增强] R19 全量立即刷新: 轮转覆盖判定。"""
import sys
import types

# 测试环境未装 TickFlow SDK, 打桩绕过导入链(不影响被测逻辑)
if "tickflow" not in sys.modules:
    _stub = types.ModuleType("tickflow")
    _stub.AsyncTickFlow = object
    _stub.TickFlow = object
    sys.modules["tickflow"] = _stub

from app.services.quote_service import QuoteService  # noqa: E402


def _service(offsets: list[int], start: int = 0) -> QuoteService:
    """构造只带轮转状态的替身: 每次 _fetch_quotes 把偏移推到脚本的下一个值。"""
    qs = object.__new__(QuoteService)
    qs._rt_rotate_offset = start
    seq = iter(offsets)

    def fetch(*a, **k):
        qs._rt_rotate_offset = next(seq)
        return True

    qs._fetch_quotes = fetch
    qs.status = lambda: {}
    return qs


def test_single_round_when_watchlist_fits_capacity():
    """自选 ≤ 每轮容量(偏移恒为 0)→ 一轮即全量。"""
    st = _service([0], start=0).refresh_full()
    assert st["full_coverage"] is True
    assert st["rounds"] == 1


def test_rotation_wrap_marks_full_coverage():
    """轮转推进 50→100→3(回绕过起点)→ 判定全覆盖, 停止。"""
    st = _service([100, 3], start=50).refresh_full()
    assert st["full_coverage"] is True
    assert st["rounds"] == 2


def test_bounded_rounds_reports_partial():
    """max_rounds 内没转完 → 如实报 full_coverage=False, 不无限阻塞。"""
    st = _service([10, 20, 30, 40, 50], start=1).refresh_full(max_rounds=3)
    assert st["full_coverage"] is False
    assert st["rounds"] == 3
