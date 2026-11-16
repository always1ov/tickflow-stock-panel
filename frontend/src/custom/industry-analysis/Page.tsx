import { useCallback, useMemo, useState, type ReactNode } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { AnimatePresence, motion } from 'framer-motion'
import {
  Crown,
  Layers3,
  RefreshCw,
  Settings2,
  X,
} from 'lucide-react'
import { PageHeader } from '@/components/PageHeader'
import { EmptyState } from '@/components/EmptyState'
import { AnalysisConfigDialog, PresetFetchState, type AnalysisFieldConfig } from '@/components/analysis-shared'
import { SectorHeatmapToolbar, SectorRankHeatmap } from '@/components/SectorRankHeatmap'
import { StockPreviewDialog } from '@/components/StockPreviewDialog'
import { toNavItems, type NavItem } from '@/lib/listNav'
import { api, type MarketSnapshotRow } from '@/lib/api'
import { QK } from '@/lib/queryKeys'
import { storage } from '@/lib/storage'
import { fmtBigNum, fmtPct, priceColorClass } from '@/lib/format'
import { cn } from '@/lib/cn'
import { resolveDimension, type DimensionGroup, type StockRow } from '@/lib/analysis-adapter'
import { SectorRotationCard } from '@/components/SectorRotationCard'
import { RpsRotationDialog } from '@/components/RpsRotationDialog'

const KEYWORDS = ['industry', '行业', 'sector', '申万', '中信']
const CANDIDATE_FIELDS = ['industry', '行业', 'sector', '申万', '中信', '行业名称', 'industry_name', 'sector_name']
const PAGE_LIMIT = 12000
const MAX_RENDERED_STOCKS = 160

/** 内置行业预设 id — 本页的数据来源与「未获取」引导按钮都锚定它 */
const PRESET_INDUSTRY_ID = 'ext_hy_ths'

// [R766] 热力图默认口径(30 日 / 前 48 名)。[R769] 改成可变档位后, 当前档位只在矩阵工具栏里显示,
// 页头副标题不再重复 —— 副标题字数一变就可能折行, 把页头从 60 挤到 89, 反过来改掉矩阵高度和行高。
// [R771] 45 → 48: 1700×913 下容器 799、表头 20, 45 行(行高 17)只占 785, 底下白留 14px;
// 补到 48 行后自适应算出 16px 行高, 48×16+20 = 788, 正好贴到容器底(余 11)。
// 47 行会剩 27px, 还是有可见空白; 49 行需要 804, 一屏放不下。
const HEATMAP_DAYS = 30
const HEATMAP_TOP_N = 48

type SortMode = 'heat' | 'avgPct' | 'leader' | 'amount' | 'down'
type IndustryLevel = 1 | 2 | 3

interface EnrichedStock extends MarketSnapshotRow {
  leaderScore: number
  leaderParts: {
    momentum: number
    turnover: number
    amount: number
    cap: number
    volume: number
    boards: number
  }
}

interface IndustryStat {
  key: string
  stocks: EnrichedStock[]
  count: number
  avgPct: number | null
  medianPct: number | null
  upCount: number
  downCount: number
  flatCount: number
  upRate: number
  strongCount: number
  weakCount: number
  totalAmount: number
  avgTurnover: number | null
  avgVolRatio: number | null
  leader: EnrichedStock | null
  heatScore: number
  riskScore: number
}

// ===== 配置持久化 =====

function loadConfig(): AnalysisFieldConfig {
  return storage.industryAnalysisConfig.get({}) as AnalysisFieldConfig
}
function saveConfig(c: AnalysisFieldConfig) {
  storage.industryAnalysisConfig.set(c)
}

// ===== 自动选取最佳数据源 =====

function pickBestConfig(
  configs: { id: string; label: string; description?: string; fields: { name: string; label: string }[] }[],
): string {
  // 内置预设优先: 关键词打分会被「描述里互相提及对方」污染 —— 概念表描述含
  // "概念/行业页", 行业表描述含"板块", 导致本页可能选中概念表 (拿不到数据,
  // 且「未获取」引导按钮因 id 不匹配而不渲染)。预设存在时直接用它。
  if (configs.some(c => c.id === PRESET_INDUSTRY_ID)) return PRESET_INDUSTRY_ID
  let best = '', bestScore = 0
  for (const c of configs) {
    const haystack = [c.id, c.label, c.description ?? '', ...c.fields.flatMap(f => [f.name, f.label])].join(' ').toLowerCase()
    const score = KEYWORDS.reduce((n, k) => n + (haystack.includes(k) ? 1 : 0), 0)
    if (score > bestScore) { bestScore = score; best = c.id }
  }
  return best
}

// ===== 工具函数 =====

function symbolKeys(symbol: unknown): string[] {
  const raw = String(symbol ?? '').trim()
  if (!raw) return []
  const plain = raw.replace(/\.\w+$/, '')
  return Array.from(new Set([raw, plain]))
}

function buildMarketMap(rows: MarketSnapshotRow[]) {
  const map = new Map<string, MarketSnapshotRow>()
  for (const r of rows) {
    for (const key of symbolKeys(r.symbol)) map.set(key, r)
  }
  return map
}

function clamp01(v: number) {
  if (!Number.isFinite(v)) return 0
  return Math.max(0, Math.min(1, v))
}

function num(v: unknown): number | null {
  return typeof v === 'number' && Number.isFinite(v) ? v : null
}

