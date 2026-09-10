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
import { useQuery } from '@tanstack/react-query'
import { ChevronDown } from 'lucide-react'
import { api, type ChannelGeometry, type ChannelRuns, type ComboTableRow, type ReviewRow } from '@/lib/api'
import { StateTimeline } from '@/components/stock-analysis/StateTimeline'
import { BAND_CN, POS_LEGEND, bandCells, rangeHint } from '@/lib/reviewTimeline'
import { QK } from '@/lib/queryKeys'
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
      <div className="text-[11px] text-muted" title={hint}>{label}</div>
      <div className="mt-0.5 text-[13px] leading-relaxed text-secondary">{body}</div>
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
            <span className="mt-0.5 block text-[12px] text-muted">
              <b className={cn('mr-1', baseCls)}>{b.level_cn}</b>
              按匀速推,短期{geo.d.s.toFixed(1)} 时中期该到{num(b.expect_m.toFixed(1))},实际{num(b.actual_m.toFixed(1))}
            </span>
          ) : (
            <span className="mt-0.5 block text-[12px] text-muted/80">
              价格离短期中线太近,这时候比快慢没有意义 —— 不给结论比给个假数强
            </span>
          )}
        </>)}
      {!!runs?.compress_days && block('重合', '到今天为止连着多少天三种看法都认同一个价 —— 也就是这只票横了多久',
        <>横了{num(String(runs.compress_days))}天</>)}
    </div>
  )
}

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
function ComboGroups({ rows, here }: { rows: ComboTableRow[]; here: string | null }) {
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
export function ComboView({ geo, runs, rows = [] }: {
  geo?: ChannelGeometry | null
  runs?: ChannelRuns | null
  /** [R273] 逐日行 —— 只为画三档时间轴; 复盘接口本来就带着, 不必再要一次 */
  rows?: ReviewRow[]
}) {
  const q = useQuery({
    queryKey: QK.comboTable,
    queryFn: () => api.comboTable(),
    staleTime: 24 * 3600_000,   // 表是恒定的 —— 一天内不必再问
  })
  const here = geo?.combo ?? null
  return (
    <div className="min-h-0 flex-1 space-y-3 overflow-auto px-4 py-3">
      {!!geo && <LiveStrip geo={geo} runs={runs} />}

      {/* [R273] 三档各一条带子 —— **这和「通道结论」那条不是一回事**:
          那边画的是三档合成后的**那一句结论**, 这边画的是三档**各自**在哪。
          27 格讲的正是三档的组合, 所以这一栏的全景就该是三条并排 ——
          「短档先动、中档跟上、长档最后翻」这种节奏, 合成后的单条带子看不出来。 */}
      {rows.length > 0 && (
        <StateTimeline
          className="mx-0"
          hint={rangeHint(rows)}
          legend={POS_LEGEND}
          bands={(['s', 'm', 'l'] as const).map(k => ({
            label: BAND_CN[k].slice(0, 2),
            cells: bandCells(rows, k),
          }))}
        />
      )}

      {/* [R225] 27 行的表改成**分组卡片**。用户: 「把这部分做好看一点, 好丑。
          看看怎么显示更有价值而不是一堆数据」。

          原来是一张 27 行的表, 每行三行字, 而「几何含义」开头那半句
          (「短期在上沿、中期在上沿、长期在上沿」)和左边的「短中长」列
          **说的是同一件事** —— 27 行里印了 27 遍纯重复。整体是一堵字墙。

          三处改动:
            ① 「你现在在这一格」提成顶上的主卡, 不再是列表里一行高亮 ——
               打开这个弹窗第一件想知道的就是它
            ② 其余按**偏贵 / 中性 / 偏便宜**分三组, 而不是按字典序摊平 ——
               要的是"我这一格在贵贱谱系的哪一端, 旁边是什么"
            ③ 重复的那半句退到悬停; 常见度画成点不写字;
               七个「几乎不出现」的默认收起来 */}
      <ComboGroups rows={q.data?.rows ?? []} here={here} />
    </div>
  )
}
