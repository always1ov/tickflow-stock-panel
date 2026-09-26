import { Settings2, RadioTower } from 'lucide-react'
import { motion } from 'framer-motion'

// ===== 来源标签 =====
//
// [R522] 「内置」不再印: 池里十几个策略里绝大多数是内置, 每颗都印一遍等于没印。
// 只给 AI / 自定义 / 叠加三种标, 它们才是"这颗跟别的不一样"。
const SRC_MAP: Record<string, string> = { custom: '自定义', ai: 'AI', composite: '叠加' }
const BADGE_CLS_MAP: Record<string, string> = {
  ai: 'bg-sky-500/10 text-sky-400 border-sky-500/30',
  custom: 'bg-amber-400/10 text-amber-400 border-amber-400/30',
  composite: 'bg-teal-500/10 text-teal-400 border-teal-500/30',
}

/** 芯片容器 —— 宽屏一行排开放不下再换行; 手机两列网格(一颗一行太长, 14 颗要滚一屏) */
export const CARD_WRAP_CLS = 'grid grid-cols-2 gap-1.5 sm:flex sm:flex-wrap'

// ===== 策略芯片 =====
//
// [R522] 用户: 「策略页面也要整改」。原来有 隐藏 / 紧凑 / 标准 / 详细 四档卡片(同一件事四种画法,
// 标准档 14 个策略占三行 150px), 现在只剩一种: **一颗芯片一个策略** —— 名字 · 命中数 · 今日失效数。
// 描述进悬停; 来源只给非内置的标; 监控天线与设置齿轮仍在芯片右侧(触屏也点得到, 不靠悬停出现)。
// 14 个策略一行放完(1440 宽), 结果表往上提一整块。

interface StrategyCardProps {
  name: string
  description?: string
  source?: string
  active: boolean
  count?: number
  /** 今日曾命中总数 */
  everMatched?: number
  /** 今日已失效数 (曾命中 - 当前命中) */
  expiredCount?: number
  loading: boolean
  onRun: () => void
  disabled: boolean
  onSettings: () => void
  /** 是否已加入策略监控 */
  monitored?: boolean
  /** 切换策略监控 (点击 RadioTower 图标) */
  onToggleMonitor?: () => void
  /** 周期徽章 (如 '分钟'); 日线策略不传 */
  timeframeBadge?: string
  /** 后台计算中 (渐进式 run_all): 数字未出时显示脉冲占位 */
  computing?: boolean
  /** 等待运行 (自动计算关闭/失败时的分钟策略): 数字未出时显示「待计算」点击引导 */
  awaitRun?: boolean
}

export function StrategyCard({
  name, description, source, active, count, expiredCount,
  loading,
  onRun, disabled, onSettings, monitored, onToggleMonitor, timeframeBadge, computing, awaitRun,
}: StrategyCardProps) {
  const activeCls = active
    ? 'border-accent/50 bg-accent/10'
    : 'border-border bg-surface hover:border-accent/40 hover:bg-accent/[0.03]'
  // [R522] 命中数原来是琥珀→橙的渐变字; 全站黑白主题之后它是芯片上唯一的彩字, 且渐变字在 R379 起就不用了
  const countCls = count === 0 ? 'text-muted' : 'text-foreground'
  const srcLabel = SRC_MAP[source ?? '']
  const badgeCls = BADGE_CLS_MAP[source ?? '']
  const hasExpired = expiredCount != null && expiredCount > 0

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.12, ease: [0.16, 1, 0.3, 1] }}
      // [R398] 窄屏上整颗占满所在的格(sm 以下两列网格), 免得右边缘成锯齿; 宽屏按内容宽平铺
      className={`inline-flex h-7 w-full items-center gap-1.5 rounded-btn border pl-2 pr-1 sm:w-auto transition-ui duration-hover text-left group ${activeCls}`}
      title={description || undefined}
    >
      <button onClick={onRun} disabled={disabled}
        className="flex min-w-0 items-center gap-1.5 cursor-pointer disabled:opacity-50 disabled:cursor-wait">
        {srcLabel && (
          <span className={`shrink-0 rounded border px-1 py-px text-micro font-medium leading-tight ${badgeCls}`}>{srcLabel}</span>
        )}
        {timeframeBadge && (
          <span className="shrink-0 rounded border border-sky-500/30 bg-sky-500/10 px-1 py-px text-micro font-medium leading-tight text-sky-400">{timeframeBadge}</span>
        )}
        <span className="truncate text-xs font-medium text-foreground">{name}</span>
        {count != null && !loading && (
          <span className={`shrink-0 font-mono text-xs font-bold tabular-nums ${countCls}`}>{count}</span>
        )}
        {count == null && !loading && computing && (
          <span className="shrink-0 animate-pulse font-mono text-xs font-bold text-muted/50">···</span>
        )}
        {count == null && !loading && !computing && awaitRun && (
          <span className="shrink-0 text-micro text-muted/60 transition-colors group-hover:text-accent/80" title="自动计算未开启或失败 — 点击实时计算">待计算</span>
        )}
        {hasExpired && (
          <span className="shrink-0 font-mono text-micro text-muted" title={`今日曾命中、现已失效 ${expiredCount} 只`}>{'-' + expiredCount}</span>
        )}
        {loading && <span className="h-3 w-5 shrink-0 animate-pulse rounded bg-elevated" />}
      </button>
      {onToggleMonitor && (
        <button onClick={(e) => { e.stopPropagation(); onToggleMonitor() }}
          className="relative shrink-0 rounded p-0.5 transition-colors hover:bg-elevated cursor-pointer" title={monitored ? '取消策略监控' : '开启策略监控'}>
          <RadioTower className={`h-3 w-3 transition-colors ${monitored ? 'text-accent' : 'text-muted hover:text-accent'}`} />
          {monitored && <span className="absolute inset-0 rounded animate-ping bg-accent/20" />}
        </button>
      )}
      <button onClick={(e) => { e.stopPropagation(); onSettings() }}
        className="shrink-0 rounded p-0.5 transition-colors hover:bg-elevated cursor-pointer" title="策略设置">
        <Settings2 className="h-3 w-3 text-muted transition-colors hover:text-accent" />
      </button>
    </motion.div>
  )
}
