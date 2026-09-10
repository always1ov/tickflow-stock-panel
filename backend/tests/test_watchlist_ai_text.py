"""[R265] 粘一段话 → AI 抽个股 → 匹配主数据。

盯的是**判定核心**(`resolve_mentions`)与解析(`parse_mentions`), 两者都是纯函数,
一次 AI 都不调。这条路最危险的失败不是"抽不出来"而是**抽错了还照样导进去** ——
所以这一组里分量最重的是「AI 记错代码」「重名」「历史已导入」三类。
"""
from __future__ import annotations

import pytest

from app.services import watchlist_ai_text as ai_text

# 一小份主数据: 覆盖普通股、ETF、带前缀、以及一对同名票
CODE_TO_SYMBOL = {
    "002475": "002475.SZ",
    "300308": "300308.SZ",
    "300502": "300502.SZ",
    "002241": "002241.SZ",
    "600519": "600519.SH",
    "515880": "515880.SH",
    "600221": "600221.SH",
    "900945": "900945.SH",
}
SYMBOL_TO_NAME = {
    "002475.SZ": "立讯精密",
    "300308.SZ": "中际旭创",
    "300502.SZ": "新易盛",
    "002241.SZ": "歌尔股份",
    "600519.SH": "贵州茅台",
    "515880.SH": "通信ETF国泰",
    "600221.SH": "*ST海航",
    "900945.SH": "海航B股",
}


def _resolve(mentions, existing=None):
    return ai_text.resolve_mentions(mentions, CODE_TO_SYMBOL, SYMBOL_TO_NAME, existing)


def _m(name="", code="", quote=""):
    return {"name": name, "code": code, "quote": quote}


# ================================================================
# 名称匹配 —— 这条路的立身之本
# ================================================================

def test_只有名字没有代码也能匹配上():
    """老路只认六位数字, 复盘笔记里的票多半只有名字 —— 这就是这条路存在的理由。"""
    out = _resolve([_m(name="中际旭创"), _m(name="新易盛")])
    assert [c["symbol"] for c in out] == ["300308.SZ", "300502.SZ"]
    assert all(c["matched"] for c in out)


def test_名称里的空白与括号不影响匹配():
    for raw in ("中际 旭创", "中际　旭创", "中际-旭创", "中际(旭创)"):
        out = _resolve([_m(name=raw)])
        assert out[0]["symbol"] == "300308.SZ", raw


def test_交易状态前缀两边都能对上():
    """主数据写「*ST海航」而原文常写「海航」, 两种写法指的是同一只。"""
    assert _resolve([_m(name="海航")])[0]["symbol"] == "600221.SH"
    assert _resolve([_m(name="*ST海航")])[0]["symbol"] == "600221.SH"


def test_名称取的是主数据的正式名而不是原文写法():
    """原文可能写简称 —— 存进自选的名字得是主数据那个, 否则以后对不上。"""
    out = _resolve([_m(name="海航")])
    assert out[0]["name"] == "*ST海航"


def test_ETF也认():
    assert _resolve([_m(name="通信ETF国泰")])[0]["symbol"] == "515880.SH"


# ================================================================
# AI 编代码 —— 这一组是整条路的安全底线
# ================================================================

def test_名称与代码指向不同的票时一律不采信():
    """**这条路最危险的失败**: 模型把「立讯精密」的代码记成了茅台的。

    照单全收就会把一只完全无关的票导进自选, 而且代码合法, 事后根本查不出来。
    """
    out = _resolve([_m(name="立讯精密", code="600519")])
    assert out[0]["matched"] is False
    assert out[0]["symbol"] is None
    assert out[0]["warn"] == ai_text.WARN_CONFLICT


def test_名称与代码一致时正常匹配():
    out = _resolve([_m(name="立讯精密", code="002475")])
    assert out[0]["symbol"] == "002475.SZ" and out[0]["matched"]
    assert out[0]["warn"] == ""


def test_代码查不到时以名称为准():
    """AI 补了个主数据里没有的代码, 名称却是对的 —— 名称能对上就该认。"""
    out = _resolve([_m(name="贵州茅台", code="999999")])
    assert out[0]["symbol"] == "600519.SH"


def test_名称查不到时以代码为准():
    """原文写的是别名/错别字, 但代码是原文里抄的 —— 代码能对上就该认。"""
    out = _resolve([_m(name="立讯", code="002475")])
    assert out[0]["symbol"] == "002475.SZ"


