/**
 * [fork 增强] 今日总览「值得关注」表 + 门槛漏斗。
 *
 * [R167] 从 Today.tsx 拆出。对外只暴露 OpportunityTable / GateFunnel 两个组件;
 * 把握分格、通道位置格、盘中格、注记胶囊、出手结论、展开详情全部是内部实现。
 */
import { Fragment, useState } from 'react'
import { ChevronDown } from 'lucide-react'
import type {
  TodayAction, TodayGates, TodayLive, TodayNote, TodayOpportunity, TodayOverview,
} from '@/lib/api'
import { cn } from '@/lib/cn'

const BOARD_CLS: Record<string, string> = {
  沪主板: 'bg-border/40 text-muted',
  深主板: 'bg-border/40 text-muted',
  创业板: 'bg-orange-400/15 text-orange-300',
  科创板: 'bg-orange-400/15 text-orange-300',
  北交所: 'bg-rose-400/15 text-rose-300',
}
const BOARD_LIMIT_CN: Record<string, string> = {
  沪主板: '10%', 深主板: '10%', 创业板: '20%', 科创板: '20%', 北交所: '30%',
}

// [R189] 三维度 → 两根轴。分法从"按数据来源"改成"按变化速度":
// 质地以月计变化, 时机逐日变化。总分 = √(质地 × 时机) —— 两边都得像样。
const AXIS_META = [
  { key: 'quality', cn: '质地', cls: 'bg-red-400',
    what: '这只票的长周期结构 —— 以月计变化',
    hint: '趋势模板(八条) / 磨底节拍 / 相对强度 / 六态状态 / 通道分离度' },
  { key: 'timing', cn: '时机', cls: 'bg-sky-400',
    what: '今天是不是那一天 —— 逐日变化',
    hint: '新鲜度 / 通道位置 / 量比(区间最优,峰在 1.3~2.5) / 换手率 / 加速度' },
] as const

/** 两轴一高一低时该说的那句话 —— 这正是合成分说不出来的东西。 */
function axisVerdict(q?: number | null, t?: number | null): string | null {
  if (q == null || t == null) return null
  if (q >= 70 && t < 50) return '好票,但今天不是买点 —— 等回踩或等放量,别追'
  if (q < 50 && t >= 70) return '今天是有动静,但这票本身结构不行 —— 不值得占仓位'
  if (q >= 70 && t >= 70) return '质地与时机都在位 —— 高概率的有苗头的东西'
  return null
}

const NOTE_TONE: Record<string, string> = {
  good: 'bg-emerald-400/15 text-emerald-300',
  bad: 'bg-danger/15 text-danger',
  info: 'bg-border/50 text-muted',
}

/** 把握分 + 两轴分解条。分数本身不再是黑箱 —— 条的形状就是理由。 */
function ScoreCell({ o, rank, total }: { o: TodayOpportunity; rank: number; total: number }) {
  const axes = o.axes
  const detail = AXIS_META
    .map(d => `${d.cn} ${axes?.[d.key] ?? '无数据'} — ${d.what}`)
    .join('\n')
  const verdict = axisVerdict(axes?.quality, axes?.timing)
  return (
    <span
      className="inline-flex w-11 shrink-0 flex-col items-center gap-1"
      title={`把握分 ${o.score} = √(质地 × 时机) —— 今日候选里排第 ${rank}/${total}\n\n${detail}\n\n`
        + (verdict ? `${verdict}\n\n` : '')
        + (o.partial
          ? '⚠ 有因子缺数据,总分是在剩下的因子上算的,偏乐观'
          : '两根轴的因子都齐全')}
    >
      <span className="font-mono text-[11px] font-semibold leading-none">
        <span className={o.score >= 80 ? 'text-danger' : o.score >= 60 ? 'text-warning' : 'text-muted'}>
          {o.score}
        </span>
        {o.partial && <span className="text-[9px] text-warning">*</span>}
      </span>
      <span className="w-full space-y-[2px]">
        {AXIS_META.map(d => {
          const v = axes?.[d.key]
          return (
            <span key={d.key} className="block h-[3px] overflow-hidden rounded-full bg-border/50">
              {v != null && (
                <span className={cn('block h-full rounded-full transition-ui duration-enter ease-smooth', d.cls)}
                      style={{ width: `${Math.max(3, Math.min(100, v))}%` }} />
              )}
            </span>
          )
        })}
      </span>
    </span>
  )
}

