"""[R405] 斐波那契二型接到 `/levels` 端点上之后, **整条链路真的通**。

`test_dinapoli_pivots.py` 钉的是算法本身; 这一组钉的是**接线**:
端点出不出那一组线、叠加层字段在不在、空数据那条早返回的形状对不对。

## 为什么要单独钉早返回

第一版漏了它 —— 有数据那条路加了 `fib2`, 没数据那条路的字典是**手写死的
12 个 key**, 没跟着加。前端拿到 `undefined` 而不是空, 于是"这只票没数据"
和"这只票算不出二型"在前端看起来一模一样。这类漏法不报错, 只在冷门路径上
安静地不一样。
"""
from __future__ import annotations

from types import SimpleNamespace

import polars as pl
import pytest
from fastapi.testclient import TestClient


def _staircase(n_flat: int = 20) -> pl.DataFrame:
    """台阶式上涨: 横盘 → 三段抬升, 每段之间一个比前一个高的谷底。

    **手工构造而不是拿真实行情** —— 真实行情跑出来的数当期望值, 等于把当时的
    bug 一起钉住; 这里要的是"形态确定, 结论可推"。
    """
    def seg(a: float, b: float, n: int) -> list[float]:
        return [a + (b - a) * i / (n - 1) for i in range(n)]
    closes = (seg(10, 10, n_flat) + seg(10, 7, 4) + seg(7, 13, 8) + seg(13, 10, 4)
              + seg(10, 17, 8) + seg(17, 14, 4) + seg(14, 24, 12) + seg(24, 20, 6))
    n = len(closes)
    return pl.DataFrame({
        "date": [f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}" for i in range(n)],
        "open": closes, "high": [c + 0.2 for c in closes],
        "low": [c - 0.2 for c in closes], "close": closes,
        "volume": [1000.0] * n, "atr_14": [0.6] * n,
    })


def _with_shallow_dip() -> pl.DataFrame:
    """**三档两两都给出不同结果**的形态。

    干净的台阶(`_staircase()`)三档一致 —— 那也是对的, 但拿它验不出档位差别:
    变异测试证过, 用它的话把默认档从「中」改成「粗」或「细」都照样全绿。
    这份序列是搜出来的, 让粗/中/细分别认出 2 / 4 / 5 个回调。
    """
    jagged = [10.0, 8.4, 6.8, 5.2, 6.4, 7.1, 5.5, 5.8, 7.0, 6.1, 6.4, 7.6, 6.0,
              6.7, 5.8, 7.6, 7.9, 8.2, 8.9, 8.0, 7.6, 6.7, 7.9, 7.0, 8.8, 9.1,
              8.7, 7.1, 7.4, 9.2]
    # 锯齿段负责造出粗细分得开的回调; 后面接一段干净拉升, 否则**推进段都不成立**,
    # 整个叠加层是空的(第一版就栽在这儿: 只有锯齿, `grain` 字段根本不存在)。
    rise = [9.2 + i * 0.75 for i in range(1, 15)]
    pull = [rise[-1] - i * 0.45 for i in range(1, 6)]
    lows = jagged + rise + pull
    closes = [x + 0.3 for x in lows]
    n = len(closes)
    return pl.DataFrame({
        "date": [f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}" for i in range(n)],
        "open": closes, "high": [c + 0.2 for c in closes], "low": lows,
        "close": closes, "volume": [1000.0] * n, "atr_14": [0.4] * n,
    })


def _open_auth(monkeypatch) -> None:
    """这组测的是价位计算, 不是登录 —— 把认证放行, 免得 403 把真结论盖住。"""
    from app import config as app_config
    monkeypatch.setattr(app_config.settings, "auth_disabled", True)


@pytest.fixture()
def client(monkeypatch):
    from app.main import app

    _open_auth(monkeypatch)
    df = _staircase()
    app.state.repo = SimpleNamespace(
        get_daily_asset=lambda *_a, **_k: df,
        resolve_asset_type=lambda _s: "stock",
    )
    return TestClient(app)


@pytest.fixture()
def dip_client(monkeypatch):
    """喂"三档会分出差别"的那份数据。"""
    from app.main import app

    _open_auth(monkeypatch)
    df = _with_shallow_dip()
    app.state.repo = SimpleNamespace(
        get_daily_asset=lambda *_a, **_k: df,
        resolve_asset_type=lambda _s: "stock",
    )
    return TestClient(app)


def _levels(client, symbol="000001.SZ"):
    r = client.get(f"/api/stock-analysis/levels?symbol={symbol}&days=250")
    assert r.status_code == 200, r.text
    return r.json()


