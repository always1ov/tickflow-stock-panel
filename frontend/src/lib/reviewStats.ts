/**
 * [R747] 复盘里的统计读数 —— 用户: 「统计学方面思考」。
 *
 * [R749] 复盘推翻重做成「结论 + 权益曲线 + 逐日」之后，这里只留还在用的那几个：
 *
 *   · 分位数 / 均值 / t 区间 —— 「每笔期望」那一个数与它的 95%CI；
 *   · Wilson 区间 —— 比例量的区间，少量样本也稳（0/6 与 6/6 也给得出上下界）；
 *   · 笔 —— 口径与后端 `flip_trades.simulate` **逐条对齐**：连着两个多头段
 *     （比如自然回升转上涨趋势）手不用动，仍算同一笔。
 *
 * 分布直方图、正态检验、分段与条件收益随页面上那几块一起删了 —— 留着就是
 * 没人调用的死代码。
 *
 * 函数都收 `ReviewRow[]`(**新→旧**, 与接口一致)，内部自己翻成时间正序。
 */
import type { LivermoreState, ReviewRow, StockReview } from '@/lib/api'

type Leg = NonNullable<StockReview['flip_trades']>['legs'][number]

function sorted(v: number[]): number[] {
  return [...v].sort((a, b) => a - b)
}

export function mean(v: number[]): number | null {
  return v.length ? v.reduce((s, x) => s + x, 0) / v.length : null
}

/** 线性插值分位 —— 与 Excel PERCENTILE.INC / numpy 默认同口径 */
export function quantile(v: number[], q: number): number | null {
  if (!v.length) return null
  const a = sorted(v)
  const pos = (a.length - 1) * q
  const lo = Math.floor(pos)
  const hi = Math.ceil(pos)
  return a[lo] + (a[hi] - a[lo]) * (pos - lo)
}

/** 样本标准差(n-1) —— 总体标准差会把小样本的离散度说小 */
export function stdev(v: number[]): number | null {
  if (v.length < 2) return null
  const m = mean(v)!
  const ss = v.reduce((s, x) => s + (x - m) ** 2, 0)
  return Math.sqrt(ss / (v.length - 1))
}

/** 双侧 95% 的 t 临界值; df 超过 30 之后与 1.96 的差已经不值得再查表 */
const T95 = [
  12.706, 4.303, 3.182, 2.776, 2.571, 2.447, 2.365, 2.306, 2.262, 2.228,
  2.201, 2.179, 2.160, 2.145, 2.131, 2.120, 2.110, 2.101, 2.093, 2.086,
  2.080, 2.074, 2.069, 2.064, 2.060, 2.056, 2.052, 2.048, 2.045, 2.042,
]

export function tCritical(df: number): number {
  if (df < 1) return Infinity
  return df <= 30 ? T95[df - 1] : 1.96
}

export type Interval = { mean: number; lo: number; hi: number; se: number; df: number }

/** 均值的 95% 置信区间(t 分布); 少于 2 个样本无从谈起 */
export function ci95(v: number[]): Interval | null {
  if (v.length < 2) return null
  const m = mean(v)!
  const se = stdev(v)! / Math.sqrt(v.length)
  const t = tCritical(v.length - 1)
  return { mean: m, lo: m - t * se, hi: m + t * se, se, df: v.length - 1 }
}

/** 比例的 Wilson 区间 —— 小样本比正态近似稳, 0/6 与 6/6 也能给出有意义的上下界 */
export function wilson(wins: number, n: number): { lo: number; hi: number } | null {
  if (n <= 0) return null
  const z = 1.96
  const p = wins / n
  const den = 1 + (z * z) / n
  const center = (p + (z * z) / (2 * n)) / den
  const half = (z * Math.sqrt((p * (1 - p)) / n + (z * z) / (4 * n * n))) / den
  return { lo: Math.max(0, center - half), hi: Math.min(1, center + half) }
}

// ==================== 六态之后 ====================

export type ForwardStat = {
  state: LivermoreState
  stateCn: string
  /** 有几天落在这个状态、且后面还有完整的 horizon 天 */
  n: number
  wins: number
  /** 之后 horizon 天的涨跌, 取中位 —— 收益是右偏厚尾的, 均值会被几根大阳线拽走 */
  median: number | null
}

/** 主态就这么四个; SR / SREA 只作为更细的注记出现, 从不单独当主态。 */
const STATE_ORDER = ['UT', 'NR', 'NREA', 'DT']

/**
 * 每个主态之后 `horizon` 个交易日涨了多少。
 *
 * 口径: 第 i 天的状态 → 第 i+horizon 天收盘 / 第 i 天收盘 - 1。用**中位**不用均值,
 * 因为单只票的收益分布也是右偏的; 用相邻几天都会算成一条样本(相互重叠), 所以
 * `n` 只用来判断「这点样本够不够看」, 不拿去当独立的样本量算显著性。
 *
 * 全市场 289 只票 × 250 日的实测结果(这张表 w<30 时就是在跟它对照):
 *   UT 44.5% / NR 45.1% / NREA 47.9% / DT 43.2% —— 四种状态之后 5 日的上涨占比
 *   全都不到五成, 所以单个状态本身指不了方向。
 */
export function forwardByState(rows: ReviewRow[], horizon = 5): ForwardStat[] {
  const a = [...rows].reverse()
  const acc = new Map<LivermoreState, { cn: string; rets: number[] }>()
  for (let i = 0; i + horizon < a.length; i++) {
    const st = a[i].trend
    if (!st) continue
    const base = a[i].close
    const later = a[i + horizon].close
    if (!base || !later) continue
    const g = acc.get(st.state) ?? { cn: st.state_cn, rets: [] }
    g.rets.push(later / base - 1)
    acc.set(st.state, g)
  }

  const out: ForwardStat[] = []
  for (const [state, g] of acc) {
    out.push({
      state,
      stateCn: g.cn,
      n: g.rets.length,
      wins: g.rets.filter(r => r > 0).length,
      median: quantile(g.rets, 0.5),
    })
  }
  const rank = (s: string) => {
    const i = STATE_ORDER.indexOf(s)
    return i < 0 ? STATE_ORDER.length : i
  }
  return out.sort((x, y) => rank(x.state) - rank(y.state) || y.n - x.n)
}

// ==================== 笔 ====================

export type Trade = {
  enter: string
  exit: string
  ret: number
  /** 横跨几个交易日 */
  bars: number
  /** 最后一笔还没卖出 */
  open: boolean
}

/**
 * legs → 真正的「笔」。**连着两个多头段是一次持仓, 不是两次买卖** ——
 * 自然回升转上涨趋势也是转折, 但手上不用动。`act` 已由后端算好:
 * 多头侧的第一段是「买入」, 之后是「持有」; 空头侧是「卖出」或「空仓」。
 * 所以一笔 = 从一次「买入」到下一次「卖出/空仓」之前。
 */
export function trades(legs: Leg[]): Trade[] {
  const out: Trade[] = []
  let cur: Trade | null = null

  for (const l of legs) {
    if (l.act === '买入') {
      if (cur) out.push(cur)
      cur = { enter: l.enter_date, exit: l.exit_date, ret: l.ret, bars: l.bars, open: l.open_ended }
    } else if (l.act === '持有' && cur) {
      cur.ret = (1 + cur.ret) * (1 + l.ret) - 1
      cur.bars += l.bars
      cur.exit = l.exit_date
      cur.open = l.open_ended
    } else if (cur) {
      out.push(cur)
      cur = null
    }
  }
  if (cur) out.push(cur)
  return out
}
