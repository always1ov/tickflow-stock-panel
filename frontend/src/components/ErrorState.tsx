import { type LucideIcon, CloudOff, RefreshCw } from 'lucide-react'

import { buttonClass } from '@/components/ui'

interface Props {
  icon?: LucideIcon
  title?: string
  hint?: string
  retrying?: boolean
  onRetry?: () => void
}

// §6.0.5 四态评审 — error 状态: 图示 + 归因提示 + 重试入口。
// 与 EmptyState 同构但语义是「加载失败」而非「无数据」, 避免错误被伪装成空态误导排查方向。
export function ErrorState({ icon: Icon = CloudOff, title = '数据加载失败', hint, retrying, onRetry }: Props) {
  return (
    <div className="h-full grid place-items-center px-8 py-16 animate-rise-in">
      <div className="text-center max-w-md">
        <Icon className="mx-auto h-10 w-10 text-danger/70" strokeWidth={1.5} />
        <h2 className="mt-4 text-title font-medium text-foreground">{title}</h2>
        {hint && <p className="mt-2 text-sm text-secondary leading-relaxed">{hint}</p>}
        {onRetry && (
          <button
            type="button"
            onClick={onRetry}
            disabled={retrying}
            className={buttonClass({}, 'mt-5 gap-1.5')}
          >
            <RefreshCw className={retrying ? 'h-3.5 w-3.5 animate-spin' : 'h-3.5 w-3.5'} />
            重试
          </button>
        )}
      </div>
    </div>
  )
}
