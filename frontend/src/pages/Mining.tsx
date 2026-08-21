import { useState } from 'react'
import { BookmarkCheck, Layers } from 'lucide-react'
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
        {/* [R53] 这三块是**包着的**, 不是三套并列的做法 —— 版面上并排放着最容易
            读成"选一个用", 于是有人一边开工作流一边手动开会话, 两路一起抢挖掘槽位,
            看着就像卡住了。这一行把关系先说清楚。 */}
        <LevelGuide />
        <WorkflowPanel
          kind="mining"
          extraConfig={{ asset_type: 'stock' }}
          hint="开了就不用管 —— AI 从内置因子里自己挑、自己配, 一次不达标就换一批重开, 直到达标或预算用尽"
        />
        <MiningAutopilot />
        <MiningWorkbench />
      </main>

      {candidatesOpen && <ResearchCandidatesDialog onClose={() => setCandidatesOpen(false)} />}
    </div>
  )
}

/**
 * 三层关系的一行说明。外层每"重开"一次就是开一个内层, 内层每"调一轮"就是按
 * 一份配置跑一次挖掘 —— 越往下越手动。
 *
 * 只讲关系, 不重复各面板自己的说明; 也刻意不做成可折叠 —— 它就一行, 而误解
 * 这三块的关系代价是真跑错(两路一起挖, 或者两边推同一个会话)。
 */
const LEVELS = [
  { name: '工作流', role: '全自动', desc: '反复开下面的会话, 不达标就换一批因子重开, 关页面照跑' },
  { name: 'AI 自动挖掘', role: '一个会话', desc: '一轮一轮盯着调: 跑 → AI 看结果 → 改配置 → 再跑' },
  { name: '挖掘配置', role: '一轮', desc: '自己选因子和档位, 跑一次' },
]

function LevelGuide() {
  return (
    <section className="rounded-card border border-border bg-surface px-3 py-2.5">
      <div className="mb-2 flex items-baseline gap-2">
        <Layers className="h-3.5 w-3.5 shrink-0 translate-y-px text-accent" />
        <h2 className="text-xs font-semibold text-foreground">这一页从上到下是三层, 一层套一层</h2>
        <span className="text-[10px] text-muted">越往下越手动 —— 不是三套并列的做法, 挑一层进就行</span>
      </div>
      <ol className="space-y-1">
        {LEVELS.map((l, i) => (
          <li key={l.name} className="flex items-baseline gap-2 text-[10px] leading-4"
            style={{ paddingLeft: `${i * 14}px` }}>
            <span className="shrink-0 text-muted/50">{i === 0 ? '' : '└'}</span>
            <span className="shrink-0 font-medium text-foreground">{l.name}</span>
            <span className="shrink-0 rounded-full bg-elevated px-1.5 text-[9px] text-secondary">{l.role}</span>
            <span className="min-w-0 text-muted">{l.desc}</span>
          </li>
        ))}
      </ol>
      <p className="mt-2 border-t border-border/60 pt-1.5 text-[10px] leading-4 text-muted">
        挖掘一次只跑得动一路。所以工作流开着的时候, 「开新会话」是停用的 ——
        再开一路不会更快, 它只会排在后面等着, 界面上看起来就像卡住了。
      </p>
    </section>
  )
}