def test_R405_端点出得来斐波那契二型那一组线(client):
    d = _levels(client)
    pts = d["levels"]["fib2"]
    assert pts, "端点没给出二型的线"
    labels = {p["label"] for p in pts}
    # 白话标签(规格 §12), 不是 F3/F5/COP
    assert any(x.startswith("浅回撤") for x in labels)
    assert any(x.startswith("深回撤") for x in labels)
    assert {"目标一", "目标二", "目标三"} <= labels
    assert "失效位" in labels
    for p in pts:
        assert p["type"] == "fib2" and p["value"] > 0


def test_R405_画不成横线的那几样走叠加层(client):
    d = _levels(client)
    ov = d["fib2"]
    assert ov, "叠加层是空的"
    assert ov["thrust"] and ov["thrust"]["days"] >= 8, "上攻段没给出来"
    z = ov["grain"]["mid"]["zone"]
    assert z and z["high"] >= z["low"]
    assert z["strength"] >= 2, "强支撑区至少要两条回撤重合"
    assert isinstance(ov.get("markers"), list)
    # 短期均线走 series(和量化通道同一个通道), 不塞进叠加层
    assert "fib2" in d["series"] and d["series"]["fib2"]["dma3"]
    # 平移之后露到最后一根之外的几个值 = 图上「未来」区
    assert len(ov["dma3_future"]) == 3


def test_R405_强支撑区必须真落在回撤线上(client):
    """色带不能凭空画 —— 它的上下沿就是那几条挤在一起的回撤线。"""
    d = _levels(client)
    ov, pts = d["fib2"], d["levels"]["fib2"]
    z = ov["grain"]["mid"]["zone"]
    lows = {round(p["value"], 2) for p in pts if p["label"].startswith(("浅回撤", "深回撤"))}
    assert round(z["low"], 2) in lows, "区下沿不是某条回撤线"
    assert round(z["high"], 2) in lows, "区上沿不是某条回撤线"


def test_R405_失效位在强支撑区下方(client):
    """「跌破它这组回撤就不成立」—— 位置在区下沿之下才说得通。"""
    d = _levels(client)
    inv = next(p["value"] for p in d["levels"]["fib2"] if p["label"] == "失效位")
    assert inv < d["fib2"]["grain"]["mid"]["zone"]["low"]


def test_R405_没数据那条早返回也要有这两个字段(monkeypatch):
    """第一版就漏在这儿: 有数据的路加了, 没数据的路是手写死的 key 列表。"""
    from app.main import app
    _open_auth(monkeypatch)
    app.state.repo = SimpleNamespace(
        get_daily_asset=lambda *_a, **_k: pl.DataFrame(),
        resolve_asset_type=lambda _s: "stock",
    )
    d = TestClient(app).get("/api/stock-analysis/levels?symbol=000001.SZ").json()
    assert "fib2" in d["levels"], "空数据时 levels.fib2 缺了 —— 前端拿到 undefined"
    assert d["levels"]["fib2"] == []
    assert d["fib2"] == {}, "空数据时叠加层也该是空对象而不是缺字段"


def test_R405_六态那一组原样还在(client):
    """挨着注入的两组, 加一组时最容易顺手碰到另一组。"""
    d = _levels(client)
    assert "livermore" in d["levels"]


def test_R405_二型不写进AI提示词那一路(client):
    """`stock_signal` / `stock_analyzer` 自己调 `compute_levels(df)` 取上下文,
    而二型是 API 层注入的 —— **算法层拿不到它**。

    这不是疏忽, 是范围: 用户要的是"图上一个指标", 不是让 AI 多一个判据。
    """
    from app.indicators.levels import compute_levels
    assert "fib2" not in compute_levels(_staircase()), \
        "二型漏进了 compute_levels —— AI 提示词会跟着多一套说法"


# ================================================================
# 红线 —— 用户点名要查的三样, 钉成守卫而不是只查一次
# ================================================================

def test_R405_二型碰不到打分系统():
    """用户: 「检查一遍有没有动我打分系统」。

    `opportunity_score.py` 是逐字节冻结的稳定版; 而且几何量自 R229 起
    **整层不进把握分**, 界面上那句话得一直是真的。二型全是几何。
    """
    import inspect

    from app.services import opportunity_score, score_ledger
    for mod in (opportunity_score, score_ledger):
        src = inspect.getsource(mod)
        assert "fib2" not in src and "dinapoli" not in src, \
            f"{mod.__name__} 里出现了二型 —— 几何量漏进打分层了"


