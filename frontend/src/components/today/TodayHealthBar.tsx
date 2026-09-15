/**
 * [fork 增强 R274] 数据自检条 —— **一切正常时一个像素都不占**。
 *
 * 常驻一条「运行正常」的绿条, 看两天就成了背景板, 真出问题那天照样被忽略。
 * 所以它只在数据陈了、或有区块没算出来时才现身。
 *
 * [R341] 从 `pages/Today.tsx` 拆出来独立成文件。原因是模拟盘也要用它 ——
 * **不复制一份**: 同一个自检条两处各写一遍, 措辞和口径必然漂(R319 那次
 * 「距今 N 天」改成「落后 N 个交易日」就得改两遍, 漏一处就是两页说法不一致)。
 */
import type { TodayHealth } from '@/lib/api'

export function TodayHealthBar({ h }: { h: TodayHealth }) {
  const stale = (h.stale_days ?? 0) >= 1
  if (h.ok && !stale) return null
  return (
    <div className={`rounded-lg border px-3 py-2 text-[11px] leading-relaxed ${
      h.blocks.length || stale
        ? 'border-warning/40 bg-warning/[0.07] text-warning'
        : 'border-border bg-elevated/30 text-muted'
    }`}>
      {stale && (
        <div>
          {/* [R319] 「落后 N 个交易日」, 不再是「距今 N 天」—— 后端已按交易日算,
              周末不会再亮; 这里的措辞要跟着口径走, 否则周一早上看到「落后 1 个
              交易日」还以为是自然日在数。 */}
          <b>这一页的数据是 {h.as_of} 的</b>,比最新该落盘的日 K 落后 {h.stale_days} 个交易日 ——
          收盘后没跑数据管道时就是这样,下面所有数字都还是那天的。
        </div>
      )}
      {h.blocks.length > 0 && (
        <div className={stale ? 'mt-1' : undefined}>
          <b>{h.blocks.length} 个区块没算出来</b>:
          {h.blocks.map(b => (
            <span key={b.key} className="ml-1.5" title={`${b.error}${b.n > 1 ? ` (共 ${b.n} 次)` : ''}`}>
              {b.cn}
            </span>
          ))}
          <span className="ml-1 opacity-80">—— 界面上这几块是空的,不是「今天没有」。</span>
        </div>
      )}
      {h.details.length > 0 && (
        <div className={`${h.blocks.length || stale ? 'mt-1 ' : ''}text-muted`}>
          另有 {h.details.length} 处只影响细节(少个标或少一列):
          {h.details.map(b => (
            <span key={b.key} className="ml-1.5" title={`${b.error}${b.n > 1 ? ` (共 ${b.n} 次)` : ''}`}>
              {b.cn}
            </span>
          ))}
        </div>
      )}
    </div>
  )
}
