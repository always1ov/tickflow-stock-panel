import { useState, useMemo, useRef, useEffect, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { X, Repeat, Sparkles, ArrowDownUp, RefreshCw, AlertCircle } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { api, friendlyStreamError } from '@/lib/api'
import { QK } from '@/lib/queryKeys'
import { cn } from '@/lib/cn'
import { fmtPct } from '@/lib/format'
import { MarkdownRenderer } from '@/components/financials/MarkdownRenderer'
import { Modal } from '@/components/Modal'
import { TYPE } from '@/components/ui'

interface Props {
  onClose: () => void
  /** 维度: concept 概念(默认) / industry 行业 */
  kind?: 'concept' | 'industry'
  /**
   * [R769] 只留 AI 报告: 行业页把矩阵并进热力图后, 这个弹窗再画一遍同一份矩阵
   * 就是第二个入口两套语义。传 true 时下半区矩阵整块不渲染。
   */
  aiOnly?: boolean
  /** [R769] 跟随热力图当前口径打开, 免得 AI 读 12 天而用户正看 30 天 */
  initialDays?: number
  initialLevel?: number
}

const DEFAULT_DAYS = 12
// [R764] 行高必须与实际渲染高度一致, 否则虚拟滚动的占位行会算错(原来 30 而实际 46)
const ROW_HEIGHT = 34
const OVERSCAN = 8           // 上下额外渲染行数, 减少滚动时的白屏闪烁
// [R764] 天数从 7~30 滑杆改成 4 档 chip, 塞进标题行
const DAY_PRESETS = [7, 12, 20, 30]
/** [R779] aiOnly 空态的四张卡 = 报告固定会覆盖的四件事 */
const AI_ANGLES = [
  { title: '主线研判', desc: '当前最强的一条线, 以及它还能不能延续' },
  { title: '新晋强势', desc: '名次快速上移、刚挤进前列的方向' },
  { title: '退潮预警', desc: '由强转弱、还在榜上但已经在掉队' },
  { title: '资金结构', desc: '机构 vs 游资, 这些名次是谁在承接' },
]
/** [R779] 标题栏上的只读口径 chip */
const CALIBER_CHIP = 'rounded-btn border border-border bg-base/60 px-1.5 py-0.5 text-micro text-secondary tabular-nums'

// 涨幅 → 背景色梯度(A 股语义: 红涨绿跌)。强度越大色越深, 一眼看出强势/弱势概念
function pctBgClass(pct: number): string {
  if (pct >= 0.05) return 'bg-bull/25'
  if (pct >= 0.03) return 'bg-bull/18'
  if (pct >= 0.01) return 'bg-bull/10'
  if (pct > -0.01) return ''
  if (pct > -0.03) return 'bg-bear/10'
  if (pct > -0.05) return 'bg-bear/18'
  return 'bg-bear/25'
}

// 把 "2026-07-01" 格式化成 "7/01" 紧凑显示(表头窄列)
function shortDate(s: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(s)
  if (!m) return s
  return `${Number(m[2])}/${m[3]}`
}

// 排名 → 前景色(A 股语义: 红=强, 绿=弱)。前 10 红, 后 10 绿, 中间默认强调色。
// total 兜底: 概念总数未知时只判前 10, 不判后 10。
function rankColorClass(rank: number, total: number): string {
  if (rank <= 10) return 'text-bull'
  if (total > 20 && rank > total - 10) return 'text-bear'
  return 'text-accent'
}

// [R504] R105 加的「弹窗内切换行业/概念」随复盘页那个统一入口一起撤了 —— 入口回到行业/概念两页, 各开各的
export function RpsRotationDialog({
  onClose,
  kind = 'concept',
  aiOnly = false,
  initialDays = DEFAULT_DAYS,
  initialLevel,
}: Props) {
  // 维度文案: concept→概念, industry→行业
  const dimLabel = kind === 'industry' ? '行业' : '概念'
  const [days, setDays] = useState(initialDays)
  const [reversed, setReversed] = useState(false)        // false=高→低, true=低→高
  const [selected, setSelected] = useState<string | null>(null)  // 点中的成员名, 高亮追踪
  // 行业层级(仅 industry): 1/2/3 级, 默认 2 级。concept 时为 null 不生效。
  const [level, setLevel] = useState<number>(kind === 'industry' ? (initialLevel ?? 2) : 0)

  // ---- AI 轮动分析状态 (组件内, 不建全局 store: 切页即关对话框) ----
  const [analysis, setAnalysis] = useState('')            // 累积的 Markdown 报告
  const [analyzing, setAnalyzing] = useState(false)       // 生成中
  const [analysisError, setAnalysisError] = useState('')  // 错误信息
  const [analysisMeta, setAnalysisMeta] = useState<{ summary?: string } | null>(null)
  const [focus, setFocus] = useState('')                  // 用户追加的关注点

  const runAnalysis = useCallback(async (daysParam: number, focusParam: string) => {
    setAnalyzing(true)
    setAnalysis('')
    setAnalysisError('')
    setAnalysisMeta(null)
    try {
      const lv = kind === 'industry' ? level : undefined
      for await (const ev of api.rotationAnalyzeStream(daysParam, focusParam, kind, lv)) {
        if (ev.type === 'meta') setAnalysisMeta({ summary: ev.summary })
        else if (ev.type === 'delta') setAnalysis(a => a + (ev.content ?? ''))
        else if (ev.type === 'error') setAnalysisError(ev.message ?? '未知错误')
        // done: 无操作
      }
    } catch (e) {
      setAnalysisError(friendlyStreamError(e instanceof Error ? e.message : String(e)))
    } finally {
      setAnalyzing(false)
    }
  }, [kind, level])

  // 数据请求: React Query 缓存, 同 (kind, level, days) 5 分钟内重开秒开
  const lvParam = kind === 'industry' ? level : undefined
  const { data, isLoading, error } = useQuery({
    queryKey: [...QK.rpsRotation(days), kind, lvParam],
    queryFn: () => api.rpsRotation(days, kind, lvParam),
    staleTime: 5 * 60 * 1000,
  })

  const dates = data?.dates ?? []
  const columns = data?.columns ?? {}
  const conceptCount = data?.concept_count ?? 0

  // 行数 = 最长那列的长度(理论上每天概念数应一致, 取最大兜底)
  const rowCount = useMemo(
    () => dates.reduce((m, d) => Math.max(m, columns[d]?.length ?? 0), 0),
    [dates, columns],
  )

  // 行索引: 翻转时不重排数据, 只翻转访问索引(省一次大数组操作)
  const getRowIndex = useCallback(
    (displayIdx: number) => (reversed ? rowCount - 1 - displayIdx : displayIdx),
    [reversed, rowCount],
  )

  // ---- 手写虚拟滚动 ----
  // 监听滚动容器 scrollTop, 只渲染 [firstIdx, lastIdx] 范围内的行。
  // 387 行只画可视的 ~25 行 + overscan, DOM 恒定 ~30 行 × N 列, 滚动 60fps。
  const scrollRef = useRef<HTMLDivElement>(null)
  // AI 报告区滚动容器: 流式生成时自动滚到底部
  const analysisRef = useRef<HTMLDivElement>(null)
  const [visibleRange, setVisibleRange] = useState({ start: 0, end: 25 })

  // 流式生成中: analysis 每次追加都把报告区滚到底部, 跟踪最新文字
  useEffect(() => {
    if (!analyzing) return
    const el = analysisRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [analysis, analyzing])

  const handleScroll = useCallback(() => {
    const el = scrollRef.current
    if (!el) return
    const scrollTop = el.scrollTop
    const viewportH = el.clientHeight
    const start = Math.max(0, Math.floor(scrollTop / ROW_HEIGHT) - OVERSCAN)
    const end = Math.min(rowCount, Math.ceil((scrollTop + viewportH) / ROW_HEIGHT) + OVERSCAN)
    setVisibleRange(prev => (prev.start === start && prev.end === end ? prev : { start, end }))
  }, [rowCount])

  useEffect(() => {
    // rowCount 变化(切天数/数据到达)时重算可视范围
    handleScroll()
  }, [handleScroll, rowCount])


  // 选中概念的追踪行: 找出它在每个日期列的(排名, 涨幅)。
  // 每列已按涨幅降序排好, 故排名 = 该概念在数组里的索引 + 1。
  // 未入选该日(概念当天无数据)显示空, 便于横向看排名变化。
  const selectedRow = useMemo(() => {
    if (!selected) return null
    const cells: ({ rank: number; pct: number } | null)[] = []
    for (const d of dates) {
      const col = columns[d] ?? []
      const idx = col.findIndex(([name]) => name === selected)
      cells.push(idx >= 0 ? { rank: idx + 1, pct: col[idx][1] } : null)
    }
    return cells
  }, [selected, dates, columns])

  const renderRows = useMemo(() => {
    const rows: JSX.Element[] = []
    for (let displayIdx = visibleRange.start; displayIdx < visibleRange.end; displayIdx++) {
      const rawIdx = getRowIndex(displayIdx)
      const cells = dates.map((d) => {
        const cell = columns[d]?.[rawIdx]
        if (!cell) {
          return (
            <td key={d} className="px-2 py-1 text-center text-muted/40">
              <span className="text-micro">—</span>
            </td>
          )
        }
        const [name, pct] = cell
        const isSelected = selected === name
        return (
          <td
            key={d}
            onClick={() => setSelected(prev => prev === name ? null : name)}
            className={cn(
              'px-1.5 py-0 cursor-pointer whitespace-nowrap text-center align-middle transition-colors',
              pctBgClass(pct),
              isSelected && 'ring-1 ring-inset ring-accent bg-accent/20',
            )}
          >
            <div className="flex flex-col items-center gap-0 leading-none">
              <span className={cn(
                'text-micro max-w-[84px] truncate',
                isSelected ? 'text-accent font-medium' : 'text-secondary',
              )} title={name}>{name}</span>
              <span className={cn(
                'text-micro tabular-nums',
                pct > 0 ? 'text-bull' : pct < 0 ? 'text-bear' : 'text-muted',
              )}>{fmtPct(pct)}</span>
            </div>
          </td>
        )
      })
      rows.push(
        <tr
          key={displayIdx}
          style={{ height: ROW_HEIGHT }}
          className="border-b border-border/30"
        >
          <td className="sticky left-0 z-10 bg-surface px-2 text-center text-micro text-muted tabular-nums border-r border-border/40">
            {displayIdx + 1}
          </td>
          {cells}
        </tr>,
      )
    }
    return rows
  }, [visibleRange, getRowIndex, dates, columns, selected])

  // [R779] aiOnly 重排: 这个弹窗只装一份报告 —— 口径钉在标题栏、操作收在底部、
  // 正文整块给结论。原来「标题 / 口径 / 输入 / 空态 / 报告」五段全挤在上方,
  // 76vh 的窗口里真正能读报告的高度被切得只剩一半。
  if (aiOnly) {
    return (
      <Modal
        onClose={onClose}
        labelledBy="rps-rotation-title"
        overlayClassName="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
        panelClassName="bg-surface border border-border rounded-card shadow-xl flex flex-col w-[800px] max-w-[92vw] h-[76vh]"
      >
        {/* 标题栏: 标题 + 只读口径。口径跟随页头工具栏, 这里没有第二个切换入口 */}
        <div className="flex shrink-0 items-center gap-2 border-b border-border px-5 py-3">
          <Sparkles className="h-4 w-4 text-accent" />
          <span id="rps-rotation-title" className={TYPE.section}>{dimLabel} AI 轮动分析</span>
          <span className="ml-1 flex items-center gap-1">
            <span className={CALIBER_CHIP}>{dates.length || days} 日</span>
            {kind === 'industry' && <span className={CALIBER_CHIP}>{level} 级</span>}
            {conceptCount > 0 && <span className={CALIBER_CHIP}>{conceptCount} 个{dimLabel}</span>}
          </span>
          <button aria-label="关闭" onClick={onClose} className="ml-auto p-1 rounded-btn hover:bg-elevated transition-colors cursor-pointer">
            <X className="h-4 w-4 text-muted" />
          </button>
        </div>

        {/* 正文: 报告 / 空态 / 错误三选一, 整块可滚 */}
        <div ref={analysisRef} className="flex-1 min-h-0 overflow-auto">
          {analysisError ? (
            <div className="flex h-full flex-col items-center justify-center gap-3 px-8 text-center">
              <AlertCircle className="h-5 w-5 text-danger" />
              <div className="text-xs text-danger">{analysisError}</div>
              <button
                onClick={() => runAnalysis(days, focus)}
                className="rounded-btn border border-border px-3 py-1 text-xs text-accent transition-colors hover:bg-elevated cursor-pointer"
              >重新生成</button>
            </div>
          ) : analysis || analyzing ? (
            <div className="px-5 py-4 leading-relaxed">
              {analysisMeta?.summary && (
                <div className="mb-3 border-l-2 border-accent/60 bg-accent/5 px-3 py-2 text-xs text-accent/90">
                  {analysisMeta.summary}
                </div>
              )}
              {analyzing && (
                <div className="mb-2 flex items-center gap-1.5 text-micro text-muted">
                  <RefreshCw className="h-3 w-3 animate-spin" />AI 正在读矩阵…
                </div>
              )}
              <div className="text-body">
                <MarkdownRenderer content={analysis} />
                {analyzing && <span className="ml-0.5 inline-block h-3.5 w-1.5 bg-accent animate-pulse align-middle" />}
              </div>
            </div>
          ) : (
            <div className="flex h-full flex-col items-center justify-center gap-5 px-8 text-center">
              <div className="flex flex-col items-center gap-1">
                <Sparkles className="h-6 w-6 text-accent/40" />
                <div className="text-body text-foreground">让 AI 读一遍这张轮动矩阵</div>
                <div className="text-micro text-muted">
                  按 {dates.length || days} 日{kind === 'industry' ? ` · ${level} 级` : ''}{conceptCount > 0 ? ` · ${conceptCount} 个${dimLabel}` : ''} 的口径
                </div>
              </div>
              {/* [R779] 固定两列 + 整体居中: flex-wrap 会因为容器 734px 装得下三张 224px 卡
                  而排成 3+1, 四件事读起来就不是一组。`w-fit` 让网格宽度贴着两列, 再 mx-auto 居中 */}
              <div className="mx-auto grid w-fit grid-cols-2 gap-2">
                {AI_ANGLES.map(a => (
                  <div key={a.title} className="w-56 rounded-btn border border-border/60 bg-elevated/20 px-3 py-2 text-left">
                    <div className="text-xs text-foreground">{a.title}</div>
                    <div className="text-micro text-muted">{a.desc}</div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* 底部操作条: 输入在左、主按钮在右, 报告往上长而不把操作顶走 */}
        <div className="shrink-0 border-t border-border px-5 py-3">
          <div className="flex items-center gap-2">
            <input
              type="text"
              value={focus}
              onChange={e => setFocus(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter' && !analyzing) runAnalysis(days, focus) }}
              placeholder="关注点(可选)，例如: 只看新能源链 / 谁在退潮"
              disabled={analyzing}
              className="h-8 min-w-0 flex-1 rounded-btn border border-border bg-base/60 px-2.5 text-xs text-foreground placeholder:text-muted/50 focus:border-accent/40 focus:outline-none disabled:opacity-50"
            />
            <button
              onClick={() => runAnalysis(days, focus)}
              disabled={analyzing}
              className={cn(
                'inline-flex h-8 shrink-0 items-center gap-1.5 rounded-btn px-3 text-xs transition-colors',
                analyzing
                  ? 'cursor-not-allowed border border-border text-secondary opacity-60'
                  : 'cursor-pointer bg-foreground font-medium text-surface hover:bg-foreground/90',
              )}
            >
              {analyzing
                ? <><RefreshCw className="h-3.5 w-3.5 animate-spin" />分析中</>
                : analysis
                  ? <><RefreshCw className="h-3.5 w-3.5" />重新分析</>
                  : <><Sparkles className="h-3.5 w-3.5" />生成分析</>}
            </button>
          </div>
          <div className="mt-2 text-micro text-muted">报告由 AI 生成，结论以热力图为准</div>
        </div>
      </Modal>
    )
  }

  return (
    <Modal
      onClose={onClose}
      labelledBy="rps-rotation-title"
      overlayClassName="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
      panelClassName="bg-surface border border-border rounded-card shadow-xl flex flex-col w-[92vw] h-[88vh] max-w-wide"
    >
          {/* 标题栏 */}
          <div className="flex items-center justify-between px-4 py-2.5 border-b border-border shrink-0">
            <div className="flex items-center gap-2">
              <Repeat className="h-4 w-4 text-accent" />
              <span id="rps-rotation-title" className={TYPE.section}>{dimLabel}涨幅轮动</span>
              <span className="text-xs text-muted">
                {conceptCount > 0 ? `${dates.length} 日 · ${conceptCount} 个${dimLabel}` : '暂无数据'}
              </span>
              {kind === 'industry' && (
                <div className="ml-1 flex items-center rounded-btn border border-border bg-base/60 p-0.5">
                  {[1, 2, 3].map(lv => (
                    <button
                      key={lv}
                      onClick={() => { setLevel(lv); setSelected(null) }}
                      className={cn(
                        'h-5 rounded-[5px] px-2 text-micro font-medium transition-colors',
                        level === lv ? 'bg-foreground font-medium text-surface' : 'text-secondary hover:text-foreground',
                      )}
                    >
                      {lv}级
                    </button>
                  ))}
                </div>
              )}
              {/* [R764] 天数改 4 档 chip + 排序并入标题行: 原工具栏 47px 整行省掉 */}
              <div className="ml-1 flex items-center rounded-btn border border-border bg-base/60 p-0.5">
                {DAY_PRESETS.map(d => (
                  <button
                    key={d}
                    onClick={() => setDays(d)}
                    className={cn(
                      'h-5 rounded-[5px] px-2 text-micro tabular-nums transition-colors',
                      days === d ? 'bg-foreground font-medium text-surface' : 'text-secondary hover:text-foreground',
                    )}
                  >
                    {d}日
                  </button>
                ))}
              </div>
              <button
                onClick={() => setReversed(r => !r)}
                className={cn(
                  'inline-flex h-6 items-center gap-1 rounded-btn px-2 text-micro transition-colors cursor-pointer border',
                  reversed
                    ? 'border-foreground bg-foreground font-medium text-surface'
                    : 'border-border text-secondary hover:bg-elevated',
                )}
                title="翻转排序(高↔低)"
              >
                <ArrowDownUp className="h-3 w-3" />
                {reversed ? '低→高' : '高→低'}
              </button>
              {selected && (
                <button onClick={() => setSelected(null)} className="text-micro text-accent hover:underline cursor-pointer">
                  取消追踪
                </button>
              )}
            </div>
            <button aria-label="关闭" onClick={onClose} className="p-1 rounded-btn hover:bg-elevated transition-colors cursor-pointer">
              <X className="h-4 w-4 text-muted" />
            </button>
          </div>

          {/* 上半区: AI 轮动分析 */}
          <div className="shrink-0 border-b border-border flex flex-col max-h-[42%]">
            {/* 标题栏: 标题 + meta 摘要 + focus 输入 + 触发按钮 */}
            <div className="flex items-center gap-2 px-4 py-1.5 bg-elevated/30 shrink-0">
              <Sparkles className={cn('h-3.5 w-3.5 text-accent/60', analyzing && 'animate-pulse')} />
              <span className="text-xs text-muted shrink-0">AI 轮动分析</span>
              {analysisMeta?.summary && (
                <span className="text-xs text-accent/80 truncate">{analysisMeta.summary}</span>
              )}
              {/* [R764] 空态提示并进标题行, 不再占一整块纵向空间 */}
              {!analysis && !analyzing && !analysisError && (
                <span className="min-w-0 truncate text-micro text-muted/60">
                  点击「生成分析」: 主线研判 / 新晋强势 / 退潮预警 / 机构vs游资 · 最近 {days} 日
                </span>
              )}
              <div className="flex items-center gap-1.5 ml-auto">
                <input
                  type="text"
                  value={focus}
                  onChange={e => setFocus(e.target.value)}
                  placeholder="关注点(可选)"
                  disabled={analyzing}
                  className="px-2 py-0.5 w-28 text-xs bg-elevated/50 border border-border rounded-btn text-foreground placeholder:text-muted/50 focus:outline-none focus:border-accent/40 disabled:opacity-50"
                />
                <button
                  onClick={() => runAnalysis(days, focus)}
                  disabled={analyzing}
                  className={cn(
                    'inline-flex items-center gap-1 px-2 py-0.5 rounded-btn text-xs transition-colors cursor-pointer border',
                    analyzing
                      ? 'opacity-60 cursor-not-allowed border-border text-secondary'
                      : 'bg-surface text-foreground border-border hover:bg-elevated',
                  )}
                >
                  {analyzing
                    ? <><RefreshCw className="h-3 w-3 animate-spin" />分析中</>
                    : analysis
                      ? <><RefreshCw className="h-3 w-3" />重新分析</>
                      : <><Sparkles className="h-3 w-3" />生成分析</>}
                </button>
              </div>
            </div>

            {/* 报告内容区: 空态不占纵向(提示已并入标题行), 有结果才展开 */}
            {(analysisError || analysis || analyzing) && (
            <div ref={analysisRef} className="flex-1 min-h-0 overflow-auto">
              {analysisError ? (
                <div className="flex items-center gap-2 px-4 py-4 text-xs text-danger">
                  <AlertCircle className="h-3.5 w-3.5 shrink-0" />
                  <span>{analysisError}</span>
                  <button
                    onClick={() => runAnalysis(days, focus)}
                    className="ml-auto text-accent hover:underline shrink-0"
                  >重试</button>
                </div>
              ) : analysis || analyzing ? (
                <div className="px-4 py-2.5 leading-relaxed text-xs">
                  <MarkdownRenderer content={analysis} />
                  {analyzing && (
                    <span className="inline-block w-1.5 h-3.5 bg-accent animate-pulse align-middle ml-0.5" />
                  )}
                </div>
              ) : null}
            </div>
            )}
          </div>

          {/* 下半区: 涨幅轮动矩阵(虚拟滚动) */}
          <div className="flex-1 min-h-0 flex flex-col">
            {isLoading ? (
              <div className="flex items-center justify-center py-16">
                <div className="w-5 h-5 border-2 border-accent/30 border-t-accent rounded-full animate-spin" />
              </div>
            ) : error ? (
              <div className="flex items-center justify-center py-16 text-xs text-danger">
                加载失败,请稍后重试
              </div>
            ) : rowCount === 0 ? (
              <div className="flex items-center justify-center py-16 text-xs text-muted">
                暂无{dimLabel}数据,请先在「{kind === 'industry' ? '行业板块' : '概念板块'}」页配置并获取{dimLabel}数据源
              </div>
            ) : (
              <div
                ref={scrollRef}
                onScroll={handleScroll}
                className="flex-1 overflow-auto"
              >
                <table className="min-w-full border-collapse">
                  {/* 表头: 日期列, 最新在最左 */}
                  <thead className="sticky top-0 z-20 bg-surface">
                    <tr>
                      <th className="sticky left-0 z-30 bg-surface px-2 py-1.5 text-micro font-normal text-muted border-b border-r border-border/40">
                        #
                      </th>
                      {dates.map(d => (
                        <th
                          key={d}
                          className="px-2 py-1.5 text-micro font-normal text-muted border-b border-border/40 whitespace-nowrap text-center"
                          title={d}
                        >
                          {shortDate(d)}
                        </th>
                      ))}
                    </tr>
                    {/* 选中概念追踪行: 在日期表头下方单独一行, 横向展示它在各日的排名+涨幅 */}
                    <AnimatePresence>
                      {selected && selectedRow && (
                        <motion.tr
                          initial={{ opacity: 0, height: 0 }}
                          animate={{ opacity: 1, height: 'auto' }}
                          exit={{ opacity: 0, height: 0 }}
                          transition={{ duration: 0.15 }}
                          className="border-b border-accent/20 bg-accent/5"
                        >
                          <td className="sticky left-0 z-30 bg-surface px-2 py-1 text-center border-r border-border/40">
                            <span className="text-micro text-accent truncate block max-w-[44px]" title={selected}>
                              {selected}
                            </span>
                          </td>
                          {selectedRow.map((cell, i) => (
                            <td key={i} className="px-2 py-1 text-center whitespace-nowrap align-middle">
                              {cell ? (
                                <div className="flex flex-col items-center gap-0.5 leading-tight">
                                  <span className={cn(
                                    'text-xs font-medium tabular-nums',
                                    rankColorClass(cell.rank, conceptCount),
                                  )}>
                                    #{cell.rank}
                                  </span>
                                  <span className={cn(
                                    'text-micro tabular-nums',
                                    cell.pct > 0 ? 'text-bull' : cell.pct < 0 ? 'text-bear' : 'text-muted',
                                  )}>
                                    {fmtPct(cell.pct)}
                                  </span>
                                </div>
                              ) : (
                                <span className="text-micro text-muted/40">—</span>
                              )}
                            </td>
                          ))}
                        </motion.tr>
                      )}
                    </AnimatePresence>
                  </thead>
                  <tbody>
                    {/* 顶部占位: 把滚动位置撑起来 */}
                    {visibleRange.start > 0 && (
                      <tr style={{ height: visibleRange.start * ROW_HEIGHT }}>
                        <td colSpan={dates.length + 1} />
                      </tr>
                    )}
                    {renderRows}
                    {/* 底部占位 */}
                    {visibleRange.end < rowCount && (
                      <tr style={{ height: (rowCount - visibleRange.end) * ROW_HEIGHT }}>
                        <td colSpan={dates.length + 1} />
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {/* 底部提示 */}
          <div className="px-4 py-1.5 border-t border-border shrink-0">
            <span className="text-micro text-muted">
              每列各自按当日涨幅排序 · 点击单元格追踪概念在各日的排名变化
            </span>
          </div>
    </Modal>
  )
}
