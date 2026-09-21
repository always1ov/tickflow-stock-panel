/**
 * [fork 增强] R133 把握分评分体检 —— 「这套评分到底有没有用」的答卷。
 *
 * 与 R121 的 AI 命中率条(TrackRecordBar)互补, 两者回答的不是同一个问题:
 *   · AI 命中率  = AI 从规则层前 8 名里挑的那 1-3 只后来涨没涨。
 *     它有选择偏差 —— 60 分和 90 分的票从没被同台比过, 所以它证明不了评分本身。
 *   · 本面板     = **完整候选池**(含被门槛滤掉的那些)按把握分分层之后的表现。
 *
 * 五张表按"看的顺序"排, 不按数据结构排:
 *   1. 总体 + 同期基准 —— 先看有没有超额。没有基准的胜率会骗人。
 *   2. 分层单调性 —— 最关键的一张。高分档不比低分档好, 这套分数就没有信息量,
 *      再漂亮的头部胜率也可能只是运气。
 *   3. 按名次 —— 直接回答"最多显示几条"该设成几。
 *   4. 维度归因 —— [R134] 高分组不明显强于低分组的维度, 就是在白占权重。
 *      (v1 时这里分的是"吃到加分/吃到扣分"; v2 的维度分是 0~100 的连续量,
 *       没有正负, 所以改成按分数高低切。要回答的问题没变。)
 *   5. [R175] 回头看 —— 前四张都在验**把握分**; 这一张验的是那批
 *      **不参与打分的标签**(通道档位/六态趋势/主线/龙虎榜)。它们在界面上
 *      天天下结论, 恰恰因为不进分数, 从来没被验证过。
 *      读法也和前四张不同: 前面看绝对水平, 这里看**全期与最近的背离** ——
 *      长期能赚的那档最近开始亏, 才是这一栏想告诉你的事。
 *      末尾挂一段 AI 提炼, 它**只念这张表**: 分组与胜率全由后端算完,
 *      AI 只负责讲成人话, 说错了也不影响任何一个数字。
 *
 * 两个导出口都指向同一件事: 把原料交出去做调参。
 *   · 「复制体检摘要」 服务端拼好的 Markdown, 粘到对话里就能直接分析(小)
 *   · 「导出明细 CSV」 一行一候选, 两轴分与各因子子分各占一列(大)
 *
 * [R134] 换打分口径之后, 老口径的记录**不进任何一张表** —— 两套分数刻度不同,
 * 混在一起算胜率没有意义。它们仍在 CSV 里(scoring_version 列区分), 面板上
 * 单独报一行数量, 免得用户以为"攒了一个月怎么样本还这么少"。
 */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { BarChart3, Check, ClipboardCopy, Download, Loader2, Sparkles, X } from 'lucide-react'
import {
  api,
  type LedgerLabelDim,
  type LedgerStat,
  type LedgerStats,
  type PatternDigest,
  type ScoreLedger,
} from '@/lib/api'
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

/**
 * [R175] 回头看: 一个标签维度的各档, 全期与最近**并排**。
 *
 * 这一栏跟上面四张表的读法不同 —— 上面看的是绝对水平(这档胜率高不高),
 * 这里看的是**变化**(这档最近还灵不灵)。所以视觉重心放在最右边那列背离上,
 * 两个数字本身反而是配角。
 */
