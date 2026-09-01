/**
 * [fork 增强] R133 把握分评分体检 —— 「这套评分到底有没有用」的答卷。
 *
 * 与 R121 的 AI 命中率条(TrackRecordBar)互补, 两者回答的不是同一个问题:
 *   · AI 命中率  = AI 从规则层前 8 名里挑的那 1-3 只后来涨没涨。
 *     它有选择偏差 —— 60 分和 90 分的票从没被同台比过, 所以它证明不了评分本身。
 *   · 本面板     = **完整候选池**(含被门槛滤掉的那些)按把握分分层之后的表现。
 *
 * 四张表按"看的顺序"排, 不按数据结构排:
 *   1. 总体 + 同期基准 —— 先看有没有超额。没有基准的胜率会骗人。
 *   2. 分层单调性 —— 最关键的一张。高分档不比低分档好, 这套分数就没有信息量,
 *      再漂亮的头部胜率也可能只是运气。
 *   3. 按名次 —— 直接回答"最多显示几条"该设成几。
 *   4. 维度归因 —— [R134] 高分组不明显强于低分组的维度, 就是在白占权重。
 *      (v1 时这里分的是"吃到加分/吃到扣分"; v2 的维度分是 0~100 的连续量,
 *       没有正负, 所以改成按分数高低切。要回答的问题没变。)
 *
 * 两个导出口都指向同一件事: 把原料交出去做调参。
 *   · 「复制体检摘要」 服务端拼好的 Markdown, 粘到对话里就能直接分析(小)
 *   · 「导出明细 CSV」 一行一候选, 三维度分与各因子子分各占一列(大)
 *
 * [R134] 换打分口径之后, 老口径的记录**不进任何一张表** —— 两套分数刻度不同,
 * 混在一起算胜率没有意义。它们仍在 CSV 里(scoring_version 列区分), 面板上
 * 单独报一行数量, 免得用户以为"攒了一个月怎么样本还这么少"。
 */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { BarChart3, Check, ClipboardCopy, Download, Loader2, X } from 'lucide-react'
import { api, type LedgerStat, type LedgerStats, type ScoreLedger } from '@/lib/api'
import { QK } from '@/lib/queryKeys'
import { Modal } from '@/components/Modal'
import { copyText } from '@/lib/clipboard'
import { toast } from '@/components/Toast'
import { cn } from '@/lib/cn'

const HORIZONS: (keyof LedgerStats)[] = ['t1', 't3', 't5']
const H_LABEL: Record<string, string> = { t1: 'T+1', t3: 'T+3', t5: 'T+5' }

/** 胜率单元格。样本数一起显示 —— 没有 n 的胜率是废话。 */
function Cell({ s }: { s?: LedgerStat }) {
  if (!s?.n) return <td className="px-2 py-1 text-center text-muted/50">—</td>
  const good = (s.win_rate ?? 0) >= 50
  return (
    <td className="whitespace-nowrap px-2 py-1 text-center font-mono">
      <span className={good ? 'text-bull' : 'text-bear'}>{s.win_rate}%</span>
      <span className="text-muted/70"> / {(s.avg ?? 0) > 0 ? '+' : ''}{s.avg}%</span>
      <span className="text-muted/50"> ({s.n})</span>
    </td>
  )
}

