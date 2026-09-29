/**
 * [fork R562] 虚拟账户「跟六态转折」—— 账户页上那一块「信号」, 与右列的规则说明。
 *
 * 转折模拟盘的「信号」栏(R329 / R513)搬进虚拟账户。长相照旧, 意思跟着实账变了一处:
 *
 *   模拟盘  「要动手」= 今天收盘转折了, **你**该去挂单
 *   实账    「明早开盘」= 今天收盘转折了, **系统已经挂好了**, 明早开盘成交
 *
 * 三段, 版面顺序即急迫程度:
 *
 *   明早开盘   卡片 —— 今晚已挂的单(盘后管道按收盘确认的转折挂的), 买入按把握分排先后
 *   盘中越线   卡片, 琥珀色 —— 按现价当收盘算会转折。**不是出手理由**(R329): 收盘还在
 *              线外, 今晚才会挂单; 只是让你知道今晚可能多一笔
 *   持仓       小方块 + 离清仓线的距离条(R513), 带持有天数
 *
 * 「没能动手」的记录(仓位满 / 钱不够 / 作废)后端照记, **页面不显示** ——
 * 用户在 R499 说过「有信号没做成的就不要放出来了」。
 *
 * 数据: `/api/paper/flip`(一趟给齐); 把握分取今日总览那份打分, 只排序不参与判定(R342)。
 * 不加任何动效: 这是看盘数据(AGENTS 动效硬规则第 7 条)。
 */
import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { TrendingDown, TrendingUp } from 'lucide-react'
import { api, type FlipTodaySignal, type PaperFlipPanel, type TodayOpportunity } from '@/lib/api'
import { QK } from '@/lib/queryKeys'
import { cn } from '@/lib/cn'
import { useTodayOverview } from '@/lib/useSharedQueries'
import { Hint } from '@/components/Hint'
import { ScoreCell } from '@/components/today/ScoreCell'
import { TrendCell } from '@/components/today/TrendCell'
import { LevelsDialog } from '@/components/stock-analysis/LevelsDialog'
import { StockPreviewDialog } from '@/components/StockPreviewDialog'

/** 离清仓线多近才算"贴着了"。**只用来上色, 不产生任何动作**(R339)。 */
const NEAR_EXIT = 0.02
/** 距离条满格对应多远 —— 超过它就画满。只影响条的长短(R513)。 */
const EXIT_GAUGE_FULL = 0.10
/** 后端 flip_trades.BEAR 的原值 */
const BEAR = '空头'

type OpenFn = (symbol: string, name: string) => void
type Order = PaperFlipPanel['orders'][number]

export function useFlipPanel(acc: string, enabled: boolean) {
  return useQuery({
    queryKey: QK.paperFlip(acc),
    queryFn: () => api.paperFlip(acc),
    enabled,
    staleTime: 60_000,
  })
}

