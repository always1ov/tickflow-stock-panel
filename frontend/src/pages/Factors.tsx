import { useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { BookmarkCheck, Combine, LibrarySquare, PenLine, Pickaxe, Sigma } from 'lucide-react'
import { PageHeader } from '@/components/PageHeader'
import { FactorDiscovery } from './backtest/FactorDiscovery'
import { FactorComposite } from './factors/FactorComposite'
import { FactorEditor } from './factors/FactorEditor'
import { FactorLibrary } from './factors/FactorLibrary'
import { MiningWorkbench } from './backtest/MiningWorkbench'
// [R53 → R172] 挖掘页被上游并进本页的 mining tab, fork 的这三层随之搬过来
import { WorkflowPanel } from '@/components/backtest/WorkflowPanel'
import { MiningAutopilot } from './backtest/MiningAutopilot'
import { LevelGuide } from '@/components/backtest/LevelGuide'
import { ResearchCandidatesDialog } from './backtest/ResearchCandidatesDialog'

type Tab = 'inspect' | 'library' | 'editor' | 'composite' | 'mining'

const TABS: Record<Tab, { title: string; icon: typeof Sigma }> = {
  inspect: { title: '检验', icon: Sigma },
  library: { title: '因子库', icon: LibrarySquare },
  editor: { title: '编辑器', icon: PenLine },
  composite: { title: '组合', icon: Combine },
  mining: { title: '挖掘', icon: Pickaxe },
}

export function Factors() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [candidatesOpen, setCandidatesOpen] = useState(false)
  const navigate = useNavigate()

  const requestedTab = searchParams.get('tab')
  const activeTab: Tab = requestedTab === 'library' || requestedTab === 'editor' || requestedTab === 'composite' || requestedTab === 'mining'
    ? requestedTab
    : 'inspect'
  const focusFactor = activeTab === 'inspect' ? searchParams.get('focus') ?? '' : ''

  const changeTab = (tab: Tab) => {
    const next = new URLSearchParams(searchParams)
    next.set('tab', tab)
    next.delete('focus') // 切 tab 清除单因子聚焦
    next.delete('edit') // 切 tab 清除编辑器载入目标
    setSearchParams(next, { replace: true })
  }

  return (
    <div className="flex min-h-full flex-col bg-base xl:h-full">
      <PageHeader
        title="因子"
        subtitle={<span className="hidden md:inline">{activeTab === 'library' ? '因子注册表目录' : activeTab === 'mining' ? '嵌套样本外因子与策略挖掘' : '因子研究与检验'}</span>}
        className="shrink-0 flex-wrap gap-x-4 gap-y-2 bg-base/95 px-3 lg:flex-nowrap lg:px-5"
        right={(
          <div className="flex w-full min-w-0 items-center gap-1.5 sm:gap-2 lg:w-auto">
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
            <span className="h-5 w-px shrink-0 bg-border" aria-hidden="true" />
            <nav className="min-w-0 flex-1 overflow-x-auto lg:flex-none" aria-label="因子视图">
              <div className="inline-flex min-w-max items-center gap-0.5 rounded-btn border border-border bg-surface/80 p-0.5">
                {(Object.keys(TABS) as Tab[]).map(tab => {
                  const mode = TABS[tab]
                  const Icon = mode.icon
                  const active = activeTab === tab
                  return (
                    <button
                      key={tab}
                      type="button"
                      onClick={() => changeTab(tab)}
                      aria-current={active ? 'page' : undefined}
                      className={`inline-flex h-7 items-center gap-1 rounded-[5px] px-1.5 text-[11px] font-medium transition-colors sm:gap-1.5 sm:px-2.5 sm:text-xs ${active
                        ? 'bg-accent text-white shadow-sm'
                        : 'text-secondary hover:bg-elevated hover:text-foreground'
                      }`}
                    >
                      <Icon className="hidden h-3.5 w-3.5 sm:block" />
                      {mode.title}
                    </button>
                  )
                })}
              </div>
            </nav>
          </div>
        )}
      />

      <main className="min-h-0 flex-1 px-3 pb-3 pt-3 lg:px-4 lg:pb-4 xl:overflow-hidden">
        {activeTab === 'inspect' && <FactorDiscovery focusFactor={focusFactor} />}
        {activeTab === 'editor' && <FactorEditor key={searchParams.get('edit') ?? ''} editId={searchParams.get('edit') ?? ''} />}
        {activeTab === 'composite' && <FactorComposite />}
        {activeTab === 'mining' && (
          <div className="h-full min-h-0 space-y-3 xl:overflow-y-auto">
            {/* [R53] 这三块是**包着的**, 不是三套并列的做法 —— 版面上并排放着最容易
                读成"选一个用", 于是有人一边开工作流一边手动开会话, 两路一起抢挖掘
                槽位, 看着就像卡住了。这一行把关系先说清楚。
                [R172] 上游把「挖掘」整页并进了因子页的这个 tab, 于是这三层跟着搬过来 ——
                只搬不改, 顺序与原挖掘页一致。 */}
            <LevelGuide />
            <WorkflowPanel
              kind="mining"
              extraConfig={{ asset_type: 'stock' }}
              hint="开了就不用管 —— AI 从内置因子里自己挑、自己配, 一次不达标就换一批重开, 直到达标或预算用尽"
            />
            <MiningAutopilot />
            <MiningWorkbench />
          </div>
        )}
        {activeTab === 'library' && (
          <FactorLibrary
            onInspect={factorId => {
              const next = new URLSearchParams(searchParams)
              next.set('tab', 'inspect')
              next.set('focus', factorId)
              setSearchParams(next)
            }}
            onEdit={factorId => {
              const next = new URLSearchParams(searchParams)
              next.set('tab', 'editor')
              next.set('edit', factorId)
              setSearchParams(next)
            }}
          />
        )}
      </main>

      {candidatesOpen && (
        <ResearchCandidatesDialog
          onClose={() => setCandidatesOpen(false)}
          onLoadStrategy={candidate => {
            setCandidatesOpen(false)
            // 跨页「载入复测」: 候选经 router state 交给回测策略页消费
            navigate('/backtest?tab=strategy', { state: { loadCandidate: candidate } })
          }}
        />
      )}
    </div>
  )
}