def test_两边都查不到就如实说不认识():
    out = _resolve([_m(name="宇宙无敌科技", code="")])
    assert out[0]["matched"] is False
    assert out[0]["warn"] == ai_text.WARN_UNKNOWN
    assert out[0]["mention"] == "宇宙无敌科技", "得把 AI 抽了什么带回去给人看"


# ================================================================
# 重名 —— 不许先到先得地静默选一只
# ================================================================

def test_一个名字对应多只时退回未匹配而不是猜一只():
    """先到先得会让人以为导对了。宁可退回来让人自己定。"""
    _lookup, ambiguous = ai_text.build_name_lookup(
        {**SYMBOL_TO_NAME, "600221.SH": "海航", "900945.SH": "海航"})
    assert ai_text.normalize_name("海航") in ambiguous
    out = ai_text.resolve_mentions(
        [_m(name="海航")], CODE_TO_SYMBOL,
        {"600221.SH": "海航", "900945.SH": "海航"}, None)
    assert out[0]["matched"] is False
    assert out[0]["warn"] == ai_text.WARN_AMBIGUOUS


def test_重名时如果原文带了代码照样能定下来():
    out = ai_text.resolve_mentions(
        [_m(name="海航", code="600221")], CODE_TO_SYMBOL,
        {"600221.SH": "海航", "900945.SH": "海航"}, None)
    assert out[0]["symbol"] == "600221.SH"


# ================================================================
# 历史已导入过 —— 用户点名要处理好的那件事
# ================================================================

def test_已在自选的票标出来但不丢掉():
    """丢掉的话「已在自选·将并入所选分组」这条路就断了 —— 用户要的是并组, 不是跳过。"""
    out = _resolve([_m(name="贵州茅台"), _m(name="中际旭创")], existing={"600519.SH"})
    by_sym = {c["symbol"]: c for c in out}
    assert by_sym["600519.SH"]["already_in_watchlist"] is True
    assert by_sym["300308.SZ"]["already_in_watchlist"] is False
    assert len(out) == 2, "已在自选的不能被剔除, 前端还要拿它并入目标分组"


def test_同一只票在一段话里提到多次只出一条():
    out = _resolve([_m(name="中际旭创", quote="第一次"),
                    _m(name="中际旭创", code="300308", quote="第二次"),
                    _m(name="中际 旭创", quote="第三次")])
    assert len(out) == 1
    assert out[0]["quote"] == "第一次", "保序取首次出现"


def test_同一个没认出来的东西也不刷屏():
    out = _resolve([_m(name="某某概念"), _m(name="某某概念"), _m(name="另一个")])
    assert len(out) == 2


# ================================================================
# 解析 AI 输出
# ================================================================

def test_解析出名称代码与原文片段():
    got = ai_text.parse_mentions(
        '{"mentions": [{"name": "中际旭创", "code": "300308", "quote": "光模块走强"}]}')
    assert got == [{"name": "中际旭创", "code": "300308", "quote": "光模块走强"}]


def test_代码字段夹带后缀或杂字也能取到六位():
    for raw in ("300308.SZ", "代码300308", "sz300308", " 300308 "):
        got = ai_text.parse_mentions(
            '{"mentions": [{"name": "中际旭创", "code": "' + raw + '"}]}')
        assert got[0]["code"] == "300308", raw


def test_代码不是六位就当没填而不是硬塞():
    got = ai_text.parse_mentions('{"mentions": [{"name": "中际旭创", "code": "30030"}]}')
    assert got[0]["code"] == ""


def test_坏数据跳过而不是抛():
    got = ai_text.parse_mentions(
        '{"mentions": ["不是对象", {"code": ""}, {"name": "新易盛"}]}')
    assert got == [{"name": "新易盛", "code": "", "quote": ""}]


def test_模型加了围栏或思考段也能抽出来():
    got = ai_text.parse_mentions(
        '<think>让我想想</think>```json\n{"mentions": [{"name": "新易盛"}]}\n```')
    assert got[0]["name"] == "新易盛"


def test_空输出返回空列表而不是抛():
    for raw in (None, "", "完全不是 JSON", "{}", '{"mentions": []}'):
        assert ai_text.parse_mentions(raw) == []


def test_提及数量有上限():
    many = ",".join(f'{{"name": "票{i}"}}' for i in range(ai_text.MAX_MENTIONS + 20))
    got = ai_text.parse_mentions(f'{{"mentions": [{many}]}}')
    assert len(got) == ai_text.MAX_MENTIONS


