"""[fork R99/R119] 全球指数独立模块: 多源解析 / 候选轮试 / TTL 合并 / 失败回旧值。"""
from __future__ import annotations

import pytest

from app.services import global_indices as gi


@pytest.fixture(autouse=True)
def _reset_cache():
    gi._set_cache({}, 0.0, ())
    yield
    gi._set_cache({}, 0.0, ())


_KOSPI = gi._BY_KEY["kospi"]
_SINA = gi._Src("sina", "int_kospi")
_TENCENT = gi._Src("tencent", "s_usIXIC")


# ------------------------------------------------------------- 解析


def test_parse_sina_int_format():
    row = gi._parse(_SINA, "韩国KOSPI,3200.12,-12.34,-0.38")
    assert row["last"] == 3200.12
    assert row["change"] == -12.34
    assert row["change_pct"] == pytest.approx(-0.0038)  # 百分数→小数制


def test_parse_sina_hk_format():
    src = gi._Src("sina", "rt_hkHSI", fmt="hk")
    payload = "HSI,恒生指数,25100.0,25000.0,25200.0,24900.0,25050.5,50.5,0.20,x,y"
    row = gi._parse(src, payload)
    assert row["last"] == 25050.5 and row["change_pct"] == pytest.approx(0.002)


def test_parse_tencent_simple_format():
    """[R119] 腾讯精简版(`s_` 前缀): 市场~名称~代码~最新~涨跌额~涨跌幅~量~额。"""
    row = gi._parse(_TENCENT, "200~纳斯达克~IXIC~22484.07~98.50~0.44~123~456")
    assert row["last"] == 22484.07
    assert row["change"] == 98.5
    assert row["change_pct"] == pytest.approx(0.0044)


def test_parse_tencent_full_format():
    """完整版的涨跌额/涨跌幅在第 31/32 位, 不能按精简版的位置读。"""
    f = ["1", "纳斯达克", "IXIC", "22484.07"] + ["0"] * 27 + ["98.50", "0.44"] + ["x"] * 5
    row = gi._parse(gi._Src("tencent", "usIXIC"), "~".join(f))
    assert row["last"] == 22484.07 and row["change_pct"] == pytest.approx(0.0044)


@pytest.mark.parametrize("payload", ["", "   ", "只有名字", "名字,不是数,x,y"])
def test_parse_garbage_returns_none(payload):
    assert gi._parse(_SINA, payload) is None


def test_parse_unknown_vendor_is_none():
    assert gi._parse(gi._Src("彭博", "SPX"), "1,2,3,4") is None


# ------------------------------------------------------------- 取数编排


def test_fetch_response_parsing_and_ttl(monkeypatch):
    calls = {"n": 0}

    def fake_fetch(sources):
        calls["n"] += 1
        return {("sina", "int_kospi"): "韩国KOSPI,3200.12,-12.34,-0.38"}

    monkeypatch.setattr(gi, "_fetch_all", fake_fetch)
    rows = gi.get_quotes(["kospi"])
    assert len(rows) == 1 and rows[0]["last"] == 3200.12
    assert rows[0]["source"] == "sina" and rows[0]["source_code"] == "int_kospi"
    # TTL 内第二次请求不打上游
    rows2 = gi.get_quotes(["kospi"])
    assert calls["n"] == 1 and rows2[0]["key"] == "kospi"


def test_candidates_fall_through_across_vendors(monkeypatch):
    """[R119] 前面的候选没数就往后试, 换厂商也一样 —— 韩国综合的实际处境。"""
    kospi = gi._BY_KEY["kospi"]
    vendors = {s.vendor for s in kospi.sources}
    assert len(kospi.sources) > 1 and vendors == {"sina", "tencent"}

    last_src = kospi.sources[-1]

    def fake_fetch(sources):
        # 只有最后一个候选有数据
        return {(last_src.vendor, last_src.code): "1~韩国综合~KS11~3200.12~-12.34~-0.38~1~2"}

    monkeypatch.setattr(gi, "_fetch_all", fake_fetch)
    rows = gi.get_quotes(["kospi"])
    assert len(rows) == 1 and rows[0]["last"] == 3200.12
    assert rows[0]["source"] == last_src.vendor and rows[0]["source_code"] == last_src.code


