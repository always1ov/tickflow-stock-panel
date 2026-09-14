/**
 * [fork 增强 R327] 转折模拟盘 —— 一个组合, 只按六态转折买卖。
 *
 * 用户: 「模拟盘页面大整改, 完全不需要我原来的了, 重新设计, 每天收盘价按照转折
 * 买卖, 所有票只看趋势状态的转折」。
 *
 * 替掉 R59 那套「AI 操盘手」(8 个操作员、每天定时问模型、账本落盘)。这一页要
 * 回答的是完全不同的一个问题: **我这套六态判定, 真按它做, 长期是赚是亏?**
 *
 * ## 版面顺序 = 读它的顺序
 *
 *   ① 结论    赚了多少 / 最大回撤 / 多少轮 / 胜率 —— 一眼就该看见的四个数
 *   ② 曲线    净值走势
 *   ③ 现在    还拿着哪几只(这是"接下来要盯的")
 *   ④ 流水    每一笔为什么买、为什么卖
 *   ⑤ 没做成  封板没买进 / 仓位满了 / 钱不够 —— **空栏必须自己解释**
 *   ⑥ 规则    口径, 从后端取, 不在这里誊抄
 *
 * 结论在最前, 规则在最后: 规则是查证用的, 不该天天占着首屏(R190 那条教训 ——
 * 「顶头那两个说明, 太多废话了」)。
 *
 * ## 参数一改就是另一条曲线
 *
 * 本金 / 同时持有上限 / 回溯年数都进 queryKey。这套后端是纯函数, 同样的参数必然
 * 同样的结果, 所以缓存可以放心留着。
 */
import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { TrendingDown, TrendingUp } from 'lucide-react'
import { api, type FlipOrder, type FlipPaper as FlipPaperData, type FlipRules } from '@/lib/api'
import { QK } from '@/lib/queryKeys'
import { PageHeader } from '@/components/PageHeader'
import { Hint } from '@/components/Hint'
import { Skeleton } from '@/components/data/Skeleton'
import { useECharts } from '@/pages/backtest/charts/useECharts'
import { cn } from '@/lib/cn'

const CAPITAL_OPTIONS = [100_000, 500_000, 1_000_000, 5_000_000]
const POSITION_OPTIONS = [3, 5, 10, 20]
const YEAR_OPTIONS = [1, 2, 3, 5]

/** 没做成的原因 —— 逐条翻译。**空栏必须自己解释**: 读的人分不清"没有"和"算不出来" */
const WHY_CN: Record<string, string> = {
  sealed: '封板挂不进去',
  no_slot: '仓位已满',
  no_cash: '现金不够一手',
  voided: '一直封到反向转折, 这张单作废',
}

const REASON_CN: Record<string, string> = {
  no_data: '自选里的票都取不到日线, 一天也跑不了',
  no_flip: '这段时间里一次转折都没有 —— 不是亏了, 是压根没动过手',
  no_watchlist: '自选是空的 —— 先去自选页加几只票',
}

function pct(v: number | null | undefined, digits = 2): string {
  if (v == null) return '—'
  return `${v >= 0 ? '+' : ''}${(v * 100).toFixed(digits)}%`
}

function money(v: number | null | undefined): string {
  if (v == null) return '—'
  return v.toLocaleString('zh-CN', { maximumFractionDigits: 0 })
}

/**
 * [R328] 标的那一格 —— **名称与代码相同时只印一个**。
 *
 * 维表里查不到名称的票(退市、新股还没进维表), 后端会退回代码。那时照旧
 * 「名称 + 代码」两栏渲染, 印出来就是「000636.SZ 000636.SZ」—— 同一个字符串
 * 重复两遍, 看着像渲染坏了。
 */
function SymbolCell({ symbol, name }: { symbol: string; name: string }) {
  const named = name && name !== symbol
  return (
    <>
      <span className="font-medium">{named ? name : symbol}</span>
      {named && <span className="ml-1.5 font-mono text-[10px] text-muted">{symbol}</span>}
    </>
  )
}

