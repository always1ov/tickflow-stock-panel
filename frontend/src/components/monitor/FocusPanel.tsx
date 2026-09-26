import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Pin, BellOff, AlertTriangle } from 'lucide-react'
import { api, type FocusItem, type FocusTier, type FocusView } from '@/lib/api'
import { QK } from '@/lib/queryKeys'
import { cn } from '@/lib/cn'
import { toast } from '@/components/Toast'
import { Skeleton } from '@/components/data/Skeleton'

/** [R159] 焦点名单 —— 自选太多时, 谁值得推送。
 *
 * 用户: 「我自选个股太多了, 不知道哪些才是我真的要推送通知的」。
 * 不让用户逐只勾(150 只没人勾得动), 而是按已有决策产出**自动分档**:
 *   持有   positions 标了持有 —— 任何时候都要推
 *   计划中 总览快照「值得关注」那一档 —— 今天/收盘打算动手的那几只
 *
 * [R392] 这三处原本写的是「今日总览」—— 那一页 R340/R351 已经拆掉并重定向到
 * 模拟盘, 让人去"打开一次今日总览"是条走不通的路。快照本身还在(仍由
 * `_build_overview` 产出, [R136] 起由日线管道保底), 改的只是怎么称呼它。
 *   观察   其余 —— 只记应用内, 不打外部渠道
 * 用户只在例外处动手: 钉住(永远推) / 静音(永远不推)。
 * 总开关默认关 —— 推送行为不能悄悄变, 看过名单觉得对了再打开。
 * 单独给某只票设的规则(点位提醒等)不受此门影响, 永远推。
 *
 * [R524] 原来是监控中心顶上一条可折叠的「推送焦点」条(FocusBar), 现在是监控中心的一栏, 四档摊开成四列。
 * 名字统一叫「焦点名单」—— CONTEXT.md 与后端一直是这个名字, 界面上叫「推送焦点」是同一个东西两个名字。 */
const TIER_STYLE: Record<FocusTier, string> = {
  held: 'border-bull/40 bg-bull/10 text-bull',
  plan: 'border-accent/40 bg-accent/10 text-accent',
  band: 'border-warning/40 bg-warning/10 text-warning',   // [R161] 贴轨: 高抛低吸候选
  watch: 'border-border bg-elevated/60 text-muted',
}
const TIERS: FocusTier[] = ['held', 'plan', 'band', 'watch']