/** 通道位置: 0.5 = 恰好站在生命线上, 1.0 = 贴上轨。甜区在刚站上那一段。 */
function PositionCell({ pct }: { pct?: number | null }) {
  if (pct == null) return <span className="text-[10px] text-muted/50">—</span>
  const p = Math.round(pct * 100)
  const tone = pct >= 0.5 && pct <= 0.66 ? 'text-danger'
    : pct >= 0.85 ? 'text-success' : 'text-secondary'
  const hint = pct >= 0.5 && pct <= 0.66 ? '刚站上生命线,位置便宜'
    : pct >= 0.95 ? '已到通道上沿,这个位置买是在最贵的地方'
    : pct >= 0.78 ? '空间已经走掉一半' : '通道中段'
  return (
    <span className={cn('font-mono', tone)}
          title={`量化波动通道·短期 位置 ${p}%(0=下轨 / 50=生命线 MA20 / 100=上轨)—— ${hint}`}>
      {p}%
    </span>
  )
}

/**
 * [R137] 盘中列 —— 只在开着实时行情时出现。
 *
 * 这一列和把握分是**两回事**, 版面上也刻意分开: 把握分冻在收盘口径(盘中一动
 * 不动, 你的决策基准), 这一列是"现在正在发生什么"。用户的用法就是这样 ——
 * 决策看收盘, 盘中一直盯着。
 *
 * 最要紧的是「破生命线」那个红标: v2 的生命线是硬门槛, 一只昨天入选的票今天
 * 盘中跌回 MA20 之下, 收盘定稿后就会被挡掉。盯盘的人得当场知道, 而不是等到
 * 收盘发现它凭空消失了。
 */
function LiveCell({ live, closePct }: { live?: TodayLive | null; closePct?: number | null }) {
  if (!live) return <span className="text-[10px] text-muted/50">—</span>
  const chg = live.change_pct
  // 通道位置今天往上走还是往下走 —— 与收盘位置的差
  const drift = live.channel_pct != null && closePct != null
    ? live.channel_pct - closePct : null
  return (
    <span className="flex flex-col items-end gap-0.5 whitespace-nowrap">
      <span className="font-mono">
        <span className="text-foreground">{live.price.toFixed(2)}</span>
        {chg != null && (
          <span className={cn('ml-1', chg > 0 ? 'text-bull' : chg < 0 ? 'text-bear' : 'text-muted')}>
            {chg > 0 ? '+' : ''}{chg}%
          </span>
        )}
      </span>
      <span className="flex items-center gap-1 text-[9px]">
        {live.below_lifeline && (
          <span title={`现价已跌回昨日生命线 MA20 ${live.ma20?.toFixed(2) ?? ''} 之下 —— 若收盘仍在下方, 定稿后会被生命线门槛挡掉。这是盘中预警, 不是结论`}
                className="rounded bg-danger/20 px-1 py-0.5 font-medium text-danger">
            破生命线
          </span>
        )}
        {live.vol_ratio != null && (
          <span title="盘中量比(不参与把握分 —— 评分用的是昨收那份)"
                className="font-mono text-muted">量{live.vol_ratio.toFixed(2)}</span>
        )}
        {drift != null && Math.abs(drift) >= 0.03 && (
          <span title={`现价在昨日通道里的位置 ${(live.channel_pct! * 100).toFixed(0)}%,较昨收${drift > 0 ? '上移' : '下移'} ${Math.abs(drift * 100).toFixed(0)} 个点`}
                className={cn('font-mono', drift > 0 ? 'text-bull' : 'text-bear')}>
            {drift > 0 ? '↑' : '↓'}{Math.abs(drift * 100).toFixed(0)}
          </span>
        )}
      </span>
    </span>
  )
}

function NoteChips({ notes }: { notes?: TodayNote[] }) {
  if (!notes?.length) return <span className="text-[10px] text-muted/50">—</span>
  return (
    <span className="flex flex-wrap gap-1">
      {notes.map(n => (
        <span key={n.key}
              title={`${n.text}\n\n（注记只作佐证,不参与把握分)`}
              className={cn('whitespace-nowrap rounded px-1.5 py-0.5 text-[9px]',
                NOTE_TONE[n.tone] ?? NOTE_TONE.info)}>
          {n.label}
        </span>
      ))}
    </span>
  )
}