function StatTable({ head, rows }: {
  head: string
  rows: { label: string; count?: number; stats: LedgerStats; dim?: boolean }[]
}) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[26rem] border-collapse text-[11px]">
        <thead>
          <tr className="border-b border-border/60 text-[10px] text-muted">
            <th className="px-2 py-1 text-left font-normal">{head}</th>
            <th className="px-2 py-1 text-right font-normal">条数</th>
            {HORIZONS.map(h => (
              <th key={h} className="px-2 py-1 text-center font-normal">{H_LABEL[h]}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map(r => (
            <tr key={r.label} className={cn('border-b border-border/25', r.dim && 'text-muted')}>
              <td className="whitespace-nowrap px-2 py-1">{r.label}</td>
              <td className="px-2 py-1 text-right font-mono text-muted">
                {r.count ?? '—'}
              </td>
              {HORIZONS.map(h => <Cell key={h} s={r.stats?.[h]} />)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function ScoreLedgerDialog({ onClose }: { onClose: () => void }) {
  const [copied, setCopied] = useState(false)
  const q = useQuery({
    queryKey: QK.todayScoreLedger,
    queryFn: api.todayScoreLedger,
    staleTime: 10 * 60 * 1000,
  })
  const d: ScoreLedger | undefined = q.data

  const onCopy = async () => {
    if (!d?.summary_md) return
    const ok = await copyText(d.summary_md)
    if (!ok) { toast('复制失败,浏览器拒绝了剪贴板权限'); return }
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
    toast('体检摘要已复制 —— 粘贴出去就能直接分析', 'success')
  }

  return (
    <Modal
      onClose={onClose}
      labelledBy="score-ledger-title"
      panelClassName="flex max-h-[86vh] w-[94vw] max-w-3xl flex-col rounded-card border border-border bg-surface shadow-xl"
    >
      <div className="flex items-center gap-2 border-b border-border/60 px-4 py-3">
        <BarChart3 className="h-4 w-4 text-sky-400" />
        <h2 id="score-ledger-title" className="text-sm font-medium text-foreground">
          把握分体检
        </h2>
        <span className="text-[10px] text-muted">
          {d ? `${d.first_day ?? '—'} ~ ${d.last_day ?? '—'} · ${d.recorded_days} 个交易日 · ${d.total_rows} 条候选` : '加载中'}
        </span>
        <button
          onClick={onClose}
          aria-label="关闭"
          className="ml-auto rounded-btn border border-border bg-base p-1 text-muted transition-colors hover:text-foreground"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      </div>

      <div className="flex-1 space-y-4 overflow-y-auto px-4 py-3">
        {q.isLoading && (
          <div className="flex items-center gap-2 py-8 text-xs text-muted">
            <Loader2 className="h-4 w-4 animate-spin" /> 正在补算历史收益…
          </div>
        )}
        {q.isError && <div className="py-8 text-xs text-danger">读取台账失败,请稍后重试</div>}

        {d && d.recorded_days === 0 && (
          <div className="rounded border border-border/60 bg-base/40 px-3 py-6 text-center text-xs text-muted">
            台账还是空的。<br />
            <span className="text-[11px]">
              每次在<span className="text-foreground">收盘口径</span>下打开今日总览会自动记一天
              (盘中开着实时行情时不记 —— 那时的现价不是收盘价, 拿它当收益起点会算出一份假收益)。
              收益要等 T+5 走完才补齐, 所以至少得攒一周才看得出东西。
            </span>
          </div>
        )}

        {d && d.recorded_days > 0 && (
          <>
            {/* ① 总体 + 基准 */}
            <section>
              <h3 className="mb-1 text-[11px] font-medium text-foreground">
                总体表现<span className="ml-1.5 font-normal text-muted">胜率 / 平均收益 (样本数)</span>
              </h3>
              <StatTable head="范围" rows={[
                { label: '全部候选(含被门槛滤掉的)', count: d.total_rows, stats: d.all },
                { label: '当时实际显示的', stats: d.shown },
                ...(d.baseline?.stats ? [{
                  label: `同期基准 ${d.baseline.name ?? ''}`,
                  stats: d.baseline.stats, dim: true,
                }] : []),
              ]} />
              <p className="mt-1 text-[10px] text-muted/80">
                跑不赢最后那行基准, 这套评分就没有存在价值 —— 直接买指数即可。
              </p>
            </section>

            {/* ② 分层单调性 —— 最关键 */}
            <section>
              <h3 className="mb-1 text-[11px] font-medium text-foreground">
                分层单调性
                <span className="ml-1.5 font-normal text-muted">分数有没有信息量, 主要看这张</span>
              </h3>
              <div className={cn(
                'mb-1.5 rounded border px-2.5 py-1.5 text-[11px]',
                d.monotonic.ok === true && 'border-bull/30 bg-bull/10 text-bull',
                d.monotonic.ok === false && 'border-danger/30 bg-danger/10 text-danger',
                d.monotonic.ok === null && 'border-border/60 bg-base/40 text-muted',
              )}>
                {d.monotonic.text}
              </div>
              <StatTable head="把握分档" rows={d.buckets.map(b => ({
                label: b.label, count: b.count, stats: b.stats,
              }))} />
            </section>

            {/* ③ 名次段 —— 定「最多显示几条」 */}
            <section>
              <h3 className="mb-1 text-[11px] font-medium text-foreground">
                按名次<span className="ml-1.5 font-normal text-muted">用来定「最多显示几条」</span>
              </h3>
              <StatTable head="名次段" rows={d.ranks.map(r => ({
                label: r.label, count: r.count, stats: r.stats,
              }))} />
            </section>

            {/* ④ 因子归因 */}
            <section>
              <h3 className="mb-1 text-[11px] font-medium text-foreground">
                维度归因
                <span className="ml-1.5 font-normal text-muted">
                  T+5;高分组不明显强于低分组 = 这一维在白占权重
                </span>
              </h3>
              <div className="overflow-x-auto">
                <table className="w-full min-w-[30rem] border-collapse text-[11px]">
                  <thead>
                    <tr className="border-b border-border/60 text-[10px] text-muted">
                      <th className="px-2 py-1 text-left font-normal">因子</th>
                      <th className="px-2 py-1 text-center font-normal" title="这一维 ≥70 分">高分组</th>
                      <th className="px-2 py-1 text-center font-normal" title="40~70 分">中间</th>
                      <th className="px-2 py-1 text-center font-normal" title="<40 分">低分组</th>
                      <th className="px-2 py-1 text-center font-normal"
                          title="这一维整档没数据。缺席比例高说明它的权重其实被重归一化悄悄分给别人了">缺席</th>
                    </tr>
                  </thead>
                  <tbody>
                    {d.factors.map(f => (
                      <tr key={f.key} className="border-b border-border/25">
                        <td className="whitespace-nowrap px-2 py-1">{f.label}</td>
                        <Cell s={f.plus.stats?.t5} />
                        <Cell s={f.mid?.stats?.t5} />
                        <Cell s={f.minus.stats?.t5} />
                        <Cell s={f.none.stats?.t5} />
                      </tr>
                    ))}
                    {d.factors.length === 0 && (
                      <tr><td colSpan={5} className="px-2 py-3 text-center text-muted">
                        还没有任何维度有样本
                      </td></tr>
                    )}
                  </tbody>
                </table>
              </div>
            </section>

            {!!d.legacy_days && (
              <p className="rounded border border-warning/30 bg-warning/10 px-2.5 py-1.5 text-[10px] text-warning">
                另有 {d.legacy_days} 天是**换打分口径之前**记的,未计入上面任何一张表 ——
                两套分数刻度不同,混在一起算胜率没有意义。它们仍在导出的 CSV 里
                (scoring_version 列区分)。
              </p>
            )}
            <p className="text-[10px] text-muted/80">
              口径: {d.caveat}
              {d.scoring_version ? ` · 打分口径 v${d.scoring_version}` : ''}
              {d.pending_symbols > 0 && ` · 还有 ${d.pending_symbols} 只标的的收益没补完, 下次打开继续补`}
            </p>
          </>
        )}
      </div>

      {/* 两个导出口 —— 这个面板存在的主要目的 */}
      <div className="flex flex-wrap items-center gap-2 border-t border-border/60 px-4 py-2.5">
        <button
          onClick={onCopy}
          disabled={!d?.summary_md}
          title="把上面四张表拼成一段 Markdown 复制走 —— 粘贴给外部即可直接分析, 不用自己抄数字"
          className="inline-flex items-center gap-1.5 rounded-btn border border-sky-400/40 bg-sky-400/15 px-2.5 py-1 text-[11px] text-sky-300 transition-colors cursor-pointer hover:bg-sky-400/25 disabled:opacity-40"
        >
          {copied ? <Check className="h-3 w-3" /> : <ClipboardCopy className="h-3 w-3" />}
          {copied ? '已复制' : '复制体检摘要'}
        </button>
        <a
          href={api.todayScoreLedgerExportUrl()}
          download
          title="一行一候选的扁平 CSV: 因子增量各占一列, 可直接丢进表格透视或离线重算权重"
          className="inline-flex items-center gap-1.5 rounded-btn border border-border bg-base px-2.5 py-1 text-[11px] text-muted transition-colors cursor-pointer hover:text-foreground"
        >
          <Download className="h-3 w-3" />
          导出明细 CSV
        </a>
        <span className="text-[10px] text-muted/70">
          摘要用于快速判断, CSV 用于重算权重 —— 要调参两个一起给
        </span>
      </div>
    </Modal>
  )
}
