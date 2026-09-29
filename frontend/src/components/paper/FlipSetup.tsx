/**
 * [fork R562] 「跟六态转折」挂进作者虚拟账户页的三个小零件: 开户时的开关、规则列表里的一行、
 * 新建规则表单里的「同时持有上限」。放在这里而不是写进 Paper.tsx —— 作者那个文件改得勤,
 * fork 在那边只留挂载点, 同步时冲突面小。
 */
import { useQuery } from '@tanstack/react-query'
import { X } from 'lucide-react'
import { api, type PaperFlipRule } from '@/lib/api'
import { QK } from '@/lib/queryKeys'
import { cn } from '@/lib/cn'

export const FLIP_RULE_NAME = '跟六态转折'

export function useFlipDefaults() {
  return useQuery({ queryKey: QK.paperFlipDefaults, queryFn: api.paperFlipDefaults, staleTime: Infinity })
}

/** 开户卡片里的开关。打开时把费率换成转折账户那一套(后端 flip_follow.FEES), 并露出同时持有上限。 */
export function FlipSetupToggle({ on, maxPos, onToggle, onMaxPos }: {
  on: boolean
  maxPos: string
  onToggle: (on: boolean, fees?: { commissionWan: string; stampQian: string; slippageBps: string }) => void
  onMaxPos: (v: string) => void
}) {
  const d = useFlipDefaults().data
  const fees = d && {
    commissionWan: String(+(d.fees.commission_pct * 10000).toFixed(2)),
    stampQian: String(+(d.fees.stamp_tax_pct * 1000).toFixed(2)),
    slippageBps: String(d.fees.slippage_bps),
  }
  return (
    <div className={cn('mt-3 rounded-btn border px-3 py-2.5 transition-colors', on ? 'border-accent/40 bg-accent/[0.06]' : 'border-border')}>
      <label className="flex cursor-pointer items-start gap-2">
        <input type="checkbox" checked={on} disabled={!fees} onChange={(e) => onToggle(e.target.checked, fees)}
               className="mt-0.5 h-3.5 w-3.5 cursor-pointer accent-accent" />
        <span className="min-w-0 text-xs">
          <span className="font-medium text-foreground">{FLIP_RULE_NAME}</span>
          <span className="mt-0.5 block text-micro leading-relaxed text-muted">
            只按收盘确认的转折自动买卖, 次日开盘成交; 不接手动单。费率换成佣金万 2 · 印花税万 5 · 滑点 5bps
          </span>
        </span>
      </label>
      {on && (
        <div className="mt-2 flex items-center gap-2 pl-5 text-xs">
          <span className="text-muted">同时最多持有</span>
          <MaxField value={maxPos} onChange={onMaxPos} cap={d?.cap ?? 50} />
          <span className="text-muted">只 · 每笔 = 净值 ÷ 这个数</span>
        </div>
      )}
    </div>
  )
}

export function MaxField({ value, onChange, cap }: { value: string; onChange: (v: string) => void; cap: number }) {
  return (
    <input type="number" min={1} max={cap} step={1} value={value} onChange={(e) => onChange(e.target.value)}
           className="w-16 rounded-btn border border-border bg-base px-2 py-1 font-mono text-sm outline-none focus:border-accent/50" />
  )
}

export const validMaxPos = (v: string, cap = 50) => Number.isInteger(Number(v)) && Number(v) >= 1 && Number(v) <= cap

/** 自动跟单规则列表里的一行 */
export function FlipRuleRow({ r, onToggle, onDelete }: { r: PaperFlipRule; onToggle: () => void; onDelete: () => void }) {
  return (
    <div className="flex items-center gap-2 rounded-btn px-2 py-1.5 text-xs transition-colors hover:bg-elevated/40">
      <span className={cn('h-1.5 w-1.5 shrink-0 rounded-full', r.enabled ? 'bg-bear' : 'bg-muted')} />
      <span className="shrink-0 truncate font-medium">{r.name}</span>
      {r.name !== FLIP_RULE_NAME && <span className="shrink-0 text-muted">{FLIP_RULE_NAME}</span>}
      <span className="min-w-0 flex-1 truncate text-micro text-muted" title="转多买入、转空清仓, 次日开盘成交">
        最多 {r.max_positions} 只 · 次日开盘
      </span>
      <button onClick={onToggle}
              className={cn('ml-auto shrink-0 rounded-btn px-2 py-0.5 text-micro transition-colors',
                r.enabled ? 'bg-bear/10 text-bear hover:bg-bear/20' : 'bg-elevated text-muted hover:text-secondary')}>
        {r.enabled ? '停用' : '启用'}
      </button>
      <button onClick={onDelete} className="shrink-0 rounded-btn p-0.5 text-muted hover:text-danger" title="删除规则">
        <X className="h-3.5 w-3.5" />
      </button>
    </div>
  )
}
