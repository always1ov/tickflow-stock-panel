/**
 * 复盘状态带 (R791) — 页头正下方的一条, 回答「这是哪一天、定稿了没、几点自动跑、推去哪」。
 *
 * 收盘 → 「收盘定稿」; 盘中 → 「盘中快照 · 复盘以收盘为准」(warning 色)。
 * 口径与看板一致: quote_status.is_trading_hours 是唯一判据, 前端不另算交易时段。
 */
import { Clock, RefreshCw, Sparkles } from 'lucide-react'

import { cn } from '@/lib/cn'
import { buttonClass } from '@/components/ui'
import { fmtArchivedAt } from './shared'

const CHANNEL_LABEL: Record<string, string> = {
  feishu: '飞书', wecom: '企微', dingtalk: '钉钉', custom: '第三方', email: '邮件',
}

export interface ReviewStatusBarProps {
  asOf?: string | null
  intraday: boolean
  /** 最近一次归档时间(ISO) —— 档案带第一条 */
  lastArchivedAt?: string | null
  schedule: { enabled: boolean; hour: number; minute: number }
  pushChannels: string[]
  generating: boolean
  refreshing: boolean
  onRefresh: () => void
  onOpenSchedule: () => void
  onGenerate: () => void
}

export function ReviewStatusBar({
  asOf, intraday, lastArchivedAt, schedule, pushChannels,
  generating, refreshing, onRefresh, onOpenSchedule, onGenerate,
}: ReviewStatusBarProps) {
  const time = `${String(schedule.hour).padStart(2, '0')}:${String(schedule.minute).padStart(2, '0')}`
  const channels = pushChannels.map(c => CHANNEL_LABEL[c] ?? c).join(' / ')

  return (
    // [R808] 按钮恒在右侧: 左侧信息区可换行、可收缩, 右侧动作组不参与换行,
    // 窄屏时压缩的是左侧文案而不是把按钮挤到下一行左对齐。
    <div className="flex items-center gap-3 rounded-card border border-border bg-surface/80 px-3.5 py-2">
      <div className="flex min-w-0 flex-1 flex-wrap items-center gap-x-4 gap-y-2">
        <span
          className={cn(
            'inline-flex items-center gap-1.5 rounded-btn border px-2 py-0.5 text-micro font-medium',
            intraday
              ? 'border-warning/35 bg-warning/10 text-warning'
              : 'border-border bg-elevated/50 text-secondary',
          )}
          title={intraday ? '盘中数据仍在变, 复盘以收盘为准' : '已收盘, 当日数据定稿'}
        >
          <span className={cn('h-1.5 w-1.5 rounded-full', intraday ? 'bg-warning' : 'bg-bull')} />
          {intraday ? '盘中快照 · 复盘以收盘为准' : '收盘定稿'}
        </span>

        <span className="font-mono text-xs text-foreground">{asOf ?? '最新交易日'}</span>

        <span className="text-micro text-muted">
          上次归档 <span className="font-mono text-secondary">{fmtArchivedAt(lastArchivedAt)}</span>
        </span>

        <span className="text-micro text-muted">
          {schedule.enabled
            ? <>定时 <span className="font-mono text-secondary">{time}</span></>
            : '定时未开启'}
          {channels && <> · 推送 {channels}</>}
        </span>
      </div>

      <div className="flex shrink-0 items-center gap-1">
        <button
          onClick={onRefresh}
          disabled={refreshing}
          className={buttonClass({}, 'gap-1')}
          title="刷新市场数据"
        >
          <RefreshCw className={cn('h-3 w-3', refreshing && 'animate-spin')} />刷新
        </button>
        <button
          onClick={onOpenSchedule}
          className={buttonClass({ selected: schedule.enabled }, 'gap-1')}
          title={schedule.enabled ? `定时复盘已开启 · 每日 ${time}` : '定时复盘'}
        >
          <Clock className="h-3 w-3" />定时
        </button>
        <button
          onClick={onGenerate}
          disabled={generating}
          className={buttonClass({ variant: 'primary' }, 'gap-1.5')}
        >
          {generating ? (
            <><RefreshCw className="h-3.5 w-3.5 animate-spin" />生成中…</>
          ) : (
            <><Sparkles className="h-3.5 w-3.5" />生成复盘</>
          )}
        </button>
      </div>
    </div>
  )
}
