"""[R271] 数据体检 —— 老数据缺了什么, 以及**注册表不许过时**。

用户: 「我不断改这个系统, 不断沿用以前的数据 …… 我加了东西或者删除了东西, 但是系统
没有重头开始, 会有残留的数据文件, 缺字段或者不完整」。

这一组里分量最重的是 `test_R271_注册表不许漏登记`: 体检报告的价值完全建立在
"这张表是全的"之上 —— 表漏一项, 报告就会对着那一项说"一切正常", 而它正在悄悄丢字段。
**注册表的完整性必须由测试保证, 不能靠自觉。**
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from app.services import data_doctor as dd

APP = Path(__file__).resolve().parents[1] / "app"


# ================================================================
# 注册表不许过时 —— 这一条是其余全部结论的前提
# ================================================================

#: [R272] 代码里出现、但**不在 user_data 下**的数据文件名 —— 逐条写明它在哪, 免得
#: 把整类放行。这张排除表过时是**安全的**(顶多是忽略一个已经不存在的名字);
#: 而下面那张注册表漏一项是**危险的**(体检会对着它说「一切正常」)。
NOT_USER_DATA = {
    "all.parquet": "kline 分区",
    "part.parquet": "kline 分区",
    "candidates.parquet": "回测候选",
    "instruments.parquet": "证券主数据",
    "instruments_etf.parquet": "ETF 主数据",
    "instruments_index.parquet": "指数主数据",
    "capabilities.json": "数据源能力探测",
    "config.json": "自定义数据源配置",
    "ext_configs.json": "扩展数据配置",
    "manifest.json": "任务/挖掘 job_store",
    "summary.json": "回测结果目录",
    "events.jsonl": "任务事件流",
}


def test_R272_注册表不许漏登记():
    """扫**所有像数据文件名的字符串字面量**, 每一个要么登记、要么显式排除。

    ## 第一版这条守卫是漏的, 而且是真机跑了一次体检才发现的

    第一版只认 `data_dir / "user_data" / "字面量"` 这一种路径写法。可仓库里另外两种
    写法根本不长那样: `JsonReportStore(filename)` 把文件名当构造参数传进去, 
    `strategy_cache` 用的是模块常量。于是六处**在用**的存储没被登记, 真实体检把它们
    当成「孤儿文件」报给了用户 —— 差一点就让人去删自己正在用的数据。

    **补丁不该是再加两条正则** —— 那只是把洞挪个位置, 下一种写法照样漏。这一版反过来:
    **宁可多收也不能漏**。多收的代价是维护一张小小的排除表(而且它过时是安全的),
    漏收的代价是体检说假话。
    """
    pat = re.compile(r'"([a-z_0-9]+\.(?:json|jsonl|parquet))"')
    found: set[str] = set()
    for p in APP.rglob("*.py"):
        found.update(pat.findall(p.read_text(encoding="utf-8")))
    known = {Path(s.rel).name for s in dd.STORES}
    missing = sorted(found - known - set(NOT_USER_DATA))
    assert not missing, (
        "这些数据文件名在代码里出现了, 却既没登记进 data_doctor.STORES、也没写进 "
        f"NOT_USER_DATA —— 体检会把它们当孤儿报给用户: {missing}"
    )


def test_R272_排除表和注册表不许打架():
    """同一个名字不能既登记又排除 —— 那说明有人改了一处忘了另一处。"""
    known = {Path(s.rel).name for s in dd.STORES}
    both = known & set(NOT_USER_DATA)
    assert not both, f"这些名字既登记又排除: {sorted(both)}"


def test_R271_注册表自己不许有重复项():
    rels = [s.rel for s in dd.STORES]
    assert len(rels) == len(set(rels))


def test_R271_每一项都说清楚是哪一类():
    """用户数据和派生数据的处置办法相反 —— 分错类, 建议就会反过来。"""
    for s in dd.STORES:
        assert s.kind in (dd.KIND_USER, dd.KIND_DERIVED), s.rel
        assert s.cn, f"{s.rel} 没有给人看的名字"


# ================================================================
# 体检本身
# ================================================================

@pytest.fixture
def dd_dir(tmp_path) -> Path:
    (tmp_path / "user_data").mkdir(parents=True)
    return tmp_path


def _write(root: Path, rel: str, payload) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return p


def test_R271_认出后加字段的缺失(dd_dir):
    """**用户抱怨的正主**: `weight` 是后加的, 老记录没有它,
    系统只会当你从没填过仓位 —— 不报错, 也不提示。"""
    _write(dd_dir, "user_data/positions.json", {
        "600519.SH": {"held": True, "cost": 1600.0, "updated_at": "2026-01-01"},  # 老记录
        "300308.SZ": {"held": True, "cost": 100.0, "weight": 20.0, "updated_at": "2026-09-01"},
    })
    got = next(s for s in dd.scan(dd_dir)["stores"] if s["rel"] == "user_data/positions.json")
    assert got["records"] == 2
    assert got["missing"] == {"weight": 1}


def test_R271_必填字段的缺失单独报而不是混进可补的里(dd_dir):
    """`id` 缺了不是"补个默认值"能解决的 —— 补出来的是一条假记录。"""
    _write(dd_dir, "user_data/usage_notes.json", [
        {"id": "a", "content": "正常", "status": "", "horizon": "news",
         "pinned": False, "digest": "", "due_at": None},
        {"content": "这条没有 id"},
    ])
    got = next(s for s in dd.scan(dd_dir)["stores"] if s["rel"] == "user_data/usage_notes.json")
    assert got["incomplete"] == {"id": 1}
    assert "id" not in got["missing"], "必填字段不该出现在「可补齐」那一栏"


def test_R271_读不动的文件如实报出来(dd_dir):
    p = dd_dir / "user_data" / "positions.json"
    p.write_text('{"600519.SH": {"held": tru', encoding="utf-8")   # 半截 JSON
    got = next(s for s in dd.scan(dd_dir)["stores"] if s["rel"] == "user_data/positions.json")
    assert got["readable"] is False and "读不动" in got["error"]


def test_R271_结构对不上也要报(dd_dir):
    """更早的版本可能写的是完全另一种结构 —— 那不是"缺字段", 是整份对不上。"""
    _write(dd_dir, "user_data/positions.json", ["这是个数组, 不是 {symbol: 记录}"])
    got = next(s for s in dd.scan(dd_dir)["stores"] if s["rel"] == "user_data/positions.json")
    assert "对不上" in got["error"]


def test_R271_文件不存在不算异常(dd_dir):
    """没用过那个功能就是没有那个文件 —— 报成异常会把真问题淹掉。"""
    rep = dd.scan(dd_dir)
    assert rep["summary"]["present"] == 0
    assert rep["summary"]["unreadable"] == 0


def test_R271_孤儿文件报出来(dd_dir):
    """功能删了、文件还在。"""
    _write(dd_dir, "user_data/退役功能.json", {"x": 1})
    rep = dd.scan(dd_dir)
    assert [o["rel"] for o in rep["orphans"]] == ["user_data/退役功能.json"]


def test_R271_体检自己留下的备份不算孤儿(dd_dir):
    _write(dd_dir, "user_data/positions.json.bak-20260101-000000", {"x": 1})
    assert dd.scan(dd_dir)["orphans"] == []


# ================================================================
# 密钥一个字节都不读
# ================================================================

def test_R271_密钥文件根本不读盘(dd_dir):
    """体检报告会经过接口、可能被截图、被贴进聊天。**把密钥读进内存再放进报告,
    是拿一个运维便利去换一条泄密通道。**

    这里验的是**真的没去读**, 不是"读了但没放进报告" —— 后者只差一次重构就漏。
    办法: 写一份**故意读不动**的内容进去; 如果体检去读了, 它必然报「读不动」,
    而现在它报的是正常, 说明那一步压根没发生。
    """
    for rel in ("user_data/secrets.json", "user_data/auth.json"):
        (dd_dir / rel).write_text("{这不是合法 JSON", encoding="utf-8")
    rep = dd.scan(dd_dir)
    for rel in ("user_data/secrets.json", "user_data/auth.json"):
        got = next(s for s in rep["stores"] if s["rel"] == rel)
        assert got["exists"] is True
        assert got["readable"] is True, "读不动说明它去读了 —— 这两处一个字节都不该读"
        assert got["error"] == ""
        assert got["records"] is None, "连记录数都不该数 —— 那要读内容"


def test_R271_密钥内容不进报告(dd_dir):
    """上一条守"不去读", 这一条守"就算读了也不许出现在报告里" —— 两道都要。"""
    secret = "sk-绝密-不该出现在任何报告里"
    _write(dd_dir, "user_data/secrets.json", {"ai_key": secret})
    _write(dd_dir, "user_data/auth.json", {"hash": secret})
    assert secret not in json.dumps(dd.scan(dd_dir), ensure_ascii=False)


# ================================================================
# 补齐 —— 只补, 不删, 先备份
# ================================================================

def test_R271_补齐只加不改(dd_dir):
    _write(dd_dir, "user_data/positions.json", {
        "600519.SH": {"held": True, "cost": 1600.0, "updated_at": "2026-01-01"},
    })
    res = dd.heal(dd_dir, ["user_data/positions.json"])["results"][0]
    assert res["ok"] and res["filled"] == 1
    after = json.loads((dd_dir / "user_data/positions.json").read_text(encoding="utf-8"))
    rec = after["600519.SH"]
    assert rec["weight"] is None, "后加的字段按默认值补上"
    assert rec["cost"] == 1600.0 and rec["held"] is True, "**已有的值一个都不许动**"
    assert rec["updated_at"] == "2026-01-01"


def test_R271_补齐前先备份(dd_dir):
    """改用户数据之前必须留一份 —— 补错了要能回去。"""
    _write(dd_dir, "user_data/positions.json", {"600519.SH": {"held": True}})
    res = dd.heal(dd_dir, ["user_data/positions.json"])["results"][0]
    assert res["backup"], "没留备份"
    bak = dd_dir / "user_data" / res["backup"]
    assert bak.exists()
    assert json.loads(bak.read_text(encoding="utf-8")) == {"600519.SH": {"held": True}}


def test_R271_没什么可补的时候不写盘也不留备份(dd_dir):
    """每点一次就多一份备份, 盘上很快堆满一堆一模一样的文件。"""
    _write(dd_dir, "user_data/positions.json", {
        "600519.SH": {"held": True, "cost": 1.0, "weight": 1.0, "updated_at": "x"},
    })
    res = dd.heal(dd_dir, ["user_data/positions.json"])["results"][0]
    assert res["ok"] and res["filled"] == 0 and res["backup"] == ""
    assert not list((dd_dir / "user_data").glob("*.bak-*"))


def test_R271_补齐后再体检就干净了(dd_dir):
    _write(dd_dir, "user_data/positions.json", {"a": {"held": True}, "b": {"held": False}})
    dd.heal(dd_dir, ["user_data/positions.json"])
    got = next(s for s in dd.scan(dd_dir)["stores"] if s["rel"] == "user_data/positions.json")
    assert got["missing"] == {}


def test_R271_补齐不碰派生数据(dd_dir):
    """派生数据缺字段该做的是删掉重算 —— 补它是在给假数据续命。"""
    derived = next(s for s in dd.STORES if s.kind == dd.KIND_DERIVED)
    _write(dd_dir, derived.rel, {"x": 1})
    res = dd.heal(dd_dir, [derived.rel])["results"][0]
    assert res["ok"] is False


def test_R271_没登记的路径一律不动(dd_dir):
    """接口收到的路径来自外部 —— 不能拿它当文件名直接去写。

    **这几个文件都真的存在**, 否则 heal 会因为「文件不存在」而拒, 测试就会为了
    错误的理由通过 —— 那样把守卫拆了它照样绿。
    """
    victims = {
        "user_data/没登记的东西.json": {"要紧数据": 1},
        "user_data/secrets.json": {"ai_key": "sk-绝密"},      # 登记了, 但不该被改
        "外面的文件.json": {"更不该动": 1},
    }
    for rel, payload in victims.items():
        _write(dd_dir, rel, payload)
    for rel, payload in victims.items():
        res = dd.heal(dd_dir, [rel])["results"][0]
        assert res["ok"] is False, rel
        after = json.loads((dd_dir / rel).read_text(encoding="utf-8"))
        assert after == payload, f"{rel} 被动过了"


def test_R271_路径穿越写不出去(dd_dir, tmp_path):
    """`../` 拼出来的路径要能被挡在外面。"""
    outside = tmp_path.parent / "外面.json"
    outside.write_text('{"a": {"held": true}}', encoding="utf-8")
    try:
        res = dd.heal(dd_dir, [f"../{outside.name}"])["results"][0]
        assert res["ok"] is False
        assert outside.read_text(encoding="utf-8") == '{"a": {"held": true}}'
    finally:
        outside.unlink(missing_ok=True)


def test_R271_补齐是纯函数可单测():
    """`_fill` 不碰盘 —— 补齐规则本身能脱离文件系统验证。"""
    store = dd._BY_REL["user_data/positions.json"]
    new, filled = dd._fill({"a": {"held": True}}, store)
    assert filled == 1
    assert new["a"]["held"] is True and "weight" in new["a"]


# ================================================================
# 端点
# ================================================================

def _client(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api.settings import router
    from app.config import settings as cfg

    monkeypatch.setattr(cfg, "data_dir", tmp_path)
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_R271_端点体检不改任何东西(dd_dir, monkeypatch):
    _write(dd_dir, "user_data/positions.json", {"a": {"held": True}})
    before = (dd_dir / "user_data/positions.json").read_bytes()
    resp = _client(dd_dir, monkeypatch).get("/api/settings/data-doctor")
    assert resp.status_code == 200
    assert resp.json()["summary"]["with_missing"] >= 1
    assert (dd_dir / "user_data/positions.json").read_bytes() == before


def test_R271_端点补齐要显式点名(dd_dir, monkeypatch):
    """不接受"全都补"这种含糊指令 —— 改的是不可重算的用户数据。"""
    resp = _client(dd_dir, monkeypatch).post("/api/settings/data-doctor/heal", json={"rels": []})
    assert resp.status_code == 400


# ================================================================
# [R272] 格式要逐种处理 —— 真机体检暴露的两个误报
# ================================================================
#
# 第一版对**任何**非目录文件都是 `read_text(encoding="utf-8")` + `json.loads`。
# 于是真机上两份完全健康的数据被报成「读不动」:
#
#   watchlist.parquet  二进制列存 → 'utf-8' codec can't decode byte 0xea
#   alerts.jsonl       每行一个 JSON → Extra data: line 2 column 1
#
# **体检误报比不报更糟**: 人看两次假警报之后就再也不看它了, 那些真问题也跟着被忽略。

def test_R272_parquet不按文本读(dd_dir):
    """二进制文件拿 UTF-8 去读, 必然报 codec 错 —— 那是体检自己的 bug, 不是数据坏了。"""
    import polars as pl
    pl.DataFrame({
        "symbol": ["600519.SH"], "added_at": ["2026-01-01"],
        "note": ["测试"], "group_ids": [["g1"]],
    }).write_parquet(dd_dir / "user_data/watchlist.parquet")
    got = next(s for s in dd.scan(dd_dir)["stores"] if s["rel"] == "user_data/watchlist.parquet")
    assert got["readable"] is True, f"健康的 parquet 被报成读不动: {got['error']}"
    assert got["error"] == ""
    assert got["records"] == 1
    assert got["missing"] == {}


def test_R272_parquet缺列查得出来(dd_dir):
    """parquet 的"字段"就是列。老版本写的表可能没有后加的那一列。"""
    import polars as pl
    pl.DataFrame({"symbol": ["600519.SH"], "added_at": ["2026-01-01"]}) \
        .write_parquet(dd_dir / "user_data/watchlist.parquet")
    got = next(s for s in dd.scan(dd_dir)["stores"] if s["rel"] == "user_data/watchlist.parquet")
    assert got["readable"] is True
    assert set(got["missing"]) == {"note", "group_ids"}


def test_R272_真坏掉的parquet还是要报(dd_dir):
    """放宽不能放宽到"什么都不查" —— 真读不动的还得报出来。"""
    (dd_dir / "user_data/watchlist.parquet").write_bytes("这根本不是 parquet".encode())
    got = next(s for s in dd.scan(dd_dir)["stores"] if s["rel"] == "user_data/watchlist.parquet")
    assert got["readable"] is False and "读不动" in got["error"]


def test_R272_jsonl逐行读(dd_dir):
    """每行一个 JSON —— 整份 json.loads 必然在第二行报 "Extra data"。"""
    (dd_dir / "user_data/alerts.jsonl").write_text(
        '{"ts": 1, "rule_id": "a"}\n{"ts": 2, "rule_id": "b"}\n', encoding="utf-8")
    got = next(s for s in dd.scan(dd_dir)["stores"] if s["rel"] == "user_data/alerts.jsonl")
    assert got["readable"] is True, f"健康的 JSONL 被报成读不动: {got['error']}"
    assert got["error"] == "" and got["records"] == 2


def test_R272_jsonl写到一半的那行报出来但不算整份坏掉(dd_dir):
    """追加写被打断会留下半行 —— 前面那些好行还在, 不该因为一行把整份判死。"""
    (dd_dir / "user_data/alerts.jsonl").write_text(
        '{"ts": 1}\n{"ts": 2}\n{"ts": 3, "半行', encoding="utf-8")
    got = next(s for s in dd.scan(dd_dir)["stores"] if s["rel"] == "user_data/alerts.jsonl")
    assert got["readable"] is True and got["records"] == 2
    assert "1 行" in got["error"]


def test_R272_store自己留的备份不算孤儿(dd_dir):
    """`paper_traders.json.bak` / `watchlist.parquet.bak` 是各个 store 保存时自己留的。
    把它们报成孤儿等于催人去删自己的备份。"""
    for name in ("paper_traders.json.bak", "watchlist.parquet.bak",
                 "positions.json.bak-20260101-000000"):
        (dd_dir / "user_data" / name).write_text("{}", encoding="utf-8")
    assert dd.scan(dd_dir)["orphans"] == []


def test_R272_六处漏登记的都补上了():
    """真机体检把这六处在用的存储当成了孤儿 —— 差一点让人去删自己正在用的数据。"""
    known = {s.rel for s in dd.STORES}
    for rel in ("user_data/ai_reports.json", "user_data/ai_stock_reports.json",
                "user_data/ai_market_recaps.json", "user_data/ladder_ai_reports.json",
                "user_data/strategy_cache.json", "user_data/strategy_run_timings.json"):
        assert rel in known, f"{rel} 还没登记"


def test_R272_报告带上体积(dd_dir):
    """真机上 strategy_cache.json 有 10MB —— 派生数据里最该被清掉的那种,
    不给体积就看不出来。"""
    _write(dd_dir, "user_data/strategy_cache.json", {"x": "y" * 500})
    got = next(s for s in dd.scan(dd_dir)["stores"] if s["rel"] == "user_data/strategy_cache.json")
    assert got["bytes"] > 500
