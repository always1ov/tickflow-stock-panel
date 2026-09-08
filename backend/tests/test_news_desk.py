"""[fork 增强] R180 消息面: 逐条凝练 / 一大段总的 / 注入决策。

这个模块唯一危险的地方是**注入** —— 它会影响每一次 AI 决策。所以测试的重点
不是"能不能凝练", 而是那几条边界:

  · 规则层一个字都不能进(把握分/出场线/六态/通道必须保持可复现);
  · 过期的消息面宁可不注入;
  · 关掉开关就完全回到改造前;
  · 附件路径这类内部信息不许随 payload 泄出去。
"""
from datetime import datetime, timedelta

import pytest

from app.services import news_desk as nd


def _note(**kw):
    base = {"id": "n1", "content": "原文", "digest": "要点", "status": "",
            "pinned": False, "updated_at": "2026-09-01T10:00:00"}
    return {**base, **kw}


# ---------- 注入边界: 只进 AI 层 ----------

def test_注入点只在AI决策路径不在规则层():
    """规则层进了这段话就再也不能自证 —— 这是整个改造最重要的一条。"""
    import pathlib
    import re

    root = pathlib.Path(__file__).resolve().parents[1] / "app"
    hits = set()
    for f in root.rglob("*.py"):
        if "__pycache__" in str(f):
            continue
        if re.search(r"news_desk\.context_for_ai\(\)", f.read_text(encoding="utf-8")):
            hits.add(f.relative_to(root).as_posix())

    allowed = {"api/today.py", "services/stock_signal.py", "services/paper_trader_run.py"}
    assert hits <= allowed, f"消息面注入到了不该去的地方: {hits - allowed}"

    # 规则层文件里绝不能出现
    forbidden = ["services/opportunity_score.py", "services/position_exit.py",
                 "indicators/keltner.py", "indicators/livermore.py",
                 "services/watchlist_urgency.py", "services/score_ledger.py"]
    for f in forbidden:
        assert f not in hits, f"{f} 是规则层, 不许吃消息面"


def test_关掉开关就完全不注入(monkeypatch, tmp_path):
    monkeypatch.setattr(nd, "_path", lambda: tmp_path / "s.json")
    nd._write({"text": "有内容", "as_of": nd._now(), "item_count": 3})
    assert nd.context_for_ai() != "", "先确认开着时是有内容的"

    monkeypatch.setattr(nd, "_inject_enabled", lambda: False)
    assert nd.context_for_ai() == "", "关掉后必须完全回到改造前的行为"


def test_过期的消息面不注入(monkeypatch, tmp_path):
    """与其拿上个月的消息面影响今天的判断, 不如没有。"""
    monkeypatch.setattr(nd, "_path", lambda: tmp_path / "s.json")
    old = (datetime.now() - timedelta(days=nd.STALE_DAYS + 1)).isoformat(timespec="seconds")
    nd._write({"text": "过期内容", "as_of": old, "item_count": 3})
    assert nd.context_for_ai() == ""


def test_刚生成的会注入(monkeypatch, tmp_path):
    monkeypatch.setattr(nd, "_path", lambda: tmp_path / "s.json")
    nd._write({"text": "新鲜内容", "as_of": nd._now(), "item_count": 5})
    got = nd.context_for_ai()
    assert "新鲜内容" in got
    assert "5 条" in got, "要告诉下游这段是基于多少条来的"


def test_注入文本自带时效与优先级说明(monkeypatch, tmp_path):
    """下游是 AI, 它看不到我们这边的判断 —— 只能靠这段话本身知道分寸。"""
    monkeypatch.setattr(nd, "_path", lambda: tmp_path / "s.json")
    nd._write({"text": "正文", "as_of": nd._now(), "item_count": 1})
    got = nd.context_for_ai()
    assert "距今" in got, "必须说清多旧"
    assert "未经核实" in got
    assert "以价格与规则为准" in got, "冲突时谁说了算, 必须写死在这段话里"


def test_没有总结时返回空串而不是报错(monkeypatch, tmp_path):
    monkeypatch.setattr(nd, "_path", lambda: tmp_path / "nothing.json")
    assert nd.context_for_ai() == ""


# ---------- 综合的输入: 白名单 ----------

def test_附件路径不进综合():
    """喂给 AI 的只该是要点, 内部存储路径没有任何理由出现在那里。"""
    pl = nd.build_payload([_note(attachment={"path": "user_data/news_desk/x.png"})])
    assert "news_desk" not in repr(pl)
    assert "x.png" not in repr(pl)


def test_不成立的条目照样进综合并带着状态():
    """标了"不成立"的必须让 AI 看见 —— 留着一条已经错了的判断比没有更糟。"""
    pl = nd.build_payload([_note(status="rejected")])
    assert pl[0]["状态"] == "不成立"


def test_没有digest时退回用正文():
    pl = nd.build_payload([_note(digest="", content="只有原文")])
    assert pl[0]["要点"] == "只有原文"


