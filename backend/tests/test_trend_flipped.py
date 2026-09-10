"""[fork 增强] R286 「今天是不是转折」进决策台的走势列。

用户: 「个股分析的走势这一列还要显示今天是不是转折, 我在趋势状态那部分发现了
这个参数」—— 复盘弹窗的逐日表上, 状态变了的那一天挂着一个「← 转折」标记, 而
决策台的走势列只写「上涨趋势 已1天」, 转折这件事得读的人自己从天数里推。

改动只有一句: 趋势载荷把 `compute()` 逐日给的 `flipped` 原样带出来。**不新增
任何判定** —— 这里全部三条测试合起来说的就是这件事:

  ① 载荷真的带上了这个读数, 并且它跟着最后一天走;
  ② 它与 `duration == 1` 恒等 —— 所以决策台不许自己再推一遍;
  ③ 恒等**不是**"随便哪条都行": 谁是源头有区别, 见 `test_R286_读的是最后一天`。
"""
import pytest

from app.services.livermore_service import _trend_payload

THR = 0.06

# 一条**精心构造**的路径: 走遍多头三态与空头三态, 中间有多次真实翻转。
# 与 `test_livermore_flip.SERIES` 同样的构造法, 后半段接一段下跌把空头侧走完。
PATH = [10, 10.5, 11, 11.6, 12.2, 12.8,   # 0-5   多头侧, 不断新高
        12.0, 11.6, 11.4,                  # 6-8   回撤(-10.9%) → NREA
        11.8,                              # 9     反弹但幅度不够
        12.3, 12.6,                        # 10-11 站上 lo×1.06 → NR
        13.0, 13.4,                        # 12-13 破前高 12.80 → UT
        13.1, 12.9, 13.2,                  # 14-16 UT 内震荡, 未创新高
        13.6,                              # 17    再创新高
        12.7, 12.0, 11.5,                  # 18-20 跌破阈值 → NREA
        10.8, 10.2, 9.6,                   # 21-23 破下关键点 → DT
        10.3, 10.6,                        # 24-25 反弹站上 lo×1.06 → NR/SR
        10.0, 9.4]                         # 26-27 再转弱


def _payload(n: int) -> dict:
    """取前 n 天当作"今天"。dates 用 d00.. 保证与下标一一对应。"""
    closes = PATH[:n]
    dates = [f"d{i:02d}" for i in range(n)]
    return _trend_payload(closes, dates, THR, "default")


def test_R286_载荷带上转折读数():
    """正面: 这个字段存在, 而且是个布尔值 —— 不是 None、不是缺席。

    缺席也能让前端那个 `trend?.flipped &&` 安静地永远不显示, 那正是这个仓库
    反复吃亏的那种"看着接上了、其实一直是假"的接线。
    """
    p = _payload(len(PATH))
    assert "flipped" in p, "趋势载荷没带 flipped —— 走势列的转折标记会永远不亮"
    assert isinstance(p["flipped"], bool), f"flipped 不是布尔值: {p['flipped']!r}"


def test_R286_读的是最后一天():
    """它讲的是**今天**转没转, 不是"这段路上转过没有"。

    具名场景, 两个方向各钉一个:
      · 第 10 天(下标 9→10 那一步)由 NREA 转 NR —— 那天就是转折日;
      · 第 11 天还在 NR 里走 —— 同一段路, 只是"今天"往后挪了一天, 就不该再亮。
    """
    flip_day = _payload(11)
    assert flip_day["duration"] == 1, "场景没搭对: 第 11 天(下标 10)应当是新状态第一天"
    assert flip_day["flipped"] is True, "转折当天没认出来"

    next_day = _payload(12)
    assert next_day["state"] == flip_day["state"], "场景没搭对: 第 12 天应当还在同一个状态"
    assert next_day["flipped"] is False, (
        "转折标记跟着整段路走了 —— 它必须只认最后一天, 否则整段状态期天天亮"
    )


def test_R286_转折与已1天恒等():
    """`flipped` ≡ `duration == 1`。**系统性地走完整条路**, 不抽样。

    这条测试是那句"决策台不许自己再推一遍"的依据, 也是
    `watchlist_urgency` 那边继续用 `duration == 1` 的依据 —— 两个式子说的是
    同一件事, 所以哪一处用哪一个都不会各说各话。

    恒等成立的原因: `duration` 是尾部连续同态段的长度, 等于 1 就意味着前一天
    的状态与今天不同; 而 `flipped` 就是 `prev != state`。两者是同一个比较。
    """
    seen = {True: 0, False: 0}
    for n in range(2, len(PATH) + 1):
        p = _payload(n)
        assert p["flipped"] == (p["duration"] == 1), (
            f"前 {n} 天: flipped={p['flipped']} 而 duration={p['duration']} —— 两个读数打架了"
        )
        seen[p["flipped"]] += 1
    # 两侧都要真的被走到, 否则这条恒等是被"全是 False"喂饱的
    assert seen[True] >= 3, f"这条路上只走到 {seen[True]} 个转折日, 样本不足以说明问题"
    assert seen[False] >= 3, f"这条路上只走到 {seen[False]} 个非转折日"


def test_R286_盘中口径不会把转折抹掉():
    """收盘价覆盖层(`_overlay_closing_prices`)只改**价位**, 不许碰状态类读数。

    盘中那一层的分工是 R30 定的: 状态/天数可以是盘中临时口径, 价位必须收盘口径。
    `flipped` 与 `duration`/`state` 同族, 所以它不在被覆盖的名单里 —— 一旦哪天
    有人把它加进 `_CLOSING_PRICE_KEYS`, 盘中转折就会被前一日的读数顶掉。
    """
    from app.services.livermore_service import _CLOSING_PRICE_KEYS
    assert "flipped" not in _CLOSING_PRICE_KEYS, (
        "flipped 被当成价位去做收盘覆盖了 —— 它是状态读数, 该跟着 duration 走"
    )


@pytest.mark.parametrize("n", [2, 11, len(PATH)])
def test_R286_短窗口也算得出来(n: int):
    """窗口短到只有两天也不能抛异常 —— 载荷是决策台整张表的地基。"""
    assert isinstance(_payload(n)["flipped"], bool)
