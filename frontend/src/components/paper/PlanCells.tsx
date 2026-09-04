/**
 * [fork 增强 R171] AI 操盘手的交易计划展示件 —— 三条线、出场归因标、出场分布。
 *
 * 升级前, 模型每天重新自由决定买卖, 界面上也就只有"买了什么/卖了什么"。
 * 复盘时最想问的那个问题 ——「它当初打算怎么做, 后来做到了吗」—— 界面根本
 * 答不上来。这几个件就是把那个问题摆到台面上。
 */
import type { PaperExitStats, PaperOrder, PaperPlan } from '@/lib/api'

const EXIT_META: Record<string, { label: string; cls: string; hint: string }> = {
  stop: {
    label: '止损', cls: 'border-emerald-400/45 bg-emerald-400/10 text-emerald-400',
    hint: '触到买入时自己立的止损线, 系统直接卖 —— 这一路不问 AI, 和跌破生命线同一条道理',
  },
  due: {
    label: '到期', cls: 'border-sky-400/45 bg-sky-400/10 text-sky-400',
    hint: '到了买入时定的最长持有天数, 系统直接卖 —— 期限到了还能续, 那期限就是空话',
  },
  target: {
    label: '止盈', cls: 'border-red-400/45 bg-red-400/10 text-red-400',
    hint: '到止盈线后模型自己决定走的。止盈系统只提醒不代劳 —— 落袋还是让利润奔跑是策略, 不是纪律',
  },
  lifeline: {
    label: '生命线', cls: 'border-amber-400/50 bg-amber-400/10 text-amber-300',
    hint: '[R61] 跌破 20 日线的纪律强平, 与模型自己的计划无关',
  },
  ai: {
    label: '主动卖', cls: 'border-border bg-base text-secondary',
    hint: '模型自己判断该走了 —— 既没触线也没到期',
  },
}

/** 成交行上的出场归因标。买入没有归因, 返回 null。 */
export function ExitTag({ o }: { o: PaperOrder }) {
  if (o.action !== 'sell' || o.rejected) return null
  const meta = EXIT_META[o.exit_reason ?? 'ai']
  if (!meta) return null
  return (
    <span
      title={meta.hint}
      className={`mr-1 inline-flex whitespace-nowrap rounded border px-1 text-[9px] leading-tight ${meta.cls}`}
    >
      {meta.label}
      {o.pnl_pct != null && (
        <span className="ml-0.5 font-mono">{o.pnl_pct > 0 ? '+' : ''}{(o.pnl_pct * 100).toFixed(1)}%</span>
      )}
    </span>
  )
}

/** 持仓行上的三条线。没有计划(升级前建的仓)时说明这一点, 而不是留空。 */
export function PlanCell({ plan, price }: { plan?: PaperPlan | null; price: number | null }) {
  if (!plan) {
    return (
      <span
        title="这一笔买入时没立计划 —— 要么是升级前建的仓, 要么模型那次没给参数。没有计划就没有自动止损/到期。"
        className="text-[10px] text-muted/50"
      >
        无计划
      </span>
    )
  }
  const gap = (line: number | null) =>
    line != null && price ? `${((line / price - 1) * 100).toFixed(1)}%` : null

  return (
    <span className="inline-flex flex-wrap items-center gap-x-1.5 gap-y-0.5 font-mono text-[10px]">
      {plan.stop_price != null && (
        <span
          title={`止损线 ${plan.stop_price}(成本 ${plan.based_on_cost} − ${plan.stop_pct}%)。触到系统直接卖, 不问 AI。`}
          className="text-emerald-400/90"
        >
          损 {plan.stop_price.toFixed(2)}
          {gap(plan.stop_price) && <span className="ml-0.5 text-muted">({gap(plan.stop_price)})</span>}
        </span>
      )}
      {plan.target_price != null && (
        <span
          title={`止盈线 ${plan.target_price}(成本 ${plan.based_on_cost} + ${plan.target_pct}%)。到线只提醒, 走不走由模型自己定。`}
          className="text-red-400/90"
        >
          盈 {plan.target_price.toFixed(2)}
          {gap(plan.target_price) && <span className="ml-0.5 text-muted">({gap(plan.target_price)})</span>}
        </span>
      )}
      {plan.due_date && (
        <span title={`买入时定的最长持有 ${plan.hold_days} 天(自然日), 到期系统直接卖。`} className="text-sky-400/85">
          期 {plan.due_date.slice(5)}
        </span>
      )}
    </span>
  )
}

/**
 * 出场原因分布 —— 这一栏才是"逼模型先立计划"真正的产出。
 *
 * 怎么读: 止盈占比高 = 它的目标定得够得着; 止损/生命线占比高 = 买入那一刻的
 * 判断经常错; 到期占比高 = 老是拿着不动等时间到。样本太少时不给结论。
 */
export function ExitStatsBar({ stats }: { stats?: PaperExitStats }) {
  if (!stats || !stats.closed) {
    return (
      <span className="text-[10px] text-muted/60" title="还没有完成过一次出场, 统计不出来。">
        出场归因: 暂无样本
      </span>
    )
  }
  const order: Array<keyof typeof EXIT_META> = ['target', 'ai', 'due', 'stop', 'lifeline']
  return (
    <span className="inline-flex flex-wrap items-center gap-1.5 text-[10px]">
      <span className="text-muted">出场 {stats.closed} 笔:</span>
      {order.map(k => {
        const n = stats.counts?.[k as keyof typeof stats.counts] ?? 0
        if (!n) return null
        const meta = EXIT_META[k]
        return (
          <span key={k} title={meta.hint} className={`inline-flex rounded border px-1 leading-tight ${meta.cls}`}>
            {meta.label} {n}
          </span>
        )
      })}
      {stats.win_rate != null && (
        <span
          className="text-muted"
          title="赚钱出场的占比。止损/到期/生命线按定义不算「计划兑现」—— 它们是计划没走通才触发的。"
        >
          · 赚钱出场 {(stats.win_rate * 100).toFixed(0)}%
        </span>
      )}
      {stats.positions_total > 0 && (
        <span
          className="text-muted/70"
          title="当前持仓里有几只挂着买入时立的计划。低于总数说明有些仓是升级前建的, 或那次模型没给参数。"
        >
          · 在仓计划 {stats.positions_with_plan}/{stats.positions_total}
        </span>
      )}
    </span>
  )
}
