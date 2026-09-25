import { Settings2, TrendingDown, RadioTower } from 'lucide-react'
import { motion } from 'framer-motion'
import { storage } from '@/lib/storage'

// ===== 卡片尺寸 =====

export type CardSize = 'mini' | 'normal' | 'large' | 'hidden'

export function loadCardSize(): CardSize {
  const v = storage.screenerCardSize.get('normal')
  if (v === 'mini' || v === 'normal' || v === 'large' || v === 'hidden') return v
  return 'normal'
}

const CARD_STYLES: Record<CardSize, {
  wrap: string
  card: string
  name: string
  count: string
  desc: string
  icon: string
}> = {
  mini: {
    wrap: 'gap-1',
    card: 'inline-flex items-center gap-1 px-2 py-0.5 rounded-btn',
    name: 'text-micro',
    count: 'text-xs',
    desc: '',
    icon: 'h-3 w-3',
  },
  normal: {
    wrap: 'gap-2',
    card: 'relative inline-flex items-center gap-2 pl-3 pr-12 py-1.5 rounded-lg',
    name: 'text-xs',
    count: 'text-xs',
    desc: 'text-micro text-muted leading-tight mt-0.5 line-clamp-1 max-w-none sm:max-w-[120px]',
    icon: 'h-3.5 w-3.5',
  },
  large: {
    wrap: 'gap-2',
    card: 'relative inline-flex flex-col items-start pl-3.5 pr-12 py-2.5 rounded-btn min-w-[100px]',
    name: 'text-xs',
    count: 'text-lg font-mono font-bold tabular-nums',
    desc: 'text-micro text-muted leading-tight mt-0.5 line-clamp-2 max-w-none sm:max-w-[140px]',
    icon: 'h-3.5 w-3.5',
  },
  hidden: {
    wrap: '',
    card: '',
    name: '',
    count: '',
    desc: '',
    icon: '',
  },
}

export { CARD_STYLES }

/** 获取卡片容器的 flex-wrap gap 样式 */
export function cardWrapCls(size: CardSize): string {
  return `flex flex-wrap ${CARD_STYLES[size].wrap}`
}

// ===== 来源标签 =====

const SRC_MAP: Record<string, string> = { builtin: '内置', custom: '自定义', ai: 'AI', composite: '叠加' }
const BADGE_CLS_MAP: Record<string, string> = {
  builtin: 'bg-secondary/10 text-muted border-border',
  ai: 'bg-sky-500/10 text-sky-400 border-sky-500/30',
  custom: 'bg-amber-400/10 text-amber-400 border-amber-400/30',
  composite: 'bg-teal-500/10 text-teal-400 border-teal-500/30',
}

