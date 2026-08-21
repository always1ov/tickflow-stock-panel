import { useState } from 'react'
import { BookmarkCheck } from 'lucide-react'
import { PageHeader } from '@/components/PageHeader'
import { WorkflowPanel } from '@/components/backtest/WorkflowPanel'
import { MiningAutopilot } from './backtest/MiningAutopilot'
import { MiningWorkbench } from './backtest/MiningWorkbench'
import { ResearchCandidatesDialog } from './backtest/ResearchCandidatesDialog'

export function Mining() {
  const [candidatesOpen, setCandidatesOpen] = useState(false)

  return (
    <div className="flex min-h-full flex-col bg-base">
      <PageHeader
        title="挖掘"
        subtitle={<span className="hidden md:inline">嵌套样本外因子与策略挖掘</span>}
        className="shrink-0 flex-wrap gap-x-4 gap-y-2 bg-base/95 px-3 lg:flex-nowrap lg:px-5"
        right={(
          <button
            type="button"
            onClick={() => setCandidatesOpen(true)}
            aria-label="打开候选方案"
            title="候选方案"
            className="inline-flex h-8 shrink-0 items-center gap-1.5 rounded-btn border border-border bg-surface px-2 text-[11px] font-medium text-secondary transition-colors hover:border-accent/40 hover:text-accent sm:px-2.5 sm:text-xs"
          >
            <BookmarkCheck className="h-3.5 w-3.5" />
            <span>候选方案</span>
          </button>
        )}
      />

      <main className="min-h-0 flex-1 space-y-3 overflow-auto px-3 pb-3 pt-3 lg:px-4 lg:pb-4">
        {/* [fork 增强] R39 工作流放最上: 开了就不用管, 关页面照跑 —— 一次不成自己换配置再来。
            下面的 R31「AI 自动挖掘」保留原样, 想一轮一轮盯着调的还是用它。 */}
        <WorkflowPanel
          kind="mining"
          extraConfig={{ asset_type: 'stock' }}
          hint="开了就不用管 —— 服务端自己跑挖掘, 一次不达标就换一批因子配置重开, 直到达标或预算用尽"
        />
        <MiningAutopilot />
        <MiningWorkbench />
      </main>

      {candidatesOpen && <ResearchCandidatesDialog onClose={() => setCandidatesOpen(false)} />}
    </div>
  )
}
