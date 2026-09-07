/**
 * [fork 增强 R53] 挖掘三层关系的一行说明。
 *
 * [R172] 原在 pages/Mining.tsx —— 上游 v0.2.3 把「挖掘」整页并进了因子页的
 * mining tab 并删掉了那个文件, 于是这块单独成文件搬过来。单独成件而不是塞进
 * 上游的 Factors.tsx: 那是上游文件, 塞进去以后每次同步都要在这儿解冲突。
 */
import { Layers } from 'lucide-react'

const LEVELS = [
  { name: '工作流', role: '全自动', desc: '反复开下面的会话, 不达标就换一批因子重开, 关页面照跑' },
  { name: 'AI 自动挖掘', role: '一个会话', desc: '一轮一轮盯着调: 跑 → AI 看结果 → 改配置 → 再跑' },
  { name: '挖掘配置', role: '一轮', desc: '自己选因子和档位, 跑一次' },
]

export function LevelGuide() {
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
            <span className="shrink-0 rounded-btn bg-elevated px-1.5 text-[9px] text-secondary">{l.role}</span>
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
