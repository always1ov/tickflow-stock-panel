/**
 * [fork 增强 R169] 决策台仓位列 → 上游「持仓提醒」页的入口。
 *
 * 两边是同一件事的两个口径: 这里是**每只票**的持有/成本/仓位%, 批次页是**每笔买入**
 * 的成本/数量/止盈止损/到期提醒。这个小按钮负责三件事:
 *
 * 1. 有批次时给出跳转(带 ?symbol=, 落地后自动定位到该票的批次);
 * 2. 手填成本与批次加权均价对不上时把偏离标出来 —— 通常意味着加仓/减仓后
 *    只更新了一边;
 * 3. 标了空仓但批次还挂着时给个提示 —— 那两条派生的监控规则还在跑, 多半是
 *    卖出后忘了删批次。
 */
import { Link } from 'react-router-dom'
import { Layers } from 'lucide-react'

/** 手填与批次均价差多少才值得提示。低于这个数多半是四舍五入或手续费, 不值得打扰。 */
const DRIFT_ALERT_PCT = 1.0

export function LotsLink({ symbol, lotCount, driftPct, lotCost, stale = false }: {
  symbol: string
  lotCount: number
  driftPct: number | null
  lotCost: number | null
  /** 空仓但批次未清 */
  stale?: boolean
}) {
  if (!lotCount) return null

  const drift = driftPct != null && Math.abs(driftPct) >= DRIFT_ALERT_PCT ? driftPct : null
  const tone = stale
    ? 'border-amber-400/40 text-amber-400'
    : drift
      ? 'border-warning/45 text-warning'
      : 'border-border text-muted hover:text-secondary'

  const title = stale
    ? `已标空仓, 但「持仓提醒」页还留着 ${lotCount} 笔批次 —— 那边派生的止盈止损/到期规则仍在跑。点击去清理。`
    : drift
      ? `手填成本与 ${lotCount} 笔批次的加权均价${lotCost != null ? ` ${lotCost.toFixed(2)}` : ''} 相差 ${drift > 0 ? '+' : ''}${drift.toFixed(1)}% —— 多半是加减仓后只更新了一边。点击去核对。`
      : `该票在「持仓提醒」页有 ${lotCount} 笔批次。点击查看。`

  return (
    <Link
      // [R184] R183 把 /lots 改成模拟盘之后, 批次页搬到了 /lots-registry ——
      // 这里没跟着改, 点进去会落到模拟盘上看不到批次。属于 R183 引入的回归。
      to={`/lots-registry?symbol=${encodeURIComponent(symbol)}`}
      title={title}
      aria-label={title}
      className={`tap-target inline-flex h-6 shrink-0 items-center gap-0.5 rounded border bg-base px-1 text-[10px] font-mono transition-colors ${tone}`}
    >
      <Layers className="h-2.5 w-2.5" />
      {lotCount}
      {drift && <span className="ml-0.5">{drift > 0 ? '+' : ''}{drift.toFixed(0)}%</span>}
    </Link>
  )
}
