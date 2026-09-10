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
 *
 * ## [R228] 从**弹窗**降成**视图**
 *
 * 用户: 「这两个弹窗也整合到一起, 外部入口就变成一个按钮了, 这样打开好看」。
 *
 * 它和逐日复盘弹窗讲的是同一只票的同一件事(通道), 只是一个横着看 27 格、
 * 一个竖着看 120 天 —— 却是两个各自铺满屏幕的模态, 从决策台同一个格子里
 * 用两个挨着的按钮分别打开。现在并进复盘弹窗当第三个页签(`ReviewTab`),
 * 这个文件只留视图, 外壳(遮罩/标题/关闭)交给那边。
 */
import { useState } from 'react'
import { ChevronDown } from 'lucide-react'
import { type ComboTableRow, type ReviewRow } from '@/lib/api'
import { cn } from '@/lib/cn'
import { storage } from '@/lib/storage'
import { ReviewDisclosure } from '@/components/stock-analysis/ReviewDisclosure'

const TONE_CLS: Record<string, string> = {
  sell: 'text-red-400',
  buy: 'text-sky-300',
  hold: 'text-amber-400',
  avoid: 'text-muted',
  watch: 'text-secondary',
}

// [R203 加, R296 删] `LiveStrip`(位置/间距/快慢/重合四个读数块)删掉了。
// **它是 `EvidencePanel` 那七行读数的第二份**: 同一批量, 一份由后端 `explain`
// 出文案(带 why), 一份在前端拿 `geo` 现排 —— 而且两处措辞还不一样
// (「间距」vs「三线间距」、「快慢」vs「最近快慢」、「重合」vs「连着挤了」)。
// 合并时正好撞上, 留后端那一份: 它更全(七行), 而且文案有唯一出处。


/** 常见度画成三颗点 —— 写字占地方, 而这一列只需要"多还是少"。 */
function Dots({ rarity }: { rarity?: string }) {
  const n = rarity?.startsWith('很常见') ? 3 : rarity === '常见' ? 2
    : rarity === '偶尔' ? 1 : 0
  return (
    <span className="inline-flex gap-[2px]" title={`这一格${rarity ?? ''}`}>
      {[0, 1, 2].map(i => (
        <i key={i} className={cn('h-[3px] w-[3px] rounded-full',
          i < n ? 'bg-amber-300/70' : 'bg-border')} />
      ))}
    </span>
  )
}

/** 一行 —— 一格组合。`hero` 是"你现在在这一格"那张主卡。 */
function Row({ r, hero }: { r: ComboTableRow; hero?: boolean }) {
  return (
    <div className={cn('flex gap-2.5 px-2.5 py-1.5',
      hero ? 'rounded-card border border-accent/40 bg-accent/10'
        : 'border-b border-border/20 last:border-0')}>
      <span className={cn('shrink-0 font-mono tabular-nums',
        hero ? 'text-[13px] text-foreground' : 'text-[13px] text-foreground/85')}
        title={r.shape}>
        {r.combo}
      </span>
      <span className="mt-[5px] shrink-0"><Dots rarity={r.rarity} /></span>
      <span className={cn('w-[4.5rem] shrink-0 text-[13px]',
        r.verdict ? TONE_CLS[r.verdict.tone] ?? 'text-muted' : 'text-muted/50')}>
        {r.verdict?.title ?? '（无结论）'}
      </span>
      <span className="min-w-0 flex-1 text-[13px] leading-relaxed text-secondary">
        {r.read}
        {!!r.note && (
          <span className="mt-0.5 block text-[12px] leading-relaxed text-amber-300/85">
            ▸ {r.note.title}:{r.note.detail}
          </span>
        )}
      </span>
    </div>
  )
}

// 三组。按**偏贵 / 中性 / 偏便宜**分, 而不是按字典序 —— 打开这张表想知道的是
// "我这一格在贵贱谱系的哪一端, 旁边是什么", 字典序回答不了这个。
const GROUPS = [
  { key: 'sell', cn: '偏贵 · 别在这加', tones: ['sell', 'avoid'], cls: 'text-red-400/80' },
  { key: 'mid', cn: '中性 · 还不到动手的时候', tones: ['hold', 'watch', ''], cls: 'text-secondary' },
  { key: 'buy', cn: '偏便宜 · 低吸侧', tones: ['buy'], cls: 'text-sky-300/80' },
] as const

/** 我这一格落在贵贱谱系的哪一段 —— 收起对照表之后, 由这一行来回答。 */
function whichGroup(r: ComboTableRow | null) {
  if (!r) return null
  return GROUPS.find(g => g.tones.includes((r.verdict?.tone ?? '') as never)) ?? null
}

/**
 * [R270] 其余 26 格**默认收起**。
 *
 * 用户: 「尤其是组合速查好多内容都是展示和个股当前状态没关系的, 相当于很多说明了」。
 * 说得准: 打开这一页, 除了「你现在在这一格」那一张, 剩下二十多行讲的是**别的格子**
 * 什么样 —— 那是查表用的参考资料, 和这只票今天的状态没有关系, 却铺满了整屏。
 *
 * R225 当初摆开它们是有道理的(「有了对照, 『短线冲高』才知道是偏贵那一头还是偏
 * 便宜那一头」), 但**那个对照只需要一句话**, 不需要二十多行: 收起时用一行说清
 * 「你这一格属于偏贵/中性/偏便宜哪一段、另外两段各有几格」, 想逐格看再展开。
 */
