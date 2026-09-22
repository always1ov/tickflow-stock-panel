"""[R415 · fork 增强] 量化MACD —— 用户自己的通达信副图公式, **逐行复刻**。

用户: 「想要用这个指标替换关键价位下面的成交量, 不再显示成交量, 换成我的量化MACD」
     「必须完美复刻」「我这个是量化指标, 和仓库系统里面的不一样的」。

所以这里**不读仓库任何现成的 MACD 列**(`pipeline.py` 的 macd_dif 等), 自己从
收盘价、成交量一行行算 —— 它是一个独立的指标, 只是开头两行碰巧和标准 MACD 同形。

## 原文(一字未改)与本模块的对照

    DIFF:=( EMA(CLOSE,12) - EMA(CLOSE,26));                  → diff
    DEA:=EMA(DIFF,9);                                        → dea
    MACD:=2*(DIFF-DEA),STICK;                                → 不输出 ①
    STICKLINE(DIFF< 0,0,DIFF,2,0),COLORGREEN;                → 前端: DIFF 实心柱
    STICKLINE(DIFF>=0,0,DIFF,2,0),COLORRED;                  → 前端: DIFF 实心柱
    STICKLINE(DEA>=0,0,DEA,2,-1),COLOR0000CC;                → 前端: DEA 空心柱 ②
    STICKLINE(DEA< 0,0,DEA,2,-1),COLORGREEN;                 → 前端: DEA 空心柱
    柱1:=IF(DIFF>DEA,DIFF,0),COLORRED;                       → 不输出 ①
    柱2:=IF(DEA< DIFF,DEA,0),COLORMAGENTA;                   → gold_icon 的高度
    DRAWICON(CROSS(DIFF,DEA),柱2,1);                         → gold_icon
    DRAWICON(CROSS(DEA,DIFF),DEA*1.1,2);                     → dead_icon
    VA:=IF(CLOSE>REF(CLOSE,1),VOL,-VOL);                     ┐
    OBV1:=SUM(IF(CLOSE=REF(CLOSE,1),0,VA),0);                │
    OBV2:=EMA(OBV1,3)-MA(OBV1,9);                            │ 只用于黄柱的条件
    OBV3:=EMA(IF(OBV2>0,OBV2,0),3);                          │
    MAC3:=MA(C,3);                                           ┘
    STICKLINE(OBV3>REF(OBV3,1) AND MAC3>REF(MAC3,1),0,DEA/4,2,0),COLORYELLOW;  → yellow

① **`:=` 是中间变量, 在通达信里不输出、不画**; 挂在它后面的 `,STICK` / `,COLORRED`
   不起作用。所以 MACD 那根红绿柱、柱1 **都不画** —— 这张副图上画出来的只有
   四条 STICKLINE、一条黄柱和两个图标。柱2 虽然不画, 但它是金叉图标的高度。

② `COLOR0000CC` **不是蓝色**。通达信的颜色写法是 BBGGRR(与 Windows COLORREF
   同序): BB=00, GG=00, RR=CC → RGB(204,0,0), **深红**。反证也对得上: 这个公式
   的配色规律是"非负红、负绿", DEA 非负用一个比 DIFF 暗一档的红来区分, 若 0000CC
   是蓝色, 整张图就只有这一处破了规律。

## 「完美复刻」在数值上靠的三件事

1. **EMA 的初值 = 第一根的值**(通达信 `EMA` 的定义: Y=[2X+(N-1)Y']/(N+1),
   首根 Y=X), 即 pandas 的 `ewm(span=N, adjust=False)`。
2. **无效值传播**。通达信里 `MA(X,9)` 前 8 根无效, `REF(X,1)` 首根无效,
   含无效值的运算结果仍无效、比较结果不成立。本模块用 `None` 表示无效并逐步传播,
   而不是像常见 pandas 翻译那样把 NaN 比较当成 False 再往下算 —— 那会让 OBV3 的
   EMA 从第 0 根就用 0 起步, 前几十根和通达信对不上。
3. **足够长的预热**。EMA 是递推的, 从哪一根开始算会影响之后的值; 差异按
   (1-α)^n 衰减。调用方(`api/stock_analysis.py`)取约 1000 根历史再算, 最慢的
   EMA26 也衰减到 (25/27)^800 ≈ 1e-27 —— **低于双精度**, 所以显示出来的每一根
   都与通达信「从上市第一根算起」逐位一致。
   OBV1 是从第一根起的累加(`SUM(X,0)`), 起点不同只差一个常数; 而 EMA 与 MA
   对常数平移是等变的, OBV2 = EMA − MA 里常数正好抵消 —— **OBV 这一支与起点无关**。

## 不受影响的两件事

- **成交量单位**(手 / 股): 只进 OBV3, 而 OBV3 只用于 `OBV3 > REF(OBV3,1)` ——
  正数倍缩放不改变大小关系。
- **复权**: 本仓库日 K 是前复权, 与通达信默认一致。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

Num = Optional[float]


# ── 通达信函数, 带无效值(None)传播 ───────────────────────────
def EMA(x: list[Num], n: int) -> list[Num]:
    """通达信 EMA: 首个有效值为初值, 之后 Y = (2X + (N-1)Y') / (N+1)。

    前面的无效值保持无效(对应 `MA` 未满、`REF` 首根这类情形); 起算之后若再遇到
    无效输入, 输出无效且**不更新状态** —— 日 K 序列里不会出现这种情况(停牌日
    没有行), 写在这里只是为了不在异常数据上静默算错。
    """
    out: list[Num] = []
    y: Num = None
    for v in x:
        if v is None:
            out.append(None)
            continue
        y = v if y is None else (2 * v + (n - 1) * y) / (n + 1)
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


def REF(x: list[Num], n: int = 1) -> list[Num]:
    return [None] * n + x[:-n] if n else list(x)


def SUM0(x: list[Num]) -> list[Num]:
    """`SUM(X,0)` —— 从第一根起累加。无效值不计入(通达信的累加跳过无效)。"""
    out: list[Num] = []
    s = 0.0
    started = False
    for v in x:
        if v is not None:
            s += v
            started = True
        out.append(s if started else None)
    return out


def CROSS(a: list[Num], b: list[Num]) -> list[bool]:
    """A 上穿 B: 本根 A>B 且上一根 A<=B。任一边无效即不成立。

    与 MyTT 等以复刻通达信为目标的实现同口径(上一根取「不大于」)。唯一的差别
    场景是上一根 A 恰好等于 B —— 对浮点的 DIFF/DEA 而言几乎不会发生。
    """
    out = [False]
    for i in range(1, len(a)):
        a0, b0, a1, b1 = a[i - 1], b[i - 1], a[i], b[i]
        out.append(None not in (a0, b0, a1, b1) and a1 > b1 and a0 <= b0)  # type: ignore[operator]
    return out


# ── 公式本体 ──────────────────────────────────────────────────
@dataclass
class QuantMacd:
    """逐根的输出。**只有画得出来的东西**; `:=` 的中间量不在这里。"""
    diff: list[Num]
    dea: list[Num]
    yellow: list[Num]      # 黄柱顶端 = DEA/4; 不满足条件的那根为 None(不画)
    gold_icon: list[Num]   # 金叉图标的高度 = 柱2; 非金叉为 None
    dead_icon: list[Num]   # 死叉图标的高度 = DEA*1.1; 非死叉为 None


def compute(close: list[float], vol: list[Num]) -> QuantMacd:
    """照原文逐行算。`close`、`vol` 按日期升序, 等长。

    `vol` 允许有 None(盘中实时那一根偶尔拿不到量): 那一根的 VA 无效, 按通达信
    的无效传播, 它只会让那一根的黄柱条件不成立 —— 不会编一个量出来。
    """
    C: list[Num] = [float(c) for c in close]
    V: list[Num] = [None if v is None else float(v) for v in vol]
    n = len(C)

    # DIFF:=( EMA(CLOSE,12) - EMA(CLOSE,26));
    e12, e26 = EMA(C, 12), EMA(C, 26)
    DIFF = [None if a is None or b is None else a - b for a, b in zip(e12, e26)]
    # DEA:=EMA(DIFF,9);
    DEA = EMA(DIFF, 9)

    # 柱2:=IF(DEA< DIFF,DEA,0);
    Z2 = [None if d is None or f is None else (d if d < f else 0.0)
          for d, f in zip(DEA, DIFF)]

    # VA:=IF(CLOSE>REF(CLOSE,1),VOL,-VOL);
    RC = REF(C, 1)
    VA: list[Num] = [None if r is None or v is None else (v if c > r else -v)  # type: ignore[operator]
                     for c, r, v in zip(C, RC, V)]
    # OBV1:=SUM(IF(CLOSE=REF(CLOSE,1),0,VA),0);
    OBV1 = SUM0([None if r is None else (0.0 if c == r else va)
                 for c, r, va in zip(C, RC, VA)])
    # ↑ 注意 `CLOSE=REF(CLOSE,1)` 时取 0 **不看量** —— 平盘那根即使量缺失也是 0,
    #   与原文逐字一致(原文的 IF 先判平盘, 再落到 VA)。
    # OBV2:=EMA(OBV1,3)-MA(OBV1,9);
    eo, mo = EMA(OBV1, 3), MA(OBV1, 9)
    OBV2 = [None if a is None or b is None else a - b for a, b in zip(eo, mo)]
    # OBV3:=EMA(IF(OBV2>0,OBV2,0),3);
    OBV3 = EMA([None if x is None else (x if x > 0 else 0.0) for x in OBV2], 3)
    # MAC3:=MA(C,3);
    MAC3 = MA(C, 3)

    # STICKLINE(OBV3>REF(OBV3,1) AND MAC3>REF(MAC3,1),0,DEA/4,2,0),COLORYELLOW;
    RO, RM = REF(OBV3, 1), REF(MAC3, 1)
    yellow: list[Num] = []
    for i in range(n):
        o, ro, m, rm, d = OBV3[i], RO[i], MAC3[i], RM[i], DEA[i]
        ok = None not in (o, ro, m, rm, d) and o > ro and m > rm   # type: ignore[operator]
        yellow.append(d / 4 if ok else None)                        # type: ignore[operator]

    # DRAWICON(CROSS(DIFF,DEA),柱2,1);  DRAWICON(CROSS(DEA,DIFF),DEA*1.1,2);
    gx, dx = CROSS(DIFF, DEA), CROSS(DEA, DIFF)
    gold = [Z2[i] if gx[i] else None for i in range(n)]
    dead = [DEA[i] * 1.1 if dx[i] and DEA[i] is not None else None for i in range(n)]  # type: ignore[operator]

    return QuantMacd(diff=DIFF, dea=DEA, yellow=yellow, gold_icon=gold, dead_icon=dead)
