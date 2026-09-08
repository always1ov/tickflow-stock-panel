"""[fork 增强] R187 红绿节拍。

要守的**只有一条, 但它是整个模块存在的理由**:

    「反复进多头又跌出」同时对应蓄势与反复失败两种相反形态, 而它们的**次数
    一模一样**。只数次数会把「同一个位置撞五次没过去」排到最前面 —— 恰好是
    最该躲开的那种。所以低点不抬高必须直接判 FAILING, 不管循环了几次。
"""
from app.services import trend_rhythm as tr


def _steps(spec: list[tuple[str, list[float]]]) -> list[dict]:
    """[(状态, [收盘...]), ...] → steps。UT/NR/SR 是红, 其余是绿。"""
    out, i = [], 0
    for state, closes in spec:
        for c in closes:
            out.append({"i": i, "date": f"d{i:03d}", "state": state, "close": c})
            i += 1
    return out


def _cycle(red: list[float], green: list[float]):
    return [("UT", red), ("NREA", green)]


# ---------- 核心: 次数相同, 形状决定一切 ----------

def test_低点抬高是蓄势():
    steps = _steps(sum([
        _cycle([10, 12, 13, 14], [13, 12, 11, 11]),      # 低点 11
        _cycle([12, 14, 15, 16], [15, 14, 13, 13]),      # 低点 13 ↑
        _cycle([14, 16, 18, 19], [18, 17, 16, 16]),      # 低点 16 ↑
    ], []))
    got = tr.assess(steps)
    assert got["level"] == tr.BUILDING, got
    assert got["low_rising"] is True


def test_低点不抬高就是反复失败_哪怕循环更多次():
    """这一条是整个模块的理由 —— 只数次数的话它会拿到最高分。"""
    steps = _steps(sum([
        _cycle([10, 12, 13, 14], [13, 12, 11, 11]),
        _cycle([12, 13, 14, 14], [13, 12, 10, 10]),      # 低点 10 ↓
        _cycle([12, 13, 14, 14], [12, 11, 9, 9]),        # 低点 9  ↓
        _cycle([11, 12, 13, 13], [11, 10, 8, 8]),        # 低点 8  ↓ 四轮!
    ], []))
    got = tr.assess(steps)
    assert got["level"] == tr.FAILING, got
    assert got["cycles"] == 4, "次数比上面那个蓄势的还多"
    assert "下台阶" in got["reason"]


def test_撞同一个位置不算蓄势():
    """高点走平、低点走平 —— 典型的"撞五次没过去"。"""
    steps = _steps(sum([_cycle([10, 14, 14], [13, 11, 11]) for _ in range(4)], []))
    got = tr.assess(steps)
    assert got["level"] != tr.BUILDING, got


# ---------- 「力量变强」的三个表达 ----------

def test_红段越来越长算增强():
    steps = _steps([
        ("UT", [10, 11, 12]), ("NREA", [11, 10, 10, 10, 10, 10]),
        ("UT", [11, 12, 13, 14, 14]), ("NREA", [13, 12, 11, 11]),
        ("UT", [12, 13, 14, 15, 16, 17, 17]), ("NREA", [16, 15, 14, 14]),
    ])
    got = tr.assess(steps)
    assert got["red_share_rising"] is True
    assert got["level"] == tr.BUILDING
    assert "红段越来越长" in got["reason"]


def test_回撤越来越浅算增强():
    steps = _steps(sum([
        _cycle([10, 15, 15], [13, 10, 10]),        # 跌 33%
        _cycle([12, 16, 16], [15, 13, 13]),        # 跌 19%
        _cycle([14, 17, 17], [16, 15, 15]),        # 跌 12%
    ], []))
    got = tr.assess(steps)
    assert got["dip_shallower"] is True
    assert got["level"] == tr.BUILDING


def test_低点抬高但没有任何增强迹象只算震荡():
    """低点微微抬高、其余全平 —— 说不出方向就别说。"""
    steps = _steps(sum([
        _cycle([10, 14, 14], [12, 11.0, 11.0]),
        _cycle([12, 14, 14], [12, 11.1, 11.1]),
    ], []))
    got = tr.assess(steps)
    assert got["level"] in (tr.CHOPPY, tr.BUILDING)
    assert got["low_rising"] is True


# ---------- 循环的切分 ----------

def test_循环不够不下结论():
    got = tr.assess(_steps(_cycle([10, 12, 13], [12, 11, 11])))
    assert got["level"] == tr.NONE
    assert got["cycles"] == 1
    assert "谈不上" in got["reason"]