def test_空条目不占位置():
    pl = nd.build_payload([_note(digest="", content=""), _note(id="n2")])
    assert len(pl) == 1


def test_置顶的优先进综合():
    notes = [_note(id=f"n{i}") for i in range(nd.MAX_ITEMS_FOR_SUMMARY + 5)]
    notes[-1] = _note(id="pinned", pinned=True, digest="置顶要点")
    pl = nd.build_payload(notes)
    assert len(pl) == nd.MAX_ITEMS_FOR_SUMMARY
    assert pl[0]["要点"] == "置顶要点", "置顶的不该被数量上限挤掉"


def test_综合有条数上限():
    notes = [_note(id=f"n{i}") for i in range(500)]
    assert len(nd.build_payload(notes)) == nd.MAX_ITEMS_FOR_SUMMARY


def test_没有可综合内容时明确报错(monkeypatch):
    """配了 AI 但没内容 —— 要说"没内容", 不是含糊地失败。
    (没配 AI 时先报"未配置 AI" 是对的, 那是更根本的问题, 所以这里先 mock 掉。)"""
    import asyncio
    monkeypatch.setattr("app.services.ai_provider.ai_configured", lambda: True)
    with pytest.raises(RuntimeError, match="可综合"):
        asyncio.run(nd.synthesize([]))


# ---------- 提示词约束 ----------

def test_逐条凝练禁止AI自己发挥():
    assert "只写素材里有的东西" in nd._ITEM_SYSTEM
    assert "不要推测" in nd._ITEM_SYSTEM


def test_综合禁止补充外部信息():
    assert "只用给你的这些要点" in nd._SUMMARY_SYSTEM
    assert "不许补充外部信息" in nd._SUMMARY_SYSTEM


# ---------- [R180 修订] 只保存凝练, 不保存图片 ----------

def test_凝练成功后图片被删掉只留要点(tmp_path, monkeypatch):
    """用户口径: 只保存凝练, 不保存图片。盘上不该长期堆附件。"""
    from app.services import usage_notes as un
    monkeypatch.setattr(un, "_path", lambda: tmp_path / "notes.json")

    img = tmp_path / "user_data" / "news_desk" / "a.png"
    img.parent.mkdir(parents=True, exist_ok=True)
    img.write_bytes(b"fake-png")

    class _S:
        data_dir = tmp_path
    monkeypatch.setattr(un, "settings", _S)

    note = un.create_note("研报截图", kind="image",
                          attachment={"path": "user_data/news_desk/a.png",
                                      "name": "a.png", "size": 8})
    got = un.set_digest(note["id"], "要点: 某某上调评级")

    assert not img.exists(), "凝练成功后图片必须删掉"
    assert got["digest"].startswith("要点"), "要点要留下"
    assert "path" not in (got["attachment"] or {}), "路径要去掉, 不能指向已删的文件"
    assert (got["attachment"] or {}).get("name") == "a.png", "文件名留着, 好知道这条从哪来"


def test_凝练失败时图片不删(tmp_path, monkeypatch):
    """一张图删了就再也凝练不了 —— 没拿到要点之前绝不能删。"""
    from app.services import usage_notes as un
    monkeypatch.setattr(un, "_path", lambda: tmp_path / "notes.json")
    img = tmp_path / "user_data" / "news_desk" / "b.png"
    img.parent.mkdir(parents=True, exist_ok=True)
    img.write_bytes(b"x")

    class _S:
        data_dir = tmp_path
    monkeypatch.setattr(un, "settings", _S)

    un.create_note("图", kind="image",
                   attachment={"path": "user_data/news_desk/b.png", "name": "b.png", "size": 1})
    # 没调 set_digest —— 模拟凝练失败那条路径
    assert img.exists(), "凝练失败时文件必须留着, 用户要能重试"


def test_文本文件的原文并进正文(tmp_path, monkeypatch):
    """用户口径: 文字允许保存原文。"""
    from app.services import usage_notes as un
    monkeypatch.setattr(un, "_path", lambda: tmp_path / "notes.json")

    class _S:
        data_dir = tmp_path
    monkeypatch.setattr(un, "settings", _S)

    note = un.create_note("这是调研纪要", kind="file",
                          attachment={"path": "user_data/news_desk/c.txt",
                                      "name": "c.txt", "size": 5})
    got = un.set_digest(note["id"], "要点", raw_text="原文第一行\n原文第二行")
    assert "这是调研纪要" in got["content"], "用户自己那句备注不能被覆盖"
    assert "原文第一行" in got["content"], "文本原文要保留"


def test_没有原文时正文不变(tmp_path, monkeypatch):
    from app.services import usage_notes as un
    monkeypatch.setattr(un, "_path", lambda: tmp_path / "notes.json")

    class _S:
        data_dir = tmp_path
    monkeypatch.setattr(un, "settings", _S)

    note = un.create_note("纯文字消息")
    got = un.set_digest(note["id"], "要点")
    assert got["content"] == "纯文字消息"
