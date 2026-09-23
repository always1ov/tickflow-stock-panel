/**
 * [R429] 个股弹窗的新头部 —— 按用户给的排版图做的第一块。
 *
 * 用户: 「我想重做整个弹窗, 我发你一点就修改一点」→ 发来头部的图:「你只需要看排版,
 * 我里面的文字大都是占位符」。又定了几条:
 *   · 新头部**加在最前面**, 旧顶栏原样留着, 「后面等我叫你删除旧的」;
 *   · 60 / 120 / 250 日「直接按照图片」放在头部, 另补一个「AI 四维分析」入口(图里漏了);
 *   · 「结论」那一句、「导出复盘」「使用说明」两个按钮**先占位**。
 *     [R447] 「使用说明」撤了。用户: 「删掉导出复盘后面的使用说明按钮, 不需要了」。
 *   · [R472] 刷新按钮挪上来。它原来只在旧顶栏里, 而旧顶栏自 R432 起排到了新块后面, 要一路
 *     滚到底才看得见 —— 量化MACD 取数失败时图上写的是「稍后点右上角刷新重试」, 右上角却没有。
 *
 * 两行:
 *
 *     名称 代码  现价  涨跌幅  起 ~ 止 · N 个交易日  [☆]      [60日][120日][250日] [AI 四维分析] [导出复盘] [⟳]
 *     结论  (待定) ───────────────────────────────────────────────────────────────
 *
 * 天数与复盘页**是同一个值**(由弹窗持有, 两处都能改): 现在用到 60/120/250 的只有复盘。
 * 「起 ~ 止 · N 个交易日」从弹窗已经在取的那份日 K 里数最后 N 根, 不为这一行另发请求 ——
 * 复盘那份要"回算", 只为了头部一行字就每次开弹窗都回算一遍不划算。
 */
import { Loader2, RefreshCw, Sparkles, Star } from 'lucide-react'
import { toast } from '@/components/Toast'
import { WatchlistAddMenu } from '@/components/WatchlistAddMenu'
import { useAnalysisKline } from '@/components/stock-analysis/StockLevelsPanel'
import { SectionTitle } from '@/components/ui'
import { PILL, PILL_IDLE, PILL_ON, SQUARE } from './pill'

export const HERO_DAYS = [60, 120, 250] as const
/** 打开弹窗、切到另一只票时的天数 */
export const HERO_DAYS_DEFAULT = 120

export function PreviewHero({
  symbol, name, days, onDaysChange, inWatchlist, watchBusy, onWatchAdd, onWatchRemove,
  onAiAnalyze, aiBusy = false, onRefresh,
}: {
  symbol: string
  name?: string
  days: number
  onDaysChange: (d: number) => void
  inWatchlist: boolean
  watchBusy: boolean
  onWatchAdd: (groupId?: string | null) => void
  onWatchRemove: () => void
  onAiAnalyze?: (symbol: string, name?: string) => void
  aiBusy?: boolean
  /** 重取这只票弹窗里的数据(与旧顶栏那个刷新是同一个函数) */
  onRefresh: () => void
}) {
  // 与关键价位页同一份日 K(同一个查询键, 不多发请求)
  const kline = useAnalysisKline(symbol)
  const rows = kline.data?.rows ?? []
  const last = rows.at(-1)
  const prev = rows.at(-2)
  const chg = last && prev && prev.close ? (last.close - prev.close) / prev.close : null
  const tone = chg == null || chg === 0 ? 'text-muted' : chg > 0 ? 'text-bull' : 'text-bear'
  const span = rows.slice(-days)
  const dateOf = (r?: { date: unknown }) => (r ? String(r.date).slice(0, 10) : '')

  const todo = (what: string) => toast(`「${what}」还没定, 先占着位置`, 'info')

  return (
    <div className="shrink-0 border-b border-border/60 px-4 pb-3 pt-4 sm:px-6">
      {/* 第一行: 左边认票 + 行情, 右边这一页的操作。窄屏整行换下去, 不挤 */}
      <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-3">
        <div className="flex min-w-0 flex-wrap items-baseline gap-x-3 gap-y-1">
          <span className="truncate text-xl font-semibold text-foreground">{name || symbol}</span>
          <span className="font-mono text-xs text-muted">{symbol}</span>
          <span className={`font-mono text-xl font-semibold tabular-nums ${tone}`}>
            {last ? last.close.toFixed(2) : '—'}
          </span>
          <span className={`font-mono text-sm tabular-nums ${tone}`}>
            {chg == null ? '—' : `${chg > 0 ? '+' : ''}${(chg * 100).toFixed(2)}%`}
          </span>
          {span.length > 0 && (
            <span className="text-xs text-muted">
              {dateOf(span[0])} ~ {dateOf(span.at(-1))} · {span.length} 个交易日
            </span>
          )}
          {/* 自选: 方框里一颗星。已在自选 = 实心金, 点了移出; 不在 = 空心, 点了选分组加入 */}
          <span className="self-center">
            {inWatchlist ? (
              <button type="button" onClick={onWatchRemove} disabled={watchBusy}
                      title="移出自选" aria-label={`将 ${symbol} 移出自选`}
                      className={SQUARE}>
                <Star className="h-4 w-4 fill-current text-[#FACC15]" />
              </button>
            ) : (
              <WatchlistAddMenu onSelect={onWatchAdd} disabled={watchBusy}
                                triggerClassName={`${SQUARE} text-muted`}
                                ariaLabel={`将 ${symbol} 加入自选`}>
                <Star className="h-4 w-4" />
              </WatchlistAddMenu>
            )}
          </span>
        </div>

        <div className="flex shrink-0 flex-wrap items-center gap-2">
          {HERO_DAYS.map(n => (
            <button key={n} type="button" onClick={() => onDaysChange(n)}
                    aria-pressed={days === n}
                    className={`${PILL} ${days === n ? PILL_ON : PILL_IDLE}`}>
              {n} 日
            </button>
          ))}
          {onAiAnalyze && (
            <button type="button" onClick={() => onAiAnalyze(symbol, name)} disabled={aiBusy}
                    title={`对 ${name || symbol} 生成 AI 四维分析(技术 / 基本面 / 财务 / 消息面)`}
                    className={`${PILL} ${PILL_IDLE} gap-1.5`}>
              {aiBusy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Sparkles className="h-3.5 w-3.5 text-accent" />}
              AI 四维分析
            </button>
          )}
          <button type="button" onClick={() => todo('导出复盘')} className={`${PILL} ${PILL_IDLE}`}>
            导出复盘
          </button>
          <button type="button" onClick={onRefresh} title="刷新" aria-label={`刷新 ${name || symbol} 的数据`}
                  className={`${SQUARE} text-secondary hover:text-foreground`}>
            <RefreshCw className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* 第二行: 结论(占位)+ 一道细线把这一行拉满 */}
      {/* [R449] 与各分区同一个形状(标题 + 副标题 + 细线), 就用同一个组件 */}
      <SectionTitle className="mt-3" title="结论" sub="(待定)" />
    </div>
  )
}
