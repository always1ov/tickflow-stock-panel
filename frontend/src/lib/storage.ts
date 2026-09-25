/**
 * 集中管理所有 localStorage 持久化。
 *
 * - key 在此注册，各页面只通过 storage.xxx.get/set 调用。
 * - 类型安全，不再散落 try/catch。
 */

function kv<T>(key: string) {
  return {
    get(fallback: T): T {
      try {
        const raw = localStorage.getItem(key)
        if (raw !== null) return JSON.parse(raw) as T
      } catch { /* ignore */ }
      return fallback
    },
    set(val: T) {
      try { localStorage.setItem(key, JSON.stringify(val)) } catch { /* ignore */ }
    },
    remove() {
      try { localStorage.removeItem(key) } catch { /* ignore */ }
    },
  }
}

/** 新建策略默认基础过滤参数 (与策略 META.basic_filter 字段/单位一致: 价格元, 市值/成交额元, 换手%) */
export interface DefaultStrategyBasicFilter {
  price_min: number | null
  price_max: number | null
  float_cap_min: number | null
  float_cap_max: number | null
  amount_min: number | null
  amount_max: number | null
  turnover_min: number | null
  turnover_max: number | null
  exclude_st: boolean
  boards: string[]
}

export const storage = {
  /** 查询轮询 / SSE 配置 */
  queryConfig:          kv<unknown>('tf-stocks-query-config'),

  /** 策略池 (screener) — 统一池 (日线+分钟共用, 执行按各自声明周期路由) */
  strategyPool:         kv<string[]>('strategy-pool'),
  /** 旧分钟隔离池 — 仅作一次性迁移读取源, 迁移完成后移除该 key */
  strategyPoolMinute:   kv<string[]>('strategy-pool-1m'),
  /** [R95] prune 自动清理的备份 — 被移除的 ID 留底, 页面提供一键恢复 */
  strategyPoolPruneBackup: kv<{ at: string; removed: string[] } | null>('strategy-pool-prune-backup'),
  /**
   * [R331] 今日信号里「只是盯着」那一段展开着没有。默认 **false(收起)** ——
   * 那一段是"今天大概率不用动"的票, 数量随自选规模走, 摊开会把真要动手的淹掉。
   *
   * [R327] R192 那个 `paperTrader`(当前看哪个操作员)跟着 AI 操盘手一起没了。
   */
  flipTodayWatchOpen:   kv<boolean>('flip-today-watch-open'),
  // [R353] 模拟盘那三个参数。用户: 「这里我要能配置而不是选择或者默认」——
  // 既然能自己填, 就得记住; 每次打开都退回默认值等于没配过。
  // [R355] 「手上这些」的展开状态。**默认展开** —— 见 FlipPaper 里那段说明:
  // 它是卖出那一侧唯一天天有位置的东西, 默认收起等于把 R338 做的事撤回去。
  flipMineOpen:         kv<boolean>('flip-mine-open'),
  /** [R358] 净值走势图折起来没有 —— 默认收起 */
  flipNavOpen:          kv<boolean>('flip-nav-open'),
  // [R512] 原来这里是 flipRulesOpen(「这套规则」折没折) —— 规则有了自己的一栏, 不再折叠, 删了
  flipCapital:          kv<number>('flip-capital'),
  flipMaxPositions:     kv<number>('flip-max-positions'),
  flipYears:            kv<number>('flip-years'),

  /** [R266] 消息面总览是否展开 —— 默认收起(那一段很长), 但看惯了展开的人不该每次重点 */
  newsDeskSummaryOpen:  kv<boolean>('news-desk-summary-open'),

  /** [R269] 复盘·通道档位里那块「依据」是否展开 —— 默认收起, 正文让给历史段落 */
  reviewEvidenceOpen:   kv<boolean>('review-evidence-open'),
  // [R270 加, R292 删] `reviewTrendStatsOpen` 在这里删掉了 —— 它记的是「趋势状态」
  // 那堆涨跌停计数折叠区的开合, 而那一块整个撤了(计数压成头部一行小字)。
  // **不留没人读的键**: 留着的话下一个人会以为界面上还有那个开关。
  /** [R270] 组合速查里「其余 26 格」是否展开 —— 那是查表用的参考, 与今天无关 */
  reviewComboRestOpen:  kv<boolean>('review-combo-rest-open'),

  /**
   * [R276] 决策台当前只看哪个分组。取值: `'all'` / `'ungrouped'` / 分组 id。
   *
   * 用字符串哨兵而不是 `string | null`: 「未分组」本身就是一个可选项, 用 null 表示
   * 它的话就和"没存过"撞在一起了 —— localStorage 分不出这两件事。
   */
  boardGroupFilter:     kv<string>('board-group-filter'),

  /** [R100] 个股弹窗最近查看(全局, 弹窗内随意切换用) */
  recentStocks:         kv<{ symbol: string; name: string }[]>('recent-stocks'),

  /** 自选列表列配置 */
  watchlistColumns:     kv<unknown[]>('watchlist_columns'),

  /** 个股日K信息条指标配置 */
  stockInfoBarFields:   kv<unknown[]>('stock_info_bar_fields'),

  /** 个股日K成交量对比设置 */
  stockVolumeCompare:   kv<{ enabled: boolean; days: number }>('stock_volume_compare'),

  /** 个股详情多日分时周期 */
  stockPreviewIntradayDays: kv<number>('stock_preview_intraday_days'),

  /** 个股详情外链 URL 模板 (支持 {code}/{market}/{symbol}; 留空关闭) */
  stockExternalTemplate: kv<string>('stock_external_template'),

  /** 策略结果列表列配置 */
  screenerResultColumns: kv<unknown[]>('screener_result_columns'),

  /** 自选列表视图模式 grid(按小分队, 默认) | table(一张表)。[R508] 原来的 card 值按 grid 处理 */
  watchlistView:        kv<string>('watchlist_view'),

  /** 自选列表日K蜡烛图显示状态 */
  watchlistCandle:      kv<boolean>('watchlist_showCandle'),

  /** [fork 增强] 个股分析页决策台展开状态(收起后下次进来保持, 让 K 线占满首屏) */

  /** 自选列表分时图显示状态 */
  watchlistIntraday:    kv<boolean>('watchlist_showIntraday'),

  /** 策略结果列表日K蜡烛图显示状态 */
  // [R182] 决策台导出选中的列 —— 选完下次打开还是这套
  boardExportCols:      kv<string[]>('board_exportCols'),
  screenerCandle:       kv<boolean>('screener_showCandle'),

  /** 策略结果列表分时图显示状态 */
  screenerIntraday:     kv<boolean>('screener_showIntraday'),

  /** 策略结果列表"策略"列标签展开状态 (false=默认收起: 每行首个+计数, 行内可单独展开) */
  screenerStrategyTags: kv<boolean>('screener_strategyTagsExpanded'),

  /** 自选列表板块筛选 */
  watchlistBoardFilter: kv<string[]>('watchlist_boardFilter'),

  /** 自选列表排除 ST 标的 (默认不排除) */
  watchlistExcludeST:    kv<boolean>('watchlist_excludeST'),

  /** [R508] 自选「按小分队」网格里块的顺序: order 分组顺序 / pct 今日涨跌 */
  watchlistGridSort:    kv<string>('watchlist_gridSort'),

  /** 异动监控: 主开关 (默认关, 开启后才轮询计算; 告警走监控中心规则) */
  abnormalEnabled:      kv<boolean>('abnormal_enabled'),

  /** 异动监控: 上次计算结果 (关闭开关后仍展示, 含 asof 计算时间戳) */
  abnormalLastResult:   kv<unknown>('abnormal_last_result'),

  /** Screener 卡片尺寸 */
  screenerCardSize:     kv<string>('screener-card-size'),

  /** 连板梯队板块筛选 */
  limitLadderBoard:     kv<string[]>('limit-ladder-board-filter'),

  /** 连板梯队 ext 字段配置 */
  limitLadderExtFields: kv<Record<string, any>>('limit-ladder-ext-fields'),

  /** 连板梯队 概念/行业 显示开关 */
  limitLadderShowExt:   kv<{ concept: boolean; industry: boolean }>('limit-ladder-show-ext'),

  /** 连板梯队 涨停/跌停 切换方向 */
  limitLadderDirection: kv<'up' | 'down'>('limit-ladder-direction'),

  /** 连板梯队 封单显示模式: vol=按成交量(手), amount=按金额(元) */
  limitLadderSealMode:  kv<'vol' | 'amount'>('limit-ladder-seal-mode'),

  /**
   * [R54] 回测/挖掘页的手动配置栏是否展开。默认收起 —— 这两页的常规用法是
   * 让 AI 拿内置的那套东西自己跑, 手动那一大列平时不需要占着主视野。
   */
  researchManualOpen:   kv<boolean>('research-manual-open'),

  /** 策略创建草稿（新建专用） */
  strategyDraft: kv<{ name: string; description: string; direction: string; style?: string; rules: string; code: string; step: number; strategyId: string; source?: 'ai' | 'custom' } | null>('strategy-draft'),

  /** 新建策略默认基础过滤参数 (策略页「默认基础参数」设置; null=未自定义, 用内置默认) */
  defaultStrategyBasicFilter: kv<DefaultStrategyBasicFilter | null>('default-strategy-basic-filter'),

  /** 策略修改草稿（AI修改专用，不影响创建按钮） */
  strategyModify: kv<{ name: string; description: string; direction: string; style?: string; rules: string; code: string; step: number; strategyId: string; source?: 'ai' | 'custom' } | null>('strategy-modify'),

  /** 策略构建器草稿（旧版兼容，逐渐废弃） */
  strategyBuilderDraft: kv<{ name: string; description: string; direction: string; style?: string; rules: string; code: string; step: number; strategyId: string; source?: 'ai' | 'custom' } | null>('strategy-builder-draft'),

  /** 已保存策略的原始规则（策略ID → 规则文本） */
  strategyRules: kv<Record<string, string>>('strategy-rules'),

  /** 策略回测快捷区间按钮配置 */
  strategyBacktestQuickRanges: kv<unknown>('strategy-backtest-quick-ranges'),

  /** 策略回测最后一次成功结果和参数 */
  strategyBacktestLast: kv<{
    selectedStrategy: string | null
    symbols: string
    assetType?: 'stock' | 'etf'
    start: string
    end: string
    matching: 'close_t' | 'open_t+1'
    entryFill: 'close_t' | 'open_t+1'
    exitFill: 'close_t' | 'open_t+1' | 'signal_next_minute'
    fees: string
    stampTax?: string
    slippage: string
    maxPositions: string
    maxExposure: string
    initialCapital: string
    positionSizing: 'equal' | 'score_weight'
    mode: 'position' | 'full'
    holdingDays: string
    minuteFill?: boolean
    regimeStates?: string[]
    regimeMinScore?: number | ''
    params?: Record<string, any>
    overrides?: Record<string, any>
    strategyConfigSignature?: string
    result: any
  } | null>('strategy-backtest-last'),

  /** 概念分析页面字段配置 */
  conceptAnalysisConfig: kv<Record<string, any>>('concept-analysis-config'),

  /** 行业分析页面字段配置 */
  industryAnalysisConfig: kv<Record<string, any>>('industry-analysis-config'),

  /** 数据页画像卡片显隐 (卡片key → 是否显示) */
  dataCardVisible: kv<Record<string, boolean>>('data-card-visible'),
  /** 数据页画像卡片顺序 (卡片key 数组, 长度=卡片总数) */
  dataCardOrder: kv<string[]>('data-card-order'),
} as const
