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
    # [R267] 下面这些取自用户给的真实文章(船舶/军工/稳定币/光模块/液冷)
    "600150": "600150.SH", "603268": "603268.SH", "600482": "600482.SH",
    "603535": "603535.SH", "302132": "302132.SZ", "000519": "000519.SZ",
    "603083": "603083.SH", "600487": "600487.SH", "688981": "688981.SH",
    "600869": "600869.SH", "002236": "002236.SZ",
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
    "600150.SH": "中国船舶", "603268.SH": "松发股份", "600482.SH": "中国动力",
    "603535.SH": "嘉诚国际", "302132.SZ": "中航成飞", "000519.SZ": "中兵红箭",
    "603083.SH": "剑桥科技", "600487.SH": "亨通光电", "688981.SH": "中芯国际",
    "600869.SH": "远东股份", "002236.SZ": "大华股份",
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
    assert got == [{"group": "", "name": "中际旭创", "code": "300308",
                    "starred": False, "quote": "光模块走强"}]


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
    assert got == [{"group": "", "name": "新易盛", "code": "",
                    "starred": False, "quote": ""}]


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
    long_text = "免责声明。" * (ai_text.MAX_TEXT_CHARS // 5 + 100)
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
    """只留代码行 —— 断言查的标识符常常也写在我自己加的注释里。

    **注释要按块剥, 不能只看行首。** 只剥首行的话, 跨行 `{/* … */}` 里除第一行以外的
    说明文字全都留在结果里, 断言照样被自己的注释喂饱 —— 这个坑在这个仓库里踩过五次。
    """
    out: list[str] = []
    in_block = False
    for ln in text.splitlines():
        line = ln
        while True:
            if in_block:
                end = line.find("*/")
                if end < 0:
                    line = ""
                    break
                line = line[end + 2:]
                in_block = False
                continue
            start = line.find("/*")
            if start < 0:
                break
            head = line[:start].rstrip().removesuffix("{")
            end = line.find("*/", start + 2)
            if end < 0:
                line = head
                in_block = True
                break
            line = head + line[end + 2:].removeprefix("}")
        stripped = line.strip()
        if not stripped or stripped.startswith("//"):
            continue
        out.append(line)
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


# ================================================================
# [R267] 小分队 —— 分类是文章作者做好的, 系统照做
# ================================================================
#
# 真实输入是公众号长文: 加粗小标题分板块(**船舶** **军工** **稳定币** **科技**),
# 科技底下还有更细的一层(光模块——剑桥科技 / 液冷——远东股份), 加粗的股票名是
# 作者的重点票, 正文里还夹着简称(中际)和一堆噪音(懂王、波斯猫、全A指数)。


def _g(group="", name="", code="", starred=False, quote=""):
    return {"group": group, "name": name, "code": code, "starred": starred, "quote": quote}


def test_R267_小分队跟着票走():
    out = _resolve([_g("船舶", "中国船舶"), _g("船舶", "松发股份"),
                    _g("军工", "中航成飞"), _g("光模块", "剑桥科技")])
    assert [c["groups"] for c in out] == [["船舶"], ["船舶"], ["军工"], ["光模块"]]


def test_R267_一只票在两个小分队里就带两个分队():
    """**用户刚点名要的多组能力**: 既在军工又在低空经济, 导入时同时进两个分组。"""
    out = _resolve([_g("军工", "中兵红箭"), _g("稳定币", "中兵红箭")])
    assert len(out) == 1, "同一只票只出一条候选, 不该让人勾两次"
    assert out[0]["groups"] == ["军工", "稳定币"]


def test_R267_同一小分队里重复提及不会把分队名记两遍():
    out = _resolve([_g("船舶", "中国船舶"), _g("船舶", "中国船舶", code="600150")])
    assert out[0]["groups"] == ["船舶"]


def test_R267_加粗的重点票带出来():
    out = _resolve([_g("船舶", "中国船舶"), _g("船舶", "松发股份", starred=True)])
    assert [c["starred"] for c in out] == [False, True]


def test_R267_一处加粗就算重点不会被后面的普通提及抹掉():
    """作者在某一节里加粗了它, 别处顺带又提一次 —— 重点标记不该因此消失。"""
    out = _resolve([_g("船舶", "松发股份", starred=True), _g("科技", "松发股份")])
    assert out[0]["starred"] is True


def test_R267_首次的原文片段不被后来的覆盖():
    """quote 是给人核对 AI 抽得对不对的 —— 覆盖掉就等于让人核对一个无关的句子。"""
    out = _resolve([_g("船舶", "中国船舶", quote="当初那句"),
                    _g("科技", "中国船舶", quote="后来那句")])
    assert out[0]["quote"] == "当初那句"


def test_R267_没归属的提及不算小分队():
    out = _resolve([_g("", "贵州茅台"), _g("船舶", "中国船舶")])
    assert out[0]["groups"] == []
    assert ai_text.group_names(out) == ["船舶"]


def test_R267_小分队按文章里出现的先后排():
    """导入界面按这个顺序摆映射行, 和读文章的顺序一致才对得上。"""
    out = _resolve([_g("船舶", "中国船舶"), _g("军工", "中航成飞"),
                    _g("船舶", "中国动力"), _g("稳定币", "大华股份")])
    assert ai_text.group_names(out) == ["船舶", "军工", "稳定币"]


def test_R267_小分队数量有上限():
    many = [_g(f"队{i}", "中国船舶") for i in range(ai_text.MAX_GROUPS + 10)]
    assert len(ai_text.group_names(_resolve(many))) == ai_text.MAX_GROUPS


def test_R267_分队名过长会截断():
    got = ai_text.parse_mentions(
        '{"mentions": [{"group": "' + "很长的分队名" * 5 + '", "name": "中国船舶"}]}')
    assert len(got[0]["group"]) == ai_text.MAX_GROUP_NAME


# ================================================================
# [R267] 简称 —— 只认唯一前缀
# ================================================================

def test_R267_唯一前缀的简称能认出来():
    """正文写「中际」, 主数据是「中际旭创」, 全库只有这一只以「中际」开头。"""
    out = _resolve([_g("科技", "中际")])
    assert out[0]["symbol"] == "300308.SZ"


def test_R267_被多只共用的前缀一律不认():
    """「中航」对上中航成飞/中航沈飞…… 猜一只最像的比认不出来更糟 ——
    认不出来会退回去让人自己定, 猜错了却是无声的。"""
    two = {**SYMBOL_TO_NAME, "302132.SZ": "中航成飞", "600760.SH": "中航沈飞"}
    out = ai_text.resolve_mentions([_g("军工", "中航")], CODE_TO_SYMBOL, two, None)
    assert out[0]["matched"] is False


def test_R267_单字不拿去做前缀匹配():
    """一个字命中一只纯属巧合, 而正文里的单字词几乎都不是股票。"""
    lookup = ai_text.build_prefix_lookup({"600150.SH": "中国船舶"})
    assert all(len(k) >= ai_text.MIN_ABBR_LEN for k in lookup)


def test_R267_全名优先于简称():
    """一个正式名恰好是另一只的前缀时, 必须判给那个正式名。"""
    names = {"000001.SZ": "中际", "300308.SZ": "中际旭创"}
    out = ai_text.resolve_mentions([_g("科技", "中际")], {}, names, None)
    assert out[0]["symbol"] == "000001.SZ", "全名精确命中就不该再走简称那条路"


def test_R267_简称表不收全名本身():
    """全名归 name_lookup 管 —— 两张表都收会让重名判定失效。"""
    lookup = ai_text.build_prefix_lookup({"600150.SH": "中国船舶", "603268.SH": "中国船务"})
    assert "中国船舶" not in lookup


# ================================================================
# [R267] 端到端 —— 照着用户给的真实文章跑
# ================================================================

@pytest.mark.anyio
async def test_R267_端到端_一篇公众号文章分成四个小分队(fake_ai):
    fake_ai["reply"] = '''{"mentions": [
      {"group": "船舶", "name": "中国船舶", "starred": false, "quote": "关注中国船舶"},
      {"group": "船舶", "name": "松发股份", "starred": true, "quote": "关注中国船舶、松发股份"},
      {"group": "军工", "name": "中航成飞", "starred": false, "quote": "关注中航成飞"},
      {"group": "军工", "name": "中兵红箭", "starred": true, "quote": "内蒙一机、中兵红箭"},
      {"group": "光模块", "name": "剑桥科技", "starred": true, "quote": "光模块——剑桥科技"},
      {"group": "液冷", "name": "远东股份", "starred": true, "quote": "液冷——远东股份"},
      {"group": "科技", "name": "中际", "starred": false, "quote": "三个龙头中际、长鑫、寒王"},
      {"group": "科技", "name": "寒王", "starred": false, "quote": "三个龙头中际、长鑫、寒王"}
    ]}'''
    res = await ai_text.generate("# 诈死复生\n**船舶**\n...", fake_ai["dir"],
                                 existing_symbols={"600150.SH"})
    assert res["section_names"] == ["船舶", "军工", "光模块", "液冷", "科技"]
    by_name = {c["name"]: c for c in res["candidates"]}
    assert by_name["中际旭创"]["symbol"] == "300308.SZ", "简称「中际」该认出来"
    assert by_name["中际旭创"]["groups"] == ["科技"]
    assert by_name["中国船舶"]["already_in_watchlist"] is True
    assert [c["name"] for c in res["candidates"] if c["starred"]] == [
        "松发股份", "中兵红箭", "剑桥科技", "远东股份"]
    # 「寒王」是外号, 主数据里没有 —— 如实退回去而不是猜一只
    miss = [c for c in res["candidates"] if not c["matched"]]
    assert [c["mention"] for c in miss] == ["寒王"]


@pytest.mark.anyio
async def test_R267_提示词钉住三条(fake_ai):
    """这三条一旦从提示词里掉了, 这条路就退回成「AI 自己想怎么分就怎么分」。"""
    fake_ai["reply"] = '{"mentions": [{"group": "船舶", "name": "中国船舶"}]}'
    await ai_text.generate("**船舶** 关注中国船舶", fake_ai["dir"])
    system = fake_ai["messages"][0]["content"]
    assert "不要自己发明分类" in system
    assert "取最细的那一层" in system
    assert "starred" in system
    assert "不要凭记忆补代码" in system


@pytest.mark.anyio
async def test_R267_整篇文章不会被腰斩(fake_ai):
    """板块清单常排在长文后半段(前半段是时事闲聊), 截太短等于专挑重点丢。"""
    assert ai_text.MAX_TEXT_CHARS >= 20000
    fake_ai["reply"] = '{"mentions": [{"group": "船舶", "name": "中国船舶"}]}'
    article = "闲聊。" * 2000 + "\n**船舶**\n关注中国船舶"
    res = await ai_text.generate(article, fake_ai["dir"])
    assert not res.get("truncated")
    assert "关注中国船舶" in fake_ai["messages"][1]["content"], "结尾的板块清单必须送到"


# ================================================================
# [R267] 前端: 小分队 → 目标分组的映射
# ================================================================

def test_R267_前端_每行按自己的小分队算目标分组():
    """一个全局目标说不清「船舶那队进 A、军工那队进 B」 —— 必须每行各算各的。"""
    dlg = _code_lines(_src("components/WatchlistImportDialog.tsx"))
    body = dlg[dlg.index("const rowTargets"):]
    body = body[:body.index("}, [")]
    # 只查「那行代码在不在」是空断言 —— 在它前面插一句无条件 return 照样能过。
    # 钉的是: 退回全局这条路**只有**挂在 !sectionMode 上的那一条。
    assert body.count("return targetGroupIds") == 1
    assert "if (!sectionMode) return targetGroupIds" in body
    assert body.index("if (!sectionMode)") < body.index("const out"), \
        "分队模式的判断必须是第一步, 前面不许有别的 return"
    assert "sectionMap[g]" in body, "每行的目标要从它自己所属的小分队映射里取"
    # 这个结果必须真的喂给 rowState, 不然算了也白算
    assert "const targets = rowTargets(c)" in dlg
    assert "rowState(c.symbol, c.matched, membership, targets)" in dlg


def test_R267_前端_建组推迟到点导入那一刻():
    """在映射界面上改主意的过程里建组, 会留下一堆删不掉的空分组。"""
    dlg = _code_lines(_src("components/WatchlistImportDialog.tsx"))
    body = dlg[dlg.index("const confirmAddBySection"):dlg.index("const confirmAdd =")]
    assert "api.watchlistGroupCreate" in body, "建组要发生在导入那一步里"
    # 映射面板的下拉只准改 state —— 在这里建组, 用户改一次主意就留一个空分组
    panel = dlg[dlg.index("{sectionMode ? ("):dlg.index("导入到分组")]
    assert "setSectionMap(prev =>" in panel
    assert "watchlistGroupCreate" not in panel


def test_R267_前端_按目标分组集合分批写():
    """batchAdd 一次只能给一批标的挂同一组分组, 而每队去向不同 —— 不分批就串组。"""
    body = _code_lines(_src("components/WatchlistImportDialog.tsx"))
    body = body[body.index("const confirmAddBySection"):]
    assert "buckets" in body and "batchAdd.mutateAsync({ symbols: b.syms, groupIds: b.gids })" in body


def test_R267_前端_一队不导入时它的票不该还能勾():
    """勾了也无处可去 —— 会被当成「加进自选但不进任何组」静默处理。"""
    dlg = _code_lines(_src("components/WatchlistImportDialog.tsx"))
    assert "const orphan = sectionMode" in dlg
    assert "state.eligible && !orphan" in dlg


def test_R267_前端_分队模式下换掉全局的导入到分组():
    """两套目标并排摆着, 用户不知道哪个说了算。"""
    dlg = _code_lines(_src("components/WatchlistImportDialog.tsx"))
    assert "{sectionMode ? (" in dlg
    assert "新建「{name}」" in dlg and "不导入这一队" in dlg


def test_R267_前端_默认同名并入否则新建():
    """第一次导某个题材就建组, 之后再导就并进去 —— 这两个默认覆盖绝大多数情况。"""
    dlg = _code_lines(_src("components/WatchlistImportDialog.tsx"))
    assert "g.name.trim().toLowerCase() === name.trim().toLowerCase()" in dlg
    assert "hit ? hit.id : SECTION_NEW" in dlg


def test_R267_前端_重点票与分队标签都显示():
    dlg = _code_lines(_src("components/WatchlistImportDialog.tsx"))
    assert "c.starred &&" in dlg
    assert "c.groups!.map(g =>" in dlg


def test_R267_AI一键分组已经拆干净():
    """用户: 「ai 不再自动分组, ai 分组的功能按钮也不要了」。"""
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    assert not (root / "backend" / "app" / "services" / "watchlist_ai_group.py").exists()
    for rel in ("pages/Watchlist.tsx", "lib/api.ts"):
        assert "AiGroup" not in _src(rel), f"{rel} 里还留着 AI 分组的接线"
    api = (root / "backend" / "app" / "api" / "watchlist.py").read_text(encoding="utf-8")
    assert "ai-group" not in api and "AiGroupApplyRequest" not in api