def test_one_vendor_down_does_not_kill_the_other(monkeypatch):
    """一家挂了不该拖累另一家 —— 多源的意义就在这。"""
    def boom(codes):
        raise RuntimeError("sina down")

    monkeypatch.setattr(gi, "_FETCHERS", {
        "sina": boom,
        "tencent": lambda codes: {"s_usIXIC": "200~纳斯达克~IXIC~22484.07~98.50~0.44~1~2"},
    })
    rows = gi.get_quotes(["nasdaq"])
    assert len(rows) == 1 and rows[0]["source"] == "tencent"


def test_upstream_failure_keeps_stale_value(monkeypatch):
    import time as _t
    monkeypatch.setattr(gi, "_fetch_all", lambda s: {("sina", "int_kospi"): "K,100.0,1.0,1.0"})
    assert gi.get_quotes(["kospi"])[0]["last"] == 100.0
    # 缓存过期 + 上游挂 → 回旧值
    monkeypatch.setattr(gi, "_cache_at", _t.time() - gi._TTL_S - 1)

    def boom(sources):
        raise RuntimeError("net down")

    monkeypatch.setattr(gi, "_fetch_all", boom)
    rows = gi.get_quotes(["kospi"])
    assert rows and rows[0]["last"] == 100.0


def test_unknown_keys_ignored():
    assert gi.get_quotes(["nope"]) == []


def test_preset_table_is_the_two_the_user_wants():
    """[R116] 只留韩国综合 + 纳斯达克, 且默认全选(表里没别的可选)。"""
    assert [p.key for p in gi.PRESETS] == ["kospi", "nasdaq"]
    assert gi.DEFAULT_KEYS == ["kospi", "nasdaq"]


def test_trading_flag_present():
    """卡片要能区分'交易中'与'休市'(休市值静止不是故障)。"""
    from datetime import datetime
    kospi = gi._BY_KEY["kospi"]
    assert gi._in_session(kospi, datetime(2026, 9, 2, 10, 0)) is True    # 周三上午
    assert gi._in_session(kospi, datetime(2026, 9, 2, 20, 0)) is False   # 韩股已收
    nasdaq = gi._BY_KEY["nasdaq"]
    assert gi._in_session(nasdaq, datetime(2026, 9, 2, 23, 0)) is True   # 美股夜盘


# ------------------------------------------------------------- 原始行拆解


def test_sina_line_extraction(monkeypatch):
    body = 'var hq_str_int_nasdaq="纳斯达克,22484.07,98.5,0.44";\nvar hq_str_int_kospi="";'

    class _Resp:
        content = body.encode("gbk")
        def raise_for_status(self): pass

    monkeypatch.setattr(gi.httpx, "get", lambda *a, **k: _Resp())
    got = gi._fetch_sina(["int_nasdaq", "int_kospi"])
    assert got == {"int_nasdaq": "纳斯达克,22484.07,98.5,0.44"}   # 空行不收


def test_tencent_line_extraction(monkeypatch):
    body = 'v_s_usIXIC="200~纳斯达克~IXIC~22484.07~98.50~0.44~1~2";\nv_int_ks11="";'

    class _Resp:
        content = body.encode("gbk")
        def raise_for_status(self): pass

    monkeypatch.setattr(gi.httpx, "get", lambda *a, **k: _Resp())
    got = gi._fetch_tencent(["s_usIXIC", "int_ks11"])
    assert got == {"s_usIXIC": "200~纳斯达克~IXIC~22484.07~98.50~0.44~1~2"}


def test_debug_fetch_reports_every_candidate(monkeypatch):
    monkeypatch.setattr(gi, "_fetch_all", lambda s: {("sina", "int_nasdaq"): "纳斯达克,22484.07,98.5,0.44"})
    out = gi.debug_fetch(["nasdaq"])
    assert out["ok"] is True
    assert "sina:int_nasdaq" in out["candidates"] and "tencent:s_usIXIC" in out["candidates"]
    parsed = out["parsed"]["nasdaq"]
    assert parsed["sina:int_nasdaq"]["last"] == 22484.07
    assert parsed["tencent:s_usIXIC"] is None      # 没数的候选如实报 null
