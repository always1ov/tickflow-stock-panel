"""[fork 增强] R22 AI 导读·优选输出解析: 永远给出可展示的结果。"""
from app.api.today import parse_ai_brief_response

VALID = {"600487.SH", "603083.SH"}


def test_clean_json():
    text = '{"brief": "盘前保持谨慎。", "picks": [{"symbol": "600487.SH", "reason": "放量突破"}]}'
    out = parse_ai_brief_response(text, VALID)
    assert out["brief"] == "盘前保持谨慎。"
    assert out["picks"] == [{"symbol": "600487.SH", "reason": "放量突破"}]


def test_fenced_json():
    text = '```json\n{"brief": "看多。", "picks": []}\n```'
    out = parse_ai_brief_response(text, VALID)
    assert out["brief"] == "看多。"
    assert out["picks"] == []


def test_truncated_json_recovers_brief():
    """被 max_tokens 掐断的 JSON: 至少要把 brief 抢救出来, 不能'点了没反应'。"""
    text = '{"brief": "大盘防守,今天没有值得出手的", "picks": [{"symbol": "600487.SH", "reason": "放量'
    out = parse_ai_brief_response(text, VALID)
    assert "error" not in out
    assert "大盘防守" in out["brief"]


def test_plain_text_falls_back_to_brief():
    """模型完全没按 JSON 格式输出 → 原文当导读正文返回。"""
    text = "今天大盘偏弱,建议保持谨慎,亨通光电可以继续观察。"
    out = parse_ai_brief_response(text, VALID)
    assert out["brief"] == text
    assert out["picks"] == []


def test_invalid_symbols_are_dropped():
    text = '{"brief": "x", "picks": [{"symbol": "999999.SZ", "reason": "编的"}, {"symbol": "603083.SH", "reason": "真的"}]}'
    out = parse_ai_brief_response(text, VALID)
    assert [p["symbol"] for p in out["picks"]] == ["603083.SH"]


def test_empty_output_returns_explicit_error():
    out = parse_ai_brief_response("", VALID)
    assert "error" in out and "空内容" in out["error"]


def test_none_output_returns_explicit_error():
    assert "error" in parse_ai_brief_response(None, VALID)