export function FlipPaper() {
  const navigate = useNavigate()
  const [capital, setCapital] = useState(1_000_000)
  const [maxPositions, setMaxPositions] = useState(10)
  const [years, setYears] = useState(2)

  const q = useQuery({
    queryKey: QK.flipPaper(capital, maxPositions, years),
    queryFn: () => api.flipPaper({ capital, maxPositions, years }),
    staleTime: 5 * 60_000,
  })
  const rules = useQuery({
    queryKey: QK.flipPaperRules,
    queryFn: () => api.flipPaperRules(),
    staleTime: 24 * 3600_000,
  })

  const d = q.data
  return (
    <div className="flex h-full flex-col">
      <PageHeader
        title="转折模拟盘"
        subtitle="非真实资金 · 只按六态转折买卖 · 每次打开当场重算"
        right={
          <div className="flex flex-wrap items-center gap-1.5 text-[10px]">
            <Picker label="本金" value={capital} options={CAPITAL_OPTIONS}
                    onChange={setCapital} fmt={money} />
            <Picker label="最多持有" value={maxPositions} options={POSITION_OPTIONS}
                    onChange={setMaxPositions} fmt={(v) => `${v} 只`} />
            <Picker label="回溯" value={years} options={YEAR_OPTIONS}
                    onChange={setYears} fmt={(v) => `${v} 年`} />
          </div>
        }
      />

      <div className="min-h-0 flex-1 space-y-3 overflow-y-auto px-3 pb-4 pt-3 lg:px-4">
        {q.isLoading && <LoadingSkeleton />}
        {q.isError && (
          <div className="rounded-card border border-danger/40 bg-danger/10 px-4 py-3 text-xs text-danger">
            跑不动:{(q.error as Error)?.message}
          </div>
        )}

        {d && d.reason && (
          <div className="rounded-card border border-warning/30 bg-warning/10 px-4 py-3 text-xs text-warning">
            {REASON_CN[d.reason] ?? d.reason}
          </div>
        )}

        {d && !d.reason && (
          <>
            <Summary d={d} />
            <NavChart d={d} />
            <Holdings d={d} onOpen={(s) => navigate(`/stock-analysis?symbol=${s}`)} />
            <Orders orders={d.orders} />
            <Skipped d={d} />
          </>
        )}

        {/* 规则排在最后 —— 查证用的, 不该天天占首屏 */}
        {rules.data && <Rules r={rules.data} d={d} />}
      </div>
    </div>
  )
}

function Picker<T extends number>({ label, value, options, onChange, fmt }: {
  label: string; value: T; options: readonly T[]
  onChange: (v: T) => void; fmt: (v: T) => string
}) {
  return (
    <label className="inline-flex items-center gap-1 text-muted">
      {label}
      <select
        value={value}
        onChange={(e) => onChange(Number(e.target.value) as T)}
        className="rounded-btn border border-border bg-base px-1.5 py-0.5 text-[10px] text-foreground cursor-pointer"
      >
        {options.map((o) => <option key={o} value={o}>{fmt(o)}</option>)}
      </select>
    </label>
  )
}

function Summary({ d }: { d: FlipPaperData }) {
  const s = d.stats
  return (
    <section className="grid grid-cols-2 divide-x divide-y divide-border/30 overflow-hidden rounded-card border border-border/60 bg-surface/40 sm:grid-cols-4 sm:divide-y-0">
      <Stat label="总收益" value={pct(s.total_ret)} tone={s.total_ret >= 0 ? 'bull' : 'bear'}
            sub={`本金 ${money(d.capital)} · ${s.days} 个交易日`} />
      <Stat label="最大回撤" value={pct(s.max_drawdown)} tone="bear"
            sub="净值从高点回落最深的一次" />
      <Stat label="完整买卖" value={`${s.round_trips} 轮`}
            sub={`买 ${s.buys} 次 · 卖 ${s.sells} 次`}
            hint={'一次买入到卖出算一轮。**还拿着的那几只不算** —— 没兑现的盈亏\n不该混进胜负(与复盘页「只数已兑现」同一条纪律)。'} />
      <Stat
        label="胜率"
        value={s.win_rate == null ? '—' : `${(s.win_rate * 100).toFixed(0)}%`}
        sub={s.win_rate == null ? '一轮都没兑现, 算不出来' : `${s.win} 胜 / ${s.round_trips} 轮`}
        hint={'空着不是 0 —— 「算不出来」与「一次没赢过」是两件事。'}
      />
    </section>
  )
}

