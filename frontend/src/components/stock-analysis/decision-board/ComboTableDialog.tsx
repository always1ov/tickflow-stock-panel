/**
 * [R203] 27 种组合速查 —— 「系统结论」与「几何含义」并排。
 *
 * 用户: 「我要看到系统结论和几何含义、偏离基准加速度等等」。
 *
 * ## 三件事摆在一起才有用
 *
 * ① **这只票现在在哪一格** —— 顶上那条读数带。三档位置、离各自中线多远、
 *    匀速基准对照、快慢、间距、挤了几天。
 * ② **这一格系统怎么说** —— 表里高亮的那一行。
 * ③ **别的格子长什么样** —— 其余 26 行。有了对照, 「短线冲高」才知道是
 *    偏贵那一头还是偏便宜那一头。
 *
 * 只给 ② 是现在决策台的样子(一个徽标), 只给 ① 是一堆数。三个一起才是
 * 「我现在在哪、这意味着什么、旁边是什么」。
 *
 * 表本身**由后端生成**(`/api/stock-analysis/combo-table`), 不在前端写死一份 ——
 * 誊抄的表会漂: 底层哪天改了措辞, 这里就开始说假话, 而且没有任何东西会报错。
 */
import { useQuery } from '@tanstack/react-query'
import { X } from 'lucide-react'
import { api, type ChannelGeometry, type ChannelRuns } from '@/lib/api'
import { QK } from '@/lib/queryKeys'
import { cn } from '@/lib/cn'

const TONE_CLS: Record<string, string> = {
  sell: 'text-red-400',
  buy: 'text-sky-300',
  hold: 'text-amber-400',
  avoid: 'text-muted',
  watch: 'text-secondary',
}

/** 顶上那条「这只票现在的读数」。没有 geo 就整条不出现 —— 不摆空格子。 */
function LiveStrip({ geo, runs }: { geo: ChannelGeometry; runs?: ChannelRuns | null }) {
  const b = geo.baseline
  const a = geo.accel
  const cell = (label: string, value: string, title?: string, cls?: string) => (
    <div key={label} className="min-w-0 flex-1 basis-[92px] bg-elevated/40 px-2.5 py-1.5" title={title}>
      <div className="truncate text-[9px] text-muted">{label}</div>
      <b className={cn('block truncate font-mono text-[12px] font-medium', cls ?? 'text-foreground')}>{value}</b>
    </div>
  )
  return (
    <div className="space-y-1.5">
      <div className="flex flex-wrap gap-px overflow-hidden rounded-card bg-border/70">
        {cell('三档位置', geo.combo ?? '—', '短期、中期、长期各自在自己通道里是高、是中、还是低')}
        {cell('离短期中线', geo.d.s.toFixed(1),
          '眼下价格离短期那条中线多远,单位是倍日常波动。正的偏贵、负的偏便宜')}
        {cell('离中期中线', geo.d.m.toFixed(1), '同上,按中期那条中线算')}
        {cell('离长期中线', geo.d.l.toFixed(1), '同上,按长期那条中线算')}
        {cell('三线间距', geo.spread.toFixed(1),
          '短线和长线离多远,带方向。接近零=方向还没出来;适中=趋势立住了;太大=已经走了很长一段')}
        {cell('快慢变化', `${a.gain_atr >= 0 ? '+' : ''}${a.gain_atr.toFixed(1)}`,
          '最近这十天比之前那一段多走(少走)了多少倍日常波动。零表示速度没变',
          a.level === 'accel' ? 'text-red-400' : a.level === 'decel' ? 'text-emerald-400' : undefined)}
        {!!runs?.compress_days && cell('已经挤了', `${runs.compress_days} 天`,
          '到今天为止连着多少天三种看法都一致 —— 这只票横了多久')}
      </div>
      {/* [R203] 匀速基准对照 —— 这句话是可以自己核对的, 而「加速度 −0.08」不是。 */}
      {b ? (
        <p className="rounded border border-border/50 bg-elevated/25 px-2.5 py-1.5 text-[10px] leading-relaxed text-secondary">
          <b className={cn('mr-1.5',
            b.level === 'lead' ? 'text-red-400' : b.level === 'lag' ? 'text-emerald-400' : 'text-foreground')}>
            {b.level_cn}
          </b>
          按「一路匀速走」推,短期离中线 {geo.d.s.toFixed(1)} 时中期该到
          <b className="mx-1 font-mono text-foreground/90">{b.expect_m.toFixed(1)}</b>
          ,实际
          <b className="mx-1 font-mono text-foreground/90">{b.actual_m.toFixed(1)}</b>
          —— {b.why}
        </p>
      ) : (
        <p className="rounded border border-border/50 bg-elevated/25 px-2.5 py-1.5 text-[10px] text-muted">
          价格离短期中线太近,这时候比「快了还是慢了」没有意义 —— 不给结论比给个假数强。
        </p>
      )}
    </div>
  )
}

