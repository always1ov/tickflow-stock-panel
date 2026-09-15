/**
 * [fork 增强 R341] 今日总览的**浓缩版** —— 挂在模拟盘底部当补充。
 *
 * 用户: 「模拟盘现在有的东西都不能动了, 特别是就只看六态这个逻辑, 想把今日总览
 * 里面的东西浓缩到模拟盘里面显示, 当作补充」, 「全都要, 尽可能节省空间」。
 *
 * ## 这一块最要紧的一条: 它**不是**出手依据
 *
 * 模拟盘整页的身份是「只看六态转折」——「今天该挂什么单」里能长出买卖徽标的,
 * 只有真转折那一档(R329 的铁律, R338 又加固过一次)。而这里搬过来的「值得关注」
 * **判据完全不同**: 打分系统 v2 的三维度加权 + 三道硬门槛, 再叠 AI 优选。
 * 两套判据放在同一页上, 最大的风险不是占地方, 是**读的人以为它们是一回事**。
 *
 * 所以这一块做了三件事把界线划死:
 *
 *   1. **一个动作徽标都不渲染** —— 没有买入/清仓, 连位置都不留;
 *   2. 标题上直接写明判据来源, 并点出「不是六态转折」;
 *   3. 整块**默认收起**, 排在模拟盘全部内容之后 —— 版面顺序即重要性,
 *      补充就该在补充的位置上。
 *
 * 守卫钉住第 1 条(动作词的字面量不许出现在本文件里)。
 *
 * ## 省空间的做法
 *
 * 收起时**只占一行**: 折叠条本身就是摘要 —— 姿态徽章 + 多空比 + 转多/转空 +
 * 主线 + 值得关注条数。也就是说不展开也能拿到「今天什么天气、有没有东西看」,
 * 展开才是明细。这比"给个标题让人点开才知道有没有内容"省的不只是像素,
 * 还有每天那一次点击。
 *
 * **自检条是例外, 永远在外面**: 它一切正常时本来就一个像素都不占, 而它要说的是
 * 「你正在看的数字是几天前的」—— 那句话被折叠起来就失去了全部意义。
 *
 * ## 数据自己取, 不动模拟盘那条查询
 *
 * 用 `QK.todayOverview` 同一个 key —— 与今日总览页共享缓存, 两页都开着时只打
 * 一次接口。节奏跟着今日总览走(盘中开实时 60 秒, 否则一小时), **不跟模拟盘的
 * `derived` 档**: 这份数据是今日总览那边的口径, 换个节奏就是第二处产地。
 */
import { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { ChevronDown, Loader2, Sparkles } from 'lucide-react'
import { api, type TodayOverview, type TodayOpportunity } from '@/lib/api'
import { QK } from '@/lib/queryKeys'
import { inRealtimeWindow } from '@/lib/marketClock'
import { cn } from '@/lib/cn'
import { storage } from '@/lib/storage'
import { toast } from '@/components/Toast'
import { TodayHealthBar } from '@/components/today/TodayHealthBar'

/** 姿态四档的配色。与今日总览那张卡同一套语义, 不另立一份说法。 */
const POSTURE_TONE: Record<string, string> = {
  进攻: 'bg-bull/15 text-bull',
  谨慎: 'bg-warning/15 text-warning',
  防守: 'bg-bear/15 text-bear',
  观察: 'bg-muted/15 text-muted',
}

/** 展开区限高 —— 值得关注可能几十只, 让它把整页顶长等于没折叠。 */
const LIST_MAX = 'max-h-72'

export function TodayDigest() {
  const navigate = useNavigate()
  const [open, setOpen] = useState(() => storage.flipDigestOpen.get(false))
  const toggle = () => {
    setOpen((v) => {
      storage.flipDigestOpen.set(!v)
      return !v
    })
  }

  const q = useQuery({
    queryKey: QK.todayOverview,
    queryFn: () => api.todayOverview(),
    staleTime: 60_000,
    // 与今日总览页逐字相同的节奏 —— 同一份数据不该有两种刷新口径
    refetchInterval: (query) =>
      (query.state.data as TodayOverview | undefined)?.live && inRealtimeWindow()
        ? 60_000
        : 60 * 60 * 1000,
    refetchOnWindowFocus: true,
  })

  const [brief, setBrief] = useState<string | null>(null)
  const [aiError, setAiError] = useState<string | null>(null)
  const aiMut = useMutation({
    mutationFn: () => api.todayAi(),
    onMutate: () => setAiError(null),
    onSuccess: (r) => {
      if (r.error) { setAiError(r.error); toast(r.error, 'error'); return }
      setBrief(r.brief || null)
    },
    // 失败必须在页面上留痕 —— toast 一闪即逝, 用户会以为"点了没反应"
    onError: (e: Error) => {
      setAiError(`AI 分析失败: ${e.message}`)
      toast(`AI 分析失败: ${e.message}`, 'error')
    },
  })

  const d = q.data
  if (!d) return null

  const w = d.weather
  const ops = d.opportunities ?? []
  const shownBrief = brief ?? d.ai?.brief ?? null
  const mainline = d.meso?.mainline?.rows?.[0]?.member ?? null

  return (
    <>
      {/* 自检条在折叠之外 —— 「你看的数字是几天前的」这句话折起来就没有意义了 */}
      {!!d.health && <TodayHealthBar h={d.health} />}

      <section className="overflow-hidden rounded-card border border-border/60 bg-surface/40">
        {/* 折叠条本身就是摘要: 不展开也拿得到天气与条数 */}
        <button
          type="button"
          onClick={toggle}
          aria-expanded={open}
          className="flex w-full flex-wrap items-center gap-x-2 gap-y-1 px-4 py-2 text-[11px] transition-colors hover:bg-elevated/40 cursor-pointer"
        >
          <ChevronDown className={cn('h-3 w-3 shrink-0 text-muted transition-transform duration-expand ease-smooth',
            open && 'rotate-180')} />
          <span className="text-muted">补充 · 今日总览</span>

          <span className={cn('rounded px-1.5 py-0.5 font-medium',
            POSTURE_TONE[w.posture] ?? POSTURE_TONE.观察)}>
            {w.posture}
          </span>
          <span className="text-secondary">
            多 {w.bull} / 空 {w.bear}
            <span className="ml-1.5 text-muted">转多 {w.new_bull} · 转空 {w.new_bear}</span>
          </span>
          {mainline && <span className="text-muted">主线 {mainline}</span>}

          <span className="ml-auto whitespace-nowrap text-muted">
            值得关注 {ops.length} 只
            {d.opportunities_filtered > 0 && (
              <span className="opacity-60"> · 门槛挡下 {d.opportunities_filtered}</span>
            )}
          </span>
        </button>

        {open && (
          <div className="border-t border-border/40">
            {/* 姿态的理由 —— 结论已经在折叠条上了, 展开要给的是依据 */}
            {w.posture_reason && (
              <div className="px-4 py-2 text-[11px] leading-relaxed text-muted">
                {w.posture_reason}
              </div>
            )}

            {/* AI 导读: 手动点一次, 不自动跑 */}
            <div className="flex flex-wrap items-center gap-2 border-t border-border/30 px-4 py-2">
              <button
                type="button"
                onClick={() => aiMut.mutate()}
                disabled={aiMut.isPending}
                className="inline-flex items-center gap-1 rounded-btn border border-border px-2 py-0.5 text-[11px] text-secondary transition-colors hover:bg-elevated/60 disabled:opacity-50 cursor-pointer"
              >
                {aiMut.isPending
                  ? <Loader2 className="h-3 w-3 animate-spin" />
                  : <Sparkles className="h-3 w-3" />}
                AI 导读
              </button>
              {aiError && <span className="text-[11px] text-danger">{aiError}</span>}
              {!aiError && !shownBrief && (
                <span className="text-[10px] text-muted">手动点一次才生成, 不自动跑</span>
              )}
            </div>
            {shownBrief && (
              <p className="max-w-[80ch] px-4 pb-2 text-[12px] leading-[1.8] text-foreground">
                {shownBrief}
              </p>
            )}

            {/* 值得关注 —— **判据与本页主线不同, 标题上就写明** */}
            <div className="flex flex-wrap items-center gap-2 border-t border-border/30 bg-elevated/20 px-4 py-2 text-[11px] text-secondary">
              值得关注
              <span className="text-[10px] text-muted">
                判据是打分三维度 + 硬门槛, <b className="text-warning/80">不是六态转折</b> ——
                这一块只作参考, 本页的出手依据永远是上面那段
              </span>
            </div>
            {ops.length === 0 ? (
              <div className="px-4 py-3 text-[11px] text-muted">
                {d.opportunities_empty_why ?? '今天没有过门槛的候选'}
              </div>
            ) : (
              <div className={cn(LIST_MAX, 'divide-y divide-border/30 overflow-y-auto')}>
                {ops.map((o) => (
                  <OpportunityRow key={o.symbol} o={o}
                                  onOpen={() => navigate(`/stock-analysis?symbol=${o.symbol}`)} />
                ))}
              </div>
            )}
          </div>
        )}
      </section>
    </>
  )
}

/**
 * 一只候选一行。**没有动作位** —— 不是灰掉, 是根本不渲染。
 * 名次比裸分好读(R201 定的口径), 所以主显名次, 分数退到悬停里。
 */
function OpportunityRow({ o, onOpen }: { o: TodayOpportunity; onOpen: () => void }) {
  return (
    <button
      type="button"
      onClick={onOpen}
      className="flex w-full flex-wrap items-center gap-x-3 gap-y-1 px-4 py-1.5 text-left text-[11px] transition-colors hover:bg-elevated/40 cursor-pointer"
    >
      <span className="min-w-[8rem]">
        <span className="font-medium text-foreground">{o.name}</span>
        {o.symbol !== o.name && (
          <span className="ml-1.5 font-mono text-[10px] text-muted">{o.symbol}</span>
        )}
      </span>
      {o.rank != null && (
        <span className="whitespace-nowrap text-[10px] text-muted"
              title={`把握分 ${o.score?.toFixed?.(0) ?? '—'}${o.partial ? '(有因子缺席, 偏乐观)' : ''}`}>
          第 {o.rank}/{o.rank_total ?? '—'}
          {o.partial && <span className="ml-1 text-warning/70">部分</span>}
        </span>
      )}
      {o.trend_state_cn && <span className="text-[10px] text-muted">{o.trend_state_cn}</span>}
      <span className="min-w-0 flex-1 truncate text-secondary">{o.text}</span>
      {o.close != null && (
        <span className="whitespace-nowrap font-mono text-[10px] text-muted">
          {o.close.toFixed(2)}
        </span>
      )}
    </button>
  )
}
