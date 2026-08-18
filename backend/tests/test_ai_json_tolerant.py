"""[fork 增强] R22 跨厂家 JSON 容错解析 + 信号词中文兼容。"""
from app.services.ai_json import extract_json_object
from app.services.stock_signal import _parse_signal


# ---------- extract_json_object ----------

def test_clean_json():
    assert extract_json_object('{"a": 1}') == {"a": 1}


def test_markdown_fenced():
    assert extract_json_object('```json\n{"a": 1}\n```') == {"a": 1}


def test_surrounded_by_prose():
    text = '好的,以下是我的分析结果:\n{"signal": "buy"}\n以上仅供参考。'
    assert extract_json_object(text) == {"signal": "buy"}


def test_truncated_object_recovered():
    """被 max_tokens 掐断: 补右括号抢救。"""
    obj = extract_json_object('{"signal": "buy", "confidence": 80, "reason": "放量突破')
    assert obj is not None
    assert obj["signal"] == "buy"


def test_truncated_array_recovered():
    obj = extract_json_object('{"picks": [{"symbol": "600487.SH"}')
    assert obj is not None


def test_garbage_returns_none():
    assert extract_json_object("今天天气不错") is None
    assert extract_json_object("") is None
    assert extract_json_object(None) is None


def test_think_block_stripped_before_parsing():
    """思考型模型: <think>推理段</think> 后才是 JSON 正文 → 剥掉推理段再解析。"""
    text = ('<think>Let me analyze. The trend is {strong} maybe...</think>\n'
            '{"signal": "buy", "confidence": 70, "reason": "放量突破"}')
    assert extract_json_object(text) == {"signal": "buy", "confidence": 70, "reason": "放量突破"}


def test_unclosed_think_block_returns_none():
    """输出在思考段内就被掐断(没有正文)→ None, 由调用方报错并提示。"""
    text = "<think>Let me analyze this data carefully. **标的**: 002463.SZ (沪电股份"
    assert extract_json_object(text) is None


def test_think_block_with_braces_does_not_confuse():
    """推理段里出现花括号也不能被误抽成结果。"""
    text = '<think>maybe {"signal": "sell"}? no wait...</think>{"signal": "hold", "confidence": 55, "reason": "等"}'
    assert extract_json_object(text)["signal"] == "hold"


# ---------- 信号解析(中文信号词 + 容错) ----------

def test_chinese_signal_word_accepted():
    """部分厂家模型用中文回信号词 → 映射回标准值, 不再'无法解析'。"""
    parsed = _parse_signal('{"signal": "买入", "confidence": 75, "reason": "放量突破"}')
    assert parsed is not None
    assert parsed["signal"] == "buy"
    assert parsed["confidence"] == 75


def test_fenced_signal_accepted():
    parsed = _parse_signal('```json\n{"signal": "watch", "confidence": 50, "reason": "等确认"}\n```')
    assert parsed is not None
    assert parsed["signal"] == "watch"


def test_invalid_signal_word_rejected():
    assert _parse_signal('{"signal": "梭哈", "confidence": 99, "reason": "冲"}') is None
