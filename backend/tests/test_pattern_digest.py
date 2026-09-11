"""[fork 增强] R175 AI 提炼层。

这一层的价值全在**边界**上, 所以测的也是边界:
  · 喂给 AI 的表里不能有个股/价格 —— 它看不见就编不出来;
  · 样本不足的档必须以 null 进去, 不能把一个不可信的胜率递给它;
  · 同一天不重复生成 —— 否则同一批数据两套说法, 会被读成行情变了;
  · AI 说的话连同**当时那张表**一起存 —— 不然三个月后没法判断它当时的依据。
"""
import pytest

from app.services import pattern_digest as pd


def _res(*, n_all: int, win_all: float, n_recent: int, min_n: int = 15) -> dict:
    """搭一份 evaluate() 形状的结果, 只填 build_table 用得上的字段。"""
    return {
        "recorded_days": 60, "recent_days": 20, "min_label_n": min_n,
        "last_day": "2025-06-30",
        "labels": [{
            "key": "verdict", "label": "通道档位",
            "items": [{
                "value": "强势深调", "count": n_all, "recent_count": n_recent,
                "stats": {"t5": {"n": n_all, "win_rate": win_all, "avg": 1.2}},
                "recent_stats": {"t5": {"n": n_recent, "win_rate": 30.0, "avg": -1.0}},
                "shift": {"dir": "down", "delta": -25.0, "text": "最近明显转差"},
            }],
        }],
    }


def test_表里不含个股与价格():
    table = pd.build_table(_res(n_all=100, win_all=55.0, n_recent=30))
    blob = repr(table)
    for banned in ("symbol", "close", "000001", "name"):
        assert banned not in blob, f"表里不该出现 {banned} —— AI 看不见才编不出来"


def test_样本不足的档胜率以None进表():
    # 全期只有 5 个样本, 低于门槛 15
    table = pd.build_table(_res(n_all=5, win_all=60.0, n_recent=2))
    item = table[0]["各档"][0]
    assert item["全期胜率"] is None, "样本不足必须是 null, 不能把不可信的数递给 AI"
    assert item["最近胜率"] is None
    assert item["全期样本"] == 5, "样本数本身要如实给出, 好让 AI 知道为什么是 null"


def test_样本够时胜率照实进表():
    table = pd.build_table(_res(n_all=100, win_all=55.0, n_recent=30))
    item = table[0]["各档"][0]
    assert item["全期胜率"] == 55.0
    assert item["背离"] == "最近明显转差"


def test_提示词写死了两条硬约束():
    sp = pd._system_prompt(15, 20)
    assert "只能引用表里出现过的数字" in sp
    assert "样本不足" in sp and "不许给倾向性判断" in sp


def test_空表不生成(monkeypatch):
    async def _boom(*a, **k):
        raise AssertionError("表是空的就不该调 AI")
    monkeypatch.setattr("app.services.ai_provider.generate_ai_text", _boom)
    monkeypatch.setattr("app.services.ai_provider.ai_configured", lambda: True)
    import asyncio
    with pytest.raises(RuntimeError, match="标签数据"):
        asyncio.run(pd.generate({"labels": [], "min_label_n": 15, "recent_days": 20}))


def test_同一天不重复生成(tmp_path, monkeypatch):
    monkeypatch.setattr(pd, "_path", lambda: tmp_path / "digest.json")
    res = _res(n_all=100, win_all=55.0, n_recent=30)
    pd.record("2025-06-30", "第一次说的话", pd.build_table(res))

    calls = {"n": 0}

    async def _count(*a, **k):
        calls["n"] += 1
        return "第二次说的话"
    monkeypatch.setattr("app.services.ai_provider.generate_ai_text", _count)
    monkeypatch.setattr("app.services.ai_provider.ai_configured", lambda: True)

    import asyncio
    got = asyncio.run(pd.refresh_if_stale(res))
    assert calls["n"] == 0, "今天已经有了就不该再问一次 AI"
    assert got["text"] == "第一次说的话", "要拿存档, 不能换一套说法"


def test_换了一天才重新生成(tmp_path, monkeypatch):
    monkeypatch.setattr(pd, "_path", lambda: tmp_path / "digest.json")
    res = _res(n_all=100, win_all=55.0, n_recent=30)
    pd.record("2025-06-29", "昨天说的话", pd.build_table(res))

    async def _new(*a, **k):
        return "今天说的话"
    monkeypatch.setattr("app.services.ai_provider.generate_ai_text", _new)
    monkeypatch.setattr("app.services.ai_provider.ai_configured", lambda: True)

    import asyncio
    got = asyncio.run(pd.refresh_if_stale(res))     # res 的 last_day 是 06-30
    assert got["text"] == "今天说的话"
    assert len(pd.history()) == 2, "昨天那条要留着, 好回看它准不准"


def test_存的时候连当时那张表一起存(tmp_path, monkeypatch):
    monkeypatch.setattr(pd, "_path", lambda: tmp_path / "digest.json")
    res = _res(n_all=100, win_all=55.0, n_recent=30)
    e = pd.record("2025-06-30", "一句话", pd.build_table(res))
    assert e["table"], "只存话不存表的话, 三个月后没法判断它当时的依据"
    assert e["table"][0]["各档"][0]["全期胜率"] == 55.0


def test_AI失败时返回None而不是抛出(tmp_path, monkeypatch):
    """提炼是锦上添花, 不该把台账统计或页面拖垮。"""
    monkeypatch.setattr(pd, "_path", lambda: tmp_path / "digest.json")

    async def _fail(*a, **k):
        raise RuntimeError("provider down")
    monkeypatch.setattr("app.services.ai_provider.generate_ai_text", _fail)
    monkeypatch.setattr("app.services.ai_provider.ai_configured", lambda: True)

    import asyncio
    assert asyncio.run(pd.refresh_if_stale(_res(n_all=100, win_all=55.0, n_recent=30))) is None