# ================================================================
# 端到端(把 AI 换掉, 只留这条路自己的逻辑)
# ================================================================

@pytest.fixture
def fake_ai(monkeypatch, tmp_path):
    """把 AI 与主数据读取都换掉 —— 留下的就是这条路自己的判定。"""
    from app.services import ai_provider

    holder = {"reply": '{"mentions": []}'}
    monkeypatch.setattr(ai_provider, "ai_configured", lambda *a, **k: True)

    async def _gen(messages, **kw):
        holder["messages"] = messages
        return holder["reply"]

    monkeypatch.setattr(ai_provider, "generate_ai_text", _gen)
    monkeypatch.setattr(ai_text, "build_instrument_lookups",
                        lambda d: (CODE_TO_SYMBOL, SYMBOL_TO_NAME))
    holder["dir"] = tmp_path
    return holder


@pytest.mark.anyio
async def test_端到端_一段复盘笔记导出三只票(fake_ai):
    fake_ai["reply"] = ('{"mentions": ['
                        '{"name": "中际旭创", "quote": "光模块方向"},'
                        '{"name": "新易盛"},'
                        '{"name": "立讯精密", "code": "002475"}]}')
    res = await ai_text.generate(
        "今天复盘: 光模块方向中际旭创、新易盛继续走强, 消费电子里立讯精密(002475)补涨。",
        fake_ai["dir"], existing_symbols={"300502.SZ"})
    assert res["matched_count"] == 3 and res["unmatched_count"] == 0
    assert [c["symbol"] for c in res["candidates"]] == [
        "300308.SZ", "300502.SZ", "002475.SZ"]
    assert [c["already_in_watchlist"] for c in res["candidates"]] == [False, True, False]
    assert res["provider"] == "ai-text"


@pytest.mark.anyio
async def test_端到端_没配AI就直说(monkeypatch, tmp_path):
    from app.services import ai_provider
    monkeypatch.setattr(ai_provider, "ai_configured", lambda *a, **k: False)
    res = await ai_text.generate("随便一段话", tmp_path)
    assert "未配置 AI" in res["error"]


@pytest.mark.anyio
async def test_端到端_空正文不去调AI(fake_ai):
    res = await ai_text.generate("   ", fake_ai["dir"])
    assert res["error"] and "messages" not in fake_ai, "空正文不该烧一次调用"


@pytest.mark.anyio
async def test_端到端_AI没认出个股时给出可读原因(fake_ai):
    fake_ai["reply"] = "这段话里我没看到股票。"
    res = await ai_text.generate("今天天气不错。", fake_ai["dir"])
    assert "没认出个股" in res["error"]


@pytest.mark.anyio
async def test_端到端_AI报错不外泄成崩溃(fake_ai, monkeypatch):
    from app.services import ai_provider

    async def _boom(messages, **kw):
        raise RuntimeError("429 限流")

    monkeypatch.setattr(ai_provider, "generate_ai_text", _boom)
    res = await ai_text.generate("随便", fake_ai["dir"])
    assert "AI 调用失败" in res["error"] and "429" in res["error"]


@pytest.mark.anyio
async def test_端到端_超长正文截断而不是拒绝(fake_ai):
    """研报动辄上万字, 提到的票基本在前半段 —— 截断比拒绝有用。"""
    fake_ai["reply"] = '{"mentions": [{"name": "贵州茅台"}]}'
    long_text = "免责声明。" * 4000
    res = await ai_text.generate(long_text, fake_ai["dir"])
    assert res.get("truncated") is True
    sent = fake_ai["messages"][1]["content"]
    assert len(sent) < len(long_text)


@pytest.mark.anyio
async def test_端到端_提示词里钉着不许凭记忆补代码(fake_ai):
    """这条规则一旦从提示词里掉了, 上面那组「AI 编代码」的防线就只剩事后拦截。"""
    fake_ai["reply"] = '{"mentions": [{"name": "贵州茅台"}]}'
    await ai_text.generate("茅台", fake_ai["dir"])
    system = fake_ai["messages"][0]["content"]
    assert "不要凭记忆补代码" in system
    assert "指数" in system and "板块" in system, "得说清只挑个股"


# ================================================================
# 端点 + 前端接线
# ================================================================

