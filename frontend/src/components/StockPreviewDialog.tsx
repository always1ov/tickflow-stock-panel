import { useEffect, useMemo, useRef, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { motion, AnimatePresence } from 'framer-motion'
import { api } from '@/lib/api'
import { QK } from '@/lib/queryKeys'
import { cn } from '@/lib/cn'
import { cnDateFromUtc } from '@/lib/format'
import { StockPanel, getDefaultRange } from '@/components/StockPanel'
import { NavWrapToast } from '@/components/NavPager'
import { StockMultiDayIntradayChart } from '@/components/StockMultiDayIntradayChart'
import { RuleEditor } from '@/components/monitor/RuleEditor'
import { PriceAlertDialog } from '@/components/stock-analysis/PriceAlertDialog'
import { StockLevelsPanel, useAnalysisKline } from '@/components/stock-analysis/StockLevelsPanel'
import { useLevelControls } from '@/components/stock-analysis/levelControls'
import { HERO_DAYS_DEFAULT, PreviewHero } from '@/components/stock-preview/PreviewHero'
import { ChartLevelsSection, type ChartView } from '@/components/stock-preview/ChartLevelsSection'
import { ReviewSection } from '@/components/stock-preview/ReviewSection'
import { StatusSection } from '@/components/stock-preview/StatusSection'
import { PILL, PILL_IDLE, PILL_ON } from '@/components/stock-preview/pill'
import { buildMonitorPriceLines } from '@/lib/price-alerts'
import { usePreferences } from '@/lib/useSharedQueries'
import { setFocusSymbol, clearFocusSymbol } from '@/lib/useQuoteStream'
import { useDialogBackdrop } from '@/lib/useDialogBackdrop'
import { storage } from '@/lib/storage'
import { navItemKey, type NavItem } from '@/lib/listNav'
import { useListNav } from '@/lib/useListNav'
import { DEFAULT_INTRADAY_DAYS } from '@/lib/kline'
import { ExtensionSlot } from '@/extensions/ExtensionSlot'

interface Props {
  symbol: string | null
  name?: string
  onClose: () => void
  /** 是否开放“关键价位”视图。[R103] 全站统一弹窗后默认开启 —— 自选/监控/异动
      等所有入口与策略页、个股分析页看到同一套三视图(日K/分时/关键价位)。 */
  enableLevelsView?: boolean
  /** 有序候选列表: 提供后支持左右键切股(首尾循环) */
  navList?: NavItem[]
  /** 切股回调: 收到目标 symbol/name, 由调用方更新预览状态 */
  onNavigate?: (symbol: string, name?: string) => void
  /**
   * [R427] 打开时落在哪一页。不传 = 「关键价位」(R185 的默认)。
   * 决策台点「走势/位置」时传 'review' —— [R479] 旧复盘页删了, 打开时直接定位到新「复盘」块。
   */
  initialView?: PreviewView
  /**
   * [R428] AI 四维分析(技术 / 基本面 / 财务 / 消息面)。传了才在顶栏操作区出这个按钮。
   * 流程(今日已分析过 → 确认查看 / 重新分析)仍归调用方, 这里只是入口 ——
   * 用户: 「ai 四维分析想要放到弹窗里面去, 找个合适的位置, 外面就不要了」。
   */
  onAiAnalyze?: (symbol: string, name?: string) => void
  /** [R428] 调用方正在查今日报告 / 发起分析 —— 按钮转圈并禁用, 防连点 */
  aiBusy?: boolean
}

export type PreviewView = 'daily' | 'intraday' | 'levels' | 'review'
interface PriceAlertDraft {
  id: number
  targetPrice: number
  currentPrice: number
}
const INTRADAY_DAY_OPTIONS = [1, 5, 10, 20] as const

function loadIntradayDays(): number {
  const saved = storage.stockPreviewIntradayDays.get(DEFAULT_INTRADAY_DAYS)
  return INTRADAY_DAY_OPTIONS.includes(saved as typeof INTRADAY_DAY_OPTIONS[number])
    ? saved
    : DEFAULT_INTRADAY_DAYS
}

export function StockPreviewDialog({ symbol, name, onClose, enableLevelsView = true, navList: navListSource, onNavigate, initialView, onAiAnalyze, aiBusy = false }: Props) {
  // [R479] 旧顶栏 + 切换条(最近查看 / 搜索)删了: 弹窗里不再有内部换股, symbol / name 就是调用方给的;
  // 方向键切股(useListNav)照旧, 由调用方 onNavigate 换票。
  // [R185] 默认落在「关键价位」而不是日K —— 这个弹窗是拿来做决策的, 图表模块
  // 自己的注释也写着「本图表面向分析决策, 核心是关键价位」。点进来先看到的
  // 该是压力/支撑/枢轴那几条线, 而不是一根还要自己看的 K 线。
  // [R429] 60 / 120 / 250 日 —— 新头部与复盘页**同一个值**(用户: 「直接按照图片」放在头部)
  const [reviewDays, setReviewDays] = useState<number>(HERO_DAYS_DEFAULT)
  // [R430] 「图表与价位」的视图, 以及价位列表与图共用的开关状态。都不随切股重置 —— 与原来的关键价位页一样,
  // 方向键翻票时开着的那几类、看的那个视图都留着。
  const [chartView, setChartView] = useState<ChartView>('levels')
  const levelCtl = useLevelControls()
  const [intradayDays, setIntradayDays] = useState<number | null>(loadIntradayDays)
  const [dateRange] = useState(getDefaultRange)
  const [showMonitorEditor, setShowMonitorEditor] = useState(false)
  const [priceAlertDraft, setPriceAlertDraft] = useState<PriceAlertDraft | null>(null)
  const qc = useQueryClient()
  const backdrop = useDialogBackdrop(onClose)

  const watchlist = useQuery({
    queryKey: QK.watchlist,
    queryFn: api.watchlistList,
    enabled: !!symbol,
  })
  const monitorRules = useQuery({
    queryKey: QK.monitorRules,
    queryFn: api.monitorRulesList,
    enabled: !!symbol,
  })
  const monitorPriceLines = useMemo(
    () => symbol ? buildMonitorPriceLines(monitorRules.data?.rules ?? [], symbol) : [],
    [monitorRules.data?.rules, symbol],
  )
  const watchlistEntry = useMemo(
    () => (watchlist.data?.symbols ?? []).find(s => s.symbol === symbol),
    [watchlist.data, symbol],
  )
  const inWatchlist = !!watchlistEntry
  // 加入自选日 (北京时间)。该日不在当前K线区间内或恰是非交易日时竖线不画, 由工具栏文字兜底。
  const addedDate = useMemo(
    () => cnDateFromUtc(watchlistEntry?.added_at) || null,
    [watchlistEntry],
  )

  const toggleWatchlist = useMutation({
    mutationFn: ({
      action,
      groupId,
    }: {
      action: 'add' | 'remove'
      groupId?: string | null
    }) => action === 'remove'
      ? api.watchlistRemove(symbol!)
      : api.watchlistAdd(symbol!, '', groupId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: QK.watchlist })
      qc.invalidateQueries({ queryKey: ['watchlist-enriched'] })
    },
  })

  // ===== 切股导航 =====
  // onClose 只有 ESC 用; onNavigate 由 useListNav 内部承接 (支持内联 lambda)
  const onCloseRef = useRef(onClose)
  onCloseRef.current = onClose

  const nav = useListNav<NavItem>({
    items: navListSource ?? [],
    keyOf: navItemKey,
    currentKey: symbol,
    onNavigate: n => onNavigate?.(n.symbol, n.name),
    // 点位监控弹窗/规则编辑器打开时方向键不切股 (与 ESC 的 !priceAlertDraft 守卫同层级)
    blocked: () => !!priceAlertDraft || showMonitorEditor,
    wrapHints: { head: '已到榜首', tail: '已到末尾' },
  })

  // 邻近预取目标: 当前股左右相邻两只 (首↔尾循环), 交由 StockPanel 提前拉取日K/财务/分时缓存
  const prefetchSymbols = useMemo(() => nav.neighbors.map(n => n.symbol), [nav.neighbors])

  // ESC 关闭 (左右键切股由 useListNav 接管)
  useEffect(() => {
    if (!symbol) return
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !priceAlertDraft) onCloseRef.current()
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [symbol, priceAlertDraft])

  // 弹窗内切股时保留当前视图 (分时 tab 下切股不应跳回去);
  // 仅当弹窗首次打开 (symbol 从 null 变非空) 时重置。
  // [R185] 重置目标跟着默认值一起从 daily 改成 levels —— 只改上面那个
  // useState 初值是不够的: 弹窗关掉再打开会走这一条, 又会跳回日K。
  // [R427] 重置目标改成**入口指定的那一页**(不传仍是 levels)。第一版在上面另加了
  // 一个「symbolProp 一变就重置」的 effect, 出图发现两处打架(这一条把复盘页又
  // 盖回了关键价位), 而且它会在父级方向键切股时把当前页也重置掉 —— 正是本条
  // 注释第一句要防的事。重置只该发生在这一处: 首次打开。
  // [R479] 入口指定 'review'(决策台点「走势/位置」)时, 打开就定位到新「复盘」块 —— 原来它打开的是
  // 旧复盘页, 旧页删了。瞬时跳过去, 不做滚动动画(AGENTS.md 前端动效硬规则: 跳转类操作要瞬时)。
  // 上面的「现状」、图表是异步到的, 一到就把复盘往下推 —— 所以不是跳一下, 而是**钉住**: 内容长高一次就
  // 再对准一次; 用户一动(滚轮 / 触摸 / 按键)立即放手, 最多钉 3 秒。
  const reviewRef = useRef<HTMLDivElement>(null)
  const scrollRef = useRef<HTMLDivElement>(null)
  const contentRef = useRef<HTMLDivElement>(null)
  const [pinReview, setPinReview] = useState(false)
  useEffect(() => {
    if (!pinReview) return
    const el = reviewRef.current, box = contentRef.current, sc = scrollRef.current
    if (!el || !box || !sc) return
    const go = () => { sc.scrollTop += el.getBoundingClientRect().top - sc.getBoundingClientRect().top }
    go()
    const ro = new ResizeObserver(go)
    ro.observe(box)
    const stop = () => setPinReview(false)
    sc.addEventListener('wheel', stop, { passive: true })
    sc.addEventListener('touchstart', stop, { passive: true })
    window.addEventListener('keydown', stop)
    const t = setTimeout(stop, 3000)
    return () => {
      ro.disconnect(); clearTimeout(t)
      sc.removeEventListener('wheel', stop); sc.removeEventListener('touchstart', stop)
      window.removeEventListener('keydown', stop)
    }
  }, [pinReview])
  const prevSymbolRef = useRef<string | null>(null)
  const initialViewRef = useRef(initialView)
  initialViewRef.current = initialView
  const enableLevelsViewRef = useRef(enableLevelsView)
  enableLevelsViewRef.current = enableLevelsView
  useEffect(() => {
    if (prevSymbolRef.current == null && symbol != null) {
      // [R430] 新那一块: 入口指定了图的视图就用它, 否则(含「复盘」)落到关键价位
      const iv = initialViewRef.current
      setChartView(iv === 'daily' || iv === 'intraday' ? iv : enableLevelsViewRef.current ? 'levels' : 'daily')
      if (iv === 'review') setPinReview(true)
    }
    prevSymbolRef.current = symbol
    setPriceAlertDraft(null)
    // [R429] 天数提到弹窗里持有后, 复盘页 `key={symbol}` 重建已经带不走它了 ——
    // 在这里补上原来的约定: 「60 日」是上一只票的上下文, 不带到下一只。
    setReviewDays(HERO_DAYS_DEFAULT)
  }, [symbol])

  // 焦点股票注册: SSE quotes_updated 推送时精准 invalidate 当前股票日K,
  // 让对话框日K最后一根蜡烛随实时价变化 (后端只读内存, 不调 TickFlow)。
  // 关闭/切股时清除, 避免无谓刷新。
  useEffect(() => {
    if (!symbol) return
    setFocusSymbol(symbol)
    return () => clearFocusSymbol()
  }, [symbol])

  // 分时图实时轮询: 详情打开即独立轮询, 不再依赖自选列表的「分时刷新」开关
  // 与实时行情运行状态 (打开详情就是要看实时分时); 间隔沿用偏好, 默认 6s。
  // 最新一根K由后端 live 参数直接实时拉取, 与行情列表节奏一致。
  const { data: prefs } = usePreferences()
  const intradayRefetchMs = (prefs?.minute_intraday_refresh_interval ?? 6) * 1000

  // 分时档位按分钟源历史深度收窄: 浅源(如 stock-sdk=5日)只显示可行档位、默认 5日;
  // 深源(tickflow/未声明)全档位、默认 20日。用户已保存的可行选择优先保留。
  const minuteHistoryDays = prefs?.minute_history_days ?? null
  const dayOptions = useMemo<number[]>(
    () => INTRADAY_DAY_OPTIONS.filter(d => minuteHistoryDays == null || d <= minuteHistoryDays),
    [minuteHistoryDays],
  )
  const defaultIntradayDays = minuteHistoryDays != null && minuteHistoryDays < 20 ? 5 : 20
  const effectiveIntradayDays = intradayDays ?? defaultIntradayDays
  useEffect(() => {
    if (!dayOptions.includes(effectiveIntradayDays)) {
      setIntradayDays(defaultIntradayDays)
    }
  }, [dayOptions, effectiveIntradayDays, defaultIntradayDays])

  // [R437] 刷新当前视图那份数据。[R479] 旧顶栏(和它的 `view`)删了, 只剩新「图表与价位」的 chartView。
  const handleRefresh = () => {
    if (!symbol) return
    if (chartView === 'daily') {
      qc.invalidateQueries({ queryKey: ['kline', symbol] })
    } else if (chartView === 'intraday') {
      qc.invalidateQueries({ queryKey: ['kline-minute-range', symbol] })
      qc.invalidateQueries({ queryKey: ['kline-minute', symbol] })
    } else {
      qc.invalidateQueries({ queryKey: QK.analysisKline(symbol) })
      qc.invalidateQueries({ queryKey: QK.stockLevels(symbol) })
      qc.invalidateQueries({ queryKey: QK.stockTrend(symbol) })
      // [R472] 关键价位图的量化MACD 副图是单独一个查询, 原来漏了 —— 它取数失败时
      // 图上叫人「点右上角刷新重试」, 点了却不会重取。
      qc.invalidateQueries({ queryKey: QK.stockQuantMacd(symbol) })
    }
  }

  const selectIntradayDays = (days: number) => {
    setIntradayDays(days)
    storage.stockPreviewIntradayDays.set(days)
  }

  // [R430] 新那一块的日 K 区间跟头部的 60 / 120 / 250 日走(用户选的「图跟着头部走」):
  // 起点取关键价位那份日 K 倒数第 N 根的日子 —— 与头部那行「起 ~ 止 · N 个交易日」
  // 是同一个数。日 K 还没到时先用旧的默认区间顶着。
  const heroRows = useAnalysisKline(symbol ?? '').data?.rows ?? []
  const heroStart = heroRows.length ? String((heroRows.at(-reviewDays) ?? heroRows[0]).date).slice(0, 10) : null
  const heroRange = heroStart ? { start: heroStart, end: new Date().toISOString().slice(0, 10) } : dateRange

  const openPriceAlert = (targetPrice: number, currentPrice: number) => {
    setPriceAlertDraft({ id: Date.now(), targetPrice, currentPrice })
  }

  return (
    <AnimatePresence>
      {symbol && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          {/* 遮罩 */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.15 }}
            className="absolute inset-0 bg-black/60 backdrop-blur-sm"
            {...backdrop}
          />

          {/* 弹窗主体 */}
          <motion.div
            initial={{ opacity: 0, scale: 0.95, y: 12 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.97, y: 8 }}
            transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
            className={cn(
              'relative rounded-card border border-border bg-base shadow-2xl overflow-hidden flex flex-col w-[92vw] max-w-[1200px] max-h-[95vh]',
            )}
          >
            {/* [R429] 新头部(用户给的排版图)。[R479] 旧顶栏已删(用户框出整块:「我是想删除掉框出来的这部分」),
                加监控 R478 已先搬到这里。 */}
            {symbol && (
              <PreviewHero
                symbol={symbol} name={name}
                days={reviewDays} onDaysChange={setReviewDays}
                inWatchlist={inWatchlist} watchBusy={toggleWatchlist.isPending}
                onWatchAdd={groupId => toggleWatchlist.mutate({ action: 'add', groupId })}
                onWatchRemove={() => toggleWatchlist.mutate({ action: 'remove' })}
                onAiAnalyze={onAiAnalyze} aiBusy={aiBusy}
                onRefresh={handleRefresh}
                onAddMonitor={() => setShowMonitorEditor(true)}
              />
            )}

            {/* [R432] 头部以下整块一起滚。[R479] 原来挪在新块后面等删的旧顶栏、切换条、信息条和旧内容已删。 */}
            <div ref={scrollRef} className="min-h-0 flex-1 overflow-auto">
              <div ref={contentRef} className="space-y-6 px-4 pb-2 pt-4 sm:px-6">
              {/* [R433] 新「现状」(用户排版图: 「结论后面加」)。只有现成读数 ——
                  图里下半块那套买卖判定先写成草案给用户审, 审完再做。 */}
              <StatusSection symbol={symbol} days={reviewDays} />

              {/* [R430] 新「图表与价位」(用户排版图第二块)。 */}
              <div>
                <ChartLevelsSection
                  view={chartView}
                  onViewChange={setChartView}
                  levelsEnabled={enableLevelsView}
                  toolbar={chartView === 'intraday' ? (
                    <div className="flex flex-wrap items-center gap-2" aria-label="分时周期">
                      {dayOptions.map(d => (
                        <button key={d} type="button" aria-pressed={effectiveIntradayDays === d}
                                onClick={() => selectIntradayDays(d)}
                                className={`${PILL} ${effectiveIntradayDays === d ? PILL_ON : PILL_IDLE}`}>
                          {d} 日
                        </button>
                      ))}
                    </div>
                  ) : chartView === 'levels' ? (
                    <span className="text-xs text-muted">关键价位模式: 点开哪一类, 就画到图上</span>
                  ) : (
                    <span className="text-xs text-muted">区间跟上面的天数走</span>
                  )}
                >
                  {chartView === 'daily' ? (
                    <StockPanel
                      symbol={symbol}
                      height={420}
                      showIntraday
                      dateRange={heroRange}
                      // 区间取到了还不够: 带分时小图时它默认只露最后 40 根
                      visibleBars={reviewDays}
                      priceLines={monitorPriceLines}
                      onPriceDoubleClick={openPriceAlert}
                      refetchIntervalMs={intradayRefetchMs}
                      prefetchSymbols={prefetchSymbols}
                      intradayDays={effectiveIntradayDays}
                      dailyKlineFlex="flex-[1.4]"
                      addedDate={addedDate}
                    />
                  ) : chartView === 'intraday' ? (
                    // [R437] 与旧分时页同一套: 上面一条信息栏(只要信息栏, 不画日 K), 下面多日分时。
                    // R430 搬过来时漏了信息栏。区间与新日 K 同一个(同一份缓存, 不多发请求)
                    <div className="flex flex-col gap-3">
                    <StockPanel
                      symbol={symbol}
                      dateRange={heroRange}
                      infoBarOnly
                      prefetchSymbols={prefetchSymbols}
                      intradayDays={effectiveIntradayDays}
                      addedDate={addedDate}
                    />
                    <StockMultiDayIntradayChart
                      symbol={symbol}
                      days={effectiveIntradayDays}
                      height={480}
                      refetchIntervalMs={intradayRefetchMs}
                      priceLines={monitorPriceLines}
                      onPriceDoubleClick={openPriceAlert}
                    />
                    </div>
                  ) : (
                    <StockLevelsPanel symbol={symbol} bare height={520}
                                      controls={levelCtl} visibleBars={reviewDays} />
                  )}
                </ChartLevelsSection>
              </div>

              {/* [R431] 新「复盘」(用户排版图第三块)。天数跟头部走 */}
              <div ref={reviewRef}>
                {/* [R442] key 跟着票走(换票时「只看有事的日子」复位) —— 与旧复盘页一样 */}
                <ReviewSection key={symbol} symbol={symbol} days={reviewDays} />
              </div>
              </div>

            </div>


            {/* 扩展插槽: 对话框底部二开区 (无注册时不渲染)。[R479] 旧顶栏删了, 显隐改跟新「图表与价位」
                的视图(chartView)走 —— 插槽名与 context 形状不变, 这是 docs/secondary-development.md
                里写明的公开插槽。 */}
            {(chartView === 'daily' || chartView === 'intraday') && (
              <div className="shrink-0">
                <ExtensionSlot
                  name="stock-preview.footer"
                  context={{ symbol, name: name ?? null, view: chartView }}
                />
              </div>
            )}

            {/* 加监控编辑器弹层 */}
            <AnimatePresence>
              {showMonitorEditor && symbol && (
                <motion.div
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  className="absolute inset-0 z-20 flex items-start justify-center overflow-auto bg-black/40 p-4"
                  onClick={() => setShowMonitorEditor(false)}
                >
                  <div className="mt-8 w-full max-w-2xl" onClick={e => e.stopPropagation()}>
                    <RuleEditor
                      rule={null}
                      simple
                      preset={{
                        scope: 'symbols',
                        symbols: [symbol],
                        type: 'signal',
                        logic: 'or',
                      }}
                      onClose={() => setShowMonitorEditor(false)}
                      onSaved={() => setShowMonitorEditor(false)}
                    />
                  </div>
                </motion.div>
              )}
            </AnimatePresence>

            {/* 首↔尾循环弱提示 */}
            <NavWrapToast message={nav.wrapMsg} />
          </motion.div>
        </div>
      )}
      {symbol && priceAlertDraft && (
        <PriceAlertDialog
          key={`${symbol}-${priceAlertDraft.id}`}
          symbol={symbol}
          name={name ?? ''}
          initialTarget={priceAlertDraft.targetPrice}
          initialCurrentPrice={priceAlertDraft.currentPrice}
          onClose={() => setPriceAlertDraft(null)}
        />
      )}
    </AnimatePresence>
  )
}