function avg(values: number[]) {
  return values.length ? values.reduce((a, b) => a + b, 0) / values.length : null
}

function median(values: number[]) {
  if (!values.length) return null
  const sorted = [...values].sort((a, b) => a - b)
  const mid = Math.floor(sorted.length / 2)
  return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2
}

// ===== 龙头算法 =====

function leaderScore(stock: MarketSnapshotRow) {
  const pct = num(stock.change_pct) ?? 0
  const turnover = num(stock.turnover_rate) ?? 0
  const amount = num(stock.amount) ?? 0
  const cap = num(stock.float_market_cap) ?? num(stock.market_cap) ?? 0
  const volRatio = num(stock.vol_ratio_5d) ?? 1
  const boards = num(stock.consecutive_limit_ups) ?? 0

  const parts = {
    momentum: clamp01((pct + 0.02) / 0.12),
    turnover: clamp01(Math.log1p(Math.max(turnover, 0)) / Math.log1p(30)),
    amount: clamp01(Math.log1p(Math.max(amount, 0)) / Math.log1p(20_000_000_000)),
    cap: clamp01(Math.log1p(Math.max(cap, 0)) / Math.log1p(300_000_000_000)),
    volume: clamp01((volRatio - 1) / 4),
    boards: clamp01(boards / 5),
  }

  const score = (
    parts.momentum * 0.35 +
    parts.turnover * 0.22 +
    parts.amount * 0.18 +
    parts.cap * 0.15 +
    parts.volume * 0.07 +
    parts.boards * 0.03
  ) * 100

  return { score, parts }
}

function enrichStock(stock: StockRow, marketMap: Map<string, MarketSnapshotRow>): EnrichedStock {
  const market = symbolKeys(stock.symbol ?? stock.code).map(k => marketMap.get(k)).find(Boolean) ?? {}
  const merged = { ...stock, ...market } as MarketSnapshotRow & StockRow
  const ls = leaderScore(merged)
  return {
    ...merged,
    symbol: String(merged.symbol ?? stock.symbol ?? stock.code ?? ''),
    name: merged.name ?? String(stock.name ?? stock['股票简称'] ?? ''),
    leaderScore: ls.score,
    leaderParts: ls.parts,
  }
}

// ===== 行业统计计算 =====

function calcIndustryStat(group: DimensionGroup, marketMap: Map<string, MarketSnapshotRow>): IndustryStat {
  const seen = new Set<string>()
  const stocks = group.stocks
    .map(s => enrichStock(s, marketMap))
    .filter(s => {
      const key = String(s.symbol ?? '')
      if (!key) return false
      if (seen.has(key)) return false
      seen.add(key)
      return true
    })

  const pctValues = stocks.map(s => num(s.change_pct)).filter((v): v is number => v != null)
  const turnoverValues = stocks.map(s => num(s.turnover_rate)).filter((v): v is number => v != null)
  const volValues = stocks.map(s => num(s.vol_ratio_5d)).filter((v): v is number => v != null)
  const totalAmount = stocks.reduce((sum, s) => sum + (num(s.amount) ?? 0), 0)
  const upCount = pctValues.filter(v => v > 0).length
  const downCount = pctValues.filter(v => v < 0).length
  const flatCount = Math.max(0, stocks.length - upCount - downCount)
  const strongCount = pctValues.filter(v => v >= 0.05).length
  const weakCount = pctValues.filter(v => v <= -0.05).length
  const leader = stocks.length ? [...stocks].sort((a, b) => b.leaderScore - a.leaderScore)[0] : null
  const avgPct = avg(pctValues)
  const medianPct = median(pctValues)
  const upRate = pctValues.length ? upCount / pctValues.length : 0
  const amountScore = clamp01(Math.log1p(totalAmount) / Math.log1p(80_000_000_000))
  const strongScore = stocks.length ? clamp01(strongCount / Math.max(1, stocks.length * 0.18)) : 0
  const leaderPart = clamp01((leader?.leaderScore ?? 0) / 100)
  const avgPart = clamp01(((avgPct ?? 0) + 0.02) / 0.09)
  const upPart = clamp01((upRate - 0.35) / 0.55)

  const heatScore = (avgPart * 0.38 + upPart * 0.2 + strongScore * 0.16 + amountScore * 0.12 + leaderPart * 0.14) * 100
  const riskScore = (clamp01((-(avgPct ?? 0) + 0.01) / 0.08) * 0.55 + clamp01(weakCount / Math.max(1, stocks.length * 0.18)) * 0.45) * 100

  return {
    key: group.key,
    stocks,
    count: stocks.length,
    avgPct,
    medianPct,
    upCount,
    downCount,
    flatCount,
    upRate,
    strongCount,
    weakCount,
    totalAmount,
    avgTurnover: avg(turnoverValues),
    avgVolRatio: avg(volValues),
    leader,
    heatScore,
    riskScore,
  }
}

function statSort(mode: SortMode) {
  return (a: IndustryStat, b: IndustryStat) => {
    switch (mode) {
      case 'avgPct': return (b.avgPct ?? -Infinity) - (a.avgPct ?? -Infinity)
      case 'leader': return (b.leader?.leaderScore ?? -Infinity) - (a.leader?.leaderScore ?? -Infinity)
      case 'amount': return b.totalAmount - a.totalAmount
      case 'down': return (a.avgPct ?? Infinity) - (b.avgPct ?? Infinity)
      case 'heat':
      default: return b.heatScore - a.heatScore
    }
  }
}

