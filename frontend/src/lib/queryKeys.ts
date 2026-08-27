/**
 * 集中管理所有 React Query key。
 *
 * - 新增查询只需在此加一行，所有消费方自动引用。
 * - SSE invalidation 基于 SSE_INVALIDATE_PREFIXES 列表，新增 key 无需改 useQuoteStream。
 */

// ===== Query Key 工厂 =====

export const QK = {
  // 全局 / 共享 (Layout 预取)
  capabilities:   ['capabilities'] as const,
  settings:       ['settings'] as const,
  endpoints:      ['endpoints'] as const,
  version:        ['version'] as const,
  preferences:    ['preferences'] as const,
  dataSources:    ['data-sources'] as const,
  quoteStatus:    ['quote-status'] as const,
  quoteInterval:  ['quote-interval'] as const,
  overviewMarket: (asOf?: string) => ['overview-market', asOf ?? 'latest'] as const,
  indexQuotes:    ['index-quotes'] as const,
  indexList:      ['index-list'] as const,

  // Watchlist
  watchlist:            ['watchlist'] as const,
  watchlistGroups:      ['watchlist-groups'] as const,
  watchlistQuotes:      ['watchlist-quotes'] as const,
  watchlistEnriched:    (ext?: string) => ['watchlist-enriched', ext] as const,
  // 异动边缘总览 (开启监控时才查询, 参数为 min_closeness/limit)
  abnormalOverview:     (minCloseness: number, limit: number) => ['abnormal-overview', minCloseness, limit] as const,
  // 不用 watchlist- 前缀: 日K历史盘中几乎不变, 若被 SSE quotes_updated 高频失效
  // (expert 1s) 会导致全自选日K每秒重拉, staleTime 形同虚设。
  // 刷新点: staleTime 过期 + Watchlist 增删自选/改蜡烛天数时的手动失效;
  // 当日最后一根蜡烛由 Watchlist 用 enriched 实时 OHLC 前端修补 (零额外请求)。
  watchlistKlineBatch:  (symbols: string) => ['kline-batch', symbols] as const,
  // 不用 watchlist- 前缀: 避免被 SSE quotes_updated 高频失效(expert 1s/pro 2s)
  // 导致每次都拉 TickFlow 触限流。分时图用固定 refetchInterval 刷新即可。
  minuteBatch:          (symbols: string) => ['minute-batch', symbols] as const,
  instrumentSearch:     (q: string, assetTypes?: string) => ['instrument-search', q, assetTypes ?? 'stock'] as const,

  // Screener
  screener:             ['screener'] as const,
  screenerStrategies:   (assetType: string = 'stock', timeframe: '1d' | '1m' | 'all' = '1d') => ['screener-strategies', assetType, timeframe] as const,
  screenerCachedSummary: ['screener-cached', 'summary'] as const,
  screenerCachedResult: (strategyId: string, asOf?: string, ext?: string) => ['screener-cached', 'strategy', strategyId, asOf ?? '', ext ?? ''] as const,
  screenerCached:       (asOf?: string, ext?: string) => ['screener-cached', 'all', asOf ?? '', ext ?? ''] as const,
  screenerKlineBatch:   (symbols: string) => ['screener-kline-batch', symbols] as const,
  marketSnapshot:       ['market-snapshot'] as const,
  limitLadder:          (asOf?: string) => ['limit-ladder', asOf] as const,

  // Backtest
  backtestStatus:       ['backtest-status'] as const,
  factorColumns:        ['backtest-factor-columns'] as const,
  miningRuns:           ['backtest-mining-runs'] as const,
  miningAvailability:   (assetType: string, profile: string, start: string, end: string) =>
                          ['backtest-mining-availability', assetType, profile, start, end] as const,
  miningRun:            (id: string) => ['backtest-mining-run', id] as const,
  miningResult:         (id: string) => ['backtest-mining-result', id] as const,
  miningConfig:         ['backtest-mining-config'] as const,
  researchCandidates:  ['research-candidates'] as const,
  strategyLinkOptions: (assetType?: 'stock' | 'etf') => assetType
    ? ['strategy-link-options', assetType] as const
    : ['strategy-link-options'] as const,
  strategyDetail:       (id: string) => ['strategy-detail', id] as const,

  // Data / Pipeline
  dataStatus:           ['data-status'] as const,
  pipelineJobs:         ['pipeline-jobs'] as const,
  pipelineJob:          (id: string) => ['pipeline-job', id] as const,
  extData:              ['ext-data'] as const,
  extDataRows:          (id: string, date?: string, limit?: number, columns?: string) => ['ext-data-rows', id, date, limit, columns] as const,
  dimensionMembers:     (id: string, field: string, value: string, date?: string) => ['dimension-members', id, field, value, date] as const,
  analysisMenus:        ['analysis-menus'] as const,
  analysisMenu:         (id: string) => ['analysis-menu', id] as const,

  // Kline
  kline:                (symbol: string, start: string, end: string, extColumns?: string) =>
                           ['kline', symbol, start, end, extColumns ?? ''] as const,
  stockLevels:          (symbol: string, days?: number) => ['stock-levels', symbol, days ?? 120] as const,
  // [fork 增强] 六态趋势
  stockTrend:           (symbol: string) => ['stock-trend', symbol] as const,
  stockTrends:          (symbols: string) => ['stock-trends', symbols] as const,
  stockKeltner:         (symbols: string) => ['stock-keltner', symbols] as const,
  stockReview:          (symbol: string, days: number) => ['stock-review', symbol, days] as const,
  klineMinute:          (symbol: string, date: string) =>
                             ['kline-minute', symbol, date] as const,
  klineMinuteRange:     (symbol: string, days: number) =>
                             ['kline-minute-range', symbol, days] as const,
  indexDaily:           (symbol: string, start: string, end: string) =>
                           ['index-daily', symbol, start, end] as const,
  indexMinute:          (symbol: string, date: string) =>
                           ['index-minute', symbol, date] as const,

  // Schema
  extDataSchemaAll:     ['ext-data-schema-all'] as const,
  tableSchema:          (table: string) => ['table-schema', table] as const,

  // Custom Signals
  customSignals:        ['custom-signals'] as const,
  customSignalsOptions: ['custom-signals-options'] as const,

  // Monitor (监控规则 + 触发记录)
  monitorRules:         ['monitor-rules'] as const,
  monitorRuleOptions:   ['monitor-rule-options'] as const,
  alerts:               (source?: string) => ['alerts', source ?? ''] as const,

  // AI 大盘复盘
  reviewReports:        ['review-reports'] as const,

  // 概念涨幅轮动矩阵
  rpsRotation:          (days: number) => ['rps-rotation', days] as const,

  // 市场环境(Regime) — 日级离线计算, 不进 SSE 刷新
  regimeHistory:        (limit?: number) => ['regime-history', limit ?? 0] as const,
  regimeLatest:         ['regime-latest'] as const,
  regimeStates:         (days: number) => ['regime-states', days] as const,
  regimeCoverage:       ['regime-coverage'] as const,
  regimePhases:         (start?: string, end?: string) => ['regime-phases', start ?? '', end ?? ''] as const,
  regimeMainline:       (kind: string, start?: string, end?: string) => ['regime-mainline', kind, start ?? '', end ?? ''] as const,

  // ===== [fork 增强] 以下是 fork 页面的 key —— 之前散在各页面里内联写,
  // R70 按上游二开守则(docs/secondary-development.md §3.4)收拢到这里。
  // 'ai-profiles' 曾同时写在两个文件里、'workflows' 也是 —— 正是这种跨文件
  // 重复字符串, 改一处漏一处时缓存就悄悄失联了。

  // 今日总览
  todayOverview:        ['today-overview'] as const,
  todayAiSchedule:      ['today-ai-schedule'] as const,
  signalAiSchedule:     ['signal-ai-schedule'] as const,
  // AI 操盘手
  paperTraders:         ['paper-traders'] as const,
  paperBooksAll:        ['paper-book'] as const,          // 前缀失效: 所有账本明细
  paperBook:            (id: string, scope: string) => ['paper-book', id, scope] as const,
  paperBookContext:     (id: string, scope: string) => ['paper-book-context', id, scope] as const,
  // 多 AI 档位 / 数据源 key
  aiProfiles:           ['ai-profiles'] as const,
  tickflowKeys:         ['tickflow-keys'] as const,
  realtimeKeysPerRound: ['realtime-keys-per-round'] as const,
  // 研究工作流 / AI 自动挖掘
  workflows:            (kind: string) => ['workflows', kind] as const,
  miningAutopilotSessions: ['mining-autopilot-sessions'] as const,
  // 板块跷跷板 / 盘中阶段
  regimeSeesaw:         (kind: string) => ['regime-seesaw', kind] as const,
  regimePhaseLive:      ['regime-phase-live'] as const,
  // 连板梯队 AI 打板复盘
  ladderAiReports:      ['ladder-ai-reports'] as const,
  // 自选决策台(持仓/出场线/AI 信号)
  watchlistPositions:   ['watchlist-positions'] as const,
  watchlistExitLines:   ['watchlist-exit-lines'] as const,
  stockSignals:         ['stock-signals'] as const,
  // 六态趋势前缀失效(带 symbols 参数的实例见 stockTrends)
  stockTrendsAll:       ['stock-trends'] as const,
  // 个股分析顶栏行情摘要 —— 键形刻意与页内看板一致, 共享缓存不发第二次请求
  analysisKline:        (symbol: string) => ['kline', symbol, ''] as const,
} as const

// ===== SSE 应该 invalidate 的 key 前缀列表 =====
// 新增需要 SSE 推送的查询，只需在此加一行
//
// 注意: 策略页 (screener-cached) 不在此列表 —— 行情刷新时策略结果不变
// (非监控策略读盘后静态缓存, 监控策略由独立的 strategy_results_updated 事件在
// 重算完成后刷新)。若加入 'screener', 会导致每个行情 tick 双重刷新策略页,
// 且在 monitor "重算" 窗口内读到空结果, 造成策略列表闪烁 (变 0 → 空失效 → 又出现)。

export const SSE_INVALIDATE_PREFIXES = [
  // 精确前缀: 只命中自选页的实时数据 (quotes/enriched)。不能用宽泛的 'watchlist' ——
  // 会误伤 ['watchlist'] (自选列表) 和 ['watchlist-groups'] (分组配置, 只随手动操作变化)。
  // 旧设置里的 'watchlist' 单开关由 useQuoteStream 兼容读取。
  'watchlist-quotes',
  'watchlist-enriched',
  'quote-status',
  'index-quotes',
  'overview-market',
  'limit-ladder',
] as const
