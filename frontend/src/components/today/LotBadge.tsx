/**
 * [fork 增强 R169] 持仓体检里的批次小标 —— 把上游「持仓提醒」页的批次登记
 * 接到今日总览上。
 *
 * 只标两件在这一屏真正有用的事:
 * 1. **成本是批次派生的**(决策台没手填) —— 浮盈这一格的分母来自哪里, 得让人知道;
 * 2. **有未过期的到期日** —— 那是当初买入时给自己设的期限, 该在早上看盘时提醒。
 *
 * 刻意不做成链接: 这一行本身点了要跳个股分析, 嵌套跳转会打架。想去清理批次走决策台
 * 仓位列那个入口。
 */
import type { TodayHolding } from '@/lib/api'

/** 到期日提前多少天开始显示。太早显示会一直挂在那儿, 变成看不见的背景。 */
const REMIND_LEAD_DAYS = 14

function daysUntil(iso: string): number | null {
  const t = Date.parse(`${iso}T00:00:00`)
  if (Number.isNaN(t)) return null
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  return Math.round((t - today.getTime()) / 86_400_000)
}

export function LotBadge({ h }: { h: TodayHolding }) {
  const derived = h.cost_source === 'lots' && (h.lot_count ?? 0) > 0
  const left = h.lot_remind_date ? daysUntil(h.lot_remind_date) : null
  const dueSoon = left != null && left >= 0 && left <= REMIND_LEAD_DAYS

  if (!derived && !dueSoon) return null

  return (
    <>
      {derived && (
        <span
          title={`成本取自「持仓提醒」页的 ${h.lot_count} 笔批次(数量加权均价), 不是在决策台手填的。想按自己的口径算, 去决策台成本格填一个数即可覆盖。`}
          className="ml-1.5 inline-flex items-center rounded border border-accent/30 bg-accent/[0.08] px-1 text-[9px] font-mono leading-tight text-accent/85"
        >
          批{h.lot_count}
        </span>
      )}
      {dueSoon && (
        <span
          title={`「持仓提醒」页给这只票设的到期日是 ${h.lot_remind_date}, 还有 ${left} 天。`}
          className={`ml-1 inline-flex items-center rounded border px-1 text-[9px] font-mono leading-tight ${
            left! <= 3
              ? 'border-warning/45 bg-warning/10 text-warning'
              : 'border-border bg-base text-muted'
          }`}
        >
          {left === 0 ? '今日到期' : `到期${left}天`}
        </span>
      )}
    </>
  )
}
