/** [fork 增强] Keltner 三档组合结论的小标签。机会区详情与持仓体检共用。[R167] 从 Today.tsx 拆出。 */
import type { KeltnerVerdict } from '@/lib/api'
import { VerdictHover } from '@/components/stock-analysis/VerdictHover'

const VERDICT_TAG_CLS: Record<KeltnerVerdict['tone'], string> = {
  sell: 'bg-red-400/20 text-red-300',
  buy: 'bg-sky-400/15 text-sky-300',
  hold: 'bg-amber-400/20 text-amber-300',
  avoid: 'bg-border/40 text-muted',
  watch: 'bg-border/40 text-muted',
}

/**
 * 三档通道档位标 —— 挂在机会区每条候选上。
 *
 * 这里的语气和持仓那侧相反: 同一个"到上沿", 持仓是止盈时机, 买入是追高。
 * 所以徽标只放结论标题, 具体怎么解读由悬停里那句话说清。
 */
export function VerdictTag({ v, holding }: { v?: KeltnerVerdict | null; holding?: boolean }) {
  if (!v) return null
  // [R49] 原生 title 换成分段排版的悬停卡片。note 这句两侧不一样, 所以由调用方给 ——
  // 同一个"到上沿", 持仓侧是止盈时机, 买入候选侧是追高, 写死在 verdict 里对不上两边。
  return (
    <VerdictHover
      v={v}
      note={holding
        ? '你正持有它 —— 到上沿是止盈时机, 到下沿才谈加仓。'
        : '这是买入候选 —— 通道位置影响的是"这一笔值不值"。与持仓侧相反: 持仓到上沿是止盈时机, 买入到上沿是追高。'}
    >
      <span className={`ml-1.5 cursor-help rounded px-1 py-0.5 text-[9px] ${VERDICT_TAG_CLS[v.tone]}`}>
        {v.title}
        {/* [R246] 这一档挂了几天 —— 第 1 天与第 20 天该做的事完全不同 */}
        {!!v.days && <span className="ml-0.5 opacity-70">已{v.days}天{v.capped ? '+' : ''}</span>}
      </span>
    </VerdictHover>
  )
}

