/**
 * [R431] 个股弹窗「复盘」。
 *
 * [R759] 用户: 「复盘那部分, 保持现在四列排版不变了, 里面内容布局先恢复最开始的样子,
 *   复盘内部的排版要排好显示出所有信息, 我还没想好怎么重做」——
 *   弹窗在 2xl 的四栏(复盘 | 现状 | 主图 | 价位)不动; 复盘栏内部回到 R431 最初那一版
 *   的三块: 逐日复盘(六态与通道两套动作都摆) / 两套买卖的对比 / 六个状态的历史表现。
 *   R749/R750 那版把收盘价、通道档位、成交→了结都收进了悬停, 只剩五列, 信息读不全。
 *
 *   窄列(常驻左列 420~460)摊不开八列, 每天拆成两行:
 *     第一行: 日期 · 收盘 · 涨跌 · 六态状态(第几天 / 细分档 / 转折)
 *     第二行: 通道档位 · 六态与通道的动作 · 成交→了结 · 结果
 *   六态历史同样一行拆两行: 出现次数与天数在上, 段内涨跌与走完后 N 天在下。
 *
 * 数据仍是同一个查询(`useStockReview`)，天数跟头部的 60 / 120 / 250 日走。
 * 判定与文案仍以 R440「不多也不少」为准：这里只改排版与读数, 不改判定。
 *
 * [R792] 用户: 「复盘部分简化保留重点」「内容都不可以折叠, 逐日复盘里面别搞滚动」——
 *   重点先行: 两套买卖对比 → 当前状态那只票上的记录 → 逐日明细 → 通道证据;
 *   全部常开不折叠(六态显示全表、逐日全部铺开), 去掉内滚与三段长脚注(细节留在 title 悬停)。
 *
 * [R793] 用户: 「复盘里面密密麻麻好多文字…出个简洁显示的方案, 但不能丢失原有所有显示内容」——
 *   三块全部改成「表头 + 单行多列」: 重复的「出现过/共/这段里/走完后」前缀收进表头,
 *   逐日每天从两行压成一行; 规则、成交价、样本提示等原文不删, 全部挂到 title 悬停。
 */
import { useMemo, useState } from 'react'
import { Loader2 } from 'lucide-react'
import type { ReviewRow, ReviewStateHistory, StockReview } from '@/lib/api'
import { cn } from '@/lib/cn'
import { TREND_FILL } from '@/lib/reviewTimeline'
import { trendBadgeCls } from '@/components/stock-analysis/TrendStateBar'
import { VerdictHover } from '@/components/stock-analysis/VerdictHover'
import {
  EvidencePanel, LimitTag, SUB_STATE_TIP, VERDICT_CLS,
  chgCls, pct, useStockReview,
} from '@/components/stock-analysis/StockReviewDialog'
import {
  LegAct, LegFill, LegResult, legResultCls, legsByFlipDate,
  type Leg,
} from '@/components/stock-analysis/FlipTradesPanel'
import { PILL, PILL_IDLE, PILL_ON } from './pill'
import { SectionTitle, TYPE } from '@/components/ui'

/** 走完不到这么多段, 「这只票的表现」就提醒样本太少(与脚注同一个数) */
const THIN = 3

export function ReviewSection({ symbol, days, compact = false }: { symbol: string; days: number; compact?: boolean }) {
  const q = useStockReview(symbol, days)
  const d: StockReview | undefined = q.data
  const ok = !!d && !d.error
  // [R840] 左栏重排: 两段之间只留一条分隔线(靠 DailyCard 自己的 border-t), 这里不再叠 mt ——
  // space-y 和块内 mt 同时存在时, 间距会变成两份, 左栏一列就松紧不匀。
  const gaps = compact ? 'space-y-4' : 'space-y-6'

  return (
    <section>
      <SectionTitle title="复盘" sub={ok ? `近 ${d.days} 天怎么走的` : undefined} />
      <div className={cn('mt-2', gaps)}>
        {q.isLoading && (
          <div className="flex items-center justify-center gap-2 rounded-card border border-border bg-surface py-16 text-xs text-muted">
            <Loader2 className="h-4 w-4 animate-spin" /> 正在回算 {days} 个交易日…
          </div>
        )}
        {q.isError && (
          <div className="rounded-card border border-border bg-surface px-4 py-16 text-center text-xs text-danger">复盘数据加载失败</div>
        )}
        {d?.error && (
          <div className="rounded-card border border-border bg-surface px-4 py-16 text-center text-xs text-muted">{d.error}</div>
        )}
        {ok && <HistoryCard d={d} compact={compact} />}
        {ok && <DailyCard d={d} />}
      </div>
    </section>
  )
}

