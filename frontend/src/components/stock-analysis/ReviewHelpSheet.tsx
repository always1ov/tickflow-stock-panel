/**
 * [fork 增强 R292] 复盘弹窗里的「说明」抽屉 —— 六态与通道结论各是什么意思。
 *
 * 用户: 「把全景按钮改成说明或者帮助按钮, 里面是解释每个六态状态、结论状态是
 * 什么意思」。
 *
 * ## 为什么是**右侧抽屉**而不是盖满
 *
 * 上一版(R289 的「全景」)是一层盖住整个正文的面板, 用户第一句就是
 * 「全景按钮做得不够好, 我点进去全屏了」。**说得对**: 词汇表是**边看边查**的
 * 东西 —— 你正盯着某一行的「自然回撤」想不起来它什么意思, 这时候把那张表整个
 * 盖掉, 等于逼你先记住要查什么再翻回去。
 *
 * 抽屉从右边推进来, 占约 26rem, 正文那一侧仍然看得见 —— 一边对着行, 一边读
 * 释义。这也是「说明」和「全景」的根本差别: 全景是**另一批内容**(该并列),
 * 说明是**手边的注解**(该并排)。
 *
 * ## 词条为什么从后端取
 *
 * 名字与结论文案的正主在 `livermore.STATE_LABELS` 与 `keltner._VERDICTS`。前端
 * 誊抄一份的话, 底层哪天改了措辞, 那份誊抄就开始说假话 —— 而且**没有任何东西
 * 会报错**。R203 的 27 格速查表当初就是为这个理由做成端点的。
 *
 * 动效: 只推 `transform`(translate-x)与 `opacity`, 180ms ease-out,
 * `motion-reduce` 下整个关掉。Esc 只关这一层, 不许穿透到外面那个复盘弹窗。
 */
import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { HelpCircle, Loader2, X } from 'lucide-react'
import { api } from '@/lib/api'
import { QK } from '@/lib/queryKeys'
import { cn } from '@/lib/cn'
import { trendBadgeCls } from '@/components/stock-analysis/TrendStateBar'

/** 打开说明的那个按钮。与页签、日期档同一套外观 —— 它是同一层级的控件 */
export function HelpButton({ onClick }: { onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      title="六态状态与通道结论各是什么意思"
      className="inline-flex items-center gap-1 rounded-btn border border-border/60 px-2 py-1 text-[10px] text-muted transition-colors hover:text-foreground"
    >
      <HelpCircle className="h-3 w-3" />
      说明
    </button>
  )
}

// 结论那十档的语气配色。与决策台、复盘逐日表同一套 —— 同一个结论在三处
// 必须是同一个颜色, 否则读的人得先确认它们是不是一回事。
const TONE_CLS: Record<string, string> = {
  sell: 'border-red-400/40 bg-red-400/10 text-red-400',
  buy: 'border-sky-400/40 bg-sky-400/10 text-sky-300',
  hold: 'border-amber-400/40 bg-amber-400/10 text-amber-400',
  avoid: 'border-border bg-base text-muted',
  watch: 'border-border bg-elevated/60 text-secondary',
}

export function ReviewHelpSheet({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [shown, setShown] = useState(false)
  useEffect(() => {
    if (!open) { setShown(false); return }
    const id = requestAnimationFrame(() => setShown(true))
    return () => cancelAnimationFrame(id)
  }, [open])

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') { e.stopPropagation(); onClose() }
    }
    window.addEventListener('keydown', onKey, true)
    return () => window.removeEventListener('keydown', onKey, true)
  }, [open, onClose])

  // 结果恒定, 拉一次就够 —— 与 27 格速查表同一个缓存策略
  const q = useQuery({
    queryKey: QK.glossary,
    queryFn: () => api.glossary(),
    staleTime: 24 * 3600_000,
    enabled: open,
  })

  if (!open) return null
  return (
    <div
      className={cn(
        'absolute inset-y-0 right-0 z-20 flex w-[min(26rem,92%)] flex-col',
        'border-l border-border bg-surface shadow-2xl',
        'transition-[opacity,transform] duration-[180ms] ease-out motion-reduce:transition-none',
        shown ? 'translate-x-0 opacity-100' : 'translate-x-4 opacity-0',
      )}
    >
      <div className="flex shrink-0 items-center gap-2 border-b border-border/60 px-3 py-2">
        <span className="text-[11px] text-secondary">说明</span>
        <span className="text-[10px] text-muted">这些词各是什么意思</span>
        <button type="button" onClick={onClose}
                className="ml-auto text-muted transition-colors hover:text-foreground">
          <X className="h-3.5 w-3.5" />
        </button>
      </div>

      <div className="min-h-0 flex-1 overflow-auto px-3 py-2.5">
        {q.isLoading && (
          <div className="flex items-center gap-2 py-10 text-[11px] text-muted">
            <Loader2 className="h-3.5 w-3.5 animate-spin" /> 正在取…
          </div>
        )}
        {q.isError && <div className="py-10 text-center text-[11px] text-red-400">说明加载失败</div>}

        {q.data && (
          <>
            <Section
              title="六态状态"
              note="这一列的徽标。六档是一条从强到弱的连续轴, 不是六个并列的标签"
            >
              {q.data.trend.map((t) => (
                <Term
                  key={t.code}
                  badge={<span className={cn('inline-flex whitespace-nowrap rounded border px-1.5 py-0.5 text-[10px]',
                                             trendBadgeCls(t.code as Parameters<typeof trendBadgeCls>[0]))}>{t.title}</span>}
                  side={t.side}
                  meaning={t.meaning}
                  action={t.action}
                />
              ))}
            </Section>

            <Section
              title="通道结论"
              note="「结论」那一列。十档按偏买 → 偏卖排, 与别处的排序同一个次序"
            >
              {q.data.verdict.map((v) => (
                <Term
                  key={v.code}
                  badge={<span className={cn('inline-flex whitespace-nowrap rounded border px-1.5 py-0.5 text-[10px]',
                                             TONE_CLS[v.tone] ?? TONE_CLS.avoid)}>{v.title}</span>}
                  meaning={v.meaning}
                  action={v.action}
                />
              ))}
            </Section>
          </>
        )}
      </div>
    </div>
  )
}

function Section({ title, note, children }: {
  title: string; note: string; children: React.ReactNode
}) {
  return (
    <section className="mb-4 last:mb-0">
      <div className="mb-1.5 flex flex-wrap items-baseline gap-x-2">
        <h3 className="text-[11px] font-medium text-foreground">{title}</h3>
        <span className="text-[10px] text-muted">{note}</span>
      </div>
      <div className="divide-y divide-border/40 rounded-btn border border-border/60">{children}</div>
    </section>
  )
}

function Term({ badge, side, meaning, action }: {
  badge: React.ReactNode; side?: string; meaning: string; action: string
}) {
  return (
    <div className="px-2.5 py-2">
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        {badge}
        {!!side && <span className="text-[10px] text-muted">{side}侧</span>}
      </div>
      <p className="mt-1 text-[10px] leading-relaxed text-secondary">{meaning}</p>
      {/* 「该怎么办」是作者那一层的原话 —— 与释义分开排, 免得读成同一句 */}
      {!!action && (
        <p className="mt-0.5 text-[10px] leading-relaxed text-muted">
          <span className="opacity-60">怎么做:</span> {action}
        </p>
      )}
    </div>
  )
}
