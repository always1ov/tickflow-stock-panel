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

/**
 * 顶上那条「这只票现在的读数」。没有 geo 就整条不出现 —— 不摆空格子。
 *
 * [R219] **按话题分块, 一个话题一块。** 用户: 「每一列的内容应该就是一部分,
 * 而不是内容上面一部分下面一部分」。
 *
 * 原来是七个等宽格子平铺 + 底下一段独立的匀速基准。问题在于**「快慢」这一个
 * 话题被劈成了两半**: 数字(「这十天多走了 0.8 倍波动」)在格子里, 而它唯一
 * 能被核对的那句解释(「按匀速推中期该到 3.7, 实际 2.1」)掉到下面的段落里,
 * 中间还隔着「横了 12 天」。读的人得自己把同一件事从两处捡回来拼上。
 *
 * 现在四块, 每块自带标题, 同一话题的数与话都在自己那一块里:
 *
 *     位置 —— 三档在哪 + 离三条中线各多远
 *     间距 —— 短线比长线高(低)多少
 *     快慢 —— 这十天多走了多少 + 匀速基准那句对照
 *     重合 —— 横了多少天
 */
function LiveStrip({ geo, runs }: { geo: ChannelGeometry; runs?: ChannelRuns | null }) {
  const b = geo.baseline
  const a = geo.accel
  const accelCls = a.level === 'accel' ? 'text-red-400'
    : a.level === 'decel' ? 'text-emerald-400' : 'text-foreground'
  // crossing(两个尺度还没走到一边)是中性的 —— 不给红也不给绿, 见 R217
  const baseCls = b?.level === 'lead' ? 'text-red-400'
    : b?.level === 'lag' ? 'text-emerald-400' : 'text-foreground'
  const block = (label: string, hint: string, body: React.ReactNode) => (
    <div key={label} className="min-w-0 flex-1 basis-[210px] rounded-card border border-border/50 bg-elevated/30 px-2.5 py-1.5">
      <div className="text-[9px] text-muted" title={hint}>{label}</div>
      <div className="mt-0.5 text-[11px] leading-relaxed text-secondary">{body}</div>
    </div>
  )
  const num = (x: string, cls = 'text-foreground/90') =>
    <b className={cn('mx-0.5 font-mono font-medium', cls)}>{x}</b>
  return (
    <div className="flex flex-wrap gap-1.5">
      {block('位置', '短期、中期、长期各自在自己通道里是高、是中、还是低;以及价格离三条中线各多远(正的偏贵、负的偏便宜)',
        <>
          三档{num(geo.combo ?? '—')}· 离中线 短{num(geo.d.s.toFixed(1))}/ 中{num(geo.d.m.toFixed(1))}/ 长{num(geo.d.l.toFixed(1))}倍波动
        </>)}
      {block('间距', '短线比长线高(低)多少。接近零 = 方向还没出来;适中 = 趋势立住了;差得太多 = 已经走了很长一段',
        <>
          {geo.spread >= 0 ? '短线高出长线' : '短线低于长线'}
          {num(Math.abs(geo.spread).toFixed(1))}倍波动
        </>)}
      {/* 数字与它的对照句在同一块里 —— 这一块就是整个改动的由来 */}
      {block('快慢', '最近这十天比之前那一段多走(少走)了多少。零表示速度没变;不是越大越好, 冲得太猛常出现在一波的末尾',
        <>
          <span>
            这十天{a.gain_atr >= 0 ? '多' : '少'}走了{num(Math.abs(a.gain_atr).toFixed(1), accelCls)}倍波动
          </span>
          {b ? (
            <span className="mt-0.5 block text-[10px] text-muted">
              <b className={cn('mr-1', baseCls)}>{b.level_cn}</b>
              按匀速推,短期{geo.d.s.toFixed(1)} 时中期该到{num(b.expect_m.toFixed(1))},实际{num(b.actual_m.toFixed(1))}
            </span>
          ) : (
            <span className="mt-0.5 block text-[10px] text-muted/80">
              价格离短期中线太近,这时候比快慢没有意义 —— 不给结论比给个假数强
            </span>
          )}
        </>)}
      {!!runs?.compress_days && block('重合', '到今天为止连着多少天三种看法都认同一个价 —— 也就是这只票横了多久',
        <>横了{num(String(runs.compress_days))}天</>)}
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
