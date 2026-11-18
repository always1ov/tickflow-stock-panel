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
import { Info, Loader2 } from 'lucide-react'
import type { ReviewRow, StockReview } from '@/lib/api'
import { cn } from '@/lib/cn'
import { TREND_FILL } from '@/lib/reviewTimeline'
import { Hint } from '@/components/Hint'
import { trendBadgeCls } from '@/components/stock-analysis/TrendStateBar'
import { VerdictHover } from '@/components/stock-analysis/VerdictHover'
import {
  LimitTag, VERDICT_CLS,
  chgCls, pct, useStockReview,
} from '@/components/stock-analysis/StockReviewDialog'
import {
  LegAct, LegFill, LegResult, legResultCls, legsByFlipDate,
  type Leg,
} from '@/components/stock-analysis/FlipTradesPanel'
import { PILL, PILL_IDLE, PILL_ON } from './pill'
import { TYPE } from '@/components/ui'

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
      {/* [R858] 用户: 「删掉这一行『复盘 近 120 天怎么走的』」—— 整行撤掉。
          左栏这一块上面本来就有分隔线, 「历史表现」「逐日复盘」自己就是小标题, 再来一行
          大标题只是重复; 原来那行还带 `mt-2`, 撤掉后间隔由外层 `pt-4` 与 `space-y` 给出。 */}
      <div className={gaps}>
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
        {ok && <HistoryCard d={d} />}
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
  // [R865] 用户: 「问号的内容应该放原理定义」—— 不再摆今天的读数, 改成这两列**怎么算出来的**:
  // 六态的口径(只认收盘 / 阈值 / 两个关键点) 与通道三档的构造(均线 ± k 个 ATR)及其五档落点。
  // 数字仍取接口字段(阈值随票走), 定义本身与 `livermore.py` / `keltner.py` 的注释一致。
  const ev = useMemo(() => {
    const th = `${(d.threshold * 100).toFixed(0)}%`
    return [
      '六态状态 —— 利弗莫尔市场关键点，只认日线收盘价：',
      `· 从高点回落超过阈值（这只票 ${th}）算回撤，从低点回升超过阈值算回升；`,
      '· 收盘突破上关键点确认上涨趋势，跌破下关键点确认下跌趋势。',
      '行里跟「趋势转变」= 这天换了一种状态。',
      '',
      '通道档位 —— Keltner 通道，三档各是一条均线 ± 若干倍 ATR：',
      '· 短期 20 日 ±2 ATR，中期 60 日 ±2.5 ATR，长期 120 日 ±3 ATR；',
      '· 收盘落在上轨之上 / 贴上轨（0.5 个 ATR 内）/ 通道内 / 贴下轨 / 下轨之下，五选一。',
      '行里跟「档位切换」= 这天换了一档。',
    ].join('\n')
  }, [d])
  const rows = useMemo(() => {
    const all = d.rows ?? []
    if (!marked && !shifted) return all
    return all.filter(r =>
      (marked && (r.limit_up || r.limit_down || r.broken_limit_up || !!r.trend?.flipped))
      || (shifted && !!r.verdict_flipped))
  }, [d, marked, shifted])

  return (
    <div className="border-t border-border/60 pt-4">
      {/* [R856] 用户: 「逐日复盘后面的文字日期可以换行, 这样两个按钮排列就能同一行好看了」——
          标题与两个按钮固定在同一行(按钮贴右), 区间·天数挪到下一行自己起一行。
          原来三者挤在一条 flex 里, 日期把按钮顶下去, 换行后按钮悬在半空。
          [R857] 用户: 「排列整理, 感觉悬浮在空中了」—— 标题独占一行、两头各挂一件东西,
          中间一片空, 按钮像挂在半空。改成: 标题单独一行, 下面一条**工具行** ——
          区间·天数靠左、两个筛选贴右, 与日期同一条基线; 视觉重量落到贴近表头的那一行。
          [R832] 两个筛选原在自己一行; [R851] 曾改左对齐; [R854] 用户: 「我喜欢放在右边」。
          [R854] 名字砍掉「的日子」四个字, 悬停里已经写着「只留下…那些天」。 */}
      <span className={TYPE.card}>逐日复盘</span>
      <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1.5">
        {/* [R826] 正文只留区间与天数, 阈值与来源进悬停 */}
        <div className="cursor-help font-mono text-micro leading-4 text-muted"
             title={`六态阈值 ${(d.threshold * 100).toFixed(0)}%${d.threshold_source !== 'default' ? `（${d.threshold_source}）` : '（默认）'}`}>
          {d.start} ~ {d.end} · {d.days} 日
        </div>
        <span className="ml-auto flex shrink-0 items-center gap-x-2">
          <button type="button" onClick={() => setMarked(v => !v)} aria-pressed={marked}
                  title="只留下有涨跌停、或六态转折的那些天 —— 其余日子状态没变, 复盘时没有信息"
                  className={`${PILL} ${marked ? PILL_ON : PILL_IDLE}`}>
            只看有事
          </button>
          <button type="button" onClick={() => setShifted(v => !v)} aria-pressed={shifted}
                  title="只留下通道档位换过的那些天 —— 其余日子档位没变, 复盘时没有信息"
                  className={`${PILL} ${shifted ? PILL_ON : PILL_IDLE}`}>
            只看档位切换
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
          {/* [R860] 「通道证据」整块撤掉后, 内容挪到表头这枚问号上。
              [R862] 用户: 「问号加个小边框, 做成点击弹窗的形式」—— 从悬停改成点击弹层:
              小边框让它看得出可以点, 弹层能滚、能读长句, 触屏也点得到。 */}
          <span className="flex min-w-0 items-center gap-x-0.5">
            <span className="whitespace-nowrap">趋势 · 档位</span>
            {/* [R864] 用户: 「把问号改成图标, 并调整到趋势档位后面」—— 方框里的字面问号
                换成 Info 图标, 紧贴标题、与文字同一条基线, 不再自带一圈边框。 */}
            <Hint title={ev} icon={<Info className="h-3.5 w-3.5" />} className="-ml-0.5 align-baseline" />
          </span>
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
    <div className="border-b border-border/30 py-2 pl-2">
      {/* [R849] 用户: 「开头不搞边框颜色, 用文字说明什么含义」—— R836 那道行首琥珀竖线撤掉,
          换回两个词, 各自跟在对应的徽标后面: 「转折」跟六态、「换档」跟通道。
          竖线看着像给整行镶了道边, 又得悬停才知道它在说什么; 文字自己就把意思说完了。
          [R850] 用户: 「去掉行底的 6% 琥珀底色」—— 标记这一天的两样(竖线、底色)都撤了,
          只留「转折」「换档」两个词。整天扫一列时, 有色底的几行反而在跳。 */}
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

        {/* [R832] 趋势与档位并到同一列: 两个徽标贴在一起读, 比隔着一列数字更好对
            [R848] 悬停只留能读的那一句: 状态名 + (细分档是什么)。英文码、细分档那三行定义
            全撤 —— 一列 30 天里天天悬停, 那些话没人会读第二遍。 */}
        {/* [R852] 用户: 「趋势档位列里面的每一行的东西重新排列美观」——
            原来四个碎片(徽标 / 天数 / 徽标 / 转折·换档)用 4px 一律排开, 读起来是四件并列的
            东西, 其实是**两组**(六态 / 通道)。改成两个不折行的小组:
              · 组内 4px: 徽标 → 天数 → 转折, 全挂在六态那枚徽标上;
              · 组间 12px: 通道那一组自成一家, 窄到放不下时整组换行, 不会把「10天」留在上一行。
            颜色与描边/实心的差别不动 —— 那是状态强弱的既有语义, 不是装饰。
            [R853] 用户: 「调整趋势档位列的字体大小和行高, 使其更美观」—— 这一格是「读状态」的,
            与旁边的数字不是一种信息, 所以只有它升到 `text-xs`(12px): 徽标内边距 px-1/py-px →
            px-1.5/py-0.5, 徽标从 ~15px 长到 ~22px, 不再是几个贴在行里的小药丸;
            天数与「转折 / 换档」仍是 `text-micro` —— 它们挂在徽标上, 小一号才有主次。
            行高被徽标撑到 42px 太松, 整行 py-2.5 → py-2, 净增约 4px。
            [R855] 用户: 「转折和换档说得太笼统, 你看怎么重新换个名词, 比如趋势转变」「按钮也是
            跟着改名称」—— 「转折」→**趋势转变**(六态从一种状态转到另一种), 「换档」→**档位切换**
            (通道三档从一档换到另一档); 第二个筛选按钮跟着改成「只看档位切换」。
            悬停里的口径也换同一套说法。 */}
        <span className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1 text-xs leading-4">
          <span className="flex items-center gap-x-1.5 whitespace-nowrap">
            {r.trend ? (
              <>
                <span className={cn('inline-flex items-center rounded-btn border px-1.5 py-0.5 leading-4', trendBadgeCls(r.trend.state))}
                      title={r.trend.sub_state_cn
                        ? `${r.trend.state_cn} · 细分档「${r.trend.sub_state_cn}」只是标注, 不参与判断`
                        : r.trend.state_cn}>
                  {r.trend.state_cn}
                </span>
                <span className="text-micro text-muted" title="这一段第几天">{r.trend.day}天</span>
                {r.trend.flipped && (
                  <span className="text-micro text-warning" title="这天六态从一种状态转到另一种">趋势转变</span>
                )}
              </>
            ) : <span className="text-micro text-muted/40">—</span>}
          </span>

          <span className="flex items-center gap-x-1.5 whitespace-nowrap">
            {r.verdict ? (
              <VerdictHover v={r.verdict} note="收盘口径" compact>
                <span className={`inline-flex cursor-help items-center rounded-btn border px-1.5 py-0.5 leading-4 ${VERDICT_CLS[r.verdict.tone]}`}>
                  {r.verdict.title}
                </span>
              </VerdictHover>
            ) : <span className="text-micro text-muted/50" title="三档都在中部">中部</span>}
            {r.verdict_flipped && (
              <span className="text-micro text-warning" title="这天通道档位从一档换到另一档">档位切换</span>
            )}
          </span>
        </span>

        {/* 事件: 只在六态/通道真出了动作的那天另起一行。
            [R844] 并进同一张网格、从第 2 列铺到最后一列 —— 原来自己写死一个 2.4rem 的空格凑缩进,
            列宽一改就错位。
            [R846] 用户: 「第二行的显示很突兀不够好看」。三处:
             ① 去掉左侧那道灰竖线 —— 行首本来就有琥珀竖线标这天, 第二条线让整行像嵌了个框;
             ② 缩进从「第 2 列起、悬在空中」改成**整行铺满**(col-span-full): 与日期同一起点,
                读起来才是这一行自己的第二行, 而不是挂在数字列下面的一条尾巴;
             ③ 动作 / 成交 / 结果三样之间补灰色「·」—— 原来是空格堆着, 8 样东西连成一串看不出分组;
                琥珀「未完」收成灰色「…」(说法仍在悬停里), 一行灰度文字不再被拦腰截断。 */}
        {legs.length > 0 && (
          <div className="col-span-full mt-1 flex min-w-0 flex-wrap items-center gap-x-4 gap-y-1">
            {legs.map(([src, l]) => (
              <span key={src} className="flex min-w-0 flex-wrap items-baseline gap-x-1.5" title={legTip(src, l)}>
                <span className="flex items-baseline gap-x-1 whitespace-nowrap">
                  {/* [R847] 用户: 「前面的六和通都说完整描述」—— 原来缩成单字(六/通),
                      单独看不知道指哪套买卖; 直接写全称。 */}
                  <span className="text-micro text-muted/70">{src}</span>
                  <LegAct leg={l} />
                </span>
                <span className="text-micro text-muted/30" aria-hidden="true">·</span>
                <span className="whitespace-nowrap font-mono text-micro tabular-nums text-muted"><LegFill leg={l} openAsDot /></span>
                <span className="text-micro text-muted/30" aria-hidden="true">·</span>
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
 *
 * [R860] 用户: 「这个部分删掉(通道证据), 问号以及里面的内容挪到趋势档位这里的后面」——
 * 整块「通道证据」撤掉, 里面的口径(阶段判定 / 通道档位 / 逐项读数)挂到逐日复盘表头
 * 「趋势 · 档位」后面那枚问号上。原来它是折叠区(点开在表里撑出一块), 现在是悬停看,
 * 不占版面; 表头那一格本来就是「这一列是什么」的说明位。
 */
function HistoryCard({ d }: { d: StockReview }) {
  return (
    <div>
      <StateHistory d={d} />
    </div>
  )
}
/**
 * 「这只票的表现」那一列: **只写客观情况**, 不写该拿该走(用户选的「只摆数」)。
 * 没有可说的就是一道横线 —— 数都在左边几列里了, 再用话复述一遍是重复。
 * [R859] 这张表只剩四行数 × 五列, 再挂一枚「样本少」小标签就会被挤换行; 那句提醒
 * 已经挂在「收涨」值的 `*` 上, 这个函数随之退场。
 */

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
          <span className="text-right" title="走完的段里, 涨着结束的有几段; 带 * 表示走完的段不到 3 段, 只作参考">收涨</span>
        </div>
        {list.map(s => {
          // [R859] 用户: 「被挤换行了不好看」—— 状态列只有约 90px, 「当前」「样本少」两枚带框
          // 小标签一挤, 「样本少」就被挤到第二行。两件事:
          //   ① 「当前」去掉边框内边距, 改成一枚强调色的两字后缀(行本身已有高亮,
          //      「现状」那块也写着当前状态, 这里不需要再像按钮一样重);
          //   ② 「样本少」搬到它真正说明的那一格 ——「收涨」的值后缀一个 `*`(悬停说明),
          //      它本来就是在说「走完的段太少, 这个胜率只作参考」。
          const thin = s.n > 0 && s.done > 0 && s.done < THIN
          return (
            <div key={s.key}
                 className={cn(STATE_COLS, 'border-b border-border/30 py-2 last:border-b-0',
                               s.current && 'bg-elevated/50')}>
              <span className="flex min-w-0 items-center gap-x-1.5 whitespace-nowrap">
                <span className={cn('h-2 w-2 shrink-0 rounded-full', TREND_FILL[s.key])} />
                <span className={cn('text-micro', s.current ? 'font-medium text-foreground' : 'text-foreground')}
                      title={s.label}>{s.label}</span>
                {/* [R841] 原来的「次数」列收成这里: ×N, 悬停给出说法 */}
                <span className="cursor-help font-mono text-micro text-muted"
                      title="这个状态在近 N 天里出现过几次">
                  ×{s.n || 0}
                </span>
                {s.current && (
                  <span className="font-medium text-micro text-primary" title="这只票眼下正处在这个状态">当前</span>
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
                {thin && <span className="cursor-help text-warning" title={`只走完 ${s.done} 段, 样本太少, 这个胜率只作参考`}>*</span>}
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}