export function ComboTableDialog({ onClose, geo, runs, name }: {
  onClose: () => void
  geo?: ChannelGeometry | null
  runs?: ChannelRuns | null
  name?: string
}) {
  const q = useQuery({
    queryKey: QK.comboTable,
    queryFn: () => api.comboTable(),
    staleTime: 24 * 3600_000,   // 表是恒定的 —— 一天内不必再问
  })
  const here = geo?.combo ?? null
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm"
         onClick={onClose}>
      <div role="dialog" aria-modal="true"
           className="flex max-h-[88vh] w-full max-w-4xl flex-col overflow-hidden rounded-lg border border-border bg-surface shadow-2xl"
           onClick={e => e.stopPropagation()}>
        <header className="flex items-center gap-2 border-b border-border px-4 py-3">
          <span className="text-sm font-medium text-foreground">
            三档组合速查{name ? ` · ${name}` : ''}
          </span>
          <span className="text-[10px] text-muted">27 种组合,系统对每一种怎么说</span>
          <button onClick={onClose} className="ml-auto text-muted hover:text-foreground">
            <X className="h-4 w-4" />
          </button>
        </header>

        <div className="min-h-0 flex-1 space-y-3 overflow-auto px-4 py-3">
          {!!geo && <LiveStrip geo={geo} runs={runs} />}

          <table className="w-full text-[11px]">
            <thead className="sticky top-0 bg-surface">
              <tr className="border-b border-border/60 text-[10px] text-muted">
                <th className="w-16 py-1.5 text-left font-normal">短中长</th>
                <th className="w-20 py-1.5 text-left font-normal">系统结论</th>
                <th className="py-1.5 text-left font-normal">几何含义</th>
              </tr>
            </thead>
            <tbody>
              {(q.data?.rows ?? []).map(r => {
                const on = r.combo === here
                return (
                  <tr key={r.combo}
                      className={cn('border-b border-border/25 align-top',
                        on && 'bg-accent/10 ring-1 ring-inset ring-accent/40')}>
                    <td className="py-1.5 font-mono tabular-nums text-foreground/90">
                      {r.combo}
                      {on && <span className="ml-1 text-[9px] text-accent">现在</span>}
                    </td>
                    <td className={cn('py-1.5', r.verdict ? TONE_CLS[r.verdict.tone] ?? 'text-muted' : 'text-muted/50')}>
                      {r.verdict?.title ?? '（无结论）'}
                    </td>
                    <td className="py-1.5 leading-relaxed text-secondary">
                      <span className="text-muted/80">{r.shape}</span>
                      <span className="mx-1 text-muted/50">·</span>
                      {r.read}
                      {!!r.note && (
                        <span className="mt-0.5 block text-[10px] leading-relaxed text-amber-300/85">
                          ▸ {r.note.title}:{r.note.detail}
                        </span>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
          {q.isLoading && <p className="py-4 text-center text-[11px] text-muted">加载中…</p>}
          <p className="pt-1 text-[10px] leading-relaxed text-muted/70">
            「系统结论」这一列是**直接调底层判定生成的**,不是誊抄 —— 底层怎么说,这里就怎么显示,
            不会有一份对照表偷偷说着过时的话。带 ▸ 的是补充:那几格底层的措辞与这一格的事实对不太上。
          </p>
        </div>
      </div>
    </div>
  )
}