/** [R134] 门槛漏斗 —— 熊市里机会区空空如也时, 这一行说明系统在干活 */
export function GateFunnel({ gates }: { gates?: TodayGates | null }) {
  if (!gates || !gates.candidates) return null
  const blocked = Object.entries(gates.blocked || {}).sort((a, b) => b[1] - a[1])
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-border/40 bg-base/30 px-4 py-2 text-[10px]">
      <span className="text-muted">
        三道硬门槛:
        <span className="ml-1 font-mono text-foreground">{gates.candidates}</span> 只候选 →
        <span className="ml-1 font-mono text-emerald-400">{gates.passed}</span> 只过关
      </span>
      {blocked.map(([code, n]) => (
        <span key={code}
              title={gates.labels?.[code]?.why ?? ''}
              className="whitespace-nowrap rounded bg-border/40 px-1.5 py-0.5 text-muted">
          {gates.labels?.[code]?.cn ?? code} <span className="font-mono">{n}</span>
        </span>
      ))}
      {blocked.length === 0 && <span className="text-muted/70">今天没有候选被门槛挡下</span>}
      <span className="text-muted/60"
            title="门槛只挡明确不该看的,不挡我们没读到的 —— 数据缺失一律放行">
        · 门槛全部是纯价格判据,可回测
      </span>
    </div>
  )
}