def test_过短的穿越并进前一段不灌水循环数():
    """两天的噪声穿越会把一次正常波动拆成两个"循环" —— 次数就假了。"""
    steps = _steps([
        ("UT", [10, 11, 12, 13, 14]),
        ("NREA", [13, 12]),            # 只有 2 天, 短于 MIN_RUN_DAYS
        ("UT", [13, 14, 15, 16]),
        ("NREA", [15, 14, 13, 13]),
    ])
    got = tr.assess(steps)
    assert got["cycles"] <= 1, f"噪声穿越不该数成一个完整循环, 实际 {got['cycles']}"


def test_空输入不崩():
    got = tr.assess(None)
    assert got["level"] == tr.NONE
    assert got["cycles"] == 0


def test_全程红没有循环():
    got = tr.assess(_steps([("UT", [10 + i for i in range(30)])]))
    assert got["cycles"] == 0
    assert got["level"] == tr.NONE


def test_全程绿没有循环():
    got = tr.assess(_steps([("DT", [30 - i for i in range(25)])]))
    assert got["cycles"] == 0


# ---------- 输出契约 ----------

def test_不给连续分数():
    """给个分数就会有人想把它加进把握分, 而那三个权重本身还在等台账验证。"""
    got = tr.assess(_steps(sum([_cycle([10, 12, 13], [12, 11, 11])] * 3, [])))
    assert "score" not in got and "points" not in got
    assert got["level"] in tr.LEVELS


def test_每个档位都有一句人能看懂的理由():
    for steps in ([], _steps(sum([_cycle([10, 14, 14], [13, 11, 11])] * 3, []))):
        got = tr.assess(steps)
        assert got["reason"], f"{got['level']} 没有给理由"


def test_不依赖任何AI():
    import inspect
    src = inspect.getsource(tr)
    for bad in ("ai_provider", "generate_ai_text", "news_desk"):
        assert bad not in src, f"这是规则层, 不许碰 {bad}"


# ---------- 磨底磨了多久 ----------
#
# 用户的原话: 「其实我是想知道一个票磨底磨了多久」。上面那套算的是**磨得好不好**,
# 这一组算的是**磨了多久** —— 两个凑一起才完整。

def _closes(vals: list[float]) -> list[dict]:
    return [{"date": f"d{i:03d}", "close": v, "state": "UT"} for i, v in enumerate(vals)]


def test_箱体之前的高位不算进磨底():
    """从 50 块跌下来在 10~13 之间磨 —— 磨底时长不该把上面那段算进去。"""
    got = tr.basing(_closes([50] * 10 + [11, 12, 13, 11, 10, 12] * 5))
    assert got["days"] == 30, got
    assert got["high"] <= 13 and got["low"] >= 10


def test_磨底时长与箱体上下沿一起给出():
    """上下沿就是突破价与破位价 —— 只给一个天数, 用户还得自己去图上量。"""
    got = tr.basing(_closes([10, 11, 12, 11, 10] * 8))
    assert got["days"] == 40
    assert got["low"] == 10.0 and got["high"] == 12.0
    assert got["range_pct"] == 0.2
    assert got["since"] == "d000"


def test_单边上涨没有箱体():
    got = tr.basing(_closes([10 * (1.03 ** i) for i in range(60)]))
    assert got["days"] < 20, f"一路涨不该算磨底, 实际 {got['days']} 天"
    assert got["is_basing"] is False


def test_横得太短不算磨底但仍给出真实天数():
    """显示「横了 12 天(还不算磨底)」比显示一个含糊的 0 有用。"""
    got = tr.basing(_closes([50] * 30 + [10, 11, 10, 11] * 3))
    assert got["days"] == 12
    assert got["is_basing"] is False


def test_够长才算磨底():
    got = tr.basing(_closes([10, 11, 10.5, 11.5] * 10))
    assert got["days"] >= tr.MIN_BASING_DAYS
    assert got["is_basing"] is True


def test_磨底_空输入不崩():
    got = tr.basing(None)
    assert got["days"] == 0 and got["is_basing"] is False


def test_assess里同时给出磨了多久和磨得好不好():
    """这两个数必须一起出现 —— 「磨了 87 天」不说好坏, 「蓄势」不说久暂。"""
    steps = _steps(sum([_cycle([10, 12, 13], [12, 11, 11])] * 3, []))
    got = tr.assess(steps)
    assert "basing" in got and "days" in got["basing"]
    assert got["level"] in tr.LEVELS