// ===== 1. 逐日复盘 =====

function DailyCard({ d }: { d: StockReview }) {
  // [R431] 两个筛选各管各的, 都开 = 两类日子都留(并集)。都关 = 全部
  const [marked, setMarked] = useState(false)
  const [shifted, setShifted] = useState(false)
  const six = useMemo(() => legsByFlipDate(d.flip_trades), [d.flip_trades])
  const ch = useMemo(() => legsByFlipDate(d.verdict_trades), [d.verdict_trades])
  const rows = useMemo(() => {
    const all = d.rows ?? []
    if (!marked && !shifted) return all
    return all.filter(r =>
      (marked && (r.limit_up || r.limit_down || r.broken_limit_up || !!r.trend?.flipped))
      || (shifted && !!r.verdict_flipped))
  }, [d, marked, shifted])

  return (
    <div className="border-t border-border/60 pt-4">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <span className={TYPE.card}>逐日复盘</span>
        {/* [R826] 正文只留区间与天数, 阈值与来源进悬停 */}
        <span className="cursor-help font-mono text-micro leading-4 text-muted"
              title={`六态阈值 ${(d.threshold * 100).toFixed(0)}%${d.threshold_source !== 'default' ? `（${d.threshold_source}）` : '（默认）'}`}>
          {d.start} ~ {d.end} · {d.days} 日
        </span>
        {/* [R832] 两个筛选挪到标题这一行(原来自己占一行, 把表头又往下压了一行) */}
        <span className="ml-auto flex flex-wrap items-center gap-2">
          <button type="button" onClick={() => setMarked(v => !v)} aria-pressed={marked}
                  title="只留下有涨跌停、或六态转折的那些天 —— 其余日子状态没变, 复盘时没有信息"
                  className={`${PILL} ${marked ? PILL_ON : PILL_IDLE}`}>
            只看有事的日子
          </button>
          <button type="button" onClick={() => setShifted(v => !v)} aria-pressed={shifted}
                  title="只留下通道档位换过的那些天 —— 其余日子档位没变, 复盘时没有信息"
                  className={`${PILL} ${shifted ? PILL_ON : PILL_IDLE}`}>
            只看换档的日子
          </button>
        </span>
      </div>

      {/* [R832] 重排: 日期/收盘/涨跌/趋势·档位 一行到底, 事件另起一行**只在真有动作的那天**出现。
          原来六列挤在 430px 里, 趋势与档位互相挤压、事件天天换行, 反而每行都不一样高。 */}
      <div className="mt-1.5 border-t border-border/60">
        <div className={cn(DAY_COLS, 'sticky top-0 z-10 border-b border-border/40 bg-surface py-1.5 text-micro text-muted')}>
          <span>日期</span>
          <span className="text-right">收盘</span>
          <span className="text-right">涨跌</span>
          <span title="六态状态 · 通道档位；行首琥珀竖线 = 翻转或换档">趋势 · 档位</span>
        </div>
        {rows.map(r => (
          <DayRow key={r.date} r={r} six={six.get(r.date)} ch={ch.get(r.date)} />
        ))}
        {rows.length === 0 && (
          <div className="px-2 py-10 text-center text-xs text-muted">这段时间里没有这类日子</div>
        )}
      </div>
    </div>
  )
}