export function OpportunityTable({ rows, pickedSymbols, onOpen, live }: {
  rows: TodayOverview['opportunities']
  pickedSymbols: Set<string>
  onOpen: (symbol: string, name: string) => void
  /** 实时行情开着 —— 多一列「盘中」。关着时整列不占版面 */
  live?: boolean
}) {
  const [open, setOpen] = useState<string | null>(null)
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr className="border-b border-border/40 text-[10px] text-muted">
            <th className="w-14 px-3 py-1.5 text-center font-normal"
                title="把握分 = √(质地 × 时机)。质地=长周期结构(趋势模板/磨底节拍/相对强度/六态),以月计变化;时机=今天是不是那一天(新鲜度/通道位置/量比/换手),逐日变化。一边好一边差不会被平均成中等 —— 下面两条细条就是这两根轴的得分。">
              把握
            </th>
            <th className="px-2 py-1.5 text-left font-normal">名称</th>
            <th className="px-2 py-1.5 text-left font-normal">信号</th>
            {live && (
              <th className="px-2 py-1.5 text-right font-normal"
                  title="盘中现价与变化。**不参与把握分** —— 把握分冻在收盘口径, 盘中一动不动">
                盘中
              </th>
            )}
            <th className="hidden px-2 py-1.5 text-right font-normal md:table-cell"
                title="量化波动通道·短期 的位置(收盘口径)。50% = 恰好站在生命线 MA20 上;甜区 50%~65%">位置</th>
            <th className="hidden px-2 py-1.5 text-right font-normal md:table-cell"
                title="量比。区间最优:峰在 1.3~2.5,超过 4 说明这波已经走完了">量比</th>
            <th className="hidden px-2 py-1.5 text-right font-normal xl:table-cell"
                title="收盘价相对关键点(转多的关键点 / 回升待突破的关键点 / AI 触发价)。「已过」= 已在关键点上方, 「还差」= 还在下方。不参与打分">距关键点</th>
            <th className="px-2 py-1.5 text-left font-normal"
                title={'今天这一天能不能下手, 一句结论。不进评分不改名次。\n今天动手: 已确认上涨趋势、信号 ≤3 天、贴着关键点(高出不到 5%)、没贴上轨、盘中没跌回关键点下方、大盘不在防守档\n收盘再动: 方向对但还差一个确认 —— 盘中临时信号 / 回升途中盘中刚过关键点 / 距触发价 2% 以内 / 转多第 4~5 天 / 盘中回落。收盘站稳(守住)关键点再动\n不动手: 大盘防守 / 盘中跌破生命线 / 当日涨幅到板幅 70% / 已高出关键点 5%+ / 贴上轨 / 转多第 6 天起 / 回升还没突破'}>
              出手
            </th>
            <th className="hidden px-2 py-1.5 text-left font-normal lg:table-cell"
                title="主线 / AI 信号 / 历史胜率 / 通道结论 —— 全部只作佐证,一分不加一分不减">
              注记·不计分
            </th>
            <th className="hidden px-2 py-1.5 text-right font-normal sm:table-cell">建议仓位</th>
            <th className="w-7 px-1 py-1.5" aria-label="展开" />
          </tr>
        </thead>
        <tbody>
          {rows.map((o, i) => {
            const picked = pickedSymbols.has(o.symbol)
            const expanded = open === o.symbol
            return (
              <Fragment key={o.symbol}>
                <tr
                  className={cn('group border-b border-border/25 transition-colors duration-hover',
                    picked ? 'bg-amber-400/[0.07]' : 'hover:bg-elevated/40')}
                >
                  <td className="px-3 py-2 text-center align-top">
                    <ScoreCell o={o} rank={i + 1} total={rows.length} />
                  </td>
                  <td className="px-2 py-2 align-top">
                    <button
                      onClick={() => onOpen(o.symbol, o.name)}
                      className="text-left font-medium text-foreground hover:text-accent hover:underline transition-colors duration-hover cursor-pointer"
                    >
                      {o.name}
                    </button>
                    <div className="mt-0.5 flex flex-wrap items-center gap-1">
                      <span className="font-mono text-[9px] text-muted">{o.symbol}</span>
                      {o.board && (
                        <span title={`${o.board} —— 涨跌停幅度 ${BOARD_LIMIT_CN[o.board] ?? '10%'}`}
                              className={`rounded px-1 py-0.5 text-[9px] ${BOARD_CLS[o.board] ?? 'bg-border/40 text-muted'}`}>
                          {o.board}
                        </span>
                      )}
                      {picked && <span className="text-[9px] text-amber-300">★ AI 优选</span>}
                    </div>
                  </td>
                  <td className="px-2 py-2 align-top text-foreground/85">
                    <div className="flex flex-wrap items-center gap-1.5">
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
                  </td>
                  {live && (
                    <td className="whitespace-nowrap px-2 py-2 text-right align-top">
                      <LiveCell live={o.live} closePct={o.channel_pct} />
                    </td>
                  )}
                  <td className="hidden whitespace-nowrap px-2 py-2 text-right align-top md:table-cell">
                    <PositionCell pct={o.channel_pct} />
                  </td>
                  <td className="hidden whitespace-nowrap px-2 py-2 text-right align-top font-mono md:table-cell">
                    {o.vol_ratio == null ? <span className="text-[10px] text-muted/50">—</span> : (
                      <span className={o.vol_ratio >= 1.3 && o.vol_ratio <= 2.5 ? 'text-danger'
                        : o.vol_ratio < 0.8 || o.vol_ratio > 4 ? 'text-success' : 'text-secondary'}
                        title={o.vol_ratio >= 1.3 && o.vol_ratio <= 2.5 ? '有增量,还没到人尽皆知'
                          : o.vol_ratio > 4 ? '量太大,这波多半已经走了一段'
                          : o.vol_ratio < 0.8 ? '没量,突破成色存疑' : ''}>
                        {o.vol_ratio.toFixed(2)}
                      </span>
                    )}
                  </td>
                  <td className="hidden whitespace-nowrap px-2 py-2 text-right align-top font-mono xl:table-cell">
                    {/* [R158] 「-2.55%」要人翻译一次; 直接说「已过 2.6%」「还差 7.0%」 */}
                    {o.gap_pct == null ? <span className="text-[10px] text-muted/50">—</span> : (
                      <span className={o.gap_pct <= 0 ? 'text-danger'
                        : o.gap_pct <= 1.5 ? 'text-warning' : 'text-secondary'}
                        title={o.pivot != null ? `关键点 ${o.pivot}` : undefined}>
                        <span className="mr-0.5 font-sans text-[9px] opacity-70">{o.gap_pct <= 0 ? '已过' : '还差'}</span>
                        {Math.abs(o.gap_pct).toFixed(1)}%
                      </span>
                    )}
                  </td>
                  <td className="px-2 py-2 align-top">
                    <ActionCell action={o.action} />
                  </td>
                  <td className="hidden px-2 py-2 align-top lg:table-cell">
                    <NoteChips notes={o.notes} />
                  </td>
                  <td className="hidden whitespace-nowrap px-2 py-2 text-right align-top sm:table-cell">
                    {o.advice ? (
                      <span title={`${o.advice.why} —— 仅供参考的上限建议, 不是操作指令`}
                            className="rounded bg-sky-400/15 px-1.5 py-0.5 text-[9px] text-sky-300">
                        {o.advice.text}
                      </span>
                    ) : <span className="text-[10px] text-muted/50">—</span>}
                  </td>
                  <td className="px-1 py-2 align-top">
                    <button
                      onClick={() => setOpen(expanded ? null : o.symbol)}
                      aria-expanded={expanded}
                      aria-label={expanded ? '收起细节' : '展开细节'}
                      className="rounded p-1 text-muted transition-colors duration-hover hover:bg-elevated hover:text-foreground"
                    >
                      <ChevronDown className={cn('h-3.5 w-3.5 transition-transform duration-expand ease-smooth',
                        expanded && 'rotate-180')} />
                    </button>
                  </td>
                </tr>
                {expanded && <OpportunityDetail o={o} live={live} />}
              </Fragment>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

/** [R158] 出手时机: 一个结论胶囊 + 一行理由。三态三色: 今天动手=强调色, 收盘再动=警示色, 不动手=灰。 */
function ActionCell({ action }: { action?: TodayAction | null }) {
  if (!action) return <span className="text-[10px] text-muted/50">—</span>
  const cls = action.code === 'today'
    ? 'border-accent/40 bg-accent/15 text-accent'
    : action.code === 'after_close'
      ? 'border-warning/40 bg-warning/15 text-warning'
      : 'border-border bg-elevated/60 text-muted'
  return (
    <div className="flex min-w-[9rem] flex-col gap-0.5" title={action.reason}>
      <span className={cn('inline-flex w-fit items-center rounded border px-1.5 py-0.5 text-[10px] font-medium', cls)}>
        {action.label}
      </span>
      <span className="max-w-[14rem] truncate text-[9px] leading-tight text-muted">{action.reason}</span>
    </div>
  )
}

/** 展开行: 把两根轴拆到因子这一层, 外加注记全文与建仓路径。 */
function OpportunityDetail({ o, live }: { o: TodayOpportunity; live?: boolean }) {
  const F_CN: Record<string, string> = {
    template: '趋势模板', base: '磨底节拍', rs: '相对强度', state: '六态状态',
    spread: '通道分离度',
    fresh: '新鲜度', pos: '通道位置', vol_ratio: '量比', turnover: '换手率',
    accel: '加速度',
  }
  const AXIS_FACTORS: Record<string, string[]> = {
    quality: ['template', 'base', 'rs', 'state', 'spread'],
    timing: ['fresh', 'pos', 'vol_ratio', 'turnover', 'accel'],
  }
  const verdict = axisVerdict(o.axes?.quality, o.axes?.timing)
  return (
    <tr className="border-b border-border/25 bg-base/40">
      <td colSpan={live ? 10 : 9} className="px-4 py-3">
        <div className="animate-rise-in space-y-2.5 text-[11px] leading-5">
          {/* [R189] 两轴的结论先说 —— 「质地 92 / 时机 41」的意思是"好票但今天
              不是买点", 而合成后的 61 分说不出这句话。那正是拆成两轴的理由。 */}
          {verdict && (
            <div className="rounded border border-accent/30 bg-accent/10 px-2.5 py-1.5 text-foreground/90">
              {verdict}
            </div>
          )}
          <div className="grid gap-2.5 sm:grid-cols-2">
            {AXIS_META.map(d => {
              const v = o.axes?.[d.key]
              return (
                <div key={d.key} className="rounded border border-border/40 bg-surface/40 px-2.5 py-2">
                  <div className="flex items-baseline justify-between">
                    <span className="text-foreground/90">{d.cn}</span>
                    <span className="text-[10px] text-muted">{d.what}</span>
                  </div>
                  <div className="mt-1 flex items-center gap-2">
                    <span className="h-1 flex-1 overflow-hidden rounded-full bg-border/50">
                      {v != null && <span className={cn('block h-full rounded-full', d.cls)}
                                          style={{ width: `${Math.max(3, Math.min(100, v))}%` }} />}
                    </span>
                    <span className="w-8 text-right font-mono text-foreground">
                      {v == null ? '无数据' : Math.round(v)}
                    </span>
                  </div>
                  <div className="mt-1.5 space-y-0.5 text-[10px] text-muted">
                    {AXIS_FACTORS[d.key].map(fk => (
                      <div key={fk} className="flex justify-between">
                        <span>{F_CN[fk]}</span>
                        <span className="font-mono">
                          {o.factors?.[fk as keyof NonNullable<typeof o.factors>] == null
                            ? '—' : Math.round(o.factors[fk as keyof NonNullable<typeof o.factors>]!)}
                        </span>
                      </div>
                    ))}
                  </div>
                  <div className="mt-1 text-[9px] text-muted/70">{d.hint}</div>
                </div>
              )
            })}
          </div>

          {live && (
            <div className="rounded border border-sky-400/30 bg-sky-400/10 px-2.5 py-1.5 text-sky-300">
              把握分与两根轴都是 <span className="font-medium">{'{'}收盘口径{'}'}</span>,盘中一动不动 ——
              它是你的决策基准。上面「盘中」那一列才是现在正在发生的事,一分不进评分。
              带「盘中·待收盘确认」标的候选例外:那是盘中才冒出来的信号,收盘可能收回去。
            </div>
          )}

          {o.partial && (
            <div className="rounded border border-warning/30 bg-warning/10 px-2.5 py-1.5 text-warning">
              有因子缺数据,总分是在剩下的因子上算的 —— 这种候选的分<b>偏乐观</b>,
              与同分候选比较时优先选数据齐全的那只。
            </div>
          )}

          {/* [R189] 趋势模板八条的原文。**分数是结论, 这里是依据** —— 「质地 88」
              没法核对, 「MA200 上行至少一个月:较 22 日前 +3.1%」可以。 */}
          {!!o.template && (
            <div className="rounded border border-border/40 bg-surface/40 px-2.5 py-2">
              <div className="mb-1 flex items-baseline justify-between">
                <span className="text-foreground/90">趋势模板</span>
                <span className="font-mono text-[10px] text-muted">
                  {o.template.passed}/{o.template.total} 条
                  {o.template.known < o.template.total
                    && ` · ${o.template.total - o.template.known} 条历史不足`}
                </span>
              </div>
              <div className="grid gap-x-4 gap-y-0.5 text-[10px] sm:grid-cols-2">
                {o.template.criteria.map(c => (
                  <div key={c.code} className="flex items-baseline gap-1.5" title={c.detail}>
                    <span className={c.pass === true ? 'text-emerald-400'
                      : c.pass === false ? 'text-danger' : 'text-muted/50'}>
                      {c.pass === true ? '✓' : c.pass === false ? '✗' : '—'}
                    </span>
                    <span className={c.pass === null ? 'text-muted/50' : 'text-muted'}>{c.label}</span>
                    <span className="ml-auto truncate font-mono text-[9px] text-muted/60">{c.detail}</span>
                  </div>
                ))}
              </div>
              <div className="mt-1 text-[9px] text-muted/70">
                八条全部满足才是确认的上升阶段;判不出来的记「—」,不当作没通过。
              </div>
            </div>
          )}

          {/* [R188/R189] 磨了多久 + 磨得好不好。两个数凑一起才完整 ——
              「磨了 87 天」不说好坏, 「蓄势」不说久暂。 */}
          {!!o.rhythm && (o.rhythm.basing.days > 0 || o.rhythm.cycles > 0) && (
            <div className="text-muted">
              <span className="text-foreground/90">磨底节拍</span>
              {o.rhythm.basing.days > 0 && (
                <span className="ml-2 font-mono text-[10px]">
                  磨底 {o.rhythm.basing.days} 天
                  {o.rhythm.basing.low != null && o.rhythm.basing.high != null
                    && ` · 箱体 ${o.rhythm.basing.low.toFixed(2)}~${o.rhythm.basing.high.toFixed(2)}`}
                </span>
              )}
              {o.rhythm.cycles > 0 && (
                <span className="ml-2">{o.rhythm.label}:{o.rhythm.reason}</span>
              )}
            </div>
          )}

          {/* [R195] 量化波动通道的几何与事件。**几何进了分**(分离度→质地、
              加速度→时机), 所以摆在依据区而不是注记区 —— 注记那一栏的规矩是
              「一分不加一分不减」, 混进去边界就读不清了。 */}
          {!!o.geo && (
            <div className="rounded border border-border/40 bg-surface/40 px-2.5 py-2">
              <div className="mb-1 flex flex-wrap items-baseline gap-x-3 gap-y-1">
                <span className="text-foreground/90">量化波动通道</span>
                {!!o.channel_event && o.channel_event.code !== 'none' && (
                  <span className={cn('rounded border px-1.5 py-0.5 text-[10px]',
                    o.channel_event.confirmed
                      ? 'border-accent/40 bg-accent/10 text-foreground'
                      : 'border-amber-400/40 bg-amber-400/10 text-amber-300')}>
                    {o.channel_event.cn}{o.channel_event.confirmed ? '' : '(未确认)'}
                  </span>
                )}
                {!!o.geo.accel?.level_cn && (
                  <span className="font-mono text-[10px] text-muted">
                    {o.geo.accel.level_cn} {o.geo.accel.gain_atr >= 0 ? '+' : ''}
                    {o.geo.accel.gain_atr.toFixed(1)} ATR/10日
                  </span>
                )}
                <span className="font-mono text-[10px] text-muted"
                      title="短期均线与长期均线相隔多少个 ATR。≈0 粘合, 1.5~3 趋势确立, >5 尺度撕裂">
                  分离度 {o.geo.spread.toFixed(1)} ATR
                </span>
                {o.geo.compress != null && (
                  <span className="font-mono text-[10px] text-muted"
                        title="三条带的交集 / 短带宽度。1 = 均线粘合(三个尺度对合理价没有分歧), 0 = 已脱开">
                    重叠 {(o.geo.compress * 100).toFixed(0)}%
                  </span>
                )}
                {!!o.geo.combo && (
                  <span className="font-mono text-[10px] text-muted/70"
                        title="短/中/长三档位置压成的三字码 —— 27 种组合表的行号">
                    组合 {o.geo.combo}
                  </span>
                )}
              </div>
              {!!o.channel_event?.why && (
                <div className="text-[10px] leading-relaxed text-muted">{o.channel_event.why}</div>
              )}
              {!!o.channel_event?.combo_note && (
                <div className="mt-1 text-[10px] leading-relaxed text-amber-300/80">
                  组合「{o.channel_event.combo_note.combo}」· {o.channel_event.combo_note.title}:
                  {o.channel_event.combo_note.detail}
                </div>
              )}
              <div className="mt-1 text-[9px] text-muted/70">
                偏离度 短 {o.geo.d.s.toFixed(1)} / 中 {o.geo.d.m.toFixed(1)} / 长 {o.geo.d.l.toFixed(1)} 个 ATR
                (破轨门槛依次 2 / 2.5 / 3)。三档共用同一个 ATR 分母, 所以可以直接相减。
              </div>
            </div>
          )}

          {!!o.why && <div className="text-muted">{o.why}</div>}

          {!!o.notes?.length && (
            <div className="space-y-1">
              <div className="text-[10px] text-muted/70">
                以下都是<b>佐证</b>,一分不加一分不减 —— 它们要么不可回测(主线口径随情绪周期漂移)、
                要么样本太小(单票历史突破常不足 10 次)、要么是模型对自己输出的自评(AI 置信度)。
              </div>
              {o.notes.map(n => (
                <div key={n.key} className="flex gap-2">
                  <span className={cn('shrink-0 rounded px-1.5 py-0.5 text-[9px]',
                    NOTE_TONE[n.tone] ?? NOTE_TONE.info)}>{n.label}</span>
                  <span className="text-muted">{n.text}</span>
                </div>
              ))}
            </div>
          )}

          {o.advice?.plan && (
            <div className="text-sky-300/90"
                 title="金字塔建仓:每一步由价格确认驱动;假突破最多损失一个试仓(比例可在「门槛」面板调)">
              建仓路径:{o.advice.plan}
            </div>
          )}
        </div>
      </td>
    </tr>
  )
}

// ===== [R121] AI 优选面板 —— 把「凭什么信它」摆到台面上 =====
//
// 旧版这里只有一行字: 名字 + 理由。理由里那些数字(涨 7.2%、量比 1.25、守住
// 2372)看着很具体, 但**没有任何东西检查它们是不是真的** —— 模型把量比 0.87
// 写成 1.25、把关键位编到一个该股从没到过的价位, 界面照样原样展示, 而用户会
// 照着这个数去挂单。新版补上两样东西, 都直接摆在优选旁边:
//   1. **逐条数字对账**: 后端拿送审时喂给 AI 的那份日K 核对理由里的每个数字,
//      对不上标存疑、价位离谱直接驳回(驳回的不当推荐展示, 折到最下面)
//   2. **历史命中率**: 过往优选 T+1/T+3/T+5 的胜率与平均收益 —— 靠不靠谱,
//      最后只能用记录说话。带口径说明, 不说清口径的胜率就是误导。