export function FlipFollowCard({ acc, holdingDays }: { acc: string; holdingDays: Map<string, number> }) {
  const q = useFlipPanel(acc, true)
  const today = useTodayOverview()
  // 把握分只用来**排序与标注**(R342), 取自今日总览那份打分, 不多打一次接口
  const conv = useMemo(() => {
    const m = new Map<string, TodayOpportunity>()
    for (const o of today.data?.opportunities ?? []) if (o.rank != null) m.set(o.symbol, o)
    return m
  }, [today.data])
  const [levels, setLevels] = useState<{ symbol: string; name: string } | null>(null)
  const [review, setReview] = useState<{ symbol: string; name: string } | null>(null)
  const openLevels: OpenFn = (symbol, name) => setLevels({ symbol, name })
  const openReview: OpenFn = (symbol, name) => setReview({ symbol, name })

  const d = q.data
  const rank = (s: string) => conv.get(s)?.rank ?? Number.MAX_SAFE_INTEGER
  // 卖在前(与撮合顺序一致), 买入按把握分名次排
  const orders = (d?.orders ?? []).slice().sort((a, b) =>
    a.side !== b.side ? (a.side === 'sell' ? -1 : 1) : rank(a.symbol) - rank(b.symbol))
  const crossing = (d?.signals ?? []).filter((r) => r.stage === 'crossing')
  const held = (d?.signals ?? []).filter((r) => r.held).sort((a, b) => rank(a.symbol) - rank(b.symbol))
  const near = held.filter((r) => r.gap_pct != null && Math.abs(r.gap_pct) <= NEAR_EXIT).length

  return (
    <>
      <section className="overflow-hidden rounded-card border border-border bg-surface">
        <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5 border-b border-border/60 px-4 py-2.5">
          <span className="text-sm font-medium">信号</span>
          <span className="text-micro text-muted">
            跟六态转折{d?.rule ? ` · 同时最多 ${d.rule.max_positions} 只` : ''} · 收盘确认转折, 次日开盘成交
          </span>
          <Hint title={'**只有收盘确认的转折才出手。**\n\n转折当晚, 盘后管道自动挂**次日开盘单** —— 不用你动手。\n盘中越线 = 按此刻现价当收盘算会翻面, **不是出手理由**:\n收盘还在线外, 今晚才会挂单。\n\n「持仓」那一段: 条越短, 离清仓线越近。'} />
          {d?.as_of && <span className="ml-auto text-micro tabular-nums text-muted">数据截至 {d.as_of}</span>}
        </div>

        {q.isLoading ? (
          <div className="px-4 py-6 text-xs text-muted">加载中…</div>
        ) : q.isError ? (
          <div className="px-4 py-6 text-xs text-danger">{String((q.error as Error).message)}</div>
        ) : (
          <div className="divide-y divide-border/40">
            <div className="px-4 py-3">
              <ZoneHead title="明早开盘" count={orders.length} note="收盘确认转折, 今晚已自动挂单" />
              {orders.length > 0 ? (
                <div className="mt-2 grid gap-2 lg:grid-cols-2 2xl:grid-cols-3">
                  {orders.map((o) => (
                    <OrderCard key={o.id} o={o} c={conv.get(o.symbol)} onOpen={openLevels} onReview={openReview} />
                  ))}
                </div>
              ) : (
                <div className="mt-2 rounded-btn border border-dashed border-border px-3 py-3 text-xs text-muted">
                  今晚没有要挂的单 —— <b className="text-secondary">管住手</b>。
                </div>
              )}
            </div>

            {crossing.length > 0 && (
              <div className="px-4 py-3">
                <ZoneHead title="盘中越线" count={crossing.length} note="收盘还在线外, 今晚才挂单" />
                <div className="mt-2 grid gap-2 lg:grid-cols-2 2xl:grid-cols-3">
                  {crossing.map((r) => (
                    <CrossingCard key={r.symbol} r={r} onOpen={openLevels} onReview={openReview} />
                  ))}
                </div>
              </div>
            )}

            <div className="px-4 py-3">
              <ZoneHead title="持仓" count={held.length} note="收盘跌破离场线才清仓"
                        right={near > 0 ? <span className="text-warning">{near} 只贴近离场线</span> : undefined} />
              {held.length > 0 ? (
                <div className="mt-2 grid grid-cols-2 gap-2 lg:grid-cols-3 2xl:grid-cols-5">
                  {held.map((r) => (
                    <HoldingTile key={r.symbol} r={r} c={conv.get(r.symbol)} days={holdingDays.get(r.symbol)}
                                 onOpen={openLevels} onReview={openReview} />
                  ))}
                </div>
              ) : (
                <div className="mt-2 text-xs text-muted">空仓 —— 等下一次转多。</div>
              )}
            </div>
          </div>
        )}
      </section>
      {/* 与个股分析页同一个组件; 一块只挂一个, 由 symbol 是否为 null 驱动(关闭时退场动画才播得完) */}
      <LevelsDialog symbol={levels?.symbol ?? null} name={levels?.name ?? ''} onClose={() => setLevels(null)} />
      <StockPreviewDialog symbol={review?.symbol ?? null} name={review?.name} initialView="review"
                          onClose={() => setReview(null)} />
    </>
  )
}

/** 右列: 规则说明。后端一处出(flip_follow.RULES), 这里不誊抄。 */
export function FlipRulesCard({ acc }: { acc: string }) {
  const q = useFlipPanel(acc, true)
  const r = q.data?.rules
  if (!r) return null
  const rows: [string, string][] = [
    ['信号', r.signal], ['成交', r.execute], ['仓位', r.sizing], ['顺序', r.order],
    ['封板', r.sealed], ['标的', r.universe], ['越线', r.crossing],
  ]
  return (
    <div className="rounded-card border border-border bg-surface p-4">
      <div className="text-sm font-medium">跟六态转折 · 规则</div>
      <div className="mt-1 text-micro leading-relaxed text-muted">
        这个账户只按转折下单, 不接手动单 —— 成绩就是这套规则本身的成绩。
      </div>
      <dl className="mt-3 space-y-1.5 text-xs">
        {rows.map(([k, v]) => (
          <div key={k} className="flex gap-2">
            <dt className="w-8 shrink-0 text-muted">{k}</dt>
            <dd className="min-w-0 flex-1 leading-relaxed text-secondary"><Md text={v} /></dd>
          </div>
        ))}
        <div className="flex gap-2">
          <dt className="w-8 shrink-0 text-muted">方向</dt>
          <dd className="min-w-0 flex-1 space-y-0.5 leading-relaxed text-secondary">
            {r.direction.map((x) => <div key={x}>{x}</div>)}
          </dd>
        </div>
      </dl>
    </div>
  )
}