function Stat({ label, value, sub, tone, hint }: {
  label: string; value: string; sub?: string
  tone?: 'bull' | 'bear'; hint?: string
}) {
  return (
    <div className="px-4 py-2.5">
      <div className="flex items-center gap-0.5 text-[10px] text-muted">
        {label}
        {hint && <Hint title={hint} />}
      </div>
      <div className={cn('mt-0.5 text-lg font-semibold tabular-nums',
        tone === 'bull' && 'text-bull', tone === 'bear' && 'text-bear')}>
        {value}
      </div>
      {sub && <div className="mt-0.5 text-[10px] text-muted">{sub}</div>}
    </div>
  )
}

function NavChart({ d }: { d: FlipPaperData }) {
  const option = useMemo(() => {
    if (!d.nav.length) return null
    return {
      grid: { left: 56, right: 16, top: 16, bottom: 28 },
      tooltip: { trigger: 'axis' as const },
      xAxis: { type: 'category' as const, data: d.nav.map((p) => p.date),
               axisLabel: { fontSize: 10 } },
      yAxis: { type: 'value' as const, scale: true,
               axisLabel: { fontSize: 10, formatter: (v: number) => money(v) } },
      series: [{
        type: 'line' as const, name: '净值', data: d.nav.map((p) => p.nav),
        showSymbol: false, lineStyle: { width: 1.5 },
        areaStyle: { opacity: 0.08 },
      }],
    }
  }, [d.nav])
  const ref = useECharts(option, [option])
  if (!d.nav.length) return null
  return (
    <section className="overflow-hidden rounded-card border border-border/60 bg-surface/40">
      <SectionHead title="净值走势"
                   note={`${d.nav[0]?.date} 起 · 最后一天 ${d.as_of ?? '—'}`} />
      <div ref={ref} className="h-[260px] w-full" />
    </section>
  )
}