export function ComboGroups({ rows, here }: { rows: ComboTableRow[]; here: string | null }) {
  const [showRare, setShowRare] = useState(false)
  const [open, setOpen] = useState(() => storage.reviewComboRestOpen.get(false))
  const mine = rows.find(r => r.combo === here) ?? null
  const mineGroup = whichGroup(mine)
  const rare = (r: ComboTableRow) => r.rarity === '几乎不出现'
  const rest = rows.filter(r => r.combo !== here)
  const hiddenCount = rest.filter(r => rare(r) && !showRare).length
  const counts = GROUPS.map(g => ({
    g, n: rest.filter(r => g.tones.includes((r.verdict?.tone ?? '') as never)).length,
  })).filter(x => x.n > 0)
  return (
    <div className="space-y-3">
      {mine ? (
        <div>
          <div className="mb-1 flex flex-wrap items-baseline gap-x-2 text-[12px] text-muted">
            <span>你现在在这一格</span>
            {mineGroup && (
              <span className={mineGroup.cls}>· 落在「{mineGroup.cn}」这一段</span>
            )}
          </div>
          <Row r={mine} hero />
        </div>
      ) : (
        <div className="rounded-card border border-border/40 px-2.5 py-2 text-[12px] text-muted">
          这只票今天算不出三档组合 —— 下面是 27 格的对照表
        </div>
      )}

      <ReviewDisclosure
        label={`其余 ${rest.length} 格`}
        note={`(查表用的对照, 与这只票今天无关 —— ${counts.map(x => `${x.g.cn.split(' · ')[0]} ${x.n}`).join(' / ')})`}
        defaultOpen={open}
        onOpenChange={(v) => { setOpen(v); storage.reviewComboRestOpen.set(v) }}
        className="mx-0"
      >
        <div className="space-y-3">
          {GROUPS.map(g => {
            const items = rest.filter(r => g.tones.includes((r.verdict?.tone ?? '') as never))
              .filter(r => showRare || !rare(r))
            if (!items.length) return null
            return (
              <div key={g.key}>
                <div className={cn('mb-0.5 text-[12px]', g.cls)}>{g.cn}</div>
                <div className="overflow-hidden rounded-card border border-border/40">
                  {items.map(r => <Row key={r.combo} r={r} />)}
                </div>
              </div>
            )
          })}
          {(hiddenCount > 0 || showRare) && (
            <button type="button" onClick={() => setShowRare(v => !v)}
                    className="flex items-center gap-1 text-[12px] text-muted hover:text-foreground">
              <ChevronDown className={cn('h-3 w-3 transition-transform', showRare && 'rotate-180')} />
              {showRare ? '收起几乎不出现的那几格'
                : `还有 ${hiddenCount} 格几乎不出现(中线跑到短线与长线的另一侧, 几何上近乎不可能)`}
            </button>
          )}
        </div>
      </ReviewDisclosure>
    </div>
  )
}

/**
 * 「组合速查」页签的内容。**没有外壳** —— 遮罩、标题、关闭按钮都在
 * `StockReviewDialog` 那边, 这里只负责内容(R228)。
 *
 * `geo`/`runs` 由复盘接口的 `channel` 给, 与它逐日表末行是同一条路算出来的
 * (`review_service._channel` 的注释)—— 所以三个页签看到的是同一天的同一份读数。
 */
/**
 * [R294] 这只票在**当前这一格**里待过几段、共几天、之后 5 日普遍怎么走。
 *
 * 用户: 「组合速查也要, 它是按照位置为核心」—— 那么这一页的头一行就该是
 * **位置本身**: 你在哪一格、这一格在这只票身上历来是什么光景。
 *
 * 按**段**不按天(R177 的老规矩): 一段连着 8 天的「上中下」算 1 次; 按天算的话
 * 那 8 天的前瞻窗口互相重叠, 次数会被撑大, 很薄的结论看着挺扎实。
 */
export function comboHistory(rows: ReviewRow[], here: string | null) {
  if (!here) return null
  // rows 是新→旧, 这里按时间正序走
  const asc = [...rows].reverse()
  let segs = 0, days = 0, prev: string | null | undefined
  const fwd: number[] = []
  asc.forEach((r, i) => {
    if (r.combo !== here) { prev = r.combo; return }
    if (prev !== here) segs += 1
    days += 1
    // 段末那天的前瞻收益 —— 与「通道结论」那边取段末同一个道理:
    // 真正该问的是"它最后一次说完之后怎么样了"
    const next = asc[i + 1]
    if ((!next || next.combo !== here) && r.fwd != null) fwd.push(r.fwd)
    prev = r.combo
  })
  const avg = fwd.length ? fwd.reduce((a, b) => a + b, 0) / fwd.length : null
  return { segs, days, scored: fwd.length, avg, win: fwd.filter(v => v > 0).length }
}


// [R228 加, R296 删] `ComboView`(「组合速查」那个页签的外壳)在这里删掉了。
// 用户: 「组合速查合并到通道结论里面去」。**本来就该合** —— 穷举 125 种三档位置
// 验过: 通道结论是这 27 格的**纯函数**(同一个三字码永远给同一个结论, 零冲突),
// 两个页签监控的是同一个对象的两层。合并之后:
//   你在哪一格 / 这一格历来  → 「通道结论」头部卡的「现在」行(这只票的事)
//   27 格谱系                → 「说明」抽屉里一节(恒定的表, 查表用的参考)
// 这条分界与 R292 定的是同一条: **常驻的是这只票的, 抽屉里是背景资料。**