/** 后端文字里的 **加粗** —— 只认这一种, 不引 markdown 库 */
function Md({ text }: { text: string }) {
  return <>{text.split('**').map((t, i) => (i % 2 ? <b key={i} className="text-foreground">{t}</b> : t))}</>
}

function ZoneHead({ title, count, note, right }: { title: string; count: number; note: string; right?: React.ReactNode }) {
  return (
    <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5 text-xs">
      <span className="font-medium text-foreground">{title}</span>
      <span className="tabular-nums text-muted">{count}</span>
      <span className="text-micro text-muted/80">{note}</span>
      {right && <span className="ml-auto text-micro">{right}</span>}
    </div>
  )
}

/** 名称与代码相同时只印一个(R328: 维表查不到名称时后端退回代码) */
function SymbolButton({ symbol, name, onOpen, className }: { symbol: string; name: string; onOpen: OpenFn; className?: string }) {
  const named = name && name !== symbol
  return (
    <button type="button" onClick={() => onOpen(symbol, name)} title={`看 ${name} 的日 K 与关键价位`}
            className={cn('min-w-0 cursor-pointer truncate text-left transition-colors hover:text-accent', className)}>
      <span className="font-medium">{named ? name : symbol}</span>
      {named && <span className="ml-1.5 font-mono text-micro text-muted">{symbol}</span>}
    </button>
  )
}

function PriceLine({ r }: { r: FlipTodaySignal }) {
  if (r.flip_price == null) return null
  return (
    <span className="whitespace-nowrap tabular-nums">
      触发 {r.flip_price.toFixed(2)}
      {r.ref_price != null && <> · 现 {r.ref_price.toFixed(2)}</>}
      {!r.live && <span className="ml-1 text-warning/70">昨收口径</span>}
    </span>
  )
}

const md = (d: string | null) => (d ? `${Number(d.slice(5, 7))}/${Number(d.slice(8, 10))}` : '')

/** 明早开盘那一段的一张卡: 买入红、清仓绿(红涨绿跌)。名次那一格只排先后, 不是动作(R344)。 */
function OrderCard({ o, c, onOpen, onReview }: { o: Order; c?: TodayOpportunity; onOpen: OpenFn; onReview: OpenFn }) {
  const buy = o.side === 'buy'
  // 挂单那天比信号日晚 = 封板没成交、方向没变, 重挂的
  const retried = !!o.since && !!o.created_at && o.created_at.slice(0, 10) > o.since
  return (
    <div className={cn('flex gap-3 rounded-btn border border-l-2 px-3 py-2.5',
      buy ? 'border-bull/30 border-l-bull bg-bull/[0.07]' : 'border-bear/30 border-l-bear bg-bear/[0.10]')}>
      {buy && c?.rank != null && (
        <div className="shrink-0"><ScoreCell o={c} rank={c.rank} total={c.rank_total ?? 0} /></div>
      )}
      <div className="min-w-0 flex-1 space-y-1">
        <div className="flex items-center gap-2">
          <SymbolButton symbol={o.symbol} name={o.name} onOpen={onOpen} className="text-sm text-foreground" />
          <span className={cn('ml-auto inline-flex shrink-0 items-center gap-1 rounded-btn px-2 py-0.5 text-xs font-semibold',
            buy ? 'bg-bull/15 text-bull' : 'bg-bear/15 text-bear')}>
            {buy ? <TrendingUp className="h-3.5 w-3.5" /> : <TrendingDown className="h-3.5 w-3.5" />}
            {buy ? '买入' : '清仓'}
          </span>
        </div>
        <button type="button" onClick={() => onReview(o.symbol, o.name)}
                title={`看 ${o.name} 的逐日复盘 —— 这个状态是怎么走到今天的`}
                className="block w-full cursor-pointer truncate text-left text-xs text-secondary transition-colors hover:text-accent">
          {md(o.since)} 收盘转{buy ? '多' : '空'} · 明早开盘{buy ? '买入' : '卖出'} {o.qty.toLocaleString('zh-CN')} 股
        </button>
        {buy && c && <div className="text-xs"><TrendCell o={c} /></div>}
        {retried && <div className="text-micro text-warning/80">开盘封板没成交, 方向没变, 今晚重挂</div>}
      </div>
    </div>
  )
}