/** [R832] 每天一行: 日期 · 收盘 · 涨跌 · 趋势·档位; 事件(六/通)另起一行, 只在有动作的那天出现。
 *  [R835] 涨跌列加宽到 5.6rem 并禁止换行 —— 「+10.02%」后面那枚「3板」原来被挤到下一行,
 *  看起来像又一天的收盘价。
 *  [R836] 用户: 「每一行都密密麻麻」。这一版只做**减法**, 不加东西:
 *   ① 「(次级回升)」这种括注搬进悬停 —— 它本来就被算进自然回升, 写在行里只是多一层括号;
 *   ② 「转折」「换档」两个琥珀词改成行首一道 2px 竖线: 同一天那行本来就有琥珀底,
 *      再写两个字等于同一件事说三遍; 竖线的含义在表脚注里说明;
 *   ③ 天数的「第 N 天」从徽标里拆出来做灰字, 徽标变短, 行内的块状感跟着降;
 *   ④ 行高 py-1.5 → py-2.5。
 *  [R842] 用户: 「行距列距离这些都调整」—— 列距 8 → 10, 日期/收盘/涨跌三列之间跟着松一档;
 *  列宽本身(2.4 / 3.1 / 5.6rem)不动, 那是按最长取值定的, 再收就会换行。
 *  [R844] 用户: 「逐日复盘的每列也要调整」。和历史表现同一套办法: 列**按比例**摊开,
 *  不再让「状态」一列吃掉全部富余(窗口一大, 三个数字挨在左边 200 里, 右边空 400)。
 *    · 下限仍按最长取值定死: 日期 33 / 收盘 46 / 涨跌 84(最长「10板 +10.02%」), 低于它必换行;
 *    · 比例 日期 0.55 / 收盘 0.65 / 涨跌 1.1 / 状态 3.0 —— 富余先给状态徽标, 窄栏时自动回到下限;
 *    · 列距 10 → 12(与历史表现同一个 12), 右侧 `pr-2` 8px —— 表头与数据一起内缩, 分隔线仍到边;
 *    · 涨跌格内「标记 + 百分比」原来叠了 8px(LimitTag 自带 ml-1 + 父级 gap-x-1), 收到 4px,
 *      腾出的 4px 正好让「10板 +10.02%」在 5.6rem 里不换行。 */
const DAY_COLS = 'grid grid-cols-[minmax(2.4rem,0.55fr)_minmax(3.1rem,0.65fr)_minmax(5.6rem,1.1fr)_minmax(0,3fr)] items-baseline gap-x-3 pr-2'

/** [R845] 用户: 「逐日复盘里面每行的悬浮字的描述也要精简」—— 一行一句, 去掉「这一段」
 *  「按最后一天收盘记」这类可省的修饰; 日期只留月-日(年份这一列本来就没有)。
 *  信息一条没丢: 动作 / 进出价 / 盈亏 / 天数 / 顺延。 */
function legTip(src: string, l: Leg): string {
  const ret = l.side === '多头' ? pct(l.ret) : `空仓 ${pct(l.ret)}`
  return `${src} ${l.act} ${l.enter_date.slice(5)} ${l.enter_price.toFixed(2)} → ${l.exit_date.slice(5)} ${l.exit_price.toFixed(2)}`
    + ` · ${ret} · ${l.bars}天`
    + `${l.open_ended ? ' · 还在走, 按最新收盘记' : ''}`
    + `${l.delayed ? ` · 顺延${l.delayed}日成交` : ''}`
}