def test_R405_二型碰不到六态():
    """用户: 「六态的所有一点都不能改动」。两组挨着注入, 最容易顺手碰到。"""
    import inspect

    from app.indicators import livermore
    from app.services import livermore_service
    for mod in (livermore, livermore_service):
        src = inspect.getsource(mod)
        assert "fib2" not in src and "dinapoli" not in src, \
            f"{mod.__name__} 里出现了二型 —— 六态被掺进东西了"


def test_R405_二型碰不到作者的内置策略与指标():
    """用户: 「作者所有的内置指标…一点都不能改动」。`strategy/` 是只读区。"""
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "app"
    hits = []
    for p in list((root / "strategy").rglob("*.py")) + [
        root / "indicators" / "keltner.py",
        root / "indicators" / "keltner_geometry.py",
        root / "indicators" / "pipeline.py",
    ]:
        if p.exists() and ("fib2" in p.read_text(encoding="utf-8")
                           or "dinapoli" in p.read_text(encoding="utf-8")):
            hits.append(str(p.relative_to(root)))
    assert not hits, f"作者的只读区被掺了二型: {hits}"


def test_R405_二型不产生任何动作():
    """它只出位置。一旦这个模块里出现买卖/仓位/推送的词, 就是越界了 ——
    用户要的是"图上一个指标", 判定和提醒都不归它管。"""
    import inspect

    from app.indicators import dinapoli
    src = inspect.getsource(dinapoli)
    # 注释里解释"不做什么"是允许的, 所以只扫会渲染出去的字符串字面量
    import ast
    tree = ast.parse(src)
    docs = {ast.get_docstring(n, clean=False) for n in ast.walk(tree)
            if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef))}
    rendered = [n.value for n in ast.walk(tree)
                if isinstance(n, ast.Constant) and isinstance(n.value, str)
                and n.value not in docs]
    for word in ("买入", "卖出", "清仓", "减仓", "加仓", "提醒", "推送", "建议"):
        bad = [s for s in rendered if word in s]
        assert not bad, f"二型吐出了动作词「{word}」: {bad}"


# ================================================================
# 粗细三档
# ================================================================

def test_R406_三档一次全给出来(client):
    """用户选了「一次做完, 当场能比」—— 所以后端一口气算三档, 前端切换零延迟。"""
    g = _levels(client)["fib2"]["grain"]
    assert set(g) == {"coarse", "mid", "fine"}
    assert [g["coarse"]["k"], g["mid"]["k"], g["fine"]["k"]] == [5, 3, 2]
    for name, one in g.items():
        assert one["levels"], f"{name} 档一条线都没有"


def test_R406_越细的档线越多_这是旋钮的方向(dip_client):
    """原书没定"多小的回调算噪音", 这个旋钮就是在回答它:
    调大只认大级别回调(线少而稳), 调小小回调也算(线多而密)。"""
    g = _levels(dip_client)["fib2"]["grain"]
    n = {k: len(v["levels"]) for k, v in g.items()}
    assert n["coarse"] <= n["mid"] <= n["fine"], f"档位方向反了: {n}"
    assert n["fine"] > n["coarse"], f"这份数据本该分出差别, 却三档一样: {n}"


def test_R406_上攻段与首次回踩不随档位变(client):
    """它们不看摆点 —— 推进段只看收盘在不在均线上方。所以三档共用一份,
    不按档重复发, 也不该因为换档就跳。"""
    ov = _levels(client)["fib2"]
    assert "thrust" in ov and "markers" in ov
    for one in ov["grain"].values():
        assert "thrust" not in one and "markers" not in one, \
            "上攻段/回踩被按档重复了 —— 它们与粗细无关"


def test_R406_中档就是默认档(dip_client):
    """`levels.fib2` 给的是中档, 好让只读 levels 的调用方拿到能用的一组。

    **必须拿"三档不同"的数据验** —— 第一版用的是干净台阶, 中档与细档算出来
    一模一样, 于是把默认改成细档也照样绿(变异测试当场证过)。
    """
    d = _levels(dip_client)
    g = d["fib2"]["grain"]
    # 三档两两都不同, 换成任意另一档都会红 —— 第一版只比了 fine, 于是换成
    # coarse 照样绿(变异测试当场证过)。
    assert g["mid"]["levels"] != g["fine"]["levels"], "这份数据本该分出差别"
    assert g["mid"]["levels"] != g["coarse"]["levels"], "这份数据本该分出差别"
    assert d["levels"]["fib2"] == g["mid"]["levels"]