// ===== 行业层级分组 =====

function industryLevelName(key: string, level: IndustryLevel) {
  const parts = key.split('-').map(s => s.trim()).filter(Boolean)
  return parts[level - 1] || parts[parts.length - 1] || key
}

function groupByIndustryLevel(groups: DimensionGroup[], level: IndustryLevel): DimensionGroup[] {
  const map = new Map<string, DimensionGroup>()
  for (const group of groups) {
    const key = industryLevelName(group.key, level)
    const existing = map.get(key)
    if (existing) {
      existing.stocks.push(...group.stocks)
      existing.count = existing.stocks.length
    } else {
      map.set(key, {
        key,
        count: group.stocks.length,
        stocks: [...group.stocks],
        metrics: { ...group.metrics },
      })
    }
  }
  return [...map.values()].sort((a, b) => b.count - a.count)
}

// ===== 主页面 =====

export function IndustryAnalysis() {
  const [fieldConfig, setFieldConfig] = useState<AnalysisFieldConfig>(loadConfig)
  const [showConfig, setShowConfig] = useState(false)
  // [R769] 矩阵口径上移到页面: 页头副标题、热力图工具栏、AI 弹窗读同一份状态
  const [heatDays, setHeatDays] = useState(HEATMAP_DAYS)
  const [heatAll, setHeatAll] = useState(false)
  // [R773] 「全部 N」的 N 由矩阵从轮动接口数据回报(页头的 stats.length 是另一套口径)
  const [heatTotal, setHeatTotal] = useState(0)
  const [showAi, setShowAi] = useState(false)
  const [aiDays, setAiDays] = useState(HEATMAP_DAYS)
  const [selectedKey, setSelectedKey] = useState<string | null>(null)
  const [previewSymbol, setPreviewSymbol] = useState<string | null>(null)
  const [previewName, setPreviewName] = useState<string>('')
  const [previewNavList, setPreviewNavList] = useState<NavItem[]>([])
  const handleStockClick = useCallback((symbol: string, name?: string, navList?: NavItem[]) => {
    setPreviewSymbol(symbol)
    setPreviewName(name ?? '')
    setPreviewNavList(navList ?? [])
  }, [])

  const configsQuery = useQuery({ queryKey: QK.extData, queryFn: api.extDataList })
  const availableConfigs = configsQuery.data?.items ?? []
  // 用户配置的 configId 可能已失效 (扩展数据被删除), 此时回退到自动选择,
  // 避免用失效 ID 请求接口报错; 用户仍可点配置按钮重新选择。
  const preferredConfigId = fieldConfig.configId || pickBestConfig(availableConfigs)
  const preferredConfig = availableConfigs.find(c => c.id === preferredConfigId)
  const activeConfigId = preferredConfig ? preferredConfigId : pickBestConfig(availableConfigs)
  const activeConfig = availableConfigs.find(c => c.id === activeConfigId)

  const rowsQuery = useQuery({
    queryKey: QK.extDataRows(activeConfigId, undefined, PAGE_LIMIT),
    queryFn: () => api.extDataRows(activeConfigId, { limit: PAGE_LIMIT }),
    enabled: !!activeConfigId,
  })

  // 内置行业预设 (ext_hy_ths) 无数据时的一键拉取: 走通用拉取端点
  // (与「数据」页扩展表的「执行」同一路径, 配方由表的 pull 配置决定)
  const queryClient = useQueryClient()
  const fetchMutation = useMutation({
    mutationFn: () => api.extDataPullRun(PRESET_INDUSTRY_ID),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QK.extData })
      queryClient.invalidateQueries({ queryKey: QK.extDataRows(PRESET_INDUSTRY_ID, undefined, PAGE_LIMIT) })
    },
  })
  // 是否处于「内置行业预设存在但无数据」状态 → 显示获取按钮
  const needsIndustryFetch =
    !!activeConfig && activeConfig.id === PRESET_INDUSTRY_ID &&
    !rowsQuery.isLoading && (rowsQuery.data?.total ?? 0) === 0

  const marketQuery = useQuery({
    queryKey: QK.marketSnapshot,
    queryFn: api.marketSnapshot,
    staleTime: 60_000,
  })

  const marketMap = useMemo(() => buildMarketMap(marketQuery.data?.rows ?? []), [marketQuery.data?.rows])
  const resolved = useMemo(
    () => resolveDimension(rowsQuery.data, activeConfig, fieldConfig.dimensionField ? [fieldConfig.dimensionField, ...CANDIDATE_FIELDS] : CANDIDATE_FIELDS),
    [rowsQuery.data, activeConfig, fieldConfig.dimensionField],
  )

  const industryLevel = fieldConfig.hierarchyLevel ?? 2
  const groups = useMemo(() => groupByIndustryLevel(resolved.groups, industryLevel), [resolved.groups, industryLevel])

  const stats = useMemo(() => {
    return groups
      .map(g => calcIndustryStat(g, marketMap))
      .filter(s => s.count > 0)
  }, [groups, marketMap])

  // [R763] rail 删除后没有默认选中项: 只有点热力图/chip 才出详情抽屉
  const selected = selectedKey ? stats.find(s => s.key === selectedKey) ?? null : null
  const leading = useMemo(() => [...stats].sort(statSort('heat')).slice(0, 10), [stats])
  const falling = useMemo(() => [...stats].sort(statSort('down')).slice(0, 10), [stats])
  // [R774] 页头那串「领涨/领跌」按涨幅排, 不能用强度榜(heat)的顺序 —— 否则
  // 「领涨 生猪养殖 +3.10%」后面跟着 +4.37% 的行业, 名字与数值自相矛盾。
  // 同时剔掉摘要里已经写过的第 1 名(最强行业 / 最大风险), 各补到 4 条 —— 同一行里
  // 同一个行业出现两遍, 读的人会以为其中一处是错的。
  const pctLeaders = useMemo(
    () => [...stats].sort(statSort('avgPct')).filter(s => s.key !== leading[0]?.key).slice(0, 4),
    [stats, leading],
  )
  const pctFallers = useMemo(
    () => [...stats].sort(statSort('down')).filter(s => s.key !== falling[0]?.key).slice(0, 4),
    [stats, falling],
  )
  const activeIndustry = useMemo(() => [...stats].sort(statSort('amount'))[0] ?? null, [stats])
  const industryBreadth = useMemo(() => {
    const priced = stats.filter(s => s.avgPct != null)
    return {
      up: priced.filter(s => (s.avgPct ?? 0) > 0).length,
      down: priced.filter(s => (s.avgPct ?? 0) < 0).length,
      flat: priced.filter(s => s.avgPct === 0).length,
    }
  }, [stats])

  const totalSymbols = useMemo(() => {
    const set = new Set<string>()
    stats.forEach(s => s.stocks.forEach(st => { if (st.symbol) set.add(st.symbol) }))
    return set.size
  }, [stats])

  const handleSaveConfig = (c: AnalysisFieldConfig) => {
    setFieldConfig(c)
    saveConfig(c)
    setSelectedKey(null)
  }

  if (configsQuery.isLoading) {
    return <div className="flex h-full items-center justify-center"><RefreshCw className="h-5 w-5 animate-spin text-muted" /></div>
  }

  if (!activeConfig) {
    // 极端情况: 无任何行业配置。仍提供一键获取内置行业数据入口
    return (
      <>
        <div className="flex h-full flex-col">
          <PageHeader
            title="行业板块"
            right={
              <button onClick={() => setShowConfig(true)} className="p-1.5 text-secondary hover:bg-surface hover:text-accent" title="配置数据源">
                <Settings2 className="h-4 w-4" />
              </button>
            }
          />
          <PresetFetchState
            title="暂无行业数据"
            hint="从同花顺获取行业分类数据后即可使用行业板块"
            isLoading={fetchMutation.isPending}
            error={fetchMutation.error}
            onFetch={() => fetchMutation.mutate()}
          />
        </div>
        <AnimatePresence>
          {showConfig && <AnalysisConfigDialog currentConfig={fieldConfig} onSave={handleSaveConfig} onClose={() => setShowConfig(false)} showHierarchyLevel />}
        </AnimatePresence>
      </>
    )
  }

  const industryLevelLabel = `${industryLevel}级行业`

  return (
    // [R768] 整页是一个等高列: 页头固定, 下面内容吃掉剩余高度, 页面本身不滚动
    <div className="flex h-full min-h-0 flex-col">
      {/* [R765] 原来独占一整条的 5 项指标(25px + 间距 12px), 现在压成一句摘要。
          [R776] 顶部整体改成「两行」, 两行都靠两端对齐: 左边读数、右边控件/口径,
          每一行的右缘都落在同一条竖线上; 按钮紧贴右缘而不是悬在中间。
          行内顺序按用户口径对调过两次: 先是「按钮那部分和它底下的文字互换位置」,
          再是「左边的那两行也是要互换」—— 定稿为
          第一行 = 领涨领跌 + 口径(层级·日期·行业数·标的数), 第二行 = 5 项摘要 + 控件簇。
          不用 PageHeader 的 `right` 槽: 它把左侧内容与右侧内容分成两个 flex item, 行高
          由各自内容决定, 上下两行天然对不齐。 */}
      <PageHeader
        className="shrink-0 [&>div:first-child]:w-full"
        afterSubtitle={
          <div className="flex w-full min-w-0 flex-col gap-2">
            <div className="flex min-w-0 flex-wrap items-center gap-x-2.5 gap-y-1">
              <IndustryLeaders leaders={pctLeaders} fallers={pctFallers} onSelect={setSelectedKey} />
              <span className="ml-auto whitespace-nowrap text-xs leading-[18px] text-muted">
                {industryLevelLabel} · {marketQuery.data?.as_of ?? rowsQuery.data?.date ?? '最新'} · {stats.length} 个行业 · {totalSymbols} 只标的
              </span>
            </div>
            <div className="flex min-w-0 flex-wrap items-center gap-x-2.5 gap-y-1">
              <IndustryBrief
                leading={leading[0]}
                falling={falling[0]}
                activeIndustry={activeIndustry}
                industryBreadth={industryBreadth}
              />
              {/* [R769] 「涨幅RPS轮动分析」按钮删除: 那个弹窗和这张热力图吃的是同一个接口、
                  同一份缓存, 弹窗只是同一份数据的另一种行语义(按名次而非按行业)。
                  [R773] 工具栏整条搬到这里, 排在刷新按钮之前 —— 用户: 「按钮们放到刷新
                  按钮前面」。它们和刷新/配置是同一类动作(改口径 / 重取数)。
                  `ml-auto` 把整簇推到右缘, 与第一行的口径行同一条右对齐线。 */}
              <div className="ml-auto flex flex-wrap items-center gap-1">
                <SectorHeatmapToolbar
                  days={heatDays}
                  onDaysChange={setHeatDays}
                  topN={HEATMAP_TOP_N}
                  showAll={heatAll}
                  onShowAllChange={setHeatAll}
                  totalCount={heatTotal}
                  onOpenAi={d => { setAiDays(d); setShowAi(true) }}
                />
                <button
                  onClick={() => { rowsQuery.refetch(); marketQuery.refetch() }}
                  disabled={rowsQuery.isFetching || marketQuery.isFetching}
                  className="p-1 text-secondary hover:bg-surface disabled:opacity-50"
                  title="刷新"
                >
                  <RefreshCw className={cn('h-4 w-4', (rowsQuery.isFetching || marketQuery.isFetching) && 'animate-spin')} />
                </button>
                <button onClick={() => setShowConfig(true)} className="p-1 text-secondary hover:bg-surface hover:text-accent" title="配置数据源">
                  <Settings2 className="h-4 w-4" />
                </button>
              </div>
            </div>
          </div>
        }
      />

      {/* [R60] 统一版式: 留白 px-3/lg:px-4、区块间距 12px, 与全站一致
          [R768] 改成 flex 列并吃掉剩余高度: 热力图按剩余空间铺满, 页面不再需要滚动 */}
      <div className="flex min-h-0 flex-1 flex-col px-3 pb-3 pt-3 lg:px-4">
        {/* [R547] 撤掉 1440px 居中上限, 与其它页一样贴左铺满(用户: 页面要铺满内容区) */}
        <div className="flex min-h-0 w-full flex-1 flex-col gap-3">
          {/* [R326 同步上游] v0.2.4 新增的盘中板块轮动卡。上游随它一起把
              这一页的留白改成了 px-6 py-5 / space-y-5 —— **版式那半不取**:
              R60 把全站统一到了 px-3/lg:px-4 + space-y-3, 只改这两页会让它们
              比别处宽出一圈。取卡片, 不取版式。 */}
          <SectorRotationCard kind="industry" />

          {/* [R762] 布局重排: 热力图提到第 2 位(紧跟指标条), Top10 挪到页面末尾。
              理由(1700×913 实机量): 原来 Top10 占 500px 却与热力图最新一列讲同一件事,
              热力图被压到第 3 位、第一屏只露表头和 6 行; 且点格子后详情在 1.5 屏之外。
              现在顺序 = 指标卡 → 热力图 → 行业矩阵+详情 → Top10, 联动可当场看到。 */}
          {groups.length > 0 && (
            <SectorRankHeatmap
              kind="industry"
              level={industryLevel}
              days={heatDays}
              topN={HEATMAP_TOP_N}
              showAll={heatAll}
              onTotalChange={setHeatTotal}
              selectedKey={selectedKey}
              onSelect={setSelectedKey}
            />
          )}

          {/* [R763] 左侧 rail(288×752) 与热力图左列同信息, 删除; 详情改为右侧抽屉,
              整页只剩「指标条 + 热力图」一屏, 空态/加载态仍原位显示 */}
          {stats.length === 0 && (rowsQuery.isLoading ? (
            <div className="rounded-dialog border border-border bg-surface px-6 py-16 text-center text-sm text-muted">正在计算行业强度...</div>
          ) : needsIndustryFetch ? (
            <PresetFetchState
              title="未获取行业数据"
              hint="内置行业数据源已就绪,点击下方按钮从同花顺获取行业分类数据"
              isLoading={fetchMutation.isPending}
              error={fetchMutation.error}
              onFetch={() => fetchMutation.mutate()}
            />
          ) : (
            <EmptyState icon={Layers3} title="未匹配到行业数据" hint={resolved.hint || '请检查扩展数据是否包含行业/板块相关字段'} />
          ))}

          {/* [R767] 页尾「领涨/领跌」chips 行删除; [R774] 用户要它回来, 已接到页头摘要末尾
              (见 `IndustryBrief`), 页面里不再有第三行读数。 */}
        </div>
      </div>

      {/* [R763] 行业详情抽屉: 点热力图格子/chip 后从右侧滑出(复用 IndustryFocus) */}
      <AnimatePresence>
        {selected && (
          <>
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={() => setSelectedKey(null)}
              className="fixed inset-0 z-30 bg-black/40"
            />
            <motion.aside
              initial={{ x: 560 }}
              animate={{ x: 0 }}
              exit={{ x: 560 }}
              transition={{ type: 'tween', duration: 0.2 }}
              className="fixed right-0 top-0 z-40 flex h-screen w-[800px] max-w-[92vw] flex-col border-l border-border bg-base shadow-2xl"
            >
              <div className="flex shrink-0 items-center justify-between border-b border-border px-4 py-2">
                <span className="text-xs text-muted">行业详情</span>
                <button onClick={() => setSelectedKey(null)} className="p-1 text-secondary hover:text-foreground" aria-label="关闭">
                  <X className="h-4 w-4" />
                </button>
              </div>
              <div className="min-h-0 flex-1 overflow-auto">
                <IndustryFocus stat={selected} activeSymbol={previewSymbol} onStockClick={handleStockClick} />
              </div>
            </motion.aside>
          </>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {showConfig && <AnalysisConfigDialog currentConfig={fieldConfig} onSave={handleSaveConfig} onClose={() => setShowConfig(false)} showHierarchyLevel />}
      </AnimatePresence>

      {/* [R550] 常挂着、靠 symbol 为空收起, 退场动画才跑得起来(见 AbnormalMoves 同一处) */}
      <StockPreviewDialog
        symbol={previewSymbol}
        name={previewName}
        onClose={() => { setPreviewSymbol(null); setPreviewName(''); setPreviewNavList([]) }}
        navList={previewNavList}
        onNavigate={(sym, n) => { setPreviewSymbol(sym); setPreviewName(n ?? '') }}
      />
      {/* [R769] AI 只留报告: 矩阵已经并进热力图, 弹窗不再画第二遍同一份矩阵 */}
      {showAi && (
        <RpsRotationDialog
          aiOnly
          kind="industry"
          initialDays={aiDays}
          initialLevel={industryLevel}
          onClose={() => setShowAi(false)}
        />
      )}
    </div>
  )
}

// ===== 页头摘要 =====

/**
 * [R765] 5 项指标从「一整条并排卡」压成副标题后的一句摘要。
 *
 * 原来那 5 张单行卡占 25px + 上下间距 12px = 37px, 全在页面最顶部, 挤的是热力图。
 * 现在同一批读数、同一套涨幅配色, 只是排成一行文本, 整条删除, 37px 还给热力图。
 *
 * 为什么是纯文本而不是 5 个 chip: 1700 视口下页头留给这块只剩 768px, 5 个 chip 的
 * 自然宽是 800px(「龙头算法 6 因子 强势+承接+容量」一项就占 179px), 塞不进去;
 * 同内容纯文本约 660px。更窄时由 `PageHeader` 的 flex-wrap 把整组折到第二行,
 * 不截断也不丢字(见 `PageHeader.afterSubtitle` 的注释)。
 *
 * 「龙头算法」不是行情读数(value 与说明都是常量), 所以正文只留「6 因子」, 全句进 title。
 */
function IndustryBrief({
  leading,
  falling,
  activeIndustry,
  industryBreadth,
}: {
  leading?: IndustryStat
  falling?: IndustryStat
  activeIndustry?: IndustryStat | null
  industryBreadth: { up: number; down: number; flat: number }
}) {
  return (
    <div className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-0.5 text-micro text-muted">
      <BriefItem label="最强行业">
        <span className="text-foreground">{leading?.key ?? '—'}</span>
        {leading?.avgPct != null
          ? <span className={priceColorClass(leading.avgPct)}>{fmtPct(leading.avgPct)}</span>
          : <span>等待行情</span>}
      </BriefItem>
      <BriefSep />
      <BriefItem label="最大风险">
        <span className="text-foreground">{falling?.key ?? '—'}</span>
        {falling?.avgPct != null
          ? <span className={priceColorClass(falling.avgPct)}>{fmtPct(falling.avgPct)}</span>
          : <span>等待行情</span>}
      </BriefItem>
      <BriefSep />
      <BriefItem label="涨跌行业">
        <span className="text-bull">{industryBreadth.up}</span>
        <span className="text-muted">/</span>
        <span className="text-bear">{industryBreadth.down}</span>
        {industryBreadth.flat > 0 && <span className="font-normal text-muted">平 {industryBreadth.flat}</span>}
      </BriefItem>
      <BriefSep />
      <BriefItem label="资金活跃">
        <span className="text-foreground">{activeIndustry?.key ?? '—'}</span>
        <span>{activeIndustry ? fmtBigNum(activeIndustry.totalAmount) : '等待行情'}</span>
      </BriefItem>
      <BriefSep />
      <span className="flex items-center gap-1 whitespace-nowrap">
        <span className="text-muted">龙头算法</span>
        <span className="font-medium text-warning" title="强势 + 承接 + 容量">6 因子</span>
      </span>
    </div>
  )
}

/**
 * [R774] 热力图底下原来那行「领涨/领跌」chips, 现在是页头第二行的左半部分。
 *
 * 各 4 条, 第 1 名已在第一行「最强行业/最大风险」里, 这里剔掉它、顺位补到第 5 名 ——
 * 同一屏里同一个行业出现两遍, 读的人会以为其中一处是错的。
 */
function IndustryLeaders({
  leaders,
  fallers,
  onSelect,
}: {
  leaders: IndustryStat[]
  fallers: IndustryStat[]
  onSelect?: (key: string) => void
}) {
  if (leaders.length === 0) return null
  return (
    <div className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-0.5 text-micro text-muted">
      <span className="shrink-0 text-bull">领涨</span>
      {leaders.map(item => (
        <BriefChip key={item.key} item={item} onSelect={onSelect} />
      ))}
      <BriefSep />
      <span className="shrink-0 text-bear">领跌</span>
      {fallers.map(item => (
        <BriefChip key={item.key} item={item} onSelect={onSelect} />
      ))}
    </div>
  )
}

/** [R774] 领涨/领跌榜里的一项: 行业名 + 平均涨幅, 点了开右侧详情抽屉(与点热力图格子同一个动作) */
function BriefChip({ item, onSelect }: { item: IndustryStat; onSelect?: (key: string) => void }) {
  return (
    <button
      onClick={() => onSelect?.(item.key)}
      className="flex items-center gap-1 whitespace-nowrap rounded-btn px-1 py-0.5 transition-colors hover:bg-elevated"
      title={`${item.key} · 等权平均涨幅 ${item.avgPct != null ? fmtPct(item.avgPct) : '—'} · ${item.count} 只标的`}
    >
      <span className="text-foreground">{item.key}</span>
      <span className={priceColorClass(item.avgPct)}>{item.avgPct != null ? fmtPct(item.avgPct) : '—'}</span>
    </button>
  )
}

/** 项与项之间的分隔点: 纯间隔会让「+3.10%」和下一个标签糊在一起 */
function BriefSep() {
  return <span aria-hidden className="select-none text-muted/40">·</span>
}

function BriefItem({ label, children }: { label: string; children: ReactNode }) {
  return (
    <span className="flex items-center gap-1 whitespace-nowrap">
      <span className="text-muted">{label}</span>
      <span className="font-medium tabular-nums">{children}</span>
    </span>
  )
}

// ===== IndustryFocus（右侧聚焦面板） =====

/**
 * [R776] 抽屉加宽到 800px 之后重排。
 *
 * 原来那版是按「560px 窄抽屉」写的, 但里面用的是**视口断点**(`lg:flex-row`、
 * `lg:w-[520px]`、`lg:grid-cols-[1fr_1.15fr]`)—— 屏幕够宽就按宽屏排, 而抽屉只有
 * 560, 于是标题与五个读数挤成一行、三龙头卡被压到 ~90px、表格 8 列横向溢出。
 * 现在一律按抽屉自身宽度排:
 *
 * 1. 标题 + 强度徽标一行, 下面一行读数(成分/平均/上涨占比/成交额/均换手);
 * 2. 五个读数格五等分整行(窄屏三列);
 * 3. 三龙头、评分拆解各占一整行 —— 并排放时三张龙头卡只剩 100 出头, 挤;
 * 4. 成分股表吃剩余高度, 单元格 px-3 让 8 列在 768 内容宽内不横滚。
 */
function IndustryFocus({ stat, onStockClick, activeSymbol }: { stat: IndustryStat | null; onStockClick: (symbol: string, name?: string, navList?: NavItem[]) => void; activeSymbol: string | null }) {
  if (!stat) return null
  const stocks = [...stat.stocks].sort((a, b) => b.leaderScore - a.leaderScore).slice(0, MAX_RENDERED_STOCKS)
  const topLeaders = stocks.slice(0, 3)
  const focusNav: NavItem[] = toNavItems(stocks)
  return (
    <section className="flex h-full min-h-0 flex-col overflow-hidden">
      <div className="shrink-0 border-b border-border px-5 py-3">
        <div className="flex items-baseline gap-2">
          <h3 className="truncate text-lg font-semibold leading-tight text-foreground">{stat.key}</h3>
          <span className="shrink-0 rounded-btn bg-warning/10 px-2 py-0.5 text-micro text-warning">强度 {stat.heatScore.toFixed(0)}</span>
        </div>
        <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted">
          <span>{stat.count} 只成分</span>
          <span className={priceColorClass(stat.avgPct)}>平均 {stat.avgPct != null ? fmtPct(stat.avgPct) : '—'}</span>
          <span>上涨占比 {(stat.upRate * 100).toFixed(0)}%</span>
          <span>成交额 {fmtBigNum(stat.totalAmount)}</span>
          {stat.avgTurnover != null && <span>均换手 {stat.avgTurnover.toFixed(2)}%</span>}
        </div>
      </div>

      <div className="grid shrink-0 grid-cols-3 gap-2 border-b border-border bg-base/25 px-5 py-3 sm:grid-cols-5">
        <MiniStat label="均涨" value={stat.avgPct != null ? fmtPct(stat.avgPct) : '—'} cls={priceColorClass(stat.avgPct)} />
        <MiniStat label="中位" value={stat.medianPct != null ? fmtPct(stat.medianPct) : '—'} cls={priceColorClass(stat.medianPct)} />
        <MiniStat label="强势" value={`${stat.strongCount}`} cls="text-bull" />
        <MiniStat label="弱势" value={`${stat.weakCount}`} cls="text-bear" />
        <MiniStat label="量比" value={stat.avgVolRatio != null ? stat.avgVolRatio.toFixed(2) : '—'} cls="text-foreground" />
      </div>

      <div className="flex shrink-0 flex-col gap-3 border-b border-border bg-base/25 px-5 py-3">
        <LeaderStage stocks={topLeaders} activeSymbol={activeSymbol} onStockClick={(sym, name) => onStockClick(sym, name, focusNav)} />
        <ScoreExplain stock={topLeaders[0]} />
      </div>

      <div className="min-h-0 flex-1 overflow-auto">
        <table className="min-w-full text-left text-xs">
          <thead className="bg-elevated/60 text-xs text-muted">
            <tr>
              <th className="px-3 py-2 font-medium">排名</th>
              <th className="px-3 py-2 font-medium">股票</th>
              <th className="px-3 py-2 font-medium">涨跌幅</th>
              <th className="px-3 py-2 font-medium">换手率</th>
              <th className="px-3 py-2 font-medium">成交额</th>
              <th className="px-3 py-2 font-medium">流通市值</th>
              <th className="px-3 py-2 font-medium">量比</th>
              <th className="px-3 py-2 font-medium">龙头分</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border/70">
            {stocks.map((s, idx) => (
              <tr key={`${s.symbol}-${idx}`} className={cn('cursor-pointer', s.symbol === activeSymbol ? 'bg-accent/10 hover:bg-accent/15' : 'hover:bg-elevated/30')} onClick={() => onStockClick(s.symbol, s.name || undefined, focusNav)}>
                <td className="px-3 py-2 font-mono text-muted">{idx + 1}</td>
                <td className="px-3 py-2">
                  <div className="font-medium text-foreground">{s.name || '—'}</div>
                  <div className="font-mono text-micro text-muted">{s.symbol}</div>
                </td>
                <td className={cn('px-3 py-2 font-mono tabular-nums', priceColorClass(s.change_pct))}>{s.change_pct != null ? fmtPct(s.change_pct) : '—'}</td>
                <td className="px-3 py-2 font-mono text-foreground">{s.turnover_rate != null ? `${s.turnover_rate.toFixed(2)}%` : '—'}</td>
                <td className="px-3 py-2 font-mono text-foreground">{fmtBigNum(s.amount)}</td>
                <td className="px-3 py-2 font-mono text-foreground">{fmtBigNum(s.float_market_cap ?? s.market_cap)}</td>
                <td className="px-3 py-2 font-mono text-foreground">{s.vol_ratio_5d != null ? s.vol_ratio_5d.toFixed(2) : '—'}</td>
                <td className="px-3 py-2">
                  <div className="flex items-center gap-2">
                    <span className="w-9 font-mono text-warning">{s.leaderScore.toFixed(0)}</span>
                    <div className="h-1.5 w-16 rounded-full bg-elevated"><div className="h-full rounded-full bg-warning" style={{ width: `${Math.max(4, s.leaderScore)}%` }} /></div>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {stat.stocks.length > MAX_RENDERED_STOCKS && <div className="shrink-0 border-t border-border px-4 py-2 text-center text-xs text-muted">仅展示龙头分前 {MAX_RENDERED_STOCKS} 只，共 {stat.stocks.length} 只</div>}
    </section>
  )
}

function MiniStat({ label, value, cls }: { label: string; value: string; cls: string }) {
  return <div className="rounded-card border border-border/60 bg-base/35 px-2 py-1.5"><div className="text-micro text-muted">{label}</div><div className={cn('mt-0.5 truncate text-sm font-semibold', cls)}>{value}</div></div>
}

function LeaderStage({ stocks, onStockClick, activeSymbol }: { stocks: EnrichedStock[]; onStockClick: (symbol: string, name?: string) => void; activeSymbol: string | null }) {
  if (!stocks.length) return <div className="rounded-dialog border border-border/60 bg-surface p-4 text-sm text-muted">暂无龙头候选</div>
  return (
    <div className="rounded-dialog border border-border/60 bg-surface p-3">
      <div className="mb-2 flex items-center gap-2 text-xs font-medium text-warning">
        <Crown className="h-3.5 w-3.5" />
        本行业三龙头
      </div>
      <div className="grid gap-2 md:grid-cols-3">
        {stocks.map((stock, idx) => (
          <div key={stock.symbol} onClick={() => onStockClick(stock.symbol, stock.name || undefined)} className={cn('rounded-card border p-3 cursor-pointer hover:brightness-110 transition-ui', idx === 0 ? 'border-warning/25 bg-warning/[0.06]' : 'border-border/60 bg-base/35', stock.symbol === activeSymbol && 'ring-1 ring-accent/60')}>
            <div className="flex items-center justify-between gap-2">
              <span className={cn('text-micro font-medium', idx === 0 ? 'text-warning' : 'text-muted')}>{idx === 0 ? '主龙头' : `辅龙 ${idx}`}</span>
              <span className="font-mono text-xs text-warning">{stock.leaderScore.toFixed(0)}</span>
            </div>
            <div className="mt-2 truncate text-sm font-medium text-foreground">{stock.name || stock.symbol}</div>
            <div className="mt-0.5 flex items-center justify-between text-xs">
              <span className="font-mono text-muted">{stock.symbol}</span>
              <span className={cn('font-mono', priceColorClass(stock.change_pct))}>{stock.change_pct != null ? fmtPct(stock.change_pct) : '—'}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

function ScoreExplain({ stock }: { stock?: EnrichedStock }) {
  if (!stock) return <div className="rounded-dialog border border-border/60 bg-surface p-4 text-sm text-muted">暂无评分拆解</div>
  const parts = stock.leaderParts
  return (
    <div className="rounded-dialog border border-border/60 bg-surface p-3">
      <div className="mb-2 flex items-center justify-between">
        <span className="text-xs font-medium text-foreground">主龙头评分拆解</span>
        <span className="text-xs text-muted">涨幅 / 换手 / 成交 / 市值 / 量比 / 连板</span>
      </div>
      <div className="grid grid-cols-3 gap-2 lg:grid-cols-6">
        <Part label="动能" value={parts.momentum} cls="bg-red-400" />
        <Part label="换手" value={parts.turnover} cls="bg-warning" />
        <Part label="成交" value={parts.amount} cls="bg-blue-400" />
        <Part label="市值" value={parts.cap} cls="bg-cyan-400" />
        <Part label="量比" value={parts.volume} cls="bg-lime-400" />
        <Part label="连板" value={parts.boards} cls="bg-warning" />
      </div>
    </div>
  )
}

function Part({ label, value, cls }: { label: string; value: number; cls: string }) {
  return <div className="rounded-card bg-base/35 px-2 py-1.5"><div className="mb-1 flex justify-between text-micro text-muted"><span>{label}</span><span>{Math.round(value * 100)}</span></div><div className="h-1 rounded-full bg-elevated"><div className={cn('h-full rounded-full', cls)} style={{ width: `${Math.max(3, value * 100)}%` }} /></div></div>
}