function DayRow({ r, six, ch }: { r: ReviewRow; six?: Leg; ch?: Leg }) {
  const legs = ([['六态', six], ['通道', ch]] as const)
    .filter((x): x is readonly ['六态' | '通道', Leg] => !!x[1])
  return (
    <div className={cn(
      'relative border-b border-border/30 py-2.5 pl-2',
      (r.trend?.flipped || r.verdict_flipped) && 'bg-warning/[0.06]',
    )}>
      {/* [R836] 翻转的日子只在行首留一道竖线 —— 原来这里写「转折」「换档」两个词 */}
      {(r.trend?.flipped || r.verdict_flipped) && (
        <span className="absolute inset-y-1 left-0 w-0.5 rounded-full bg-warning/60"
              title={[r.trend?.flipped && '六态翻转', r.verdict_flipped && '通道换档']
                .filter(Boolean).join(' · ')} />
      )}
      <div className={DAY_COLS}>
        <span className="font-mono text-micro text-secondary">{r.date.slice(5)}</span>

        <span className="text-right font-mono text-micro font-medium tabular-nums text-foreground">
          {r.close.toFixed(2)}
        </span>

        {/* [R835] 涨跌与「停/板」标记必须同一行, 且百分比统一贴右 —— 标记在前、数字在后,
            有标记的日子与没标记的日子, 百分比的右边界才落在同一条竖线上。
            [R844] 标记自带 ml-1, 父级不再补 gap —— 两处叠成 8px, 挤掉的是「10板」那一档的余量。 */}
        <span className={cn('flex items-baseline justify-end whitespace-nowrap text-right font-mono text-micro tabular-nums', chgCls(r.change_pct))}>
          <LimitTag r={r} />{pct(r.change_pct, 2)}
        </span>

        {/* [R832] 趋势与档位并到同一列: 两个徽标贴在一起读, 比隔着一列数字更好对 */}
        <span className="flex min-w-0 flex-wrap items-center gap-x-1 gap-y-0.5">
          {r.trend ? (
            <>
              <span className={cn('inline-flex whitespace-nowrap rounded-btn border px-1 py-px text-micro', trendBadgeCls(r.trend.state))}
                    title={[r.trend.state_cn,
                      r.trend.sub_state_cn && `细分档：${r.trend.sub_state_cn}`, SUB_STATE_TIP]
                      .filter(Boolean).join(' · ')}>
                {r.trend.state_cn}
              </span>
              <span className="shrink-0 text-micro text-muted" title="这一段第几天">{r.trend.day}天</span>
            </>
          ) : <span className="text-micro text-muted/40">—</span>}
          {r.verdict ? (
            <VerdictHover v={r.verdict} note="收盘口径">
              <span className={`inline-flex cursor-help whitespace-nowrap rounded-btn border px-1 py-px text-micro ${VERDICT_CLS[r.verdict.tone]}`}>
                {r.verdict.title}
              </span>
            </VerdictHover>
          ) : <span className="text-micro text-muted/50" title="三档都在中部">中部</span>}
        </span>

        {/* 事件: 只在六态/通道真出了动作的那天另起一行。
            [R844] 并进同一张网格、从第 2 列铺到最后一列 —— 原来自己写死一个 2.4rem 的空格凑缩进,
            列宽一改就错位。 */}
        {legs.length > 0 && (
          <div className="col-start-2 col-span-3 mt-1 flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1 border-l border-border/40 pl-2">
            {legs.map(([src, l]) => (
              <span key={src} className="flex min-w-0 flex-wrap items-baseline gap-x-2" title={legTip(src, l)}>
                <span className="flex items-baseline gap-x-1 whitespace-nowrap">
                  <span className="text-micro text-muted">{src === '六态' ? '六' : '通'}</span>
                  <LegAct leg={l} />
                </span>
                <span className="whitespace-nowrap font-mono text-micro tabular-nums text-muted"><LegFill leg={l} /></span>
                <span className={cn('whitespace-nowrap font-mono text-micro tabular-nums', legResultCls(l))}><LegResult leg={l} /></span>
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

// ===== 2. 六个状态的历史表现 (+ 通道证据) =====

/**
 * [R827] 用户: 「两套买卖的对比这部分我不想要了，删了」。
 *
 * R825/R826 刚把这块改成两张卡、文案也精简过, 现在整块撤掉 —— 与其再调一版,
 * 不如让复盘只留"逐日怎么走的 + 六个状态各自的历史"。两套口径的账仍在
 * `FlipTradesPanel`(六态卡片里的分段战绩)与 `StockReviewDialog` 里, 没丢数据。
 *
 * 连带撤掉的是只用来解释这四个数的东西: 口径引用、`TRADE_STAT_TIPS` 悬停、
 * 未了结/样本少那行提醒 —— 它们的对象已经不在了, 留着就是没有指的注释。
 */
function HistoryCard({ d, compact }: { d: StockReview; compact: boolean }) {
  return (
    <div>
      <StateHistory d={d} />

      {!!d.channel && (
        <div className="mt-3 border-t border-border/40 pt-2">
          <div className="mb-1 cursor-help text-micro text-muted" title="上轨 / 中轨 / 下轨 三档当天的结论明细">通道证据</div>
          <EvidencePanel ch={d.channel} edge={d.verdict_edge} compact={compact} />
        </div>
      )}
    </div>
  )
}
/**
 * 「这只票的表现」那一列: **只写客观情况**, 不写该拿该走(用户选的「只摆数」)。
 * 没有可说的就是一道横线 —— 数都在左边几列里了, 再用话复述一遍是重复。
 */
function factOf(s: ReviewStateHistory, days: number): string | null {
  if (s.n === 0) return `这 ${days} 天没出现过`
  if (s.done === 0) return s.current ? '只有眼下这一段, 还没走完' : null
  if (s.done < THIN) return `只走完 ${s.done} 段, 样本太少, 只作参考`
  return null
}

// [R831] 列距拉开: 原来 gap-x-1.5(6px) 时「天数」的条+数挨着「段内」, 两组数看着连成
// 一片; 数字列宽也按各自最长的取值定(天数 3 位+条、百分比 6 字、胜负 5 字)。
// [R833] 状态列必须容得下「状态名 + 当前」两件东西: 原来标签带 truncate, 而后缀
// 把列挤满, 名字被压成 0 宽 —— 屏幕上只剩一个圆点。改法是把状态名与后缀都设成
// 不许收缩, 放不下时**换行**而不是把字吃掉; 数字列各让一点宽度过来。
// [R841] 用户: 「看不全」—— 左栏并成一列后只有 360~500 宽, 六列最小要 424, 最右的
// 「收涨」被挤到栏外(截图里 2/2 只剩一个 2)。两件事: ①「次数」不再占一列, 收成状态名
// 后面的 ×N(它本来就只有一个数字); ②状态列改成 minmax(0,1fr), 名字与后缀放不下时换行。
// 现在最小约 248 + 状态, 320 宽也不出栏。
// [R842] 用户: 「行距列距离这些都调整」。原来是「状态吃掉所有富余 + 四个数字列挤在右边」,
// 宽一点的表里两半像两张表拼起来。改成按比例分列(状态 2fr, 数字列 1.1/1/1/0.8),
// 列距 6 → 12, 表头 py-1 → py-1.5, 行 py-1.5 → py-2; 数字仍各列右对齐。
// [R843] 用户: 「贴着边我好难受」—— 最右「收涨」的数字正好压在容器右边缘上。整张表加
// `pr-2`(8px) 右内边距, 表头与数据一起内缩, 分隔线仍通到边。
const STATE_COLS = 'grid grid-cols-[minmax(0,2fr)_minmax(0,1.1fr)_minmax(0,1fr)_minmax(0,1fr)_minmax(0,0.8fr)] items-baseline gap-x-3 pr-2'

function StateHistory({ d }: { d: StockReview }) {
  // [R830] 次级回升/次级回撤已由后端**并进自然档**(统计时合并, 不是显示层藏行),
  // 载荷就是四个状态 —— 这里不再重复过滤一遍。
  const list = d.state_history ?? []
  if (!list.length) return null
  const maxDays = Math.max(1, ...list.map(s => s.days))
  const N = d.forward_days

  return (
    <div>
      {/* [R828] 标题从「六个状态的历史表现」收到「历史表现」—— 六个状态是内容不是标题;
          口径(这只票自己的记录 / 近 N 天 / 区间)进悬停 */}
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <span className={TYPE.card}>历史表现</span>
        <span className="cursor-help font-mono text-micro text-muted"
              title={`这只票自己的记录 · 近 ${d.days} 天 · ${d.start} → ${d.end}`}>
          四个状态 · 近 {d.days} 天
        </span>
      </div>

      {/* [R793] 表头承载原来每行重复的前缀词, 六态各占一行、不折叠; 当前状态高亮 */}
      <div className="mt-1.5 border-y border-border/50">
        <div className={cn(STATE_COLS, 'border-b border-border/40 py-1.5 text-micro text-muted')}>
          <span>状态</span>
          <span className="text-right" title="这个状态一共占了多少个交易日">天数</span>
          <span className="text-right" title="从进入这个状态前一天收盘, 到它结束那天收盘; 走完的段平均">段内</span>
          <span className="text-right" title={`这个状态结束之后 ${N} 个交易日的平均涨跌`}>后 {N} 天</span>
          <span className="text-right" title="走完的段里, 涨着结束的有几段">收涨</span>
        </div>
        {list.map(s => {
          const fact = factOf(s, d.days)
          // [R834] 用户: 「不需要显示未走完这个字眼」—— 那一段本来就有「当前」标签,
          // 段内/后 N 天为空的理由放在那三格的悬停里, 不再在行里多挂一枚标签。
          const badge = s.n === 0 ? '无' : (s.done > 0 && s.done < THIN ? '样本少' : null)
          return (
            <div key={s.key}
                 className={cn(STATE_COLS, 'border-b border-border/30 py-2 last:border-b-0',
                               s.current && 'bg-elevated/50')}>
              <span className="flex min-w-0 flex-wrap items-center gap-x-1 gap-y-0.5">
                <span className={cn('h-2 w-2 shrink-0 rounded-full', TREND_FILL[s.key])} />
                <span className={cn('shrink-0 whitespace-nowrap text-micro', s.current ? 'font-medium text-foreground' : 'text-foreground')}
                      title={s.label}>{s.label}</span>
                {/* [R841] 原来的「次数」列收成这里: ×N, 悬停给出说法 */}
                <span className="shrink-0 cursor-help whitespace-nowrap font-mono text-micro text-muted"
                      title="这个状态在近 N 天里出现过几次">
                  ×{s.n || 0}
                </span>
                {/* [R828] 三种后缀统一成同一枚小标签, 不再各写一种字色; 解释仍在悬停里 */}
                {s.current && (
                  <span className="shrink-0 whitespace-nowrap rounded-btn border border-border px-1 text-micro text-foreground">当前</span>
                )}
                {badge && (
                  <span className="shrink-0 cursor-help whitespace-nowrap rounded-btn border border-border px-1 text-micro text-muted"
                        title={fact ?? undefined}>{badge}</span>
                )}
              </span>
              {/* [R828] 条形在前、数字贴右 —— 表头「天数」右对齐, 才对得上数字而不是条尾 */}
              <span className="flex items-center justify-end gap-1">
                <span className="h-1 w-8 shrink-0 overflow-hidden rounded-full bg-border/40">
                  <span className="block h-full rounded-full bg-muted/60" style={{ width: `${(s.days / maxDays) * 100}%` }} />
                </span>
                <span className="font-mono text-micro tabular-nums text-secondary">{s.days}</span>
              </span>
              {/* [R833] 当前这段还没走完, 段内涨跌与「走完之后」都还不存在 —— 悬停里说清楚, 别让人以为是漏数 */}
              <span className={cn('text-right font-mono text-micro tabular-nums', chgCls(s.avg_ret))}
                    title={s.current ? '这一段还没走完：段内涨跌要等它结束才算' : undefined}>
                {pct(s.avg_ret)}
              </span>
              <span className={cn('text-right font-mono text-micro tabular-nums', chgCls(s.avg_after))}
                    title={s.current ? `这一段还没走完：走完后 ${N} 天同样要等它结束才量得到` : undefined}>
                {pct(s.avg_after)}
              </span>
              <span className="text-right font-mono text-micro tabular-nums text-secondary"
                    title={s.current ? '走完的段才有胜负 —— 这一段还在走' : undefined}>
                {s.done ? `${s.ret_win}/${s.done}` : '—'}
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}