export function FocusPanel() {
  const qc = useQueryClient()
  const [showWatch, setShowWatch] = useState(false)
  const q = useQuery({ queryKey: QK.focus, queryFn: api.focusList, staleTime: 30_000 })
  const apply = (v: FocusView) => qc.setQueryData(QK.focus, v)
  const prefsMut = useMutation({
    mutationFn: (on: boolean) => api.focusPrefs(on),
    onSuccess: (v) => { apply(v); toast(v.focus_only ? '已开启: 弹窗/推送/徽标只认焦点名单' : '已关闭: 所有告警照常打扰', 'success') },
    onError: (e: Error) => toast(e.message, 'error'),
  })
  const overrideMut = useMutation({
    mutationFn: ({ symbol, mode }: { symbol: string; mode: 'pin' | 'mute' | null }) => api.focusOverride(symbol, mode),
    onSuccess: apply,
    onError: (e: Error) => toast(e.message, 'error'),
  })
  const v = q.data
  if (!v) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} h="h-8" rounded="rounded-card" />)}
      </div>
    )
  }
  const labels = v.labels
  const byTier = (t: FocusTier) => v.items.filter(i => i.effective === t)
  const gated = byTier('held').length + byTier('plan').length + byTier('band').length

  const Row = ({ it }: { it: FocusItem }) => {
    const pinned = it.override === 'pin'
    const muted = it.override === 'mute'
    return (
      <li className="flex items-center gap-2 border-b border-border/50 py-1.5 pl-1 pr-0.5 text-xs">
        <span className="shrink-0 font-medium text-foreground">{it.name}</span>
        <span className="shrink-0 font-mono text-micro text-muted">{it.symbol}</span>
        <span className="min-w-0 flex-1 truncate text-muted" title={it.reason}>{it.reason}</span>
        <button
          onClick={() => overrideMut.mutate({ symbol: it.symbol, mode: pinned ? null : 'pin' })}
          title={pinned ? '取消钉住' : '钉住: 无论分档, 永远推送'}
          className={cn('rounded p-1 transition-colors cursor-pointer', pinned ? 'text-accent' : 'text-muted/50 hover:text-accent')}
        ><Pin className="h-3 w-3" /></button>
        <button
          onClick={() => overrideMut.mutate({ symbol: it.symbol, mode: muted ? null : 'mute' })}
          title={muted ? '取消静音' : '静音: 无论分档, 广域规则不推(单独设的点位提醒仍推)'}
          className={cn('rounded p-1 transition-colors cursor-pointer', muted ? 'text-warning' : 'text-muted/50 hover:text-warning')}
        ><BellOff className="h-3 w-3" /></button>
      </li>
    )
  }

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center gap-x-4 gap-y-2 text-xs text-muted">
        <span>
          名单来自总览快照(持有 + 值得关注), 每次构建自动刷新
          {v.as_of ? ` · 数据日 ${v.as_of}` : ''}。钉住 / 静音是你的例外, 长期有效。
        </span>
        {!v.fresh && (
          <span className="inline-flex items-center gap-1 text-micro text-warning" title="总览快照超过 7 天没构建, 名单失效期间推送门放行">
            <AlertTriangle className="h-3 w-3" />名单已过期, 放行中
          </span>
        )}
        <label className="ml-auto inline-flex cursor-pointer items-center gap-2 text-xs text-secondary"
               title={'开(默认): 全市场/自选分组/板块这类广域规则, 只对「持有 + 计划中 + 钉住」弹窗、响铃、推外部渠道、计徽标; 焦点外的只写进触发记录(灰显)。\n单独给某只票设的规则(点位提醒等)不受影响, 永远推。\n关: 所有告警照常打扰。'}>
          <span>只认焦点名单</span>
          <button
            role="switch" aria-checked={v.focus_only}
            disabled={prefsMut.isPending}
            onClick={() => prefsMut.mutate(!v.focus_only)}
            className={cn('relative h-4 w-7 rounded-full transition-colors', v.focus_only ? 'bg-accent' : 'bg-border')}
          >
            <span className={cn('absolute top-0.5 h-3 w-3 rounded-full bg-white transition-transform', v.focus_only ? 'translate-x-3.5' : 'translate-x-0.5')} />
          </button>
        </label>
      </div>
      {gated === 0 && (
        <div className="mb-3 text-xs text-muted">还没有持有 / 计划中 / 贴轨的票 —— 日线管道跑一次、或打开一次模拟盘, 名单就会生成。</div>
      )}
      <div className="grid gap-x-6 gap-y-4 md:grid-cols-2 xl:grid-cols-4">
        {TIERS.map(t => {
          const items = byTier(t)
          const collapsed = t === 'watch' && !showWatch
          return (
            <section key={t} className="min-w-0">
              <div className="flex items-center gap-2 border-b border-border pb-1">
                <span className={cn('rounded border px-1.5 py-px text-micro', TIER_STYLE[t])}>{labels[t]}</span>
                <span className="font-mono text-micro tabular-nums text-muted">{v.counts[t]}</span>
                {t === 'watch' && (
                  <button onClick={() => setShowWatch(s => !s)} className="ml-auto text-micro text-muted transition-colors hover:text-foreground cursor-pointer">
                    {showWatch ? '收起' : '展开'}
                  </button>
                )}
              </div>
              {collapsed ? (
                <div className="py-2 text-micro text-muted">不推外部渠道, 想推就钉住它</div>
              ) : items.length === 0 ? (
                <div className="py-2 text-micro text-muted/60">无</div>
              ) : (
                <ul>{items.map(it => <Row key={it.symbol} it={it} />)}</ul>
              )}
            </section>
          )
        })}
      </div>
    </div>
  )
}
