/**
 * [fork 增强 R349] 「走势」那一格 —— **一处实现, 两页共用**。
 *
 * 原来是 `OpportunityTable.tsx` 里的私有组件(`posWord`/`volWord` 早就 export
 * 出去给导出件用了)。模拟盘也要这一列(用户: 「这一列也要有」), **不复制一份**:
 * 「多少算多」的那两条分界一旦抄成两份, **屏幕说「放量刚好」而导出说「量太大」**
 * 的那天就没法查了 —— R212 立的就是这条规矩, 这次把组件也收进同一处。
 */
import type { TodayOpportunity } from '@/lib/api'

/**
 * [R214] 三个原始数字 → 三句状态词。
 *
 * 「位置 68% / 量比 1.82 / 距关键点 -2.55%」三列并排, 每一个都要人先知道
 * **多少算多** 才读得出好坏 —— 而那正是不该逼人记的东西。这三列合成一格
 * 「走势」, 只说状态词, 数字全退到悬停。做法与决策台 R211 那一轮完全一样,
 * 两个页面对同一件事得用同一种说法。
 *
 * 配色沿用原来的(涨红跌绿): 红 = 位置便宜/量刚好, 绿 = 已经贵了/量过头。
 *
 * 两个函数都 export 出去给 todayHtmlExport 用 —— **「多少算多」的分界只该有
 * 一处定义**(R212 立的规矩)。分界抄成两份, 屏幕说「放量刚好」而导出说
 * 「量太大」的那天就没法查了。
 */
export function posWord(pct: number): { cn: string; tone: string; why: string } {
  if (pct >= 0.95) return { cn: '已到上沿', tone: 'text-success', why: '这个位置买是在最贵的地方' }
  if (pct >= 0.78) return { cn: '空间走掉一半', tone: 'text-secondary', why: '还能走,但便宜的那一段过去了' }
  if (pct >= 0.5 && pct <= 0.66) return { cn: '刚站上生命线', tone: 'text-danger', why: '方向出来了而位置还便宜 —— 甜区' }
  if (pct >= 0.5) return { cn: '通道中段', tone: 'text-secondary', why: '不贵也不便宜' }
  return { cn: '还在生命线下', tone: 'text-muted', why: '方向还没站住' }
}

export function volWord(v: number): { cn: string; tone: string; why: string } {
  if (v >= 1.3 && v <= 2.5) return { cn: '放量刚好', tone: 'text-danger', why: '有增量,还没到人尽皆知' }
  if (v > 4) return { cn: '量太大了', tone: 'text-success', why: '这波多半已经走了一段' }
  if (v < 0.8) return { cn: '几乎没量', tone: 'text-success', why: '突破成色存疑' }
  return { cn: '量能平平', tone: 'text-secondary', why: '既没放大,也没缩到没有' }
}

/**
 * 「走势」—— 信号 + 六态 + 位置 + 量能 + 距关键点, **一格一行**。
 *
 * 为什么合成一格: 它们回答的是同一个问题(**凭什么把这只挑出来**)。
 * 拆成四列, 人得左右对眼把依据接起来; 并成一格, 一扫就是一条链:
 * 出了什么信号 → 现在贵不贵、有没有量 → 离该动手的价还有多远。
 *
 * [R356] 原来这段写的是「一格里三行」, 那是它长在机会表里时的样子。那张表随今日
 * 总览删了, **唯一的消费方现在是模拟盘的信号行** —— 在那儿多一行就是多一截行高,
 * 而且只有"进了候选池"的票才多, 一屏扫下去参差不齐。见下面 `flex-wrap` 那段。
 */
export function TrendCell({ o }: { o: TodayOpportunity }) {
  const p = o.channel_pct != null ? posWord(o.channel_pct) : null
  const v = o.vol_ratio != null ? volWord(o.vol_ratio) : null
  return (
    /* [R356] **一行, 不是两行。** 原来是 `flex-col`(信号一行、三个状态词一行),
       那是机会表里"一格两行"的排法; 那张表随今日总览删了, 现在唯一的消费方是
       模拟盘的信号行 —— 而在那儿分两行会让**有走势的票比没走势的高一截**,
       一屏扫下去行高参差。摊成一行, 右边那片空地正好用上。 */
    <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5">
      <div className="flex flex-wrap items-center gap-1.5 text-foreground/85">
        <span>{o.text}</span>
        {o.trend_state_cn && (
          <span title="六态趋势状态 —— 门槛要求必须在多头侧(上涨趋势/自然回升/次级回升)"
                className="whitespace-nowrap rounded bg-border/40 px-1 py-0.5 text-[9px] text-muted">
            {o.trend_state_cn}
          </span>
        )}
        {o.fresh_from === 'near_breakout' && (
          <span title="这只是靠「逼近触发价」进来的:突破还没发生,跑道最长但也最未经确认"
                className="whitespace-nowrap rounded bg-sky-400/15 px-1 py-0.5 text-[9px] text-sky-300">
            尚未突破
          </span>
        )}
        {o.intraday && (
          <span title="这个信号由盘中实时价触发,收盘可能收回去 —— 只记录观察,收盘确认后再动手"
                className="rounded bg-amber-400/15 px-1 py-0.5 text-[9px] text-amber-300">
            盘中·待收盘确认
          </span>
        )}
      </div>
      <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[10px]">
        {p && (
          <span className={p.tone}
                title={`量化波动通道·短期 位置 ${Math.round(o.channel_pct! * 100)}%`
                  // [R351] 原来这儿写的是「50=生命线 MA20」。**扫描面一扩就查出来了**:
                  // 这一格以前不在 `test_glossary_hides_math` 的扫描面内(老锚点排在它后面),
                  // 于是「MA20」在一个用户悬停就能看到的地方躺了很久。界面上只说
                  // 「生命线」——**那是这套系统对外的说法**, 均线周期是实现细节。
                  + `(0=下轨 / 50=生命线 / 100=上轨)—— ${p.why}`}>
            {p.cn}
          </span>
        )}
        {v && (
          <span className={v.tone} title={`量比 ${o.vol_ratio!.toFixed(2)} —— ${v.why}`}>
            {v.cn}
          </span>
        )}
        {/* [R158] 「-2.55%」要人翻译一次; 直接说「已过 2.6%」「还差 7.0%」。
            这一个本来就是"词 + 数"的样子, 已经是对的, 原样保留。 */}
        {o.gap_pct != null && (
          <span className={o.gap_pct <= 0 ? 'text-danger'
            : o.gap_pct <= 1.5 ? 'text-warning' : 'text-secondary'}
            title={'收盘价相对关键点(转多的关键点 / 回升待突破的关键点 / AI 触发价)。不参与打分'
              + (o.pivot != null ? `\n关键点 ${o.pivot}` : '')}>
            {o.gap_pct <= 0 ? '已过关键点 ' : o.gap_pct <= 1.5 ? '就差 ' : '还差 '}
            <span className="font-mono">{Math.abs(o.gap_pct).toFixed(1)}%</span>
          </span>
        )}
        {!p && !v && o.gap_pct == null && <span className="text-muted/50">—</span>}
      </div>
    </div>
  )
}
