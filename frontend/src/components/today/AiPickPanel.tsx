/** [fork 增强] AI 导读·优选面板(含 R121 事后命中率条)。[R167] 从 Today.tsx 拆出。 */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api, type TodayOverview, type TodayPick } from '@/lib/api'
import { QK } from '@/lib/queryKeys'

const VERDICT_STYLE: Record<string, { cls: string; label: string }> = {
  已核对: { cls: 'bg-emerald-400/15 text-emerald-300 border-emerald-400/30', label: '✓ 数字已核对' },
  待查:   { cls: 'bg-border/40 text-muted border-border', label: '理由无数字可核' },
  存疑:   { cls: 'bg-amber-400/15 text-amber-300 border-amber-400/30', label: '⚠ 存疑' },
  驳回:   { cls: 'bg-danger/15 text-danger border-danger/30', label: '✕ 已驳回' },
}

function CheckRow({ c }: { c: NonNullable<TodayPick['checks']>[number] }) {
  const actual = Array.isArray(c.actual) ? `${c.actual[0]}~${c.actual[1]}` : c.actual
  return (
    <li className="flex items-baseline gap-1.5 font-mono text-[10px]">
      <span className={c.ok === true ? 'text-emerald-400' : c.ok === false ? 'text-danger' : 'text-muted'}>
        {c.ok === true ? '✓' : c.ok === false ? '✕' : '?'}
      </span>
      <span className="text-muted">{c.kind}</span>
      <span className="text-foreground/80">AI 说 {c.said}</span>
      {actual !== null && actual !== undefined && (
        <span className={c.ok === false ? 'text-danger' : 'text-muted'}>· 实际 {actual}</span>
      )}
    </li>
  )
}

function TrackRecordBar() {
  const q = useQuery({
    queryKey: QK.todayAiTrackRecord,
    queryFn: api.todayAiTrackRecord,
    staleTime: 10 * 60 * 1000,
  })
  const s = q.data?.stats
  if (!s || (s.t1.n === 0 && s.t3.n === 0 && s.t5.n === 0)) {
    return (
      <span className="text-[10px] text-muted">
        历史命中率:样本还不够(已记录 {q.data?.recorded_days ?? 0} 天,每天优选后自动累计)
      </span>
    )
  }
  const cell = (k: 't1' | 't3' | 't5', label: string) => {
    const v = s[k]
    if (!v.n) return null
    const good = (v.win_rate ?? 0) >= 50
    return (
      <span key={k} className="whitespace-nowrap">
        <span className="text-muted">{label} </span>
        <span className={good ? 'text-danger' : 'text-success'}>
          {v.win_rate}% 胜 / 均 {(v.avg ?? 0) > 0 ? '+' : ''}{v.avg}%
        </span>
        <span className="text-muted/70"> ({v.n})</span>
      </span>
    )
  }
  return (
    <span className="flex flex-wrap items-baseline gap-x-3 gap-y-0.5 text-[10px]"
          title={q.data?.caveat}>
      <span className="text-muted">历史命中率</span>
      {(['t1', 't3', 't5'] as const).map((k, i) => cell(k, ['T+1', 'T+3', 'T+5'][i]))}
      <span className="text-muted/60">· 收盘价口径,未计滑点</span>
    </span>
  )
}