function LabelDimTable({ dim, minN }: { dim: LedgerLabelDim; minN: number }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[30rem] border-collapse text-[11px]">
        <thead>
          <tr className="border-b border-border/60 text-[10px] text-muted">
            <th className="px-2 py-1 text-left font-normal">{dim.label}</th>
            <th className="px-2 py-1 text-right font-normal">条数</th>
            <th className="px-2 py-1 text-center font-normal" title="全部记录日, T+5">全期</th>
            <th className="px-2 py-1 text-center font-normal" title="最近那段, T+5">最近</th>
            <th className="px-2 py-1 text-left font-normal"
                title="两边样本都够才给结论 —— 这一列才是这张表存在的理由">变化</th>
          </tr>
        </thead>
        <tbody>
          {dim.items.map(it => {
            // 样本不够的档整行压暗: 让它可见(用户要知道这档还没攒够),
            // 但读起来明显不如够样本的那几行有分量
            const thin = (it.stats?.t5?.n ?? 0) < minN
            return (
              <tr key={it.value}
                  className={cn('border-b border-border/25', thin && 'text-muted/60')}>
                <td className="whitespace-nowrap px-2 py-1">{it.value}</td>
                <td className="px-2 py-1 text-right font-mono text-muted">{it.count}</td>
                <Cell s={it.stats?.t5} />
                <Cell s={it.recent_stats?.t5} />
                <td className="px-2 py-1">
                  {it.shift ? (
                    <span className={cn(
                      'whitespace-nowrap',
                      it.shift.dir === 'down' && 'text-bear',
                      it.shift.dir === 'up' && 'text-bull',
                      it.shift.dir === 'flat' && 'text-muted/70',
                    )}>
                      {it.shift.dir === 'down' ? '↓ ' : it.shift.dir === 'up' ? '↑ ' : ''}
                      {it.shift.delta > 0 ? '+' : ''}{it.shift.delta}pt
                    </span>
                  ) : (
                    <span className="text-muted/40" title={`两边各需 ${minN} 个样本才给结论`}>
                      样本不足
                    </span>
                  )}
                </td>
              </tr>
            )
          })}
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

  // [R175] 提炼**只在点按钮时**跑。打开弹窗显示的是服务端存档(可能是昨天的) ——
  // 同一批数据反复问 AI 会给两套说法, 而"今天和昨天说的不一样"会被读成行情
  // 变了, 其实只是采样噪声。
  const [digesting, setDigesting] = useState(false)
  const [fresh, setFresh] = useState<PatternDigest | null>(null)
  const digest = fresh ?? d?.digest ?? null

  const onDigest = async () => {
    setDigesting(true)
    try {
      setFresh(await api.todayScoreLedgerDigest())
    } catch (e) {
      toast(e instanceof Error ? e.message : '提炼失败', 'error')
    } finally {
      setDigesting(false)
    }
  }

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
        {q.isError && (
          <div className="py-8 text-xs text-danger">
            读取台账失败:{(q.error as Error)?.message || '未知错误'}
          </div>
        )}

        {/* 空态要说清**为什么**空 —— 「台账还是空的」本身回答不了任何问题。
            两个真实原因各有各的出路, 分开说:
              · 记了, 但全是换口径之前的 → 数量报出来, 免得以为一天都没攒
              · 一天都没记 → 十有八九是只在盘中看盘(那时不记, 见下)
            原来这里写的是「打开**今日总览**会自动记一天」—— 那一页在 R340/R343
            已经拆掉了, 照这句话去做是做不到的。改成指这一页。 */}
        {d && d.recorded_days === 0 && (
          <div className="rounded border border-border/60 bg-base/40 px-3 py-6 text-center text-xs text-muted">
            {d.legacy_days
              ? <>台账里有 {d.legacy_days} 天, 但<span className="text-foreground">全是换打分口径之前</span>记的 ——
                  两套分数刻度不同, 混在一起算胜率没有意义, 所以一张表都排不出来。
                  它们仍在导出的 CSV 里。</>
              : <>台账还是空的。</>}
            <br />
            <span className="text-[11px]">
              这一页每打开一次就记一天, <span className="text-foreground">但只在收盘口径下记</span> ——
              盘中开着实时行情时不记(那时的现价不是收盘价, 拿它当收益起点会算出一份假收益)。
              <b className="font-medium text-foreground/90">所以只在盘中看盘的话, 台账会一直是空的</b>;
              收盘后、或关掉实时行情再打开一次才会落账, 顶上那条自检会写明这次记没记。
              收益还要等 T+5 走完才补齐, 所以至少得攒一周才看得出东西。
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

            {/* ⑤ [R175] 回头看 —— 不参与打分的那批标签, 到底灵不灵 */}
            {!!d.labels?.length && (
              <section className="rounded border border-border/60 bg-base/40 p-2.5">
                <h3 className="mb-1 text-[11px] font-medium text-foreground">
                  回头看 · 这些结论最近还灵吗
                  <span className="ml-1.5 font-normal text-muted">
                    T+5;这批标签<b className="font-medium text-foreground/90">一分不参与打分</b>,也正因如此从没被验证过
                  </span>
                </h3>
                <p className="mb-2 text-[10px] text-muted/80">
                  「全期」是长期成色,「最近」是近 {d.recent_days ?? 20} 个记录日 ——
                  真正要看的是<b className="font-medium text-foreground/90">两者背离</b>:长期能赚的那档最近开始亏,才是这张表想告诉你的事。
                  单看全期看不出来,一年的均值会把最近一个月的转向稀释掉。
                </p>
                <div className="space-y-3">
                  {d.labels.map(dim => (
                    <LabelDimTable key={dim.key} dim={dim} minN={d.min_label_n ?? 15} />
                  ))}
                </div>

                {/* AI 提炼 —— 只念上面那张表 */}
                <div className="mt-3 border-t border-border/40 pt-2">
                  <div className="mb-1 flex flex-wrap items-center gap-2">
                    <span className="text-[11px] font-medium text-foreground">AI 提炼</span>
                    <button
                      onClick={onDigest}
                      disabled={digesting}
                      title="把上面那几张表交给 AI 念成人话。它只能引用表里的数字,样本不足的档不许下结论;今天已经跑过就直接返回存档"
                      className="inline-flex items-center gap-1 rounded-btn border border-violet-400/40 bg-violet-400/15 px-2 py-0.5 text-[10px] text-violet-300 transition-colors cursor-pointer hover:bg-violet-400/25 disabled:opacity-40"
                    >
                      {digesting
                        ? <Loader2 className="h-3 w-3 animate-spin" />
                        : <Sparkles className="h-3 w-3" />}
                      {digest ? '重新提炼' : '让 AI 试着说两句'}
                    </button>
                    {digest?.as_of && (
                      <span className="text-[10px] text-muted/70">{digest.as_of} 的提炼</span>
                    )}
                  </div>
                  {digest?.text ? (
                    <p className="whitespace-pre-wrap rounded border border-violet-400/20 bg-violet-400/5 px-2.5 py-2 text-[11px] leading-relaxed text-foreground/90">
                      {digest.text}
                    </p>
                  ) : (
                    <p className="text-[10px] text-muted/70">
                      还没跑过。AI 只负责把上面的数字讲成人话 ——
                      分组和胜率都是代码算的,它说错了也不影响那些数。
                    </p>
                  )}
                  <p className="mt-1 text-[10px] text-muted/60">
                    提炼结果<b className="font-medium text-foreground/80">不参与打分、不进任何提示词</b>,并且连同当时那张表一起存档 ——
                    三个月后能回头看它当时说得准不准。
                  </p>
                </div>
              </section>
            )}

            {!!d.legacy_days && (
              <p className="rounded border border-warning/30 bg-warning/10 px-2.5 py-1.5 text-[10px] text-warning">
                另有 {d.legacy_days} 天是<b className="font-medium">换打分口径之前</b>记的,未计入上面任何一张表 ——
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