/** 盘中越线: 琥珀色左条, **不给动作徽标** —— 越线不是出手理由, 连徽标的位置都不留(R513)。 */
function CrossingCard({ r, onOpen, onReview }: { r: FlipTodaySignal; onOpen: OpenFn; onReview: OpenFn }) {
  const toBear = r.side !== BEAR
  return (
    <div className="space-y-1 rounded-btn border border-l-2 border-warning/30 border-l-warning bg-warning/[0.05] px-3 py-2.5">
      <div className="flex items-center gap-2">
        <SymbolButton symbol={r.symbol} name={r.name} onOpen={onOpen} className="text-sm text-foreground" />
        <span className="ml-auto shrink-0 text-micro text-warning">盘中越线</span>
      </div>
      <button type="button" onClick={() => onReview(r.symbol, r.name)}
              title={`看 ${r.name} 的逐日复盘`}
              className="block w-full cursor-pointer truncate text-left text-xs text-secondary transition-colors hover:text-accent">
        按现价会转{toBear ? '空' : '多'} —— <b className="text-warning">收盘还在线外, 今晚才{toBear ? '挂清仓' : '挂买入'}</b>
      </button>
      <div className="text-micro text-muted"><PriceLine r={r} /></div>
    </div>
  )
}

/** 持仓那一段的一个方块: 只问一件事 —— 离清仓线还有多远(R513)。不带动作徽标。 */
function HoldingTile({ r, c, days, onOpen, onReview }: {
  r: FlipTodaySignal; c?: TodayOpportunity; days?: number; onOpen: OpenFn; onReview: OpenFn
}) {
  const dist = r.gap_pct != null ? Math.abs(r.gap_pct) : null
  const warn = r.stage === 'crossing' || (dist != null && dist <= NEAR_EXIT)
  const fill = dist != null ? Math.min(1, dist / EXIT_GAUGE_FULL) : 0
  // 收盘已确认转空 —— 今晚已挂清仓单(在「明早开盘」那一段), 这里不再画离清仓线的距离
  const exiting = r.stage === 'flipped' && r.side === BEAR
  return (
    <div className={cn('rounded-btn border px-3 py-2', warn ? 'border-warning/40 bg-warning/[0.06]' : 'border-border/50 bg-base/30')}>
      <div className="flex items-baseline gap-2">
        <SymbolButton symbol={r.symbol} name={r.name} onOpen={onOpen} className="text-xs text-foreground" />
        {c?.rank != null && <span className="ml-auto shrink-0 text-micro tabular-nums text-muted" title="把握分名次">第 {c.rank} 名</span>}
      </div>
      <button type="button" onClick={() => onReview(r.symbol, r.name)}
              title={`离清仓线还有多远 —— 条越短越近, 满格是 ${EXIT_GAUGE_FULL * 100}% 以上。点开看 ${r.name} 的逐日复盘`}
              className="mt-1.5 flex w-full cursor-pointer items-center gap-2 text-left">
        <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-elevated">
          {!exiting && <span className={cn('block h-full rounded-full', warn ? 'bg-warning' : 'bg-secondary/50')}
                             style={{ width: `${Math.max(fill * 100, 3)}%` }} />}
        </span>
        <span className={cn('shrink-0 text-xs font-semibold tabular-nums',
          exiting ? 'text-bear' : warn ? 'text-warning' : 'text-secondary')}>
          {exiting ? '明早清仓' : r.stage === 'crossing' ? '越线' : dist != null ? `${(dist * 100).toFixed(1)}%` : '—'}
        </span>
      </button>
      <div className="mt-1 flex justify-between gap-2 text-micro text-muted">
        <span className="shrink-0 tabular-nums">{days != null ? `持有 ${days} 天` : '持有 —'}</span>
        <span className="min-w-0 truncate"><PriceLine r={r} /></span>
      </div>
    </div>
  )
}