function Holdings({ d, onOpen }: { d: FlipPaperData; onOpen: (s: string) => void }) {
  return (
    <section className="overflow-hidden rounded-card border border-border/60 bg-surface/40">
      <SectionHead
        title="现在拿着"
        note={`${d.positions.length} 只 · 现金 ${money(d.nav.at(-1)?.cash)}`}
        hint={'这几只就是接下来要盯的 —— 它们各自下一次转空时, 这套规则会清掉。'}
      />
      {d.positions.length === 0 ? (
        <div className="px-4 py-5 text-xs text-muted">
          当前空仓 —— 自选里没有一只处在多头侧。<b className="text-secondary">空仓也是一种仓位</b>。
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[560px] text-xs">
            <thead className="text-[10px] text-muted">
              <tr className="text-left">
                <th className="px-4 py-1.5 font-normal">标的</th>
                <th className="px-2 py-1.5 text-right font-normal">股数</th>
                <th className="px-2 py-1.5 text-right font-normal">成本</th>
                <th className="px-2 py-1.5 text-right font-normal">现价</th>
                <th className="px-2 py-1.5 text-right font-normal">市值</th>
                <th className="px-2 py-1.5 text-right font-normal">浮盈</th>
              </tr>
            </thead>
            <tbody>
              {d.positions.map((p) => (
                <tr key={p.symbol} className="border-t border-border/30 hover:bg-elevated/40">
                  <td className="px-4 py-1.5">
                    <button onClick={() => onOpen(p.symbol)}
                            className="text-left hover:text-accent cursor-pointer">
                      <SymbolCell symbol={p.symbol} name={p.name} />
                    </button>
                  </td>
                  <td className="px-2 py-1.5 text-right tabular-nums">{p.shares.toLocaleString()}</td>
                  <td className="px-2 py-1.5 text-right tabular-nums">{p.cost?.toFixed(2) ?? '—'}</td>
                  <td className="px-2 py-1.5 text-right tabular-nums">{p.last.toFixed(2)}</td>
                  <td className="px-2 py-1.5 text-right tabular-nums">{money(p.market_value)}</td>
                  <td className={cn('px-2 py-1.5 text-right tabular-nums font-medium',
                    (p.pnl ?? 0) >= 0 ? 'text-bull' : 'text-bear')}>
                    {pct(p.pnl_pct)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}

function Orders({ orders }: { orders: FlipOrder[] }) {
  const [all, setAll] = useState(false)
  // 最近的排前面 —— 流水要回答"最近做了什么"
  const rows = useMemo(() => [...orders].reverse(), [orders])
  const shown = all ? rows : rows.slice(0, 30)
  return (
    <section className="overflow-hidden rounded-card border border-border/60 bg-surface/40">
      <SectionHead
        title="成交流水"
        note={`${orders.length} 笔 · 最近的在前`}
        right={rows.length > 30 && (
          <button onClick={() => setAll((v) => !v)}
                  className="text-[10px] text-muted hover:text-foreground cursor-pointer">
            {all ? '只看最近 30 笔' : `展开全部 ${rows.length} 笔`}
          </button>
        )}
      />
      {rows.length === 0 ? (
        <div className="px-4 py-5 text-xs text-muted">这段时间一次转折都没有, 所以一笔都没做。</div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[640px] text-xs">
            <thead className="text-[10px] text-muted">
              <tr className="text-left">
                <th className="px-4 py-1.5 font-normal">日期</th>
                <th className="px-2 py-1.5 font-normal">标的</th>
                <th className="px-2 py-1.5 font-normal">动作</th>
                <th className="px-2 py-1.5 font-normal">因为</th>
                <th className="px-2 py-1.5 text-right font-normal">成交价</th>
                <th className="px-2 py-1.5 text-right font-normal">金额</th>
              </tr>
            </thead>
            <tbody>
              {shown.map((o, i) => (
                <tr key={`${o.date}-${o.symbol}-${i}`} className="border-t border-border/30">
                  <td className="px-4 py-1.5 font-mono text-[10px] text-muted">
                    {o.date}
                    {o.delayed && (
                      <span className="ml-1 text-warning"
                            title={`信号在 ${o.signal_date}, 那几天封板挂不进去, 顺延到这天才成交`}>
                        ·延
                      </span>
                    )}
                  </td>
                  <td className="px-2 py-1.5">
                    <SymbolCell symbol={o.symbol} name={o.name} />
                  </td>
                  <td className="px-2 py-1.5">
                    <span className={cn('inline-flex items-center gap-0.5 rounded px-1.5 py-0.5 text-[10px] font-medium',
                      o.act === 'buy' ? 'bg-bull/15 text-bull' : 'bg-bear/15 text-bear')}>
                      {o.act === 'buy' ? <TrendingUp className="h-2.5 w-2.5" /> : <TrendingDown className="h-2.5 w-2.5" />}
                      {o.act === 'buy' ? '买入' : '清仓'}
                    </span>
                  </td>
                  <td className="px-2 py-1.5 text-[10px] text-secondary">
                    {o.reason}
                    {o.state_cn && <span className="ml-1 text-muted">({o.state_cn})</span>}
                  </td>
                  <td className="px-2 py-1.5 text-right tabular-nums">{o.price.toFixed(2)}</td>
                  <td className="px-2 py-1.5 text-right tabular-nums text-muted">{money(o.amount)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}

function Skipped({ d }: { d: FlipPaperData }) {
  if (!d.skipped.length && !d.missing.length) return null
  const byReason = d.skipped.reduce<Record<string, number>>((acc, s) => {
    acc[s.reason] = (acc[s.reason] ?? 0) + 1
    return acc
  }, {})
  return (
    <section className="overflow-hidden rounded-card border border-border/60 bg-surface/40">
      <SectionHead
        title="有信号但没做成"
        note={`${d.skipped.length} 次`}
        hint={'这一栏存在的理由: **不说出来的话, 曲线会显得比实际更"顺"**。\n有信号却没动手的次数, 与做成的那些同样是这套打法的一部分。'}
      />
      <div className="space-y-1.5 px-4 py-2.5 text-[11px]">
        {Object.entries(byReason).map(([r, n]) => (
          <div key={r} className="flex items-center gap-2">
            <span className="min-w-[9rem] text-secondary">{WHY_CN[r] ?? r}</span>
            <span className="tabular-nums text-muted">{n} 次</span>
          </div>
        ))}
        {d.missing.length > 0 && (
          <div className="flex items-start gap-2 pt-1">
            <span className="min-w-[9rem] shrink-0 text-warning">取不到日线</span>
            <span className="text-muted">
              {d.missing.join('、')} —— 这几只没进这次模拟, 不是它们没信号
            </span>
          </div>
        )}
        {d.pending.length > 0 && (
          <div className="flex items-start gap-2 pt-1">
            <span className="min-w-[9rem] shrink-0 text-secondary">还在等成交</span>
            <span className="text-muted">
              {d.pending.map((p) => `${p.name}(${p.act === 'buy' ? '买' : '卖'})`).join('、')}
            </span>
          </div>
        )}
      </div>
    </section>
  )
}

function Rules({ r, d }: { r: FlipRules; d?: FlipPaperData }) {
  return (
    <section className="overflow-hidden rounded-card border border-border/60 bg-surface/40">
      <SectionHead title="这套规则" note="口径 —— 与后端同一份, 不是这里另写的" />
      <div className="space-y-2 px-4 py-3 text-[11px] leading-relaxed">
        <Rule k="信号" v={r.signal} />
        <Rule k="成交" v={r.execute} />
        <Rule k="方向" v={r.direction.join('; ')} />
        <Rule k="仓位" v={`${r.sizing} —— 现在是 ${d?.max_positions ?? '—'} 只`} />
        <Rule k="标的" v={`${r.universe}${d ? ` —— 现在 ${d.symbols.length} 只` : ''}`} />
        <Rule k="不做空" v={r.short} />
        <Rule k="成本" v={`佣金 ${(r.costs.commission * 10000).toFixed(1)}‱ 双边 · 印花税 ${(r.costs.stamp_tax * 10000).toFixed(1)}‱ 卖出单边 · 滑点 ${r.costs.slippage_bps}bp · ${r.costs.lot} 股一手`} />
        <div className="mt-2 space-y-1.5 border-t border-border/40 pt-2 text-muted">
          <p>{r.caveat}</p>
          <p>{r.vs_flip_trades}</p>
          <p>{r.why_no_state}</p>
        </div>
      </div>
    </section>
  )
}

function Rule({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex gap-2">
      <span className="min-w-[3.5rem] shrink-0 text-muted">{k}</span>
      <span className="text-secondary">{v}</span>
    </div>
  )
}

function SectionHead({ title, note, right, hint }: {
  title: string; note?: string; right?: React.ReactNode; hint?: string
}) {
  return (
    <div className="flex items-center gap-2 border-b border-border/40 px-4 py-2.5">
      <span className="text-sm font-medium text-foreground">{title}</span>
      {hint && <Hint title={hint} />}
      {note && <span className="text-[10px] text-muted">{note}</span>}
      {right && <span className="ml-auto">{right}</span>}
    </div>
  )
}

function LoadingSkeleton() {
  return (
    <div role="status" aria-label="正在算" className="space-y-3">
      <div className="grid grid-cols-2 divide-x divide-y divide-border/30 overflow-hidden rounded-card border border-border/60 bg-surface/40 sm:grid-cols-4 sm:divide-y-0">
        {Array.from({ length: 4 }, (_, i) => (
          <div key={i} className="space-y-1.5 px-4 py-2.5">
            <Skeleton w="w-12" h="h-2.5" />
            <Skeleton w="w-16" h="h-5" />
            <Skeleton w="w-20" h="h-2.5" />
          </div>
        ))}
      </div>
      <div className="rounded-card border border-border/60 bg-surface/40 p-4">
        <Skeleton h="h-[240px]" rounded="rounded" />
      </div>
    </div>
  )
}