export function AiPickPanel({ picks, analyzed, opportunities, onOpen }: {
  picks: TodayPick[]
  analyzed: number
  opportunities: TodayOverview['opportunities']
  onOpen: (symbol: string, name: string) => void
}) {
  const [openChecks, setOpenChecks] = useState<string | null>(null)
  // 驳回的不当推荐展示 —— 一条编造价位的建议, 比没有建议更糟
  const shown = picks.filter(p => p.verdict !== '驳回')
  const rejected = picks.filter(p => p.verdict === '驳回')

  return (
    <div className="border-b border-amber-400/20 bg-amber-400/[0.06] px-4 py-2.5 text-xs">
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <span className="text-[10px] font-medium text-amber-300">
          AI 优选 {shown.length} 只
          <span className="ml-1.5 font-normal text-muted">· 已对比 {analyzed} 只的日 K 与量能后选出</span>
        </span>
        <TrackRecordBar />
      </div>

      {shown.length === 0 && rejected.length === 0 ? (
        <div className="mt-1.5 text-muted">
          AI 逐一看过这 {analyzed} 只的量价后,认为都不够理想 —— 空仓等待也是决策
        </div>
      ) : (
        // [R139] 一只一行, 不再是一只一个三行的方框。
        //
        // 原来每只优选要占三行(名字+徽标 / 理由 / 存疑说明)外加一圈边框与内边距,
        // 两只就吃掉 ~180px, 把下面真正要看的候选表挤下屏。这里全部收进一行:
        // 名字、核对徽标、理由、存疑提示、对账入口横着排, 窄屏才回落成换行。
        // 信息一项没少 —— 少的是包装。
        <ul className="mt-1 divide-y divide-border/30">
          {shown.map((p, i) => {
            const o = opportunities.find((x) => x.symbol === p.symbol)
            const style = VERDICT_STYLE[p.verdict ?? '待查'] ?? VERDICT_STYLE.待查
            const open = openChecks === p.symbol
            return (
              // [R122] 入场: 320ms 上移淡入, 逐条错开 60ms —— AI 跑完后结果是
              // "长出来"的, 不是突然闪现; 只给优选卡, 表格行不做(每次刷新都动会闹)
              <li key={p.symbol}
                  style={{ animationDelay: `${i * 60}ms` }}
                  className="animate-rise-in py-1">
                <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
                  <button
                    onClick={() => onOpen(p.symbol, o?.name ?? p.name ?? p.symbol)}
                    className="shrink-0 font-medium text-foreground hover:underline cursor-pointer"
                  >
                    {o?.name ?? p.name ?? p.symbol}
                  </button>
                  <span className={`shrink-0 rounded border px-1.5 py-0.5 text-[9px] ${style.cls}`}
                        title={p.verdict_note || undefined}>
                    {style.label}
                  </span>
                  <span className="text-foreground/80">{p.reason}</span>
                  {/* 存疑说明原来单独占一行; 它只是补充, 跟在理由后面就够 */}
                  {p.verdict === '存疑' && p.verdict_note && (
                    <span className="text-[10px] text-amber-300/90">({p.verdict_note})</span>
                  )}
                  {!!p.checks?.length && (
                    <button
                      onClick={() => setOpenChecks(open ? null : p.symbol)}
                      className="ml-auto shrink-0 text-[9px] text-muted hover:text-foreground"
                    >
                      {open ? '收起对账' : `对账 ${p.checks.length} 项`}
                    </button>
                  )}
                </div>
                {open && p.checks && (
                  <ul className="mt-1 space-y-0.5 border-l-2 border-border/40 pl-2">
                    {p.checks.map((c, i) => <CheckRow key={i} c={c} />)}
                  </ul>
                )}
              </li>
            )
          })}
        </ul>
      )}

      {rejected.length > 0 && (
        <div className="mt-2 rounded border border-danger/25 bg-danger/[0.05] px-2.5 py-1.5">
          <div className="text-[10px] font-medium text-danger">
            {rejected.length} 条被驳回,没有当作推荐
          </div>
          <ul className="mt-0.5">
            {rejected.map((p) => (
              <li key={p.symbol} className="flex flex-wrap items-baseline gap-x-1.5 text-[10px] leading-5 text-muted">
                <span className="text-foreground/70">{p.name || p.symbol}</span>
                <span className="line-through">{p.reason}</span>
                <span className="text-danger/80">{p.verdict_note}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

// ===== [R142] 市场状态卡 —— 原来的「市场天气」+「中观」两条横幅合并重做 =====
//
// 旧版的毛病不是配色, 是**版式**: 两条横幅各自是一行跑马灯式的长句, 关键数字
// 全埋在散文里 ——「沪深300 收盘 4611 已跌破年线(200日均线)4699,大环境转坏;
// 自选:在涨势中的自选只剩 40%,今天转弱的(38 只)明显多于转强的(54 只)…」。
// 要从这样一句话里读出"今天能不能出手", 得逐字扫一遍; 而这五个数
// (仓位基调 / 出手结构 / 自选强弱 / 全市场 / 成交额)才是真正要看的东西。
//
// 重做的三件事:
//   1. **数字从散文里拎出来做成统计格** —— 标签在上、数值加大加粗在中、口径在下。
//      一眼扫过去就是五个数, 不用读句子。
//   2. **长句降级成可展开的「为什么」** —— 它是解释不是结论, 不该默认占两行。
//   3. **两条横幅合并** —— 大盘姿态与中观资金说的是同一件事的两个层面,
//      拆成两个卡片反而要在两处找同一个判断。
