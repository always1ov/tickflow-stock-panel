"""[R486 · fork 增强] 趋势量化 —— 用户给的通达信副图公式, **逐行复刻**。

用户: 「在量化macd上方加个副图, 先还原做出来再说, 名称就叫趋势量化」。

与量化MACD、庄现一样**自成一体**: 需要的通达信函数在下面各抄一份, 不 import 别的指标
模块 —— 哪一个以后调了, 另外两个都不跟着变。

## 原文(去掉了作者的广告注释)与本模块的对照

    超买:3.2,COLORYELLOW;  超卖:0.5,COLORYELLOW;                 → 前端画两条水平线
    最小值:=LLV(LOW,10);  最大值:=HHV(HIGH,25);
    波动线:=EMA((CLOSE-最小值)/(最大值-最小值)*4,4);              → wave
    平均线:EMA(波动线,3);                                       → avg(输出线)
    信息:=平均线>=REF(平均线,1);
    走强:=CLOSE>MA(CLOSE,20)AND CLOSE>MA(CLOSE,5);
    走弱:=CLOSE<MA(CLOSE,10)AND CLOSE<MA(CLOSE,5);
    量:=VOL>MA(VOL,5);
    STICKLINE(平均线>=REF(平均线,1),波动线,REF(波动线,1),2,0),COLORRED;   → stick_up
    STICKLINE(平均线<REF(平均线,1),波动线 ,REF(波动线,1),2,0),COLORGREEN;  → stick_up=False
    D / S / DD / TZ  → 极底 / 升 / 顶 / 下(条件逐字照抄, 见 compute)
    LC … 建仓买点:=IF(CROSS(VAR6,VAR7) AND (VAR6<40),5,0);  → 建仓
    VAR8 … 逃亡:=IF(会员< REF(会员,1) AND 会员>79,会员,0);   → 逃
    见底 / 绝底: 两条 DRAWTEXT 的条件
    VAR11 … 吸筹:VAR17/CDXS+0.53;                               → xichou / xichou_bar

## 与通达信对齐靠的几件事

1. **EMA / SMA 的初值 = 第一个有效值**, 之后按通达信的递推; 输入无效的那一根输出
   无效、不更新状态(与量化MACD 同一个处理)。
2. **无效值传播**: `MA` 不足 N 根无效、`REF` 开头无效; 比较 / 运算碰到无效, 结果无效,
   条件不成立。
3. **除以 0 当无效**, 不除出无穷大(高低价相等、分母那几根全是 0 时)。
   **乘除的先后照原文写的顺序**(R489): 原文 `A/B*100` 就先除后乘, `DMP*100/TR1` 就先乘后除。
   数学上一样, 浮点上差最后一位 —— 而「会员<昨天」「平均线>=昨天」这类比较恰好碰上相等
   (比如会员顶到 100)时, 差的这一位就决定了出不出字。
4. **「吸筹」要从上市第一根算起**: `CDXS:=HHV(VAR17,0)` 是「第一根到今天的最高值」,
   柱子高度 = VAR17 ÷ 它。调用方取全部历史再算; 历史不全时只影响吸筹的高低, 不影响
   它出现在哪天, 其他信号只要最近几百根。
5. 原文几处**恒成立的条件照样写进来**(`88>0`、`REF(L,1)<=688`、`VAR6<40`、
   `IF(CLOSE*1.2,…)`、`IF(LLV(LOW,90),1,0)`): 复刻就是复刻, 不替作者删。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

Num = Optional[float]


# ── 通达信函数, 带无效值(None)传播。**本模块自有** ──────────────
def EMA(x: list[Num], n: int) -> list[Num]:
    """Y = (2X + (N−1)Y') / (N+1), 首个有效值为初值。"""
    out: list[Num] = []
    y: Num = None
    for v in x:
        if v is None:
            out.append(None)
            continue
        y = v if y is None else (2 * v + (n - 1) * y) / (n + 1)
        out.append(y)
    return out


def SMA(x: list[Num], n: int, m: int) -> list[Num]:
    """Y = (M·X + (N−M)·Y') / N, 首个有效值为初值。"""
    out: list[Num] = []
    y: Num = None
    for v in x:
        if v is None:
            out.append(None)
            continue
        y = v if y is None else (m * v + (n - m) * y) / n
        out.append(y)
    return out


def MA(x: list[Num], n: int) -> list[Num]:
    """不足 N 根无效; 窗口内有无效值也无效。"""
    out: list[Num] = []
    for i in range(len(x)):
        if i + 1 < n:
            out.append(None)
            continue
        w = x[i - n + 1:i + 1]
        out.append(None if any(v is None for v in w) else sum(w) / n)  # type: ignore[arg-type]
    return out


def _window(x: list[Num], n: int, pick: Callable[[list[float]], float]) -> list[Num]:
    """N 根内取极值; N=0 为「第一根到当前」。开头不足 N 根时取已有的; 窗口里有无效值则无效。"""
    out: list[Num] = []
    run: Num = None
    for i, v in enumerate(x):
        if n == 0:
            if v is not None:
                run = v if run is None else pick([run, v])
            out.append(run)
            continue
        w = x[max(0, i - n + 1):i + 1]
        out.append(None if any(u is None for u in w) else pick(w))  # type: ignore[arg-type]
    return out


def HHV(x: list[Num], n: int) -> list[Num]:
    return _window(x, n, max)


def LLV(x: list[Num], n: int) -> list[Num]:
    return _window(x, n, min)


def REF(x: list, n: int = 1) -> list:
    return [None] * n + list(x[:-n]) if n else list(x)


def SUM(x: list[Num], n: int) -> list[Num]:
    """N 根之和; 不足 N 根时按已有的加(通达信的 SUM), 窗口里有无效值则无效。"""
    out: list[Num] = []
    for i in range(len(x)):
        w = x[max(0, i - n + 1):i + 1]
        out.append(None if any(v is None for v in w) else sum(w))  # type: ignore[arg-type]
    return out


def CROSS(a: list[Num], b: list[Num]) -> list[bool]:
    """A 上穿 B: 本根 A>B 且上一根 A<=B。任一边无效即不成立。"""
    out = [False]
    for i in range(1, len(a)):
        a0, b0, a1, b1 = a[i - 1], b[i - 1], a[i], b[i]
        out.append(None not in (a0, b0, a1, b1) and a1 > b1 and a0 <= b0)  # type: ignore[operator]
    return out


# ── 逐根运算的小工具: 任一参数无效, 结果无效 ─────────────────────
def _op(f: Callable[..., Num], *cols: list) -> list:
    return [None if any(v is None for v in vs) else f(*vs) for vs in zip(*cols)]


def _div(a: Num, b: Num) -> Num:
    return None if a is None or b is None or b == 0 else a / b


def _mul(a: Num, k: float) -> Num:
    return None if a is None else a * k


def _div_col(a: list[Num], b: list[Num]) -> list[Num]:
    return [_div(x, y) for x, y in zip(a, b)]


def _true(v) -> bool:
    """条件成立: 有效且非 0(通达信里非 0 即真)。"""
    return v is not None and bool(v)


# ── 公式本体 ──────────────────────────────────────────────────
@dataclass
class TrendQuant:
    """逐根的输出。**只有画得出来的东西**; `:=` 的中间量不在这里。"""
    wave: list[Num]        # 波动线(红绿短柱的两端: 今天与昨天)
    avg: list[Num]         # 平均线(输出线)
    stick_up: list[Num]    # 平均线 >= 昨天: 1 红 / 0 绿 / None 不画
    jidi: list[bool]       # 极底
    sheng: list[bool]      # 升
    ding: list[bool]       # 顶
    xia: list[bool]        # 下
    jiancang: list[bool]   # 建仓
    tao: list[bool]        # 逃
    jiandi: list[bool]     # 见底
    juedi: list[bool]      # 绝底
    xichou: list[Num]      # 吸筹(输出线) = VAR17/CDXS + 0.53
    xichou_bar: list[bool] # 吸筹白柱: VAR17 非 0 的那几根


def compute(o: list[Num], h: list[Num], l: list[Num], c: list[Num], v: list[Num]) -> TrendQuant:
    """照原文逐行算。五个序列按日期升序、等长; 缺的值传 None。"""
    n = len(c)
    # 最小值 / 最大值 / 波动线 / 平均线
    lo10, hi25 = LLV(l, 10), HHV(h, 25)
    wave = EMA(_op(lambda cc, a, b: _mul(_div(cc - a, b - a), 4), c, lo10, hi25), 4)
    avg = EMA(wave, 3)
    avg1 = REF(avg, 1)
    info = [None if a is None or b is None else (1 if a >= b else 0) for a, b in zip(avg, avg1)]

    ma5, ma10, ma20 = MA(c, 5), MA(c, 10), MA(c, 20)
    strong = [None if x is None or a is None or b is None else (1 if x > a and x > b else 0)
              for x, a, b in zip(c, ma20, ma5)]
    weak = [None if x is None or a is None or b is None else (1 if x < a and x < b else 0)
            for x, a, b in zip(c, ma10, ma5)]
    vma5 = MA(v, 5)
    vol_up = [None if x is None or a is None else (1 if x > a else 0) for x, a in zip(v, vma5)]

    i1, i2, i3 = REF(info, 1), REF(info, 2), REF(info, 3)
    s1 = REF(strong, 1)

    def eq(x, k) -> bool:
        return x is not None and x == k

    def sum_eq(x, y, k) -> bool:
        return x is not None and y is not None and x + y == k

    turn_up = [eq(a, 1) and eq(b, 0) and sum_eq(x, y, 0) for a, b, x, y in zip(info, i1, i2, i3)]
    turn_dn = [eq(a, 0) and eq(b, 1) and sum_eq(x, y, 2) for a, b, x, y in zip(info, i1, i2, i3)]
    jidi = [t and a is not None and a < 0.5 for t, a in zip(turn_up, avg)]
    sheng = [t and eq(s, 1) and eq(sp, 0) and eq(q, 1)
             for t, s, sp, q in zip(turn_up, strong, s1, vol_up)]
    ding = [t and a is not None and a > 2 for t, a in zip(turn_dn, avg)]
    xia = [t and eq(w, 1) and a is not None and a > 1 for t, w, a in zip(turn_dn, weak, avg)]

    # 建仓: RSI5 + ADX + (RSI5 − WR10) 上穿 0, 三重平滑后金叉
    lc = REF(c, 1)
    up_move = _op(lambda x, y: max(x - y, 0.0), c, lc)
    abs_move = _op(lambda x, y: abs(x - y), c, lc)
    rsi5 = _op(lambda a, b: _mul(_div(a, b), 100), SMA(up_move, 5, 1), SMA(abs_move, 5, 1))
    h1, l1 = REF(h, 1), REF(l, 1)
    tr = _op(lambda hh, ll, cc: max(max(hh - ll, abs(hh - cc)), abs(ll - cc)), h, l, lc)
    tr1 = SUM(tr, 10)
    hd = _op(lambda a, b: a - b, h, h1)
    ld = _op(lambda a, b: a - b, l1, l)
    dmp = SUM(_op(lambda a, b: a if a > 0 and a > b else 0.0, hd, ld), 10)
    dmm = SUM(_op(lambda a, b: b if b > 0 and b > a else 0.0, hd, ld), 10)
    pdi = _div_col(_op(lambda a: a * 100, dmp), tr1)
    mdi = _div_col(_op(lambda a: a * 100, dmm), tr1)
    adx = MA(_op(lambda m, p: _mul(_div(abs(m - p), m + p), 100), mdi, pdi), 5)
    av = _op(lambda a, b: a + b, rsi5, adx)
    hh10, ll10 = HHV(h, 10), LLV(l, 10)
    wr10 = _op(lambda a, cc, b: _div(100 * (a - cc), a - b), hh10, c, ll10)
    zcjl = _op(lambda a, b: a - b, rsi5, wr10)
    best = _op(lambda a, b: a + b, av, zcjl)
    pick = [1.0 if x else 0.0 for x in CROSS(best, [0.0] * n)]
    var5 = SMA(pick, 3, 1)
    var6 = SMA(var5, 3, 1)
    var7 = SMA(var6, 3, 1)
    jiancang = [x and y is not None and y < 40 for x, y in zip(CROSS(var6, var7), var6)]

    # 逃
    c2 = REF(c, 2)
    member = _op(lambda a, b: _mul(_div(a, b), 100),
                 SMA(_op(lambda x, y: max(x - y, 0.0), c, c2), 7, 1),
                 SMA(_op(lambda x, y: abs(x - y), c, c2), 7, 1))
    m1 = REF(member, 1)
    tao = [a is not None and b is not None and a < b and a > 79 and _true(a)
           for a, b in zip(member, m1)]

    # 见底 / 绝底
    o1, c1 = REF(o, 1), REF(c, 1)
    jiandi = [None not in (oo, cc, po, pc, pl) and 88 > 0 and _div(po, pc) is not None
              and po / pc > 1.04 and pl <= 688 and oo > pc and cc < po and oo != 0
              and cc / oo >= 1.01
              for oo, cc, po, pc, pl in zip(o, c, o1, c1, l1)]
    llv20 = LLV(l, 20)
    juedi = [None not in (oo, cc, ll, m) and ll != 0 and cc - oo >= 0 and oo / ll > 1.05 and ll <= m
             for oo, cc, ll, m in zip(o, c, l, llv20)]

    # 主力吸货 / 吸筹
    var11 = REF(l, 1)
    var12 = _op(lambda a, b: _mul(_div(a, b), 100),
                SMA(_op(lambda x, y: abs(x - y), l, var11), 3, 1),
                SMA(_op(lambda x, y: max(x - y, 0.0), l, var11), 3, 1))
    var13 = EMA(_op(lambda cc, x: x * 10 if cc * 1.2 else x / 10, c, var12), 3)
    var14 = LLV(l, 38)
    var15 = HHV(var13, 38)
    var16 = [None if x is None else (1.0 if x else 0.0) for x in LLV(l, 90)]
    raw17 = EMA(_op(lambda ll, a, b, cc: (b + cc * 2) / 2 if ll <= a else 0.0,
                    l, var14, var13, var15), 3)
    var17 = _op(lambda a, b: a / 618 * b, raw17, var16)
    cdxs = _op(lambda a: a / 2.6, HHV(var17, 0))
    xichou = [None if a is None or b is None else (_div(a, b) + 0.53 if _div(a, b) is not None else None)
              for a, b in zip(var17, cdxs)]
    xichou_bar = [_true(a) and x is not None for a, x in zip(var17, xichou)]

    stick_up = [None if a is None or b is None else (1.0 if a >= b else 0.0) for a, b in zip(avg, avg1)]
    return TrendQuant(wave=wave, avg=avg, stick_up=stick_up, jidi=jidi, sheng=sheng, ding=ding,
                      xia=xia, jiancang=jiancang, tao=tao, jiandi=jiandi, juedi=juedi,
                      xichou=xichou, xichou_bar=xichou_bar)