def _client(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api.watchlist import router
    from app.services import watchlist

    monkeypatch.setattr(watchlist, "list_symbols", lambda: [{"symbol": "600519.SH"}])
    app = FastAPI()
    app.include_router(router)
    app.state.repo = SimpleNamespace(store=SimpleNamespace(data_dir=tmp_path))
    return TestClient(app)


def test_端点_把自选现状喂给解析(tmp_path, monkeypatch):
    """**用户点名要处理好的那件事**: 历史已导入过的票必须被标出来。"""
    seen: dict = {}

    async def _fake(text, data_dir, *, existing_symbols=None):
        seen["existing"] = existing_symbols
        return {"provider": "ai-text", "codes": ["600519"], "matched_count": 1,
                "unmatched_count": 0,
                "candidates": [{"code": "600519", "symbol": "600519.SH", "name": "贵州茅台",
                                "matched": True, "already_in_watchlist": True}]}

    monkeypatch.setattr(ai_text, "generate", _fake)
    resp = _client(tmp_path, monkeypatch).post(
        "/api/watchlist/import-text", json={"text": "茅台还能拿"})
    assert resp.status_code == 200
    assert seen["existing"] == {"600519.SH"}
    assert resp.json()["candidates"][0]["already_in_watchlist"] is True


def test_端点_解析失败给可读原因而不是500(tmp_path, monkeypatch):
    async def _fake(text, data_dir, *, existing_symbols=None):
        return {"error": "未配置 AI —— 到设置页填 AI Key 后再试"}

    monkeypatch.setattr(ai_text, "generate", _fake)
    resp = _client(tmp_path, monkeypatch).post(
        "/api/watchlist/import-text", json={"text": "随便"})
    assert resp.status_code == 400 and "未配置 AI" in resp.json()["detail"]


def test_端点_空正文直接拒(tmp_path, monkeypatch):
    resp = _client(tmp_path, monkeypatch).post(
        "/api/watchlist/import-text", json={"text": "   "})
    assert resp.status_code == 400


def test_端点_不回传整段原文(tmp_path, monkeypatch):
    """正文可能上万字, 原样回传只是把它在网线上再走一遍。"""
    async def _fake(text, data_dir, *, existing_symbols=None):
        return {"provider": "ai-text", "codes": [], "matched_count": 1, "unmatched_count": 0,
                "raw_text": "很长很长的正文",
                "candidates": [{"code": "600519", "symbol": "600519.SH", "name": "贵州茅台",
                                "matched": True, "already_in_watchlist": False}]}

    monkeypatch.setattr(ai_text, "generate", _fake)
    body = _client(tmp_path, monkeypatch).post(
        "/api/watchlist/import-text", json={"text": "x"}).json()
    assert "raw_text" not in body


def _src(rel: str) -> str:
    from pathlib import Path
    p = Path(__file__).resolve().parents[2] / "frontend" / "src" / rel
    return p.read_text(encoding="utf-8")


def _code_lines(text: str) -> str:
    """只留代码行 —— 断言查的标识符常常也写在我自己加的注释里。"""
    out = []
    for ln in text.splitlines():
        s = ln.strip()
        if s.startswith(("//", "/*", "*", "{/*")):
            continue
        out.append(ln)
    return "\n".join(out)


def test_前端_接的是新端点():
    api = _code_lines(_src("lib/api.ts"))
    assert "watchlistImportText" in api
    assert "/api/watchlist/import-text" in api


def test_前端_两个按钮分别走两条路():
    """同一个输入框两条解析路 —— 接串了会让「一段话」白烧一次 AI 却抽不出东西。"""
    dlg = _code_lines(_src("components/WatchlistImportDialog.tsx"))
    assert "api.watchlistImportText" in dlg and "api.watchlistImportCodes" in dlg
    assert "AI 认股票" in dlg and "解析代码" in dlg


def test_前端_未匹配时显示的是原因而不是统一一句():
    dlg = _code_lines(_src("components/WatchlistImportDialog.tsx"))
    assert "c.warn || NO_MATCH_MSG" in dlg, "AI 那条路知道为什么没匹配上, 得说出来"


def test_前端_候选行的key不会在没有代码时撞车():
    """AI 的未匹配项可能没有代码, 光用 code 做 key 会让 React 把两行当成一行。"""
    dlg = _code_lines(_src("components/WatchlistImportDialog.tsx"))
    assert "key={sym ?? `${c.code}|${c.mention ?? ''}`}" in dlg
