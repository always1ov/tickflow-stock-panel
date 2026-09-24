"""[R485 · fork 增强] 庄现 —— 用户通达信副图「主力捉妖」里的一个信号, **逐行复刻、冻结**。

用户: 「现在想办法移植到量化macd里面, 当作辅助指标不在动了, 就算我以后微调量化macd
也不动这些了」。所以这个模块:

  · **不 import `quant_macd`**。需要的几个通达信函数在下面各抄一份 —— 那边以后怎么改,
    这里一个字节都不跟着变;
  · 输出被 `tests/test_zhuang_xian.py` 钉死(固定输入 → 固定的出现位置)。真要改,
    得先改那份基线, 让改动是有意的、看得见的;
  · **只是标记**: 不进把握分、不推送、不碰六态, 与「注记·不计分」同一个性质。

同一个副图里还有「拐点」「确认」两个信号, 用户选了**不移植**: 它们要用通达信的获利盘
比例 `WINNER`(通达信自己的筹码模型)和实时函数 `DYNAINFO(6)`(历史上每一根都拿「今天」
的最低价去比, 是未来函数), 在系统里做不到与通达信一致。庄现只用 K 线价格, 能逐位对上。

## 原文(一字未改)与本模块的对照

    RSV2:=(C-LLV(LOW,9))/(HHV(H,9)-LLV(LOW,9))*100;      → rsv2
    K:=SMA(RSV2,2,1);                                     → k
    D:=SMA(K,2,1);J:=3*K-2*D;                             → d, j
    J1:=REVERSE(J);                                       → 取负(REVERSE 就是 -X)
    AA1:=REF(MA(C,1),10)>REF(MA(C,60),10);                → MA(C,1) 就是 C 本身
    突破点:CROSS(J,J1) AND AA1 ,NODRAW;                   → compute() 的返回值
    STICKLINE(突破点 AND YXRQ, ...);  DRAWTEXT(..., '庄现！')  → 前端画狗头

`YXRQ` 是原文的有效期开关(过了 2026-05-10 就不画), 用户已改成永久, 这里恒为真, 不带。

`CROSS(J, -J)` 等价于「J 从 ≤0 变成 >0」, 这里照原文写成 CROSS, 不化简 ——
逐行对照时一眼能对上, 比省一行更要紧。
"""
from __future__ import annotations

from typing import Optional

Num = Optional[float]


# ── 通达信函数, 带无效值(None)传播。**本模块自有, 不与 quant_macd 共用** ──────
def SMA(x: list[Num], n: int, m: int) -> list[Num]:
    """通达信 SMA(X,N,M): 首个有效值为初值, 之后 Y = (M·X + (N−M)·Y') / N。

    输入无效的那一根输出无效、不更新状态(与 quant_macd.EMA 同一个处理)。
    """
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
    """通达信 MA: 不足 N 根无效; 窗口内有无效值也无效。"""
    out: list[Num] = []
    for i in range(len(x)):
        if i + 1 < n:
            out.append(None)
            continue
        w = x[i - n + 1:i + 1]
        out.append(None if any(v is None for v in w) else sum(w) / n)  # type: ignore[arg-type]
    return out


def HHV(x: list[Num], n: int) -> list[Num]:
    """N 根内最高; 开头不足 N 根时取已有的那几根。窗口内有无效值则无效。"""
    out: list[Num] = []
    for i in range(len(x)):
        w = x[max(0, i - n + 1):i + 1]
        out.append(None if any(v is None for v in w) else max(w))  # type: ignore[type-var]
    return out


def LLV(x: list[Num], n: int) -> list[Num]:
    """N 根内最低, 口径同 HHV。"""
    out: list[Num] = []
    for i in range(len(x)):
        w = x[max(0, i - n + 1):i + 1]
        out.append(None if any(v is None for v in w) else min(w))  # type: ignore[type-var]
    return out


def REF(x: list[Num], n: int = 1) -> list[Num]:
    return [None] * n + x[:-n] if n else list(x)


def CROSS(a: list[Num], b: list[Num]) -> list[bool]:
    """A 上穿 B: 本根 A>B 且上一根 A<=B。任一边无效即不成立。"""
    out = [False]
    for i in range(1, len(a)):
        a0, b0, a1, b1 = a[i - 1], b[i - 1], a[i], b[i]
        out.append(None not in (a0, b0, a1, b1) and a1 > b1 and a0 <= b0)  # type: ignore[operator]
    return out


# ── 公式本体 ──────────────────────────────────────────────────
def compute(high: list[Num], low: list[Num], close: list[Num]) -> list[bool]:
    """逐根返回「这一根出不出庄现」。三个序列按日期升序、等长; 缺的值传 None。

    RSV2 的分母是 9 根的高低差 —— 连续 9 根一字(高低差为 0)时这一根无效, 不出信号,
    而不是除出一个无穷大。
    """
    llv9, hhv9 = LLV(low, 9), HHV(high, 9)
    rsv2: list[Num] = []
    for c, lo, hi in zip(close, llv9, hhv9):
        if c is None or lo is None or hi is None or hi == lo:
            rsv2.append(None)
        else:
            rsv2.append((c - lo) / (hi - lo) * 100)
    k = SMA(rsv2, 2, 1)
    d = SMA(k, 2, 1)
    j: list[Num] = [None if a is None or b is None else 3 * a - 2 * b for a, b in zip(k, d)]
    j1: list[Num] = [None if v is None else -v for v in j]          # REVERSE(J)
    ma1_ref, ma60_ref = REF(list(close), 10), REF(MA(list(close), 60), 10)
    aa1 = [a is not None and b is not None and a > b for a, b in zip(ma1_ref, ma60_ref)]
    return [x and y for x, y in zip(CROSS(j, j1), aa1)]