// ===== 策略卡片 =====

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
  cardSize: CardSize
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
  loading, cardSize,
  onRun, disabled, onSettings, monitored, onToggleMonitor, timeframeBadge, computing, awaitRun,
}: StrategyCardProps) {
  const cs = CARD_STYLES[cardSize]
  const activeCls = active
    ? 'border-accent/50 bg-accent/10'
    : 'border-border bg-surface hover:border-accent/40 hover:bg-accent/[0.03]'
  const countCls = count === 0
    ? 'text-muted'
    : 'bg-gradient-to-r from-amber-400 to-orange-500 bg-clip-text text-transparent'
  const srcLabel = cardSize === 'mini' ? (SRC_MAP[source ?? ''] ?? '内') : (SRC_MAP[source ?? ''] ?? '内置')
  const badgeCls = BADGE_CLS_MAP[source ?? 'builtin'] ?? BADGE_CLS_MAP.builtin

  // 失效数 > 0 时显示
  const hasExpired = expiredCount != null && expiredCount > 0

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.12, ease: [0.16, 1, 0.3, 1] }}
      // [R398] 窄屏上整张卡占满一列。
      //
      // 这些卡是 `inline-flex` 的 —— **按各自内容撑宽**。宽屏上一行能塞好几张,
      // 平铺开来看不出问题; 到了手机上一行只放得下一张, 于是每张宽度都不一样,
      // 右边缘成了锯齿(用户截图: 「跌破生命线」窄、「相对活力指数转强」几乎顶到边)。
      //
      // 只在 `sm`(640px)以下铺满, 宽屏的平铺一个像素不变。
      className={`${cs.card} w-full sm:w-auto border transition-ui duration-hover text-left group ${activeCls}`}
    >
      {cardSize === 'large' ? (
        <>
          <button onClick={onRun} disabled={disabled}
            className="flex flex-col items-start cursor-pointer disabled:opacity-50 disabled:cursor-wait w-full">
            <div className="flex items-center gap-1.5 max-w-full">
              <span className={`text-micro px-1 py-px rounded border font-medium leading-tight shrink-0 ${badgeCls}`}>{srcLabel}</span>
              {timeframeBadge && (
                <span className="text-micro px-1 py-px rounded border font-medium leading-tight shrink-0 border-sky-500/30 bg-sky-500/10 text-sky-400">{timeframeBadge}</span>
              )}
              <span className="text-xs font-medium truncate text-foreground">{name}</span>
            </div>
            {description && (
              <span className="text-micro text-muted leading-tight mt-0.5 line-clamp-1">{description}</span>
            )}
            {count != null && !loading && (
              <div className="mt-1.5 flex items-center gap-2">
                <div className="flex items-center gap-1">
                  <span className={`text-sm font-mono font-bold tabular-nums ${countCls}`}>{count}</span>
                  <span className="text-micro text-muted">只</span>
                </div>
                {hasExpired && (
                  <div className="flex items-center gap-0.5 px-1.5 py-0.5 rounded bg-red-500/8 border border-red-500/15">
                    <TrendingDown className="h-2.5 w-2.5 text-red-400" />
                    <span className="text-micro font-mono font-medium text-red-400">{expiredCount}</span>
                  </div>
                )}
              </div>
            )}
            {count == null && !loading && computing && (
              <span className="mt-1.5 text-sm font-mono font-bold text-muted/50 animate-pulse">···</span>
            )}
            {count == null && !loading && !computing && awaitRun && (
              <span className="mt-1.5 text-micro text-muted/60 transition-colors group-hover:text-accent/80" title="自动计算未开启或失败 — 点击卡片实时计算">待计算</span>
            )}
            {loading && <div className="mt-1 h-4 w-10 rounded bg-elevated animate-pulse" />}
          </button>
          <button onClick={(e) => { e.stopPropagation(); onSettings() }}
            className="absolute top-1.5 right-1.5 p-0.5 rounded hover:bg-elevated transition-colors cursor-pointer" title="策略设置">
            <Settings2 className="h-3 w-3 text-muted hover:text-accent transition-colors" />
          </button>
          {onToggleMonitor && (
            <button onClick={(e) => { e.stopPropagation(); onToggleMonitor() }}
              className="absolute top-1.5 right-7 p-0.5 rounded hover:bg-elevated transition-colors cursor-pointer" title={monitored ? '取消策略监控' : '开启策略监控'}>
              <RadioTower className={`relative h-3 w-3 transition-colors ${monitored ? 'text-accent' : 'text-muted hover:text-accent'}`} />
              {monitored && <span className="absolute inset-0 rounded animate-ping bg-accent/20" />}
            </button>
          )}
        </>
      ) : cardSize === 'normal' ? (
        <>
          <button onClick={onRun} disabled={disabled}
            className="flex flex-col items-start cursor-pointer disabled:opacity-50 disabled:cursor-wait min-w-0">
            <div className="flex items-center gap-1.5 min-w-0">
              <span className={`text-micro px-1 py-px rounded border font-medium leading-tight shrink-0 ${badgeCls}`}>{srcLabel}</span>
              {timeframeBadge && (
                <span className="text-micro px-1 py-px rounded border font-medium leading-tight shrink-0 border-sky-500/30 bg-sky-500/10 text-sky-400">{timeframeBadge}</span>
              )}
              <span className="text-xs font-medium truncate text-foreground">{name}</span>
              {count != null && !loading && (
                <span className={`text-xs font-mono font-bold tabular-nums shrink-0 ${countCls}`}>{count}</span>
              )}
              {count == null && !loading && computing && (
                <span className="text-xs font-mono font-bold text-muted/50 animate-pulse shrink-0">···</span>
              )}
              {count == null && !loading && !computing && awaitRun && (
                <span className="text-micro text-muted/60 transition-colors group-hover:text-accent/80 shrink-0" title="自动计算未开启或失败 — 点击卡片实时计算">待计算</span>
              )}
              {loading && <span className="w-5 h-3 rounded bg-elevated animate-pulse shrink-0" />}
            </div>
            <div className="flex items-center gap-1.5 mt-0.5">
              {description && (
                <span className="text-micro text-muted leading-tight line-clamp-1 max-w-none sm:max-w-[120px]">{description}</span>
              )}
              {hasExpired && (
                <span className="text-micro font-mono text-red-400/80">{'-' + expiredCount}</span>
              )}
            </div>
          </button>
          <button onClick={(e) => { e.stopPropagation(); onSettings() }}
            className="absolute top-1.5 right-1.5 p-0.5 rounded hover:bg-elevated transition-colors cursor-pointer" title="策略设置">
            <Settings2 className="h-3 w-3 text-muted hover:text-accent transition-colors" />
          </button>
          {onToggleMonitor && (
            <button onClick={(e) => { e.stopPropagation(); onToggleMonitor() }}
              className="absolute top-1.5 right-7 p-0.5 rounded hover:bg-elevated transition-colors cursor-pointer" title={monitored ? '取消策略监控' : '开启策略监控'}>
              <RadioTower className={`relative h-3 w-3 transition-colors ${monitored ? 'text-accent' : 'text-muted hover:text-accent'}`} />
              {monitored && <span className="absolute inset-0 rounded animate-ping bg-accent/20" />}
            </button>
          )}
        </>
      ) : (
        /* mini */
        <>
          <button onClick={onRun} disabled={disabled}
            className="flex items-center gap-1 cursor-pointer disabled:opacity-50 disabled:cursor-wait">
            <span className="text-micro px-0.5 rounded bg-secondary/10 text-muted border border-border font-medium leading-tight">{srcLabel}</span>
            <span className="text-micro font-medium whitespace-nowrap text-foreground">{name}</span>
            {count != null && !loading && (
              <span className={`text-xs font-mono font-bold tabular-nums ${countCls}`}>{count}</span>
            )}
            {count == null && !loading && computing && (
              <span className="text-xs font-mono font-bold text-muted/50 animate-pulse">···</span>
            )}
            {count == null && !loading && !computing && awaitRun && (
              <span className="text-micro text-muted/60 transition-colors group-hover:text-accent/80 shrink-0" title="自动计算未开启或失败 — 点击卡片实时计算">待算</span>
            )}
            {hasExpired && (
              <span className="text-micro font-mono text-red-400/70">{'-' + expiredCount}</span>
            )}
            {loading && <span className="w-4 h-2.5 rounded bg-elevated animate-pulse" />}
          </button>
          {onToggleMonitor && (
            <button onClick={(e) => { e.stopPropagation(); onToggleMonitor() }}
              className="relative p-0.5 rounded hover:bg-elevated transition-colors cursor-pointer" title={monitored ? '取消策略监控' : '开启策略监控'}>
              <RadioTower className={`h-3 w-3 transition-colors ${monitored ? 'text-accent' : 'text-muted hover:text-accent'}`} />
              {monitored && <span className="absolute inset-0 rounded animate-ping bg-accent/20" />}
            </button>
          )}
          <button onClick={(e) => { e.stopPropagation(); onSettings() }}
            className="p-0.5 rounded hover:bg-elevated transition-colors cursor-pointer" title="策略设置">
            <Settings2 className="h-3 w-3 text-muted hover:text-accent transition-colors" />
          </button>
        </>
      )}
    </motion.div>
  )
}
