/** [fork 增强] R147 AI 导读·优选的补充说明弹窗(可填可不填)。[R167] 从 Today.tsx 拆出。 */
import { useRef, useState } from 'react'
import { Loader2, Sparkles } from 'lucide-react'
import { Modal } from '@/components/Modal'

export function AiAskDialog({ initial, pending, onClose, onStart }: {
  initial: string
  pending: boolean
  onClose: () => void
  onStart: (note: string) => void
}) {
  const [note, setNote] = useState(initial)
  const startRef = useRef<HTMLButtonElement>(null)
  const EXAMPLES = ['今天只想看半导体', '重点看量能和回踩', '解释详细一点', '偏保守一些']
  return (
    <Modal
      onClose={onClose}
      labelledBy="ai-ask-title"
      initialFocusRef={startRef}
      panelClassName="w-[92vw] max-w-lg rounded-card border border-border bg-surface shadow-xl"
    >
      <div className="flex items-center gap-2 border-b border-border/60 px-4 py-3">
        <Sparkles className="h-4 w-4 text-violet-300" />
        <h2 id="ai-ask-title" className="text-sm font-medium text-foreground">AI 导读·优选</h2>
        <span className="text-[10px] text-muted">可以先说一句这次想让它重点看什么</span>
      </div>
      <div className="space-y-2.5 px-4 py-3">
        <textarea
          value={note}
          onChange={(e) => setNote(e.target.value.slice(0, 500))}
          onKeyDown={(e) => {
            // Ctrl/⌘+Enter 直接开始 —— 手还在输入框上时不必去够按钮
            if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') { e.preventDefault(); onStart(note.trim()) }
          }}
          rows={3}
          placeholder="不填也可以,直接点「开始分析」就是原来的行为"
          className="w-full resize-none rounded border border-border bg-base px-2.5 py-2 text-xs leading-relaxed text-foreground outline-none placeholder:text-muted/60 focus:border-accent/50"
        />
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-[10px] text-muted">试试:</span>
          {EXAMPLES.map(x => (
            <button
              key={x}
              onClick={() => setNote(x)}
              className="rounded-btn border border-border bg-base px-2 py-0.5 text-[10px] text-muted transition-colors cursor-pointer hover:text-foreground"
            >
              {x}
            </button>
          ))}
          <span className="ml-auto font-mono text-[10px] text-muted/60">{note.length}/500</span>
        </div>
        <p className="text-[10px] leading-relaxed text-muted/80">
          这句话只影响它<span className="text-foreground/80">关注哪几只、理由怎么写</span>;
          输出格式、逐条数字核对、宁缺毋滥这几条由系统守着,不会因为你怎么说而变。
          候选池也仍然由规则层给定 —— 点名了没进候选的票,它会在导读里说明为什么没进。
        </p>
      </div>
      <div className="flex items-center gap-2 border-t border-border/60 px-4 py-2.5">
        <button
          onClick={onClose}
          className="rounded-btn border border-border bg-base px-3 py-1 text-[11px] text-muted transition-colors cursor-pointer hover:text-foreground"
        >
          取消
        </button>
        <span className="text-[10px] text-muted/60">⌘/Ctrl + Enter 也可开始</span>
        <button
          ref={startRef}
          onClick={() => onStart(note.trim())}
          disabled={pending}
          className="ml-auto inline-flex items-center gap-1.5 rounded-btn border border-violet-400/30 bg-violet-400/15 px-3 py-1 text-[11px] text-violet-300 transition-colors cursor-pointer hover:bg-violet-400/25 disabled:opacity-50"
        >
          {pending ? <Loader2 className="h-3 w-3 animate-spin" /> : <Sparkles className="h-3 w-3" />}
          {note.trim() ? '带着这句话分析' : '开始分析'}
        </button>
      </div>
    </Modal>
  )
}

