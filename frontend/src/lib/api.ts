// 后端 API 客户端 — 全项目统一入口
//
// Dev: Vite 按启动脚本解析出的 BACKEND_HOST/BACKEND_PORT 代理 /api
// Prod:同源(FastAPI 托管前端 dist)

import { toast } from '@/components/Toast'
import type { ExtSpec } from '@/lib/externalView'   // [R117] 外部网页固定契约

const BASE = ''

type RequestOptions = RequestInit & {
  /** 为 true 时不弹错误 toast（由调用方自行汇总提示，如多图串行队列） */
  quiet?: boolean
  /** 请求超时毫秒数; null 关闭。默认 30s — 后端依赖 polars, 偶发挂起时无超时
   *  会占满浏览器同源连接池, 拖垮整页所有请求 (表现为全部排队"已停止")。 */
  timeoutMs?: number | null
}

export class ApiError extends Error {
  readonly status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

const DEFAULT_REQUEST_TIMEOUT_MS = 30_000
/** 同步计算型接口 (回测/筛选等) 的放宽超时: 合法耗时可能远超轮询类接口。 */
const COMPUTE_REQUEST_TIMEOUT_MS = 300_000

async function request<T>(path: string, init?: RequestOptions): Promise<T> {
  const { quiet, timeoutMs = DEFAULT_REQUEST_TIMEOUT_MS, ...fetchInit } = init ?? {}
  const isFormData = fetchInit.body instanceof FormData
  const headers: Record<string, string> = {}
  if (!isFormData) headers['Content-Type'] = 'application/json'
  // 合并调用方传入的 headers (此前会被整体覆盖丢弃)
  Object.assign(headers, fetchInit.headers as Record<string, string> | undefined)
  // 自带 signal 的调用方 (上传/串行队列) 由其自行控制中止; 其余走默认超时。
  const ctl = timeoutMs == null || fetchInit.signal ? undefined : new AbortController()
  const timeoutSeconds = Math.round((timeoutMs ?? DEFAULT_REQUEST_TIMEOUT_MS) / 1000)
  let timer: number | undefined
  if (ctl && timeoutMs != null) timer = window.setTimeout(() => ctl.abort(), timeoutMs)
  let res: Response
  try {
    res = await fetch(`${BASE}${path}`, {
      ...fetchInit,
      headers,
      ...(ctl ? { signal: ctl.signal } : {}),
    })
  } catch (err) {
    if (ctl && err instanceof DOMException && err.name === 'AbortError') {
      const msg = `请求超时（${timeoutSeconds}s）· ${path.split('?')[0]}`
      if (!quiet) toast(msg, 'error')
      throw new ApiError(msg, 0)
    }
    throw err
  } finally {
    if (timer !== undefined) window.clearTimeout(timer)
  }
  if (!res.ok) {
    let detail = ''
    try {
      const j = JSON.parse(await res.text())
      const raw = j.detail ?? j.message ?? ''
      if (Array.isArray(raw)) {
        // FastAPI 422 校验错误: [{type, loc, msg, input}, ...] → 取 msg 拼接
        detail = raw.map((e: any) => e?.msg || String(e)).join('; ')
      } else if (typeof raw === 'string') {
        detail = raw
      } else if (raw && typeof raw === 'object') {
        detail = JSON.stringify(raw)
      }
    } catch { /* ignore */ }
    const msg = detail || `${res.status} ${res.statusText}`
    // 401 (未登录/会话过期) 不弹 toast — 由全局认证拦截器统一跳登录页, 避免刷屏
    if (res.status !== 401 && !quiet) toast(msg, 'error')
    throw new ApiError(msg, res.status)
  }
  return res.json() as Promise<T>
}

// ===== Capabilities =====
export interface CapabilityLimits {
  rpm: number | null
  batch: number | null
  subscribe: number | null
}

export interface CapabilitiesResponse {
  label: string
  capabilities: Record<string, CapabilityLimits>
}

// ===== Financials =====
export interface FinancialStatus {
  available: boolean
  tables: Record<string, { rows: number; symbols: number }>
  last_sync: Record<string, string>
  /** 服务端是否正在同步(手动触发)——驱动"同步中"UI 并防重复点击 */
  syncing?: boolean
}

export interface FinancialMetricRecord {
  symbol?: string
  period_end: string
  announce_date?: string | null
  eps_basic?: number | null
  eps_diluted?: number | null
  bps?: number | null
  ocfps?: number | null
  roe?: number | null
  roe_diluted?: number | null
  roa?: number | null
  gross_margin?: number | null
  net_margin?: number | null
  debt_to_asset_ratio?: number | null
  revenue_yoy?: number | null
  net_income_yoy?: number | null
  operating_cash_to_revenue?: number | null
  inventory_turnover?: number | null
  [key: string]: any
}

export interface FinancialIncomeRecord {
  symbol?: string
  period_end: string
  announce_date?: string | null
  revenue?: number | null
  operating_cost?: number | null
  operating_profit?: number | null
  total_profit?: number | null
  net_income?: number | null
  net_income_attributable?: number | null
  basic_eps?: number | null
  diluted_eps?: number | null
  [key: string]: any
}

export interface FinancialBalanceSheetRecord {
  symbol?: string
  period_end: string
  announce_date?: string | null
  total_assets?: number | null
  total_current_assets?: number | null
  cash_and_equivalents?: number | null
  total_liabilities?: number | null
  total_equity?: number | null
  equity_attributable?: number | null
  [key: string]: any
}

export interface FinancialCashFlowRecord {
  symbol?: string
  period_end: string
  announce_date?: string | null
  net_operating_cash_flow?: number | null
  net_investing_cash_flow?: number | null
  net_financing_cash_flow?: number | null
  capex?: number | null
  net_cash_change?: number | null
  [key: string]: any
}

export interface FinancialSharesRecord {
  symbol?: string
  period_end: string
  announce_date?: string | null
  total_shares?: number | null
  float_shares?: number | null
  [key: string]: any
}

/** AI 财务分析历史报告 */
export interface AiFinancialReport {
  id: string
  symbol: string
  name: string
  focus: string
  content: string
  periods?: number
  summary?: string
  created_at: string
}

// ===== 个股分析 =====
export type LevelType = 'sr' | 'pivot' | 'extreme' | 'boll' | 'keltner_s' | 'keltner_m' | 'keltner_l' | 'atr_stop' | 'gap' | 'fib' | 'round' | 'livermore' | 'exit'

// [fork 增强] 今日总览(决策汇聚层)
/** [R179] 四档: fatal 无条件清仓 > high 该处理了 > mid 要盯着 > low 已发生过的事(监控触发) */
export interface TodayActionItem {
  kind: string
  severity: 'fatal' | 'high' | 'mid' | 'low'
  symbol: string
  name: string
  text: string
}
/** [fork 增强] R37 主线归属(候选票所属的今日主线, 不在主线内则字段缺席) */
export interface TodayMainlineTag {
  member: string; rank: number; limit_up_count: number; also: string[]
}
export interface TodayOpportunity {
  kind: string; symbol: string; name: string; text: string; score: number; why: string
  advice?: { fraction: number; text: string; why: string; plan?: string | null } | null
  intraday?: boolean
  mainline?: TodayMainlineTag | null
  /** [R40] 板块归属(沪主板/深主板/创业板/科创板/北交所) */
  board?: string
  /** [R47] 三档通道结论; 三档都在中部时为 null。与决策台「结论」列同一份 */
  verdict?: KeltnerVerdict | null
  /** [R123] 量比 —— 突破是不是真的(也是 AI 优选的核心判据, 摆成列好让用户自己核) */
  vol_ratio?: number | null
  /** [R123] 收盘价距关键点/触发价还差几个点; 负数 = 已越过 */
  gap_pct?: number | null
  /** [R158] 关键点/触发价本身(gap_pct 就是相对它算的); 界面上悬停显示 */
  pivot?: number | null

  // ===== [R134/R189] 评分: 四道硬门槛 + 质地 × 时机两轴 =====
  /** 两根轴(0~100)。**总分 = √(质地 × 时机)** —— 一边好一边差不许平均成中等。
   *  质地以月计变化(结构), 时机逐日变化(买点); 整根轴的因子全缺时为 null。 */
  axes?: { quality: number | null; timing: number | null }
  /** 每个因子的子分(0~100) —— 轴分说明"时机不行", 子分说明是量比还是位置 */
  factors?: Record<
    'template' | 'base' | 'rs' | 'state' | 'spread'
    | 'fresh' | 'pos' | 'vol_ratio' | 'turnover' | 'accel',
    number | null>
  /** 各轴实际覆盖到的因子权重占比 */
  coverage?: { quality: number; timing: number }
  /** 有因子缺席 → 总分是在剩下的因子上算的, 偏乐观, 界面必须说清楚 */
  partial?: boolean
  /** [R189] 趋势模板(Minervini 八条)的原始事实 —— 分数是结论, 这是依据 */
  template?: {
    passed: number; known: number; total: number; text: string
    criteria: { code: string; label: string; pass: boolean | null; detail: string }[]
  } | null
  /** [R189] 红绿节拍与磨底时长(trend_rhythm 的返回值) */
  rhythm?: TrendRhythm | null
  /** [R195] 量化波动通道的几何层 —— 分离度进质地轴、加速度进时机轴 */
  geo?: ChannelGeometry | null
  /** [R195] 位置 × 六态 × 在轨外天数 → 事件 */
  channel_event?: ChannelEvent | null
  /** [R200] 现在处在哪一段 + 该盯什么 */
  channel_phase?: ChannelPhase | null
  /** [R201] 今日名次(1 = 最好)与候选总数 —— 界面主显它们, 不再主显裸分 */
  rank?: number
  rank_total?: number
  /** [R201] 分位: 1.0 = 今天最好的那只, 0.0 = 最后一名 */
  pct_rank?: number
  /** [R220] 这个分数在台账历史分布里的百分位。入选门槛按它判;
   *  台账没攒够时为 null, 那时门槛整个失效。 */
  hist_pct?: number | null
  /** [R201] 置信系数 0~1 —— 因子读到了几成, 已经乘进 score 里 */
  confidence?: number
  /** [R201] 保底行: 没过把握分门槛, 是为了让页面不空才摆出来的 */
  below_bar?: boolean
  /** [R195/R197] 压缩持续天数、平均压缩度、在轨外连续天数 */
  runs?: ChannelRuns | null
  /** [R197] 频段能量分布 */
  energy?: BandEnergy | null
  /** 新鲜度来自哪一路: 六态信号 / 逼近触发价 / 都没有 */
  fresh_from?: 'signal' | 'near_breakout' | 'none'
  /** 命中的候选来源(可同时命中两路) */
  kinds?: string[]
  /** 信号第几天 */
  duration?: number | null
  /** 六态状态与中文名 */
  trend_state?: string | null
  trend_state_cn?: string | null
  /** Keltner 短期通道位置 0~1(0.5 = 恰好站在生命线 MA20 上) */
  channel_pct?: number | null
  /** 换手率 % */
  turnover?: number | null
  /** 近 20 日相对大盘(百分点) */
  rs_pct?: number | null
  close?: number | null
  /** 不参与打分的佐证: 主线/AI/历史胜率/通道结论/策略命中/龙虎榜 */
  notes?: TodayNote[]
  /** [R137] 盘中视图 —— 与 score/axes **完全并列, 一分不进评分**。
   *  把握分冻在收盘口径(盘中一动不动, 是稳定的决策基准), 盘中的变化摆这里。
   *  只在开着实时行情、且该标的拿到了实时行时才有。 */
  live?: TodayLive | null
  /** [R158] 出手时机: 今天动手 / 收盘再动 / 不动手 —— 一句结论, 不进评分不改名次 */
  action?: TodayAction | null
}

/** [R158] 出手时机结论。trigger = 结论围绕的那个关键点/触发价(有则给) */
export interface TodayAction {
  code: 'today' | 'after_close' | 'hold_off'
  label: string
  reason: string
  trigger?: number | null
}

/** [R159] 推送焦点名单: 持有 / 计划中 / 观察 三档, 用户可钉住或静音 */
/** held 持有 / plan 计划中 / band [R161] 短期贴·破上下轨 / watch 观察 */
export type FocusTier = 'held' | 'plan' | 'band' | 'watch'
export interface FocusItem {
  symbol: string; name: string
  tier: FocusTier
  /** 覆盖(钉住/静音)之后的有效档 —— 推送门看的是这个 */
  effective: FocusTier
  override?: 'pin' | 'mute' | null
  reason: string
  score?: number | null
  action?: string | null
}
export interface FocusView {
  focus_only: boolean
  as_of?: string | null
  generated_at?: string | null
  /** 快照是否在有效期内; 过期时推送门放行 */
  fresh: boolean
  counts: Record<FocusTier, number>
  labels: Record<string, string>
  items: FocusItem[]
}

/** [R137] 盘中盯盘数据。拿现价去比**昨天那条**通道与生命线 —— MA20 与通道边界
 *  都是慢变量, 这个近似给的是方向性预警, 不是结论(结论等收盘)。 */
export interface TodayLive {
  price: number
  change_pct?: number
  vol_ratio?: number
  /** 现价落在昨天那条短期通道里的位置; 与收盘的 channel_pct 并排看就知道今天往哪走 */
  channel_pct?: number
  /** 现价已跌回昨日 MA20 之下 —— 收盘定稿后会被生命线门槛挡掉 */
  below_lifeline?: boolean
  ma20?: number
}

/** [R134] 注记 —— 展示用的佐证, **一分不加一分不减**。tone 决定界面配色。 */
export interface TodayNote {
  key: 'ai' | 'mainline' | 'win' | 'verdict' | 'dragon' | string
  tone: 'good' | 'bad' | 'info'
  label: string
  text: string
}

/** [R134] 门槛漏斗 —— "今天 N 只候选被挡掉 M 只"本身就是市场状态的读数 */
export interface TodayGates {
  candidates: number
  passed: number
  blocked_total: number
  /** {门槛代码: 被这条挡了几只}; 各项之和会大于 blocked_total(一只可踩多条) */
  blocked: Record<string, number>
  labels: Record<string, { cn: string; why: string }>
  text: string
}

/**
 * [R43] 高抛/低吸压力 —— 由 Keltner 三档通道位置合成, 与决策台三列、
 * 个股分析图表、回测策略同一组口径。
 *
 * 短期档定方向(它是操作级别), 中期档定强弱(只放大不改向), 长期档仅供参考。
 */
export interface TodayHeat {
  side: 'high' | 'low'
  level: 'strong' | 'mild'
  /** 哪几档共振, 如"短期破上轨、中期也贴上轨" */
  text: string
  where: string
  bands_aligned: number
  /** [R44] 三档组合的结论; 与决策台「结论」列同一份 */
  verdict?: KeltnerVerdict | null
}

/** [R40] 板块过滤的可选项与展示顺序 —— 与后端 price_limits.BOARDS 一致 */
export const TODAY_BOARDS = ['沪主板', '深主板', '创业板', '科创板', '北交所'] as const
/** [fork 增强] R37 中观快照: 三层推导 大盘 → 主线 → 个股 里缺的那一层 */
export interface TodayMeso {
  amount: {
    total: number; text: string
    pct_rank: number | null; label: string | null; sample: number; date?: string
  } | null
  breadth: { up: number; down: number; date: string } | null
  mainline: {
    date: string; age_days: number; stale: boolean
    rows: {
      member: string; rank: number; score: number | null
      limit_up_count: number; max_boards: number; leader_symbol: string | null
    }[]
  } | null
  membership_note: string
}
/** [R121] 一条数字对账结果: AI 说的 vs 日K 里真实的 */
export interface TodayPickCheck {
  kind: '涨幅' | '量比' | '价位' | string
  said: number
  actual: number | number[] | null
  /** true=对得上 / false=对不上 / null=没数据可对 */
  ok: boolean | null
  fatal?: boolean
  note: string
}
export interface TodayPick {
  symbol: string
  reason: string
  name?: string
  /** [R121] 事实校验结论: 已核对 / 待查 / 存疑 / 驳回 */
  verdict?: '已核对' | '待查' | '存疑' | '驳回'
  verdict_note?: string
  checks?: TodayPickCheck[]
}
/** [R121] AI 优选的事实校验汇总 */
export interface TodayPickVerify {
  total: number; rejected: number; doubtful: number; clean: number; text: string
}
/** [R121] AI 优选历史命中率(纯事后统计, 不参与选股) */
export interface AiTrackRecord {
  detail: { symbol: string; name?: string; as_of: string; reason?: string
            t1: number | null; t3: number | null; t5: number | null }[]
  stats: Record<'t1' | 't3' | 't5', { n: number; win_rate: number | null; avg: number | null }>
  recorded_days: number
  caveat: string
}
/** [R133] 一段区间的表现: 胜率 / 平均收益 / 样本数 */
export interface LedgerStat { n: number; win_rate: number | null; avg: number | null }
export type LedgerStats = Record<'t1' | 't3' | 't5', LedgerStat>
/** [R133] 规则层把握分体检 —— 与 AI 命中率互补: 那个只看 AI 挑的几只(有选择
 *  偏差), 这个看完整候选池, 才回答得了"把握分本身有没有区分度" */
/** [R175] 一个标签维度(通道结论/六态趋势/主线归属/龙虎榜)下的各档表现。 */
export interface LedgerLabelDim {
  key: string
  label: string
  items: {
    value: string
    count: number
    recent_count: number
    stats: LedgerStats
    recent_stats: LedgerStats
    /** 全期与最近的背离; 两边样本都够才有值 —— 这是整栏唯一有信息量的数 */
    shift: { dir: 'up' | 'down' | 'flat'; delta: number; text: string } | null
  }[]
}

/** [R175] AI 把上面那张表念成的人话。连同当时那张表一起存, 好回看它准不准。 */
export interface PatternDigest {
  as_of: string
  text: string
  table?: unknown
  created_at?: string
}

export interface ScoreLedger {
  recorded_days: number
  total_rows: number
  evaluated_rows: number
  pending_symbols: number
  /** [R134] 当前打分口径版本; 换口径前的记录不进统计 */
  scoring_version?: number
  legacy_days?: number
  first_day: string | null
  last_day: string | null
  all: LedgerStats
  shown: LedgerStats
  buckets: { label: string; lo: number; hi: number; count: number; stats: LedgerStats }[]
  ranks: { label: string; cut: number; count: number; stats: LedgerStats }[]
  /** [R134] 维度归因: 高分组 / 中间 / 低分组 / 缺席 */
  factors: {
    key: string; label: string
    plus: { count: number; stats: LedgerStats }
    mid?: { count: number; stats: LedgerStats }
    minus: { count: number; stats: LedgerStats }
    none: { count: number; stats: LedgerStats }
  }[]
  baseline: { symbol?: string; name?: string; stats?: LedgerStats }
  monotonic: { ok: boolean | null; text: string }
  /** [R175] 回头看: 不参与打分的那批标签, 全期 vs 最近 */
  labels?: LedgerLabelDim[]
  /** 「最近」那一列覆盖多少个记录日 */
  recent_days?: number
  /** 一档至少要多少样本才给读数 */
  min_label_n?: number
  /** 已存档的 AI 提炼(可能是前一天的); 生成走单独的端点 */
  digest?: PatternDigest | null
  caveat: string
  /** 服务端拼好的可粘贴摘要(Markdown) —— 一键复制就能整段交出去做调参 */
  summary_md: string
}
/** [fork 增强] 缓存的 AI 导读·优选(刷新页面仍在) */
export interface TodayAiCache {
  as_of: string | null
  brief: string
  /** [R147] 生成这份结论时用户写的补充说明; 空 = 没写 */
  note?: string
  picks: TodayPick[]
  analyzed: number
  created_at: string
  source: 'manual' | 'scheduled'
}
export interface TodayAiSchedule { enabled: boolean; hour: number; minute: number }
export interface SignalAiSchedule {
  enabled: boolean; hour: number; minute: number
  scope: 'held' | 'watchlist'; gap_seconds: number
}

export interface TodayPrefs {
  min_hist_pct: number; max_show: number; max_single: number; target_vol: number; max_drawdown: number
  pyramid_probe: number; pyramid_confirm: number; pyramid_days: number
  /** [R40] 只看这几个板; 空 = 全看 */
  boards: string[]
  /** [R204] 参与打分的因子键; 空 = 全开(与 boards 同一个约定) */
  /** [R204] 因子目录 —— 只在 GET /prefs 与总览里给, 保存时不用回传。
   *  从后端权重表推出来的, 前端不写死一份免得漂。 */
}
export interface TodayHolding {
  symbol: string; name: string; close: number | null; cost: number | null; pnl_pct: number | null
  stage_cn: string | null; line: number | null; line_cn: string | null; distance_pct: number | null
  exit_triggered: boolean; trend_cn: string | null; trend_duration: number | null
  trend_side: string | null; signal: string | null
  stance: string; stance_why: string
  weight?: number | null
  /** [R43] 高抛/低吸压力; 短期档在通道内时为 null */
  heat?: TodayHeat | null
  /** [R43] 三档通道原始读数, 供悬停显示具体轨价 */
  bands?: KeltnerBands | null
  /** [R169] 成本是手填还是从「持仓提醒」页的批次派生 */
  cost_source?: 'manual' | 'lots' | null
  /** [R169] 该票在批次页登记了几笔 */
  lot_count?: number
  /** [R169] 最近一个未过期的批次到期日 (YYYY-MM-DD) */
  lot_remind_date?: string | null
}
export interface TodayPortfolio {
  count: number; avg_pnl: number | null; triggered: number; near_exit: number; bearish: number
  total_weight?: number | null; nav?: number | null; drawdown?: number | null; posture_cap?: number
}
export interface TodayOverview {
  as_of: string | null
  watchlist_total: number
  trend_total: number
  live?: boolean
  live_count?: number
  actions: TodayActionItem[]
  opportunities: TodayOpportunity[]
  opportunities_filtered: number
  /** [R220] 台账攒够样本了吗 —— 入选门槛按历史分位判, 没攒够时它整个失效。
   *  界面必须据此说明白, 而不是让人拖一个没反应的旋钮。 */
  hist_pct_ready?: boolean
  /** [R210] 机会区为空时的原因(候选池空 / 门槛全挡 / 板块过滤滤没了)。非空时为 null */
  opportunities_empty_why?: string | null
  /** [R134] 三道硬门槛的漏斗统计 */
  gates?: TodayGates | null
  prefs: TodayPrefs
  position_hint?: { posture_cap: number; max_single: number; target_vol: number }
  ai?: TodayAiCache | null
  weather: {
    bull: number; bear: number; new_bull: number; new_bear: number
    posture: string; posture_reason: string
    breadth_posture?: string
    market?: {
      mode: string; reason: string; benchmark_name: string | null; as_of: string | null
      pending: { mode: string; streak: number; need: number; raw_reason: string } | null
      metrics: { close?: number; ma50?: number; ma200?: number; momentum_12m?: number; ma200_rising?: boolean; ret_20d?: number }
    } | null
    market_breadth?: { date: string; up: number; down: number; capped: boolean } | null
  }
  meso?: TodayMeso | null
  holdings: TodayHolding[]
  portfolio?: TodayPortfolio | null
}

// [fork 增强] 持仓出场线(ATR 三阶段 + 生命线)
export interface ExitLine {
  stage: 'risk' | 'breakeven' | 'trail' | 'fatal' | 'lifeline'
  lifeline?: number | null
  stage_cn: string
  line_cn: string
  action: string
  line: number
  atr: number
  profit_atr: number
  highest_close: number | null
  k: number
  close: number
  distance_pct: number
  triggered: boolean
  as_of: string
  entry_date: string
  cost: number
}

// [fork 增强] 六态趋势(利弗莫尔 Market Key)
export type LivermoreState = 'UT' | 'NR' | 'SR' | 'SREA' | 'NREA' | 'DT'

/** [R42] 一档 Keltner 通道的读数。算不出来的档整个缺席, 不会给一个空壳。 */
export interface KeltnerBand {
  /** above=破上轨 near_upper=贴上轨 inside=通道内 near_lower=贴下轨 below=破下轨 */
  pos: 'above' | 'near_upper' | 'inside' | 'near_lower' | 'below'
  pos_cn: string
  hint: string
  upper: number
  lower: number
  /** 通道内相对位置: 0=贴下轨 1=贴上轨; 轨外会 <0 或 >1 */
  pct: number
  to_upper_atr: number | null
  to_lower_atr: number | null
  band_cn: string
}

/**
 * [R44] 三档组合的结论。短期在通道中部时为 null —— 那时这一列没有信息,
 * 不硬凑一句话。
 */
export interface KeltnerVerdict {
  code: string
  /** 4-6 字, 当徽标用 */
  title: string
  /** 一句话结论 */
  action: string
  /** 为什么 */
  detail: string
  side: 'high' | 'low'
  /** 界面配色: 偏卖/偏买/别动/别碰/先盯着 */
  tone: 'sell' | 'buy' | 'hold' | 'avoid' | 'watch'
  /** 排序权重, 越大越偏卖。由后端给 —— 界面不自己编一套顺序 */
  rank: number
  /** 哪几档共振, 如"短期破上轨、中期也贴上轨" */
  bands_text: string
  bands_aligned: number
}

/**
 * [R48] 逐日复盘 —— 决策台「趋势」「结论」两列点进去看的那份数据。
 *
 * 三样东西按同一条时间轴对齐: 六态状态、三档通道结论、涨停。与那两列
 * 同一个状态机、同一组公式、同一个阈值, 所以翻出来的历史能直接套回今天。
 */
export interface ReviewRow {
  date: string
  close: number
  /** 小数, 如 0.05 = 5% */
  change_pct: number | null
  limit_up: boolean
  limit_down: boolean
  /** 炸板: 最高触及涨停但收盘没封住 */
  broken_limit_up: boolean
  /** 第几个板; 非涨停日为 0 */
  limit_streak: number
  trend?: {
    state: LivermoreState; state_cn: string; state_en: string
    side: '多头' | '空头'
    /** 这个状态到当天已经走了第几天 */
    day: number
    /** 转折那天 —— 复盘最想找的就是这些 */
    flipped: boolean
  } | null
  /** 当天三档位置; 算不出来的档缺席 */
  bands: Partial<Record<'s' | 'm' | 'l', { pos: string; pos_cn: string }>>
  verdict?: KeltnerVerdict | null
  /** [R51] 这天之后 forward_days 的涨跌(小数); 最近几天还不知道结果, 为 null */
  fwd: number | null
}

/** 每种结论在这只票上出现过几次、之后 forward_days 走成什么样 */
export interface ReviewOutcome {
  code: string; title: string; tone: KeltnerVerdict['tone']
  /** [R177] 出现过几**段**(不是几天) —— 一段持续 8 天的状态算 1 次,
   *  按天算的话那 8 天的前瞻窗口互相重叠, n 会被撑大 */
  n: number
  /** 平均每段持续几天 */
  avg_days: number
  /** n 段里有几段已经够 N 日、知道结果了 */
  scored: number
  /** 之后 N 日平均涨跌(小数); 一段都没兑现时为 null */
  avg_fwd: number | null
  /** 其中收涨的段数。样本小, 后端刻意不折算成百分比胜率 */
  win: number
}

/** [R177] 六态各状态在这只票上的同类统计。与 ReviewOutcome 同形状, 少了通道那几个字段。 */
export interface ReviewTrendOutcome {
  key: string
  label: string
  n: number
  avg_days: number
  scored: number
  avg_fwd: number | null
  win: number
}

export interface StockReview {
  symbol: string
  error?: string
  days: number
  start: string | null
  end: string | null
  threshold: number
  threshold_source: string
  forward_days: number
  stats: {
    limit_ups: number; limit_downs: number; broken_limit_ups: number
    max_streak: number
    /** 涨停都出现在什么趋势状态下 */
    limit_up_states: { state_cn: string; n: number }[]
    /** [R191] 封板率 —— 冲了几次板、封住几次, 外加一句性格判断。
     *  冲板次数少于 3 次时为 null(那个比率没有意义)。 */
    seal?: { attempts: number; sealed: number; rate: number; text: string } | null
  }
  outcomes: ReviewOutcome[]
  /** [R177] 「趋势状态」那一栏的同类统计: 每种六态之后普遍怎么走 */
  trend_outcomes: ReviewTrendOutcome[]
  /** [R191] 多头侧 vs 空头侧的分离度 —— 「六态在这只票上哪一半有用」。
   *  这是整栏唯一的**结论**, 其余都是测量。 */
  side_edge?: {
    level: 'both' | 'defense' | 'offense' | 'flat' | 'inverted' | 'thin'
    label: string
    text: string
    spread: number | null
    bull: { episodes: number; avg_fwd: number | null; win: number }
    bear: { episodes: number; avg_fwd: number | null; win: number }
  } | null
  /** [R191] 当前这一段与它自己的历史对照 —— 「我现在在哪、盯哪个价」 */
  now?: {
    date: string; state: string; state_cn: string | null; side: string | null
    day: number
    /** 这只票上这个状态平均持续几天(不是预测, 只为回答"在这一段的前段还是后段") */
    avg_days: number | null
    phase: '前段' | '中段' | '后段' | null
    n: number; scored: number; avg_fwd: number | null; win: number
    flip_down: number | null; flip_up: number | null
    close: number
  } | null
  /** [R188] 红绿节拍与磨底时长 —— 「这只票磨底磨了多久」 */
  rhythm?: TrendRhythm | null
  /** [R198] 量化波动通道的几何层 —— 复盘是唯一有地方把它摊开的位置 */
  channel?: {
    geo: ChannelGeometry
    runs: ChannelRuns
    energy: BandEnergy | null
    event: ChannelEvent
    /** [R199] 阶段判定 —— 三个几何量单看都答不了「我该怎么办」, 合起来才回答
     *  「现在处在哪一段」。watch 是这一段该盯什么, 不是买卖指令。 */
    phase: ChannelPhase | null
    /** [R212] 一行一条: 名称 · 数值 · 这个数意味着什么。
     *  数值保留(能核对), 后面跟一句「所以呢」—— 只给数字看不懂, 只给状态词
     *  又得不到结论, 三样一起才成立。 */
    explain: { label: string; value: string; why: string }[]
  } | null
  /** [R199] 偏买档 vs 偏卖档的分离度 —— 「位置结论在这只票上灵不灵」。
   *  与趋势那栏的 side_edge 完全平行。 */
  verdict_edge?: {
    level: 'both' | 'offense' | 'defense' | 'flat' | 'inverted' | 'thin'
    label: string
    text: string
    spread: number | null
    buy: { episodes: number; avg_fwd: number | null; win: number }
    sell: { episodes: number; avg_fwd: number | null; win: number }
  } | null
  /** 新 → 旧 */
  rows: ReviewRow[]
}

/** 短期 MA20±2ATR / 中期 MA60±2.5ATR / 长期 MA120±3ATR */
/** [R178] 决策台「该动了」判定。纯规则层产出, AI 不参与 —— 它只决定顺序, 不做判断。 */
export interface Urgency {
  /** triggered 已触发 > near 逼近 > flip 刚变盘 > band 到轨 > idle 无事 */
  level: 'triggered' | 'near' | 'flip' | 'band' | 'idle'
  label: string
  /** 越小越急; 直接拿来排序, 前端不另编一套顺序 */
  order: number
  /** 促成这个档位的那个距离(绝对值, 小数); 同档内按它升序。无事档为 null。
   *  [R193] 已触发档给的是**已经破了多少**, 不再是写死的 0 */
  distance: number | null
  /** 为什么是这个档 —— 悬停显示, 用户得能追问"凭什么"。= what + action */
  reason: string
  /** [R193] 哪条线促成的: exit_broken / exit_near / flip_down_near /
   *  flip_up_near / flipped / band_up / band_down / none */
  kind?: string
  /** [R193] **这一列最要命的那一项**: 这一条是卖方向还是买方向。
   *  同样是「逼近」, 可能是"再跌一点就破止损"也可能是"再涨一点就转强" ——
   *  两个相反的动作, 不标方向就长得一模一样。 */
  side?: 'sell' | 'buy' | 'info'
  /** 「卖」/「买」/空 */
  side_cn?: string
  /** 哪条线、什么价、差多远 —— 一句能直接照着挂单的话 */
  what?: string
  /** 该干什么 */
  action?: string
}

/**
 * [R195] 量化波动通道的**几何补充层**。底层三档读数一个字没改, 这些是从
 * 已算好的上下轨反推出来的导出量(轨 = MA ± k×ATR 是恒等式)。
 */
export interface ChannelGeometry {
  atr: number
  /** 三条均线 */
  ma: { s: number; m: number; l: number }
  /** 价格偏离各档均线多少个 ATR。破轨门槛依次是 2 / 2.5 / 3 */
  d: { s: number; m: number; l: number }
  /** 三段平均速度(ATR/天): 近 10 天 / 10~30 天前 / 30~60 天前 */
  v: { v1: number; v2: number; v3: number }
  /** 二阶: 加速度。匀速时 a1 = 0 是恒等而非近似 */
  accel: {
    a1: number; a2: number
    /** 近 10 天因为加速多走(少走)了几个 ATR —— 比 ATR/天 好读 */
    gain_atr: number
    level: 'accel' | 'steady' | 'decel' | null
    level_cn: string
  }
  /**
   * [R203] 匀速基准对照 —— 加速度的**比值形式**。
   * 匀速时 d短 : d中 : d长 = 1 : 3.105 : 6.263 是精确成立的, 偏离这条线就是
   * 加速/减速。比 a1 好讲: 「短期 1.2 时中期该到 3.7, 实际 2.1」可以自己核对。
   * 短期偏离太小时分母趋近 0, 返回 null(不给假数)。
   */
  baseline: {
    expect_m: number; expect_l: number
    actual_m: number; actual_l: number
    ratio: number
    level: 'lead' | 'onpace' | 'lag'
    level_cn: string
    why: string
  } | null
  /** 压缩指数 = 三带交集 / 短带宽度 ∈ [0,1]。1 = 均线粘合, 0 = 已脱开 */
  compress: number | null
  compress_level: 'tight' | 'mid' | 'loose' | null
  /** 带符号的短长均线间距(ATR)。**打分用它不用压缩指数** —— 后者没有方向 */
  spread: number
  /** |spread| ≥ 5 ATR: 短带与长带没有任何共同价格区间 */
  torn: boolean
  /** |spread| ≤ 1 ATR: 短带完全包在长带里 */
  nested: boolean
  stack: 'bull' | 'bear' | 'mixed' | null
  /** 三档位置压成三字码, 如「上中下」—— 27 种组合表的行号 */
  combo: string | null
}

/**
 * [R195] 位置 × 方向 × 时间 → 一个明确的事件。
 *
 * 「穿过上轨算站稳还是突破还是主升浪」这个问题混着三个独立维度: 通道只回答
 * 位置, 六态回答方向, **在轨外连续几天**才回答确认。少一个都答不了。
 */
/**
 * [R200] 阶段 —— 「现在处在哪一段, 该盯什么」。
 *
 * 与 ChannelEvent 分工: 事件说的是**今天发生了什么**(冲出上沿了没、站稳没),
 * 阶段说的是**整体走到哪一段了**。用户要的指导性意义在 watch 这一行, 所以
 * 三个界面(决策台悬停 / 今日总览 / 复盘弹窗)都该给, 不能只有复盘有。
 */
export interface ChannelPhase {
  code: string
  cn: string
  why: string
  /** 这一段该盯什么。**不是买卖指令** —— 那是把握分与六态的事 */
  watch: string
  /** [R209] 走到哪一步了: 刚起步 / 走到中段 / 走了很长 / 走过头了。**不带数字** */
  maturity_cn: string
  /** [R209] 还有没有劲: 还在加速 / 速度平稳 / 正在放慢 */
  pace_cn: string
  /** [R223] 六态与这个阶段在说相反的话时才有值。
   *
   *  两边量的不是同一个东西 —— 六态看价格的高低点, 阶段看三条均线的中枢,
   *  而均线是滞后的。转折那一段它们必然对不上, 这个字段负责把它说出来,
   *  而不是让两个相反的标签上下一摞。 */
  gap?: { cn: string; why: string } | null
}

export interface ChannelEvent {
  code: string
  cn: string
  why: string
  /** false = 还没站稳。突破与站稳是两件事, 混在一起就是在鼓励追高 */
  confirmed: boolean
  /** 这一格组合底层结论说得不准时的补充(27 种里有 11 种) */
  combo_note?: { combo: string; title: string; detail: string }
}

/**
 * [R205] 「怎么办」—— 五套判定的收敛层。
 * level: exit 纪律已破 / act 今天就得动 / conflict 判定打架 / watch 盯着 /
 *        shape 形态提示 / idle 没事。order 越小越该先看。
 */
export interface Playbook {
  level: 'exit' | 'act' | 'conflict' | 'watch' | 'shape' | 'idle'
  label: string
  order: number
  tone: 'danger' | 'warn' | 'info' | 'muted'
  headline: string
  why: string
  price: number | null
  /** 互相矛盾的判定对。**任何档位都会带**, 不只是 conflict 档 */
  conflicts: string[]
}

/** [R203] 27 种组合速查表的一行。整份由后端从底层判定生成, 前端不写死。 */
export interface ComboTableRow {
  combo: string
  shape: string
  /** [R221] 这一格有多常见。27 行看着势均力敌, 实际四格占一多半、
   *  七格几乎不出现 —— 不标出来会把常态当警报。 */
  rarity?: string
  read: string
  verdict: { title: string; code: string; tone: KeltnerVerdict['tone']
             action: string; detail: string } | null
  note: { title: string; detail: string } | null
}

export interface KeltnerBands {
  s?: KeltnerBand
  m?: KeltnerBand
  l?: KeltnerBand
  verdict?: KeltnerVerdict | null
  /** [R195] 几何补充层 —— 速度/加速度/压缩/排列。底层三档未动, 这是从它反推的 */
  geo?: ChannelGeometry | null
  /** [R195] 历史序列导出量: 压缩持续天数(新的「磨底磨了多久」)与在轨外连续天数 */
  runs?: ChannelRuns | null
  /** [R197] 频段能量分布 —— 这只票的波动主要来自哪个周期 */
  energy?: BandEnergy | null
}

export interface ChannelRuns {
  /** 连续多少天三带交集 ≥ 80% —— **这是新的「磨底磨了多久」**, 按 ATR 归一化,
   *  取代原来「最高/最低收盘 ≤ 1.35」那个绝对幅度判据 */
  compress_days: number
  /** [R197] O 的时间积分 ÷ 窗口 = 这个季度的平均压缩度。与 compress_days 不同:
   *  中间脱开一天会把 compress_days 清零, 却只把均值拉低一点 */
  compress_avg?: number | null
  /** 连续多少天收盘在短期上轨之上。1 天 = 突破, ≥2 天 = 站稳 */
  above_run: number
  below_run: number
  box_high: number | null
  box_low: number | null
  box_range_atr: number | null
}

/**
 * [R197] 频段能量分布。三档通道本质上是一组带通滤波器, 这里量的是各频段的
 * 能量占比 —— **已扣掉匀速趋势基线**(不扣的话会恒定说"低频占优", 那是均线的
 * 定义不是这只票的特征)。[R217] 基准是**零漂移随机游走**而不是匀速直线 ——
 * 零假设是「这只票什么也没发生」, 无趋势时三份各 1/3, 偏离 1/3 才是信息。
 */
export interface BandEnergy {
  share: { s: number; m: number; l: number }
  rms: { s: number; m: number; l: number }
  dominant: 's' | 'm' | 'l'
  dominant_cn: string
  /** [R217] 最高那一段有多突出。**不是开关** —— dominant 永远有值,
   *  这个字段只说该给它多少信任。flat = 三段差不多。 */
  lead?: 'clear' | 'slight' | 'flat'
  lead_cn?: string
}

/** [R188] 红绿节拍 —— 反复进多头又跌出, 是蓄势还是反复失败。
 *
 *  **档位不是分数**: 这东西还没被台账验证过, 给分数就会有人想加进把握分。
 *  低点不抬高是否决项 —— 「同一位置撞五次没过去」次数最多, 却最该躲开。 */
export interface TrendRhythm {
  level: 'building' | 'choppy' | 'failing' | 'none'
  label: string
  cycles: number
  low_rising: boolean | null
  high_rising: boolean | null
  red_share_rising: boolean | null
  dip_shallower: boolean | null
  reason: string
  /** 磨底磨了多久 + 箱体上下沿(那就是突破价与破位价) */
  basing: {
    days: number
    high: number | null
    low: number | null
    range_pct: number | null
    since: string | null
    is_basing: boolean
  }
}

export interface TrendInfo {
  state: LivermoreState
  state_cn: string
  state_en: string
  action: string
  side: '多头' | '空头'
  duration: number
  since: string
  entered_from: LivermoreState | null
  entered_from_cn: string | null
  up_pivot: number | null
  dn_pivot: number | null
  /** [R29] 收盘跌破即转弱的价位。趋势途中 up_pivot 退化成本轮最高收盘价, 这条才前瞻 */
  flip_down?: number | null
  /** [R29] 收盘站上即转强的价位 */
  flip_up?: number | null
  /** [R178] 离翻转还有多远。口径与出场线 distance_pct 一致: (线−现价)/现价。
   *  价位回答"到哪儿", 距离才回答"还有多急" —— 买点侧原来缺的就是这个数。 */
  flip_down_distance_pct?: number | null
  flip_up_distance_pct?: number | null
  /** [R188] 红绿节拍与磨底时长。零成本算出来的 —— 六态 compute 已经跑完,
   *  steps 就在手上, 原来用完即弃。 */
  rhythm?: TrendRhythm | null
  /** [R29] 本轮高/低水位收盘价(上关键点在趋势态下就等于 leg_high) */
  leg_high?: number | null
  leg_low?: number | null
  close: number
  as_of: string
  signal: '转多' | '转空' | '回升' | '回撤' | null
  signal_desc: string | null
  threshold: number
  threshold_source: 'override' | 'default'
  window_days: number
  ret_20d?: number | null
  /** [R18] 实时价参与了判定 → 盘中临时口径, 收盘确认为准 */
  intraday?: boolean
  /** [R30] 'closing' = 上面的价位一律按已收盘日线算(盘中也不含实时价, PRD §7.5) */
  price_basis?: 'closing'
  /** [R30] 收盘口径下的状态(与盘中临时状态对照用) */
  closing_state?: LivermoreState | null
  closing_as_of?: string | null
}

export interface TrendDetail extends TrendInfo {
  symbol: string
  segments?: { side: 'bull' | 'bear'; start_date: string; end_date: string }[]
  error?: string
}

export interface TrendBacktestRow {
  threshold: number
  flips: number
  seg_count: number
  bull_segs: number
  false_rate: number | null
  avg_seg_days: number
  strategy_return: number
  buyhold_return: number
  excess: number
  first_half: number
  second_half: number
}

export interface TrendBacktestResult {
  symbol: string
  window_days: number
  from: string
  to: string
  grid: TrendBacktestRow[]
  rule_suggestion: { threshold: number; reason: string; sample_insufficient: boolean }
  current_threshold: number
  current_source: 'override' | 'default'
  ai: { threshold: number; confidence: number; reason: string } | null
  ai_error?: string
  error?: string
}

export interface PriceLevel {
  value: number
  label: string
  type: LevelType
  side: 'resistance' | 'support' | 'neutral'
  strength?: 'strong' | 'medium' | 'weak'
  /** 档位(仅 pivot 有):0=P, 1=R1/S1, 2=R2/S2, 3=R3/S3。前端按"显示到第几档"过滤。 */
  rank?: number
}

/** 带状曲线指标(布林带/Keltner/ATR)的每日时间序列,与 dates 对齐。 */
export interface LevelSeries {
  boll?: { upper: (number | null)[]; lower: (number | null)[]; mid?: (number | null)[] }
  keltner_s?: { upper: (number | null)[]; lower: (number | null)[] }
  keltner_m?: { upper: (number | null)[]; lower: (number | null)[] }
  keltner_l?: { upper: (number | null)[]; lower: (number | null)[] }
  atr?: { stop_loss: (number | null)[]; take_profit: (number | null)[] }
}

export interface StockLevels {
  levels: Record<LevelType, PriceLevel[]>
  close: number | null
  summary: string
  symbol: string
  /** dates 与 series 对齐;前端按自身 rows 的日期映射,缺失填 null */
  dates?: string[]
  series?: LevelSeries
}

export interface AiStockReport {
  id: string
  symbol: string
  name: string
  focus: string
  content: string
  summary?: string
  close?: number | null
  levels?: Record<LevelType, PriceLevel[]>
  created_at: string
}

// ===== Kline =====
export interface MinuteKlineRow {
  datetime: string
  /** 分钟开盘价; 部分数据源(stock-sdk 历史日)无真实分钟 open, 为 null */
  open: number | null
  high: number
  low: number
  close: number
  volume: number
  amount: number | null
}

export interface MinuteKlineSession {
  date: string
  prev_close: number | null
  rows: MinuteKlineRow[]
}

export interface PriceLimitInfo {
  rate: number
  limit_up: number | null
  limit_down: number | null
  source: 'rule' | 'instrument'
}

export interface KlineRow {
  symbol?: string
  date: string
  open: number
  high: number
  low: number
  close: number
  volume?: number
  change_pct?: number
  ma5?: number | null
  ma20?: number | null
  ma60?: number | null
  macd_dif?: number | null
  macd_dea?: number | null
  macd_hist?: number | null
  rsi_14?: number | null
  vol_ratio_5d?: number | null
  [key: string]: any
}

export interface KlineDailyResponse {
  symbol: string
  name?: string
  stock_info?: { name?: string; total_shares?: number; float_shares?: number; ext?: Record<string, unknown> }
  rows: KlineRow[]
  source?: string
}

export interface KlineDailyLatestResponse {
  symbol: string
  row: KlineRow | null
  source: 'live' | 'none'
}

// ===== Watchlist =====
export interface WatchlistEntry {
  symbol: string
  added_at: string
  note?: string
  name?: string | null
  /** 所属分组 id 列表 (同一标的可属于多个分组; 空数组=未分组) */
  group_ids?: string[]
}

export type WatchlistGroupColor =
  | 'sky'
  | 'blue'
  | 'indigo'
  | 'violet'
  | 'fuchsia'
  | 'rose'
  | 'orange'
  | 'amber'
  | 'lime'
  | 'emerald'
  | 'teal'
  | 'cyan'

export interface WatchlistGroup {
  id: string
  name: string
  color: WatchlistGroupColor
}

export interface WatchlistImportCandidate {
  code: string
  symbol: string | null
  name: string | null
  matched: boolean
  already_in_watchlist: boolean
}

export interface WatchlistImportResult {
  provider: string
  codes: string[]
  candidates: WatchlistImportCandidate[]
  matched_count: number
  unmatched_count: number
}

/**
 * [fork 增强 R169] 标的级持仓视图 —— 决策台手填的仓位标记 ⊕ 上游「持仓提醒」页的批次登记。
 *
 * 两者是同一件事的两个口径: 批次是**每笔买入**(成本/数量/到期提醒), 这里是**每只票**
 * (持有与否/成本/占总资金 %)。唯一重合的字段是成本价, 所以后端在读侧合并:
 * 手填永远优先, 没手填时用批次的数量加权平均补上。写仍只落 positions.json。
 */
export interface EffectivePosition {
  held: boolean
  /** 生效成本: 手填优先, 没填则取批次加权平均 */
  cost: number | null
  /** 仓位比例(占总资金 %) —— 只能手填, 批次不知道总资金 */
  weight?: number | null
  updated_at?: string
  /** 'manual' 手填 | 'lots' 批次派生 | null 没有成本 */
  cost_source?: 'manual' | 'lots' | null
  /** 批次加权平均成本(手填优先时也带出来, 供并排显示) */
  lot_cost?: number | null
  /** 手填相对批次均价的偏离 %, 两者都有时才给 */
  cost_drift_pct?: number | null
  lot_count?: number
  lot_qty?: number
}

export interface Quote {
  symbol: string
  price?: number
  pct?: number
  close?: number
  change_pct?: number
  [key: string]: any
}

export interface IndexInstrument {
  symbol: string
  name?: string | null
  code?: string | null
  asset_type?: 'index'
  [key: string]: any
}

export interface IndexQuote {
  symbol: string
  name?: string | null
  last_price?: number | null
  close?: number | null
  prev_close?: number | null
  change_pct?: number | null
  change_amount?: number | null
  open?: number | null
  high?: number | null
  low?: number | null
  volume?: number | null
  amount?: number | null
  timestamp?: number | null
  [key: string]: any
}

// ===== Screener =====
export interface ScreenerStrategy {
  id: string
  name: string
  description: string
  source?: string
  /** 支持的周期, 如 ['1d'] / ['1m'] (分钟策略) */
  timeframes?: string[]
}

export interface StrategyLoadError {
  file: string
  error: string
}

export interface ScreenerResult {
  as_of: string
  strategy: string | null
  rows: any[]
  total: number
  elapsed_ms: number
}

export interface ScreenerResultSummary {
  total: number
  as_of: string
  /** 渐进式 run_all 写入的计算时间戳 (Unix ms); 监控实时叠加等来源无此字段 */
  computed_at?: number | null
}

export interface ScreenerCachedSummary {
  as_of: string | null
  results: Record<string, ScreenerResultSummary>
  today_ever_counts: Record<string, number>
  updated_at: number | null
}

/** run_all 渐进式返回: 快策略已算完, 慢策略后台继续算 */
export interface ScreenerRunAllSummary {
  as_of: string | null
  results: Record<string, ScreenerResultSummary>
  /** 尚未算完的策略 (后台继续, 逐个写入缓存) */
  pending?: string[]
  /** 全部算完时为 true */
  complete?: boolean
  /** 后台执行出错时的错误信息 (部分结果仍会返回) */
  error?: string | null
  /** 本次执行起点 (Unix ms, 后端时钟), 用于判断缓存结果是否属于本轮 */
  started_at?: number | null
}

export interface ScreenerCachedResult {
  result: ScreenerResult | null
  today_ever_rows: Record<string, any> | null
  strategy_ids_by_symbol: Record<string, string[]>
  updated_at: number | null
}

export interface MarketSnapshotRow {
  symbol: string
  name?: string | null
  close?: number | null
  change_pct?: number | null
  amount?: number | null
  volume?: number | null
  turnover_rate?: number | null
  vol_ratio_5d?: number | null
  total_shares?: number | null
  float_shares?: number | null
  market_cap?: number | null
  float_market_cap?: number | null
  consecutive_limit_ups?: number | null
  [key: string]: any
}

export interface OverviewDimensionRankItem {
  name: string
  count: number
  avg_pct: number
  up_count: number
  down_count: number
  amount: number
  /** 该维度组首个命中的扩展字段 "configId.field" (成分股弹窗直连; 无扩展源时缺失) */
  source_field?: string | null
  leader?: {
    symbol?: string | null
    name?: string | null
    change_pct?: number | null
  } | null
}

export interface OverviewMarket {
  as_of: string | null
  quote_status: {
    enabled?: boolean
    running?: boolean
    quote_age_ms?: number | null
    is_trading_hours?: boolean
    [key: string]: any
  }
  indices: IndexQuote[]
  breadth: {
    total: number
    up: number
    down: number
    flat: number
    up_pct: number
    down_pct: number
    avg_pct?: number | null
    median_pct?: number | null
    strong_up?: number
    strong_down?: number
  }
  amount: { total: number; avg: number }
  boards: { board: string; count: number; up: number; down: number; up_pct: number; amount: number }[]
  limit: { limit_up: number; broken: number; failed: number; limit_down: number; max_boards: number; seal_rate?: number; tiers: { boards: number; count: number; stocks?: { symbol: string; name?: string; amount?: number }[] }[]; sealed_ready?: boolean; fake_up?: number; fake_down?: number }
  distribution: { label: string; count: number; pct: number }[]
  trend: { above_ma5: number; above_ma20: number; above_ma60: number; above_ma5_pct: number; above_ma20_pct: number; above_ma60_pct: number; new_high: number; new_low: number }
  activity: { avg_turnover: number; high_turnover: number; high_vol_ratio: number; vol_ratio: number }
  radar: { key: string; label: string; value: number }[]
  emotion: { score: number; label: string }
  top_gainers: MarketSnapshotRow[]
  top_losers: MarketSnapshotRow[]
  turnover_leaders: MarketSnapshotRow[]
  active_leaders: MarketSnapshotRow[]
  concept_rank: { leading: OverviewDimensionRankItem[]; lagging: OverviewDimensionRankItem[] }
  industry_rank: { leading: OverviewDimensionRankItem[]; lagging: OverviewDimensionRankItem[] }
}

// ===== 概念涨幅轮动矩阵 =====
// dates: 日期字符串列表(最新在最前); columns: {日期: [[概念名, 涨幅小数], ...]} 每列各自降序
export interface RpsRotationData {
  dates: string[]
  columns: Record<string, [string, number][]>
  concept_count: number
}

// ===== 市场环境(Regime) =====
export type RegimeState = 'strong' | 'lean_strong' | 'range' | 'lean_weak' | 'weak'

export const REGIME_STATE_LABELS: Record<RegimeState, string> = {
  strong: '强势',
  lean_strong: '偏强',
  range: '震荡',
  lean_weak: '偏弱',
  weak: '弱势',
}

export const REGIME_STATE_COLORS: Record<RegimeState, string> = {
  strong: '#ef4444',      // 红(强)
  lean_strong: '#f97316', // 橙
  range: '#6b7280',       // 灰
  lean_weak: '#3b82f6',   // 蓝
  weak: '#10b981',        // 绿(弱)
}

// [fork 增强] 盘中实时阶段(付费全市场档专属; 免费档 available=false)
export interface RegimePhaseLive {
  available: boolean
  reason?: string
  as_of?: string
  intraday?: boolean
  phase?: string | null
  phase_label?: string | null
  metrics?: {
    first_board: number; ge2_count: number; max_consecutive: number
    seal_rate: number | null; promo_rate: number | null
  }
}

export interface RegimeRow {
  date: string
  state: RegimeState
  score: number
  limit_up: number
  limit_down: number
  broken_limit: number
  max_consecutive: number
  seal_rate: number
  up_count: number
  down_count: number
  up_ratio: number
  index_pct: number
  above_ma20_pct: number
  total_amount: number
  avg_turnover: number
  // 4 个子维度分(0-100, 重算后才有; 旧数据可能缺) — 综合分的加权来源
  avg_pct?: number
  median_pct?: number
  strong_up_pct?: number
  strong_down_pct?: number
  profit_score?: number
  speculation_score?: number
  resilience_score?: number
  trend_score?: number
  // 情绪周期阶段与梯队指标(重算后才有; 旧数据可能缺)
  phase?: MarketPhase | null
  first_board?: number | null
  ge2_count?: number | null
  ge3_count?: number | null
  ge5_count?: number | null
  ladder_completeness?: number | null
  promo_rate?: number | null
  promo_pool?: number | null
}

export interface RegimeHistory {
  rows: RegimeRow[]
  total: number
}

export interface RegimeStateItem {
  state: RegimeState
  label: string
  count: number
  pct: number
}

export interface RegimeStates {
  distribution: RegimeStateItem[]
  days: number
}

export interface RegimeCoverage {
  rows: number
  earliest_date: string | null
  latest_date: string | null
}

// ── 市场阶段(情绪周期) 与 主线 ──
export type MarketPhase = 'ice' | 'ignite' | 'rally' | 'climax' | 'ebb' | 'repair'

export const MARKET_PHASE_LABELS: Record<MarketPhase, string> = {
  ice: '冰点',
  ignite: '启动',
  rally: '主升',
  climax: '高潮',
  ebb: '退潮',
  repair: '修复',
}

export const MARKET_PHASE_COLORS: Record<MarketPhase, string> = {
  ice: '#38bdf8',     // 天蓝(冻结)
  ignite: '#f59e0b',  // 琥珀(升温)
  rally: '#ef4444',   // 红(主升)
  climax: '#d946ef',  // 品红(极端)
  ebb: '#14b8a6',     // 青(退潮)
  repair: '#94a3b8',  // 灰(修复)
}

export const MARKET_PHASE_ORDER: MarketPhase[] = ['ice', 'ignite', 'rally', 'climax', 'ebb', 'repair']

export interface MainlineMemberStat {
  member: string
  top5_days: number
  score_sum: number
  max_boards: number
  leader_symbol: string
}

export interface PhaseSegment {
  phase: MarketPhase
  label: string
  start: string
  end: string
  days: number
  avg_height: number
  avg_first_board: number
  avg_ge2: number
  avg_promo: number | null
  avg_seal_rate: number
  top_mainlines: MainlineMemberStat[]
}

export interface PhaseSegments {
  segments: PhaseSegment[]
  total: number
}

export interface MainlineRow {
  date: string
  kind: string
  member: string
  limit_up_count: number
  ge2_count: number
  max_boards: number
  boards_sum: number
  rungs_filled: number
  leader_symbol: string
  score: number
  rank: number
}

export interface MainlineLeader {
  member: string
  top1_days: number
  avg_score: number
  max_boards: number
}

export interface MainlineFilter {
  min_members: number
  max_members: number
  blacklist: string[]
  exclude_st: boolean
}

export interface MainlineResult {
  rows: MainlineRow[]
  leaders: MainlineLeader[]
  membership_note: string
  filter: MainlineFilter
}

// ===== [fork 增强] R28 板块跷跷板 =====
export interface SeesawPair {
  pair: string
  a: string
  b: string
  score: number
  corr: number
  flips: number
  active_a: number
  active_b: number
  recent_a: number
  recent_b: number
  leader: string
  lead_days: number
  hint: string
  series_a?: number[]
  series_b?: number[]
}
export interface SeesawAi {
  summary: string
  picks: { pair: string; verdict: string; leader: string; note: string }[]
}
export interface SeesawEntry {
  as_of: string | null
  kind: string
  pairs: SeesawPair[]
  ai: SeesawAi | null
  created_at: string
  source: string
}
export interface SeesawResult {
  as_of?: string | null
  kind?: string
  window?: number
  dates?: string[]
  pairs: SeesawPair[]
  ai?: SeesawAi
  latest?: SeesawEntry | null
  history?: SeesawEntry[]
  error?: string
  created_at?: string
  source?: string
}


// ===== [fork 增强] R31 AI 自动挖掘 =====
/** AI 每轮的判断。satisfied=true 时循环收工, 由人工决定要不要发布。 */
export interface AutopilotPlan {
  satisfied: boolean
  verdict: string
  pick: string | null
  reason: string | null
  next: {
    factor_names: string[]
    budget_profile: 'balanced' | 'strict'
    max_combination_factors: number
    beam_width: number
    correlation_threshold: number
  } | null
  error?: string
}
export interface AutopilotIteration {
  iteration: number
  run_id: string | null
  status: string
  config: Record<string, unknown>
  candidates: Record<string, unknown>[]
  ai: AutopilotPlan | null
  created_at: string
  /** [R38] 正在跑的那一轮才有: run 的实时进度, 用来区分"排队/在算/卡住" */
  live?: {
    status: MiningRunStatus
    progress: MiningRunProgress | null
    queued_at: string | null
    started_at: string | null
    updated_at: string | null
    error: string | null
  } | null
}
// ===== [fork 增强] R39 研究工作流 =====
// 挖掘/回测自己一直跑, 跑到达标为止。一次"重开"= 一个完整会话(挖掘)或一串轮次(回测),
// 用满轮数还没达标就换一批配置再开一次。
export type WorkflowKind = 'mining' | 'backtest'
export type WorkflowStatus = 'running' | 'satisfied' | 'exhausted' | 'stopped' | 'failed'

export interface WorkflowBest {
  passed: boolean
  sharpe: number | null
  label: string
  kind: WorkflowKind
  run_id?: string | null
  signature?: string | null
  session_id?: string | null
  config?: Record<string, unknown>
  detail?: Record<string, unknown>
}

export interface WorkflowAttempt {
  attempt: number | null
  outcome: string
  started_at: string | null
  ended_at: string
  rounds?: number
  session_id?: string
  message?: string
  conclusion?: string
}

// [fork 增强] R110 竞价一进二
export interface AuctionScanItem {
  symbol: string
  name: string
  score: number
  auction_pct: number
  auction_price?: number | null
  auction_volume?: number | null
  prev_volume?: number | null
  breakdown: { dim: string; score: number; max: number; note: string; proxy?: boolean }[]
}
export interface AuctionScanPayload {
  as_of: string | null
  candidates: AuctionScanItem[]
  total_first_boards?: number
  matched?: number
  quality_proxy?: boolean
  cached?: boolean
  dates?: string[]
  hint?: string
  error?: string
}

// [fork 增强] R99 全球指数实时
export interface GlobalIndexQuote {
  key: string
  name: string
  last: number
  change?: number | null
  change_pct?: number | null   // 小数制
  updated_at?: number          // epoch 秒 —— 我们**抓取**的时刻, 不是行情的时刻
  /** [R112] 该市场此刻是否在交易时段(北京时间) —— 休市时值静止是正常的 */
  trading?: boolean
  /** [R148] 行情**自己**说的时刻(epoch 秒); 这家不给就是 null */
  quote_at?: number | null
  /** [R148] 行情多久没动了(秒); null = 这家不给时刻, 说不出来 */
  quote_age_s?: number | null
  /** [R148] 盘中却半天没更新 —— 这个数已经不能当实时看了 */
  stale?: boolean
  source?: string
  source_code?: string
}

// [fork 增强] R93 使用观察笔记
export interface UsageNote {
  id: string
  content: string
  /** ''=随手记 / pending=待验证 / verified=已验证 / rejected=不成立 */
  status?: '' | 'pending' | 'verified' | 'rejected'
  pinned?: boolean
  /** [R180] 消息形态; 老数据没有这个字段, 后端读时补 text */
  kind?: 'text' | 'image' | 'file'
  /** [R180] 凝练成功后 path 会被去掉、原件删除 —— 只保存凝练不保存图片。
   *  留 name/size 是为了知道这条要点是从哪个文件来的。 */
  attachment?: { path?: string; name: string; size: number } | null
  /** AI 对这一条的凝练; 空 = 还没凝练过 */
  digest?: string
  digest_at?: string | null
  /** [R181] 时效档 —— 与 status(成立了吗)正交的第二个轴: 这条多久有效。
   *  news 时效(几天内有效, 影响今天买不买) /
   *  thesis 埋伏(业绩等逻辑, 影响持有耐心, 到 due_at 回来核对) /
   *  rule 规律(方法论, 不过期) */
  horizon?: 'news' | 'thesis' | 'rule'
  /** 埋伏的兑现检查点; 只有 thesis 有 */
  due_at?: string | null
  created_at: string
  updated_at: string
}

/** [R180] 一大段总的 —— 综合全部条目, 之后每次 AI 决策都会带上它 */
export interface NewsDeskSummary {
  text: string
  as_of: string
  item_count: number
  item_ids?: string[]
}


// ===== 大盘复盘 =====
export interface AiReviewReport {
  id: string
  as_of: string
  focus?: string
  content: string
  summary?: string
  emotion_score?: number | null
  emotion_label?: string
  /** 生成时用的复盘模式(today/continuity/week); 旧存档无此字段 */
  mode?: 'today' | 'continuity' | 'week'
  created_at: string
}

// ===== 龙虎榜 (fuyao 专有, 复盘页) =====
export interface DragonTigerStockItem {
  thscode: string
  ticker?: string | null
  name?: string | null
  change?: number | null      // 当日涨跌幅 (小数制)
  net_value?: number | null   // 龙虎榜净买入 (元)
  net_rate?: number | null    // 净买占比 (小数制)
  buy_value?: number | null   // 买入额 (元)
  sell_value?: number | null  // 卖出额 (元)
  hot_rank?: number | null    // 同花顺人气排名 (小=靠前)
  range_days?: number | null  // 1=当日榜 3=3日榜
  hot_money_net_value?: number | null
  hot_money_item_net_value?: number | null  // 游资榜 rows 专用: 该席位在该股的净买入
  org_net_value?: number | null
  org_net_rate?: number | null
  org_buy_num?: number | null
  org_sell_num?: number | null
  concept_list?: { name?: string }[] | null
}

export interface DragonTigerHotMoney {
  name?: string | null
  buying?: number | null                    // 席位合计净买入 (元)
  rows?: DragonTigerStockItem[] | null      // 关联股票 (字段同 stock item)
}

export interface DragonTigerPayload {
  state: 'ok' | 'fallback_prev' | 'source_unavailable' | 'no_data'
  requested_date?: string | null
  trade_date?: string | null
  message?: string
  all?: { trade_date?: string | null; stock_count?: number | null; count?: number | null; stock_items?: DragonTigerStockItem[] }
  org?: { trade_date?: string | null; stock_count?: number | null; count?: number | null; stock_items?: DragonTigerStockItem[] }
  hot_money?: { trade_date?: string | null; count?: number | null; hot_money_items?: DragonTigerHotMoney[] }
}

// ===== 盘前风向标 (fuyao 专有, 复盘页) =====
export interface AuctionBenchmarkItem {
  thscode: string
  ticker?: string | null
  name?: string | null
  auction_pct?: number | null   // 竞价涨跌幅 (百分数原值, 如 9.97 = +9.97%)
  tags?: string[]               // 同花顺概念标签
  day0_oc?: number | null       // 当日开盘买→收盘卖 (小数制, 服务端由本地日K enrich)
  day0_pct?: number | null      // 当日全天涨跌幅 (小数制)
  d1_pct?: number | null        // 次日收盘→收盘 (小数制; 最新交易日无次日为 null)
}

export interface AuctionBenchmarkPayload {
  state: 'ok' | 'fallback_prev' | 'source_unavailable' | 'no_data'
  requested_date?: string | null
  trade_date?: string | null
  count?: number
  message?: string
  items?: AuctionBenchmarkItem[]
}

// ===== Strategy Engine =====
/** select 参数的单个选项：可为纯字符串, 或 AI/自定义策略常用的 {label, value} 对象。 */
export type StrategyParamOption = string | { label: string; value: string | number }

/** 取选项的实际取值 (提交给后端 / 作为 <option value>)。 */
export function paramOptionValue(o: StrategyParamOption): string | number {
  return o != null && typeof o === 'object' ? o.value : o
}

/** 取选项的显示文案 (渲染为 <option> 子节点, 必须是字符串以免 React 直接渲染对象报错)。 */
export function paramOptionLabel(o: StrategyParamOption): string {
  return o != null && typeof o === 'object' ? o.label : String(o)
}

export interface StrategyParamDef {
  id: string
  label: string
  type: 'float' | 'int' | 'select' | 'bool'
  default: number | string | boolean
  min?: number
  max?: number
  step?: number
  // 兼容两种形态: string[] 或 [{label, value}]（后者是 AI 策略生成器的约定格式）
  options?: StrategyParamOption[]
}

export interface CompositeChildInfo {
  id: string
  name: string
  source: string
  weight: number
}

export interface StrategyDetail {
  id: string
  name: string
  description: string
  tags: string[]
  source: 'builtin' | 'custom' | 'ai' | 'composite'
  research_only?: boolean
  execution_backend: 'polars_expr' | 'matrix_native' | 'python_history_legacy' | 'composite' | 'minute_filter'
  asset_types: string[]
  timeframes: string[]
  version: string
  basic_filter: Record<string, any>
  params: StrategyParamDef[]
  params_defaults: Record<string, any>
  scoring: Record<string, number>
  scoring_directions: Record<string, ScoringDirection>
  entry_signals: string[]
  exit_signals: string[]
  minute_exit_trigger_supported_signals: string[]
  stop_loss: number | null
  take_profit: number | null
  trailing_stop: number | null
  trailing_take_profit_activate: number | null
  trailing_take_profit_drawdown: number | null
  max_hold_days: number | null
  display_limit?: number
  order_by: string
  descending: boolean
  limit: number
  // 叠加策略(composite)专属: 子策略列表与合并模式。非 composite 时为 null。
  composite_children?: CompositeChildInfo[] | null
}

export type ScoringDirection = 'high' | 'low'

export interface StrategyBuildResult {
  code: string
  meta: Record<string, any>
  valid: boolean
  error: string | null
}

export type StrategyBuildStreamEvent =
  | { type: 'meta'; strategy_id?: string; step?: number }
  | { type: 'delta'; content: string }
  | ({ type: 'result' } & StrategyBuildResult)
  | { type: 'error'; message: string }

export interface StrategyCodeSaveResult {
  ok: boolean
  strategy_id: string
  source: 'ai' | 'custom' | 'composite'
  path: string
  meta: Record<string, any>
  research_only?: boolean
}

// ===== Custom Signals (自定义信号) =====
export interface CustomSignalCondition {
  left: string     // 字段名
  op: string       // > >= < <= == !=
  right: string    // "field:xxx" 或数字字符串
  leftDays?: number   // 左字段取几日前 (0=当日, 默认)
  rightDays?: number  // 右字段取几日前 (仅 right 为字段时有意义)
}

export interface CustomSignal {
  id: string
  name: string
  kind: 'entry' | 'exit' | 'both'
  conditions: CustomSignalCondition[]
  enabled: boolean
}

export interface CustomSignalFieldGroup {
  key: string
  label: string
  fields: { key: string; label: string }[]
}

export interface CustomSignalOptions {
  fields: { key: string; label: string }[]
  groups?: CustomSignalFieldGroup[]
  maxDays?: number
  operators: string[]
  /** string 扩展字段 (概念/行业归属): 这些字段用 stringOperators + 字符串右值 */
  stringFields?: string[]
  stringOperators?: string[]
  kinds: { key: string; label: string }[]
}

export interface CustomSignalAIGenerateResult {
  name: string
  conditions: CustomSignalCondition[]
}

// ===== Monitor (监控规则 + 触发记录) =====
export interface MonitorCondition {
  field: string
  op: string              // truth | > >= < <= == !=
  value?: number | null   // op 非 truth 时必填
}

export type StrategyNotifyEvent = 'buy_signal' | 'sell_signal' | 'pool_entry' | 'pool_exit'

export type SectorKind = 'index' | 'concept' | 'industry'

export interface SectorMonitorTarget {
  key: string
  kind: SectorKind
  name: string
  symbol?: string
  source_id?: string
  field?: string
  source_field?: string
  value?: string
  level?: number | null
  available: boolean
  member_count: number
}

export interface AbnormalWindowInfo {
  /** 实时偏离值 (小数) */
  value: number
  /** 该窗口阈值 (小数) — 后端已按偏离方向取对应侧 (严重异动负向更严) */
  threshold: number
  /** 接近度 |value|/threshold */
  closeness: number
}

export type AbnormalStatus = 'triggered' | 'edge' | 'watch'

export interface AbnormalRow {
  symbol: string
  name: string | null
  board: string
  st: boolean
  close: number | null
  rt_pct: number | null
  windows: Record<string, AbnormalWindowInfo>
  max_closeness: number
  status: AbnormalStatus
}

export interface AbnormalOverview {
  asof: number
  cache_date: string | null
  bench_rt_pct: number
  includes_today: boolean
  rules: Array<{
    board: string
    st: boolean
    /** 各窗口双侧阈值 {up: 正向, down: 负向} (小数) */
    thresholds: Record<string, { up: number; down: number }>
    note: string
  }>
  counts: { triggered: number; edge: number; watch: number }
  rows: AbnormalRow[]
}

// ===== 盘中异动 (enriched 当日信号聚合, 异动监控「盘中」tab) =====
export type IntradaySignalKey = 'limit_up' | 'broken' | 'recovery' | 'limit_down'
  | 'new_high' | 'new_low' | 'volume_surge'

export interface AbnormalIntradayRow {
  symbol: string
  name?: string | null
  close?: number | null
  change_pct?: number | null      // 今日涨跌幅 (小数制)
  amplitude?: number | null       // 日振幅 (小数制)
  vol_ratio_5d?: number | null    // 5日量比
  turnover_rate?: number | null   // 换手率 (百分数原值)
  consecutive_limit_ups?: number | null
  signals: IntradaySignalKey[]    // 命中信号 (按优先级排序)
}

export interface AbnormalIntradayPayload {
  cache_date?: string | null
  counts?: Partial<Record<IntradaySignalKey, number>>
  rows?: AbnormalIntradayRow[]
}

export interface MonitorRule {
  id: string
  name: string
  enabled: boolean
  type: 'strategy' | 'signal' | 'price' | 'market' | 'ladder' | 'sector' | 'abnormal' | 'volume_delta' | 'date'
  asset_type?: 'stock' | 'etf' | 'index'
  scope: 'symbols' | 'all' | 'sector' | 'watchlist_group'
  symbols: string[]
  /** scope=watchlist_group 时绑定的自选分组 id (成员动态解析, 增删自选自动生效) */
  group_id?: string | null
  sector?: string | null
  sector_kind?: SectorKind | null
  sector_targets?: SectorMonitorTarget[]
  sector_trigger?: 'change_pct' | 'momentum'
  threshold_pct?: number
  window_minutes?: 1 | 3 | 5 | 10 | 15
  /** abnormal 专属: 关注窗口 (any=全部) */
  abnormal_window?: 'any' | '3d' | '10d' | '30d'
  strategy_id?: string | null
  direction: 'entry' | 'exit' | 'both' | 'up' | 'down'
  notify_events?: StrategyNotifyEvent[]
  score_min?: number | null
  score_max?: number | null
  conditions: MonitorCondition[]
  logic: 'and' | 'or'
  cooldown_seconds: number
  severity: 'info' | 'warn' | 'critical'
  message: string
  webhook_url?: string
  webhook_enabled?: boolean  // 兼容老规则, 已由 webhook_channels 取代
  webhook_channels?: string[]  // 合法值: feishu | wecom | dingtalk[fork] | custom | email
  created_at?: string
  runtime_warning?: string
  // ladder 专属: 封单监控; volume_delta 复用 metric 表示阈值口径 (volume=手数, amount=金额)
  metric?: 'sealed_vol' | 'sealed_amount' | 'volume' | 'amount'
  threshold?: number                        // 封单 <= 此值时报警
  // volume_delta 专属 (轮询放量): 相邻两次全市场快照的成交量增量(手)
  threshold_volume?: number                 // 单轮增量 >= 此值时报警
  threshold_amount?: number                 // metric=amount 时: 单轮增量 >= 此值(元)时报警
  basic_filter?: VDBasicFilter             // 基础过滤 (与策略 basic_filter 语义对齐)
  // date 类型 (日期提醒): 纯日历窗口, 无行情 conditions
  remind_date?: string | null   // YYYY-MM-DD
  lead_days?: number            // 提前 N 天进入提醒窗口
  lot_id?: string               // 由「持仓提醒」页生成的规则, 托管在批次页 (监控中心只读)
}

// 批次登记 (薄批次, 页面名"持仓提醒") — 只作监控规则生成的载体, 不做任何会计
export interface Lot {
  id: string
  symbol: string
  qty: number
  cost_price: number
  buy_date?: string | null
  target_pct: number
  stop_pct: number
  remind_date?: string | null
  lead_days: number
  created_at?: string
}

export interface VDBasicFilter {
  price_min?: number | null                 // 股价下限 (元)
  price_max?: number | null                 // 股价上限 (元)
  market_cap_min?: number | null            // 总市值下限 (元)
  float_cap_min?: number | null             // 流通市值下限 (元)
  float_cap_max?: number | null             // 流通市值上限 (元)
  amount_min?: number | null                // 当日成交额下限 (元)
  exclude_st?: boolean                      // 剔除 ST
}

export interface MonitorRuleOptions {
  threshold_fields: { key: string; label: string }[]
  builtin_signals: { key: string; label: string }[]
  custom_signals: { key: string; label: string }[]
  operators: string[]
  types: { key: string; label: string }[]
  scopes: { key: string; label: string }[]
  logics: { key: string; label: string }[]
  severities: { key: string; label: string }[]
  directions: { key: string; label: string }[]
  intraday_signal_support: {
    available: boolean
    source: string | null
    max_symbols: number
    reason: string
  }
  sector_targets: Record<SectorKind, SectorMonitorTarget[]>
}

export interface AlertEvent {
  ts: number
  /** [R160] 评估时盖的章: 这只票不在推送焦点名单里 —— 不弹窗、不响、不推外部、不计徽标; 触发记录仍保留 */
  focus_muted?: boolean
  rule_id?: string
  rule_name?: string
  source: string
  type: string
  symbol?: string
  name?: string | null
  message: string
  price?: number | null
  change_pct?: number | null
  signals?: string[]
  severity?: string
  strategy_id?: string
  conditions?: MonitorCondition[]
  logic?: 'and' | 'or'
  sector_kind?: SectorKind
  sector_key?: string
  sector_name?: string
  sector_source_field?: string
  sector_value?: string
  sector_level?: number | null
  window_change_pct?: number | null
  coverage_ratio?: number
  valid_count?: number
  total_count?: number
  up_count?: number
  down_count?: number
  leader?: { symbol?: string; name?: string; change_pct?: number } | null
  /** 异动边缘告警 (source=abnormal) 附加字段 */
  abnormal_window?: string
  abnormal_value?: number
  abnormal_threshold?: number
  abnormal_closeness?: number
  /** ext 富化字段 (行业/概念等), 键为 "{configId}__{fieldName}" */
  [key: string]: unknown
}

/** 生成监控规则 id (时间戳 + 随机后缀), 用户无需手动填写。 */
export function genRuleId(): string {
  const ts = Date.now().toString(36)
  const rand = Math.random().toString(36).slice(2, 6)
  return `mr_${ts}_${rand}`
}

// ===== Limit Ladder =====
export interface LimitLadderStock {
  symbol: string
  name?: string | null
  close?: number | null
  change_pct?: number | null
  consecutive_limit_ups?: number | null
  consecutive_limit_downs?: number | null
  status?: 'limit_up' | 'broken' | 'failed' | 'limit_down' | 'recovery' | null
  /** 五档 sealed: real=真封板, fake=假涨停(已归炸板), pending=待确认, null=降级/无能力 */
  sealed_status?: 'real' | 'fake' | 'pending' | null
  /** 封单量(买一/卖一量), 仅真封板有值 */
  sealed_vol?: number | null
  /** 最终状态为涨跌停且当天开高低收四价相同 */
  is_one_word?: boolean
}

export interface LimitLadderTier {
  boards: number
  count: number
  stocks: LimitLadderStock[]
}

export interface LimitLadderResult {
  as_of: string
  /** 部分数据日标注: 不完整的原始日期(默认日期已自动回退到 as_of 所示的上一完整交易日) */
  partial_from?: string | null
  /** 显式选择了部分数据日时: 该日仅有的股票数; null=已回退 */
  partial_count?: number | null
  tiers: LimitLadderTier[]
  /** 双方向涨跌停计数(修正后, 不论当前 direction) */
  counts?: { up: number; down: number }
  /** 双方向涨跌停原始计数(修正前, 供弹窗对比) */
  counts_raw?: { up: number; down: number }
  /** sealed 数据是否就绪(false→前端显示降级标识) */
  sealed_ready?: boolean
  /** sealed 数据 age(秒), null=盘后定版或无数据 */
  sealed_age?: number | null
  /** sealed 修正统计: real=真封板, fake=假涨停(归炸板), pending=待确认 */
  sealed_counts?: { real: number; fake: number; pending: number }
  /** 涨停侧 sealed 明细 */
  sealed_counts_up?: { real: number; fake: number; pending: number }
  /** 跌停侧 sealed 明细 */
  sealed_counts_down?: { real: number; fake: number; pending: number }
}

// ===== Backtest =====
export interface BacktestResult {
  run_id: string
  config: any
  stats: Record<string, any>
  equity_curve: { date: string; value: number }[]
  trades: any[]
  per_symbol_stats: { symbol: string; total_return: number }[]
}

// ===== Factor Backtest =====
export interface FactorColumn {
  id: string
  label: string
  group: string
  desc: string
}

// ===== Factor Library (注册表, P1) =====
export type FactorKind = 'base' | 'virtual' | 'composite' | 'custom'
export type FactorStability = 'stable' | 'experimental' | 'deprecated'

export interface FactorLibraryItem {
  id: string
  label: string
  group: string
  kind: FactorKind
  version: number
  formula: string
  direction: 'high' | 'low' | 'none'
  unit: string
  warmup_bars: number
  pit: boolean
  asset_types: string[]
  stability: FactorStability
  scale_free: boolean
  dependencies: string[]
}

export interface FactorDslError {
  code: string
  message: string
  position: { offset: number; line: number }
  detail?: Record<string, unknown>
}

export interface FactorValidateResponse {
  ok: boolean
  errors: FactorDslError[]
  dependencies: string[]
  referenced_factors: string[]
  warmup_bars: number
  cross_sectional: boolean
}

export interface FactorTrialResponse {
  ok: boolean
  n_dates: number
  null_ratio: number | null
  ic_mean: number | null
  ic_std: number | null
  ir: number | null
  ic_win_rate: number | null
  t_newey_west?: number | null
  ic_series: { date: string; ic: number; n_symbols: number }[]
  message?: string
}

export interface GroupStat {
  group: number
  label: string
  total_return: number
  annual_return: number
  max_drawdown: number
  sharpe: number
  win_rate: number
}

export interface FactorBacktestResult {
  run_id: string
  config: Record<string, any>
  ic_mean: number | null
  ic_std: number | null
  ir: number | null
  ic_win_rate: number | null
  ic_series: { date: string; ic: number }[]
  group_stats: GroupStat[]
  group_nav: Record<string, any>[]
  long_short_stats: Record<string, any>
  long_short_nav: { date: string; value: number }[]
  elapsed_ms: number
  n_symbols: number
  n_dates: number
  error: string | null
}

export interface FactorBatchItem {
  factor_name: string
  label: string
  group: string
  ic_mean: number | null
  ir: number | null
  ic_win_rate: number | null
  long_short_return: number | null
  long_short_max_drawdown: number | null
  n_symbols: number
  n_dates: number
  elapsed_ms: number
  error: string | null
  // metrics_v2 (P3): NW HAC t 值与 BH-FDR q 值; 样本不足为 null (前端降级经验规则)
  t_naive?: number | null
  t_newey_west?: number | null
  nw_lag?: number | null
  p_value?: number | null
  q_value?: number | null
}

// ===== [fork 增强] R32 因子 AI 解读 =====
export interface FactorShortlistRow {
  factor: string
  label: string
  group: string
  可用度: number
  IC均值: number | null
  IR: number | null
  IC胜率: number | null
}

/** 代跑的一轮记录: 配置 + 该轮短名单/漏斗 + AI 当时的判断 */
export interface FactorAiRound {
  round: number
  config: Record<string, unknown>
  shortlist: FactorShortlistRow[]
  stats: Record<string, number>
  note: string
  satisfied: boolean
}

/** 代跑的一轮: 配置 + 关键指标 + 是否达标 + AI 当时的判断 */
export interface BacktestAiRound {
  round: number
  config: Record<string, unknown>
  digest: Record<string, number | null>
  passed: boolean
  note: string
}

export interface FactorBatchResult {
  run_id: string
  config: Record<string, any>
  results: FactorBatchItem[]
  elapsed_ms: number
  n_symbols: number
  n_dates: number
  error: string | null
}

// ===== Factor / strategy mining =====
export type MiningBudgetProfile = 'exploratory' | 'balanced' | 'strict'
export type MiningRunStatus =
  | 'queued'
  | 'running'
  | 'cancelling'
  | 'succeeded'
  | 'succeeded_with_budget_exhausted'
  | 'failed'
  | 'cancelled'
  | 'interrupted'
  | 'skipped_prerequisite'

export interface MiningAvailability {
  asset_type: 'stock' | 'etf'
  budget_profile: MiningBudgetProfile
  trading_bars: number
  required_bars: number
  outer_folds: number
  required_outer_folds: number
  eligible: boolean
  available_start: string | null
  available_end: string | null
  effective_start: string | null
  effective_end: string | null
  suggested_start: string | null
}

export interface MiningRequestV1 {
  factor_names: string[]
  strategy_ids?: string[]
  symbols?: string[] | null
  asset_type?: 'stock' | 'etf'
  start?: string | null
  end?: string | null
  budget_profile?: MiningBudgetProfile
  commission_pct?: number
  stamp_tax_pct?: number
  slippage_bps?: number
  correlation_threshold?: number
  max_combination_factors?: number
  beam_width?: number
  max_finalists?: number
  force?: boolean
}

export interface MiningRunProgress {
  phase: string
  label?: string
  done?: number
  total?: number
  percent?: number
  elapsed_ms?: number
  message?: string
}

export interface MiningRun {
  run_id: string
  signature: string
  status: MiningRunStatus
  request: MiningRequestV1 & { auto?: boolean; auto_screening?: AutoScreening }
  source?: 'manual' | 'scheduled' | 'auto'
  created_at: string
  updated_at: string
  started_at?: string | null
  finished_at?: string | null
  data_as_of?: string | null
  progress?: MiningRunProgress | null
  error?: string | null
  reused?: boolean
  summary?: MiningResultSummary | null
}

// 自动挖掘 L1 筛选摘要 (后端 app/services/auto_mining.py 产出结构)
export interface AutoScreening {
  profile: MiningBudgetProfile
  gate: { min_abs_ic: number; min_abs_ir: number; min_abs_t: number; max_q: number }
  screen_window: { start: string; end: string }
  n_total: number
  n_qualified: number
  pool: string[]
  pool_truncated: boolean
  qualified: Array<{ factor_name: string; label: string; group: string; ic: number | null; ir: number | null; t: number | null; q: number | null; direction: 1 | -1 }>
  failed: Array<{ factor_name: string; label: string; group: string; ic: number | null; ir: number | null; t: number | null; q: number | null; reason: string }>
  reason_counts: Record<string, number>
  elapsed_ms: number
}

export interface MiningAutoStartPayload {
  asset_type?: 'stock' | 'etf'
  start?: string | null
  end?: string | null
  budget_profile?: MiningBudgetProfile
  correlation_threshold?: number
  force?: boolean
}

export interface MiningAutoStartResponse {
  started: boolean
  reason?: string
  run?: MiningRun
  screening?: AutoScreening
}

export interface MiningResultSummary {
  factor_count: number
  selected_factor_count: number
  candidate_count: number
  valid_fold_count: number
  skipped_fold_count: number
  confidence: 'low' | 'standard' | 'high'
  budget_exhausted?: boolean
  elapsed_ms?: number
  peak_rss_bytes?: number
}

export interface MiningFactorRow {
  factor_name: string
  label?: string
  direction: 1 | -1
  score: number | null
  ic_mean: number | null
  ir: number | null
  coverage: number | null
  turnover: number | null
  spread_return?: number | null
  spread_sharpe?: number | null
  selected: boolean
  excluded_reason?: string | null
}

export interface MiningRegimeRow {
  state: 'overall' | 'strong' | 'range' | 'weak' | string
  label: string
  n_dates: number
  total_return: number | null
  sharpe: number | null
  max_drawdown: number | null
}

export interface MiningFoldRow {
  fold: number
  label?: string
  train_start?: string
  train_end?: string
  test_start?: string
  test_end?: string
  selected_factors?: string[]
  total_return: number | null
  sharpe: number | null
  max_drawdown?: number | null
  n_trades?: number | null
  skipped?: boolean
  reason?: string | null
  evaluation_kind?: 'selected' | 'cross' | 'benchmark' | null
}

export interface MiningCandidateGate {
  qualified: boolean
  reasons: string[]
}

export interface MiningCandidateRow {
  signature: string
  name: string
  kind: 'factor_combination' | 'existing_strategy'
  factor_names?: string[]
  strategy_id?: string | null
  regime_state?: string | null
  score: number | null
  oos_return: number | null
  oos_sharpe: number | null
  oos_max_drawdown: number | null
  oos_positive_fold_ratio: number | null
  oos_n_trades: number | null
  confidence: 'low' | 'standard' | 'high'
  valid_folds?: number | null
  skipped_folds?: number | null
  promoted_candidate_id?: string | null
  published_strategy_id?: string | null
  gate?: MiningCandidateGate | null
  folds?: MiningFoldRow[]
}

export interface MiningTelemetry {
  elapsed_ms?: number
  peak_rss_bytes?: number
  panel_scans?: number
  matrix_bytes?: number
  cache_hits?: number
  fold_reuses?: number
  serialized_result_bytes?: number
  phase_ms?: Record<string, number>
}

export interface MiningRequestSummary {
  asset_type: string
  budget_profile: string
  start: string | null
  end: string | null
  factor_count: number
  strategy_count: number
  commission_pct: number | null
  stamp_tax_pct: number | null
  slippage_bps: number | null
  correlation_threshold: number | null
}

export interface MiningResult {
  run_id: string
  methodology_version: string
  algorithm_version: string
  data_as_of: string | null
  summary: MiningResultSummary
  request_summary?: MiningRequestSummary | null
  factors: MiningFactorRow[]
  correlation: {
    labels: string[]
    matrix: (number | null)[][]
    pair_counts?: (number | null)[][]
    threshold: number
  }
  regimes: MiningRegimeRow[]
  candidates: MiningCandidateRow[]
  folds: MiningFoldRow[]
  telemetry: MiningTelemetry
}

export interface MiningEvent {
  id: number
  type: string
  timestamp?: string
  payload?: Record<string, unknown>
  message?: string
}

export interface MiningScheduleConfig {
  mining_schedule_enabled: boolean
  mining_schedule_weekday: number
  mining_budget_profile: Exclude<MiningBudgetProfile, 'exploratory'>
}

export type ResearchCandidateKind = 'factor' | 'strategy'
export type ResearchCandidateStatus = 'pending' | 'validated' | 'rejected'

export interface ResearchCandidate {
  id: string
  kind: ResearchCandidateKind
  name: string
  source_id: string
  config: Record<string, unknown>
  metrics: Record<string, number | string | boolean | null>
  data_as_of: string | null
  status: ResearchCandidateStatus
  created_at: string
  updated_at: string
}

export interface ResearchCandidateCreate {
  kind: ResearchCandidateKind
  name: string
  source_id: string
  config: Record<string, unknown>
  metrics: Record<string, number | string | boolean | null>
  data_as_of?: string | null
  status?: ResearchCandidateStatus
}

// ===== Strategy Backtest =====
export interface StrategyBacktestTrade {
  symbol: string
  name?: string
  entry_date: string
  exit_date: string
  entry_price: number
  exit_price: number
  pnl_pct: number
  duration: number
  exit_reason: string
  shares?: number
  lots?: number
  position_pct?: number
  entry_value?: number
  exit_value?: number
  pnl_amount?: number
  entry_score?: number | null
  entry_signal_date?: string | null
  exit_signal_date?: string | null
  blocked_exit_days?: number
  entry_signal_id?: string | null
  exit_signal_id?: string | null
}

export interface StrategyBacktestResult {
  run_id: string
  config: Record<string, any>
  stats: Record<string, any>
  equity_curve: { date: string; value: number; cash?: number; positions?: number; exposure?: number }[]
  drawdown_curve: { date: string; value: number }[]
  benchmark_curve?: { date: string; value: number; close?: number; name?: string; symbol?: string }[]
  trades: StrategyBacktestTrade[]
  /** v1 因子归因: 入场信号日因子值快照 × 成交盈亏 (胜/败单均值对比); 无评分因子或分钟路径时为 null */
  factor_attribution?: {
    factors: { factor: string; win_mean: number | null; lose_mean: number | null; win_n: number; lose_n: number }[]
    n_win: number
    n_lose: number
  } | null
  per_symbol_stats: {
    symbol: string
    n_trades: number
    total_return: number
    win_rate: number
    best: number
    worst: number
  }[]
  strategy_info: {
    id: string
    name: string
    description: string
    entry_signals: string[]
    exit_signals: string[]
    stop_loss: number | null
    take_profit: number | null
    trailing_stop: number | null
    trailing_take_profit_activate: number | null
    trailing_take_profit_drawdown: number | null
    score_min: number | null
    score_max: number | null
    max_hold_days: number | null
    source: string
    execution_backend?: string
    // 叠加策略回测: 子策略构成与权重归因
    composite_children?: { id: string; weight: number }[]
  }
  elapsed_ms: number
  error: string | null
}

// ===== Settings =====

/** 端点发现清单 —— 对应 tickflow.org/endpoints.json */
export interface EndpointItem {
  id: string
  url: string
  label: string
  region?: string
  description?: string
  premium?: boolean
}

export interface EndpointManifest {
  version?: number
  description?: string
  healthPath?: string
  /** 每端点测试轮数,用于 /health 多轮探测取中位数 */
  testRounds?: number
  endpoints: EndpointItem[]
  /** 数据来源:remote=远程拉取 / fallback=内置回退列表 */
  source?: 'remote' | 'fallback'
}

/**
 * [R56] 一条 AI 档位。**列表顺序就是优先级** —— 排在前面的先用, 那一档因为
 * 额度/限流/鉴权/宕机用不了就顺位往下试。不另设 priority 字段: 两处表达
 * 同一件事迟早会打架。
 */
/** [R58] 一个数据源 key 的死活。明文 —— 本地单机应用, 遮起来反而没法核对是哪个失效 */
export interface TickflowKeyRow {
  index: number
  key: string
  /** 第一个是主 key: 档位探测、付费端点、历史日 K 都走它 */
  primary: boolean
  /** 只有验活之后才有 */
  alive?: boolean
  error?: string
}

/**
 * [R61] 选股范围。每个操作员带**两本独立的账**:
 *   market    只能从全市场候选里选
 *   watchlist 只能从我圈的自选里选
 * 这是这套系统最想问的那个问题的对照组 —— 我这份自选到底有没有价值。
 */
export type PaperScope = 'market' | 'watchlist'

/** 一本账的成绩 */
/** [R183] 模拟盘持仓的批次视图。字段名与作者的批次一致, 界面可照批次表渲染。 */
export interface PaperLot {
  id: string
  symbol: string
  cost_price: number
  qty: number
  buy_date: string | null
  price: number | null
  market_value: number | null
  pnl_pct: number | null
  trader_id: string
  scope: string
}

/** [R183] 绩效指标。**null = 算不出来**(样本不足/没有基准), 不是 0。 */
export interface PaperMetrics {
  days: number
  total_return: number | null
  max_drawdown: number | null
  sharpe: number | null
  exposure: number | null
  benchmark_return: number | null
  excess_return: number | null
}

export interface PaperBook {
  scope: PaperScope
  scope_cn: string
  /** [R63] 每本账各自的本金 —— 收益率各按各的算, 设成不同的数也照样可比 */
  initial_capital: number
  cash: number
  nav: number
  /** 相对初始资金的收益率(小数) */
  return_pct: number
  positions_count: number
  orders_count: number
  /** 记过净值的天数 */
  days: number
  last_run_at: string | null
  last_error: string
  last_note: string
  /** [R171] 出场原因分布 —— 立计划之后真正的产出 */
  exit_stats?: PaperExitStats
  /** [R183] 持仓的**批次视图** —— 「我的批次」并进模拟盘后按批次的样子给出来。
   *  是派生的: 唯一真相在账本里, 不写进作者的 lots.json(那会派生真实监控规则,
   *  并经 effective_positions 污染决策台管真钱的那几列)。 */
  lots?: PaperLot[]
  /** [R183] 绩效。参考 MarketPulse 的 Metrics 补的; 算不出的是 null, 不用 0 顶替 */
  metrics?: PaperMetrics
  /** [R186] 净值曲线(只 date/nav 两个字段, 最近 260 点)。
   *  nav_history 一直在存却从没画过 —— 总资产只说明现在几块钱, 曲线才说明
   *  这一路是怎么走过来的。 */
  nav_curve?: { date: string; nav: number }[]
  /** [R171] 已到止盈线但系统没替它卖的, 会写进下一轮它的上下文 */
  plan_reminders?: { symbol: string; kind: string; reason: string }[]
}

export interface PaperSchedule {
  enabled: boolean
  hour: number
  minute: number
}

/** [R59] AI 操作员。名字就是模型名 —— 要比的是哪个模型用同一份信息做得更好 */
export interface PaperTrader {
  id: string
  name: string
  profile_id: string
  created_at: string
  /** [R63] 同时最多持有几只。两本账一视同仁 —— 要对照, 这个数就得对齐 */
  max_positions: number
  schedule: PaperSchedule
  /** 两本账并排 —— 分开请求会让人下意识只看其中一边 */
  books: PaperBook[]
}

/**
 * [R171] 买入时立的交易计划 —— 借鉴「持仓提醒」的批次: 按成本价 ± 止盈/止损%
 * 推出监控线, 按最长持有天数推出到期日。
 *
 * 纪律分两档: **止损线与到期日到了系统直接卖, 不问 AI**(和跌破生命线同一条道理);
 * **止盈线到了只提醒**, 由模型自己决定落袋还是让利润奔跑 —— 那是策略不是纪律。
 */
export interface PaperPlan {
  target_pct: number | null
  stop_pct: number | null
  hold_days: number | null
  target_price: number | null
  stop_price: number | null
  due_date: string | null
  /** 三条线是按哪个成本算出来的(加仓后会按新的加权成本重算) */
  based_on_cost: number
}

/** [R171] 出场归因: 每笔卖出归到其中一类 */
export type PaperExitReason = 'stop' | 'due' | 'target' | 'lifeline' | 'ai'

export interface PaperExitStats {
  counts: Record<PaperExitReason, number>
  closed: number
  wins: number
  win_rate: number | null
  positions_with_plan: number
  positions_total: number
}

export interface PaperPosition {
  symbol: string; shares: number; cost: number
  price: number | null
  opened_on: string
  pnl_pct: number | null
  market_value: number
  /** [R171] 买入时立的三条线; 升级前建的仓没有 */
  plan?: PaperPlan | null
}

export interface PaperOrder {
  ts: string; date: string
  action: 'buy' | 'sell'
  symbol: string; shares: number; price: number
  amount?: number
  reason: string
  /** 有值 = 这一笔被拒了。拒单也留痕: "想买但买不成"和"没想买"是两件事 */
  rejected?: string
  /** [R61] 跌破生命线的纪律强平 —— 这一路不问 AI */
  lifeline?: boolean
  /** 那一笔用的是实时价(生命线是全流程唯一允许用实时的地方) */
  intraday?: boolean
  /** [R171] 卖出归因。买入没有这个字段 */
  exit_reason?: PaperExitReason
  /** [R171] 卖出时的成本与已实现盈亏 */
  cost?: number | null
  pnl_pct?: number | null
  /** [R171] 买入时立的计划(存一份在成交上, 便于复盘当时怎么想的) */
  plan?: PaperPlan | null
  /** [R171] 这笔强平是被计划的哪条线带走的 */
  plan_hit?: 'stop' | 'due'
}

/** 一本账的全部家当 */
export interface PaperBookDetail extends PaperBook {
  id: string
  name: string
  max_positions: number
  positions: PaperPosition[]
  /** 新 → 旧 */
  orders: PaperOrder[]
  nav_history: { date: string; nav: number; cash: number; market_value: number }[]
}

export interface AiProfile {
  id: string
  /** 给自己看的名字, 如"主力"、"备用" */
  label: string
  provider: string
  base_url: string
  /** 只在提交时带明文; 留空 = 沿用原来那条的 key */
  api_key?: string
  /** 服务端下发的脱敏串, 只用来显示 */
  api_key_masked?: string
  model: string
  reasoning_effort?: string
  enabled: boolean
  /** [R111] true=后端现合成的兼容档(存储里还没有档位表); 存储里的真实档位为 false。
      不能靠 id==='legacy' 判断 —— 早期合成的那条被保存后 id 会原样留在表里。 */
  synthesized?: boolean
}

export interface SettingsState {
  mode: 'none' | 'free' | 'api_key'
  tickflow_api_key_masked: string
  has_tickflow_key: boolean
  tier_label: string
  current_endpoint: string
  probe_log: string[]
  missing_caps: string[]
  extras_caps: string[]
  // 首次使用引导
  onboarding_completed: boolean
  // AI 配置
  ai_provider: string
  ai_base_url: string
  ai_api_key_masked: string
  has_ai_key: boolean
  ai_configured?: boolean
  ai_model: string
  ai_openai_model?: string
  ai_reasoning_effort?: string
  ai_codex_model?: string
  ai_codex_command?: string
  ai_codex_reasoning_effort?: string
  ai_user_agent: string
  ai_max_output_tokens?: number
  ai_context_window?: number
}

/** 保存 TickFlow Key 的响应(先探后存) */
export interface SaveTickflowKeyResult {
  ok: boolean
  /** ok=false 且 key 无效时的原因标识,前端据此提示「Key 无效」 */
  reason?: 'invalid'
  error?: string
  mode?: 'none' | 'free' | 'api_key'
  tier_label?: string
  current_endpoint?: string
  tickflow_api_key_masked?: string
  capabilities_count?: number
}

export interface DataSourceItem {
  name: string
  display_name: string
  datasets: string[]
  path?: string | null
}

/** 内置可选插件数据源 (plugins/ 目录, 需手动装依赖) */
export interface PluginDataSourceItem {
  name: string
  display_name: string
  datasets: string[]
  runtime: string          // node | python | none
  available: boolean       // 依赖是否已安装
  status: string           // 可用性原因 (供 UI 显示)
  description: string
  install_hint: string     // 未装依赖时显示的安装命令
  homepage?: string        // 插件官网/申请地址 (manifest 可选声明)
  api_key_env?: string     // 声明后设置页提供 Key 输入框 (先探后存)
  api_key_masked?: string  // 当前生效 Key 的脱敏串 (secrets.json 优先, .env 兜底; 与 TickFlow Key 同一展示契约)
}

/** 数据源路由偏好字段 (每个能力一个, 与后端能力注册表一一对应) */
export type ProviderField =
  | 'daily_data_provider'
  | 'adj_factor_provider'
  | 'minute_data_provider'
  | 'full_minute_data_provider'
  | 'depth5_data_provider'
  | 'realtime_data_provider'
  | 'financial_data_provider'

/** 能力路由矩阵中的一个候选源 (candidates 只含当前确实可提供该能力的源) */
export interface CapabilityCandidate {
  name: string
  display: string
  kind: 'builtin' | 'plugin' | 'custom'
  available: boolean
  status: string
  note?: string | null
}

/** 一个能力 (标准化数据集) 的路由视图 */
export interface CapabilityRoute {
  id: string
  label: string
  desc: string
  field: ProviderField | null                    // null = 不可路由能力 (仅 TickFlow 提供)
  default: string
  tf_tier: string                                  // TickFlow 所需最低订阅档位
  tf_available: boolean                            // 当前 TickFlow 档位是否提供该能力
  usable: boolean                                  // 生效源当前能否真正提供 (各页能力门控的统一判定)
  current: string                                  // 原始偏好值
  current_display: string
  effective: string                                // 当前生效源 (独立路由, current 即生效)
  effective_display: string
  candidates: CapabilityCandidate[]                // 当前可用候选 (按当前 TickFlow 档位过滤)
  pending: CapabilityCandidate[]                   // 声明了该能力但未就绪的源 (置灰提示)
}

export interface CapabilityMatrix {
  tickflow_tier?: string                           // TickFlow 当前档位基础名 (none/free/...)
  capabilities: CapabilityRoute[]
}

export interface DataSourceLoadError {
  name?: string
  path: string
  errors: string[]
}

export interface DataSourcesResponse {
  builtin: DataSourceItem[]
  plugins: PluginDataSourceItem[]
  custom: DataSourceItem[]
  errors: DataSourceLoadError[]
  config_dir: string
}

export interface DataSourceTestResult {
  provider: string
  dataset: string
  rows: number
  columns: string[]
  preview: Record<string, unknown>[]
}

/** 插件 Key 保存结果 (先探后存: 无效 Key 返回 ok=false 且不落盘) */
export interface PluginKeyResult {
  ok: boolean
  reason?: string
  error?: string
  api_key_masked?: string
  plugin_available?: boolean
  plugin?: PluginDataSourceItem | null
}

export interface DatasetConfig {
  url: string
  method: string
  batch?: number | null
  rpm?: number | null
  response_path: string
  field_map: Record<string, string>
  transforms?: Record<string, string>
  symbols_param?: string
  start_param?: string
  end_param?: string
  asset_type_param?: string | null
  freq_param?: string | null
  timeout?: number | null
}

export interface AuthConfig {
  type: string
  token_env?: string | null
  header?: string
  param?: string
}

export interface CustomSourceConfig {
  name: string
  display_name: string
  auth: AuthConfig
  datasets: Record<string, DatasetConfig>
}

export interface WecomBotStatus {
  enabled: boolean
  running: boolean
  connected: boolean
  bot_id_configured: boolean
  secret_configured: boolean
  last_error: string
}

export interface Preferences {
  realtime_quotes_enabled: boolean
  /** [R118] 按交易日/交易时段自动开关实时行情 */
  realtime_auto: boolean
  watchlist_groups_in_nav: boolean
  minute_sync_enabled: boolean
  minute_sync_days: number
  minute_sync_segment_days: number
  minute_refresh_enabled: boolean
  minute_refresh_interval: number
  daily_data_provider?: string
  adj_factor_provider?: string
  minute_data_provider?: string
  /** 全量分钟 (盘中全市场分钟落盘) 生效源; 默认 tickflow (需 Expert 档) */
  full_minute_data_provider?: string
  /** 分钟源 1 分钟历史深度(交易日); null/缺省 = 深历史 (如 tickflow)。分时档位据此收窄 */
  minute_history_days?: number | null
  depth5_data_provider?: string
  realtime_data_provider?: string
  financial_data_provider?: string
  data_source_job_timeout_s: number
  data_source_long_job_timeout_s: number
  minute_batch_compress: boolean
  daily_batch_compress: boolean
  realtime_pull_stock?: boolean
  realtime_pull_etf?: boolean
  pipeline_pull_a_share: boolean
  pipeline_pull_etf: boolean
  pipeline_pull_index: boolean
  pipeline_regime_enabled: boolean
  regime_batch_days: number
  regime_warmup_days: number
  pipeline_index_symbols: string
  pipeline_schedule: { hour: number; minute: number }
  instruments_schedule: { hour: number; minute: number }
  enriched_batch_size: number
  index_daily_batch_size: number
  limit_ladder_monitor_enabled: boolean
  depth_polling_interval: number
  depth_finalize_time: { hour: number; minute: number }
  review_schedule: { enabled: boolean; hour: number; minute: number }
  review_push_channels: string[]
  review_push_mode?: 'auto' | 'manual'
  sse_refresh_pages: Record<string, boolean>
  strategy_monitor_enabled: boolean
  strategy_monitor_ids: string[]
  system_notify_enabled: boolean
  feishu_webhook_url?: string
  feishu_webhook_secret?: string
  wecom_webhook_url?: string
  dingtalk_webhook_url?: string
  dingtalk_keyword?: string
  custom_webhook_url?: string
  custom_webhook_secret_set?: boolean
  email_smtp_config?: EmailSmtpConfig
  email_smtp_password_set?: boolean
  wecom_bot_id?: string
  wecom_bot_secret?: string
  wecom_bot_enabled?: boolean
  webhook_enabled_default?: boolean
  webhook_default_channels?: string[]
  nav_order: string[]
  nav_hidden: string[]
  screener_auto_run: boolean
  minute_intraday_refresh: boolean
  minute_intraday_refresh_interval: number
  monitor_ext_fields: { concept: MonitorExtFieldItem | null; industry: MonitorExtFieldItem | null }
  external_page_enabled: boolean
  external_page_name: string
  external_page_url: string
  /** [R117] iframe=内嵌整站; fetch=抓原文 + 面板 AI 整理 + 固定版式 */
  external_page_mode: 'iframe' | 'fetch'
  /** [R117] 用大白话说明想从这页看到什么, 会拼进 AI 提示词 */
  external_page_ai_hint: string
}

/** [R117] 抓取模式的成品: AI 整理后、后端已归一化的固定结构 */
export interface ExternalPageView {
  spec: ExtSpec
  url: string
  hint: string
  model: string
  generated_at: number
  fetched_at: number
  source_chars: number
  from_cache: boolean
  /** [R146] 这份结果是哪来的:
   *  latest = 最近一次结果(30 分钟内, **连页面都没抓**)
   *  source = 抓了但原文一个字没变, 省掉了 AI
   *  fresh  = 这次真抓真整理 */
  cache_kind?: 'latest' | 'source' | 'fresh'
  /** 距这份整理生成过了多少秒 */
  age_seconds?: number
}

/** [R117] 只抓原文不调 AI —— 设置页确认地址通不通用 */
export interface ExternalPageRaw {
  ok: boolean
  url: string
  status: number
  content_type: string
  bytes: number
  fetched_at: number
  preview: string
  source_chars: number
}

export interface EmailSmtpConfig {
  host: string
  port: number
  security: 'ssl' | 'starttls' | 'none'
  username: string
  from_address: string
  to_addresses: string[]
}

/** 监控中心 ext 字段单项配置 (行业/概念标签的来源 + 显示裁剪) */
export interface MonitorExtFieldItem {
  /** "configId.fieldName" */
  field: string
  /** 显示前N个标签, 0=不限制 */
  maxTags?: number
  /** 隐藏的位置 (0-based), 如 [0] 表示隐藏第一个 */
  hiddenIndices?: number[]
}
export interface StrategyAlertEvent {
  source: 'strategy' | 'depth'
  type: string
  strategy_id?: string
  symbol?: string
  name?: string | null
  message: string
  price?: number | null
  change_pct?: number | null
  signals?: string[]
  /** ext 富化字段 (行业/概念等), 键为 "{configId}__{fieldName}" */
  [key: string]: unknown
}

// ===== API surface =====
export const api = {
  health: () => request<{ status: string; version: string; mode: string }>('/health'),

  // ===== Auth (访问认证) =====
  authStatus: () =>
    request<{ configured: boolean; authenticated: boolean }>('/api/auth/status'),
  authSetup: (password: string) =>
    request<{ ok: boolean }>('/api/auth/setup', {
      method: 'POST',
      body: JSON.stringify({ password }),
    }),
  authLogin: (password: string) =>
    request<{ ok: boolean }>('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ password }),
    }),
  authLogout: () =>
    request<{ ok: boolean }>('/api/auth/logout', { method: 'POST' }),
  authChangePassword: (oldPassword: string, newPassword: string) =>
    request<{ ok: boolean }>('/api/auth/change-password', {
      method: 'POST',
      body: JSON.stringify({ old_password: oldPassword, new_password: newPassword }),
    }),

  settings: () => request<SettingsState>('/api/settings'),
  saveTickflowKey: (api_key: string) =>
    request<SaveTickflowKeyResult>('/api/settings/tickflow-key', {
      method: 'POST',
      body: JSON.stringify({ api_key }),
    }),
  clearTickflowKey: () =>
    request<any>('/api/settings/tickflow-key', { method: 'DELETE' }),

  /** 标记首次使用向导完成（持久化到后端 preferences） */
  completeOnboarding: () =>
    request<{ ok: boolean; onboarding_completed: boolean }>(
      '/api/settings/onboarding/complete', { method: 'POST' },
    ),

  // ===== [R59] AI 操盘手 =====
  paperTraders: () =>
    request<{ traders: PaperTrader[] }>('/api/paper-trading/traders'),

  /**
   * [R170] 各标的被**几个**操作员持有 —— 供「我的批次」表做对照标记。
   *
   * 刻意只有计数: 不带操作员身份、成本、理由。作者在 paper_trader 里写明界面不做
   * "所有人持仓一览"(看完再去调提示词会破坏操作员隔离, 而隔离正是这个实验的价值)。
   * 一个聚合数能回答"AI 那边也看上这只了吗", 又不泄露任何一本账。
   */
  /**
   * [R171] 过一遍模型买入时立的交易计划。与生命线那个端点成对, 同样**不问 AI**:
   * 止损线与到期日直接卖, 止盈线只记提醒(下一轮写进它的上下文)。
   */
  paperPlanCheck: (id: string, scope: PaperScope) =>
    request<{ forced: PaperOrder[]; reminders: { symbol: string; kind: string; reason: string }[]; count: number }>(
      `/api/paper-trading/traders/${encodeURIComponent(id)}/books/${scope}/plan-check`,
      { method: 'POST' }),

  paperHoldingsOverlap: () =>
    request<{ overlap: Record<string, number>; trader_count: number }>(
      '/api/paper-trading/holdings-overlap'),

  paperBook: (id: string, scope: PaperScope) =>
    request<PaperBookDetail>(
      `/api/paper-trading/traders/${encodeURIComponent(id)}/books/${scope}`),

  paperTraderCreate: (body: {
    name: string; profile_id: string; capital: number; max_positions: number
  }) =>
    request<PaperTrader>('/api/paper-trading/traders', {
      method: 'POST', body: JSON.stringify(body),
    }),

  /** 让这一本账按今天的信息做一次决策 */
  paperBookRun: (id: string, scope: PaperScope) =>
    request<{
      date: string; scope: PaperScope; orders: PaperOrder[]; note: string
      /** [R65] 它这一轮要求细看的几只 */
      focus?: string[]
      /** [R66] 它认为信号旧了、要求现场重出的几只 */
      refreshed?: { symbol: string; ok: boolean; error: string }[]
      raw: string
    }>(
      `/api/paper-trading/traders/${encodeURIComponent(id)}/books/${scope}/run`, { method: 'POST' }),

  /** [R61] 生命线检查 —— 不问 AI, 也是全流程唯一用实时价的地方 */
  paperBookLifeline: (id: string, scope: PaperScope) =>
    request<{ forced: PaperOrder[]; count: number }>(
      `/api/paper-trading/traders/${encodeURIComponent(id)}/books/${scope}/lifeline`,
      { method: 'POST' }),

  /** [R63] 操作员级设置(持仓只数上限对两本账一视同仁) */
  paperTraderSettings: (id: string, maxPositions: number) =>
    request<{ ok: boolean; max_positions: number }>(
      `/api/paper-trading/traders/${encodeURIComponent(id)}/settings`,
      { method: 'PUT', body: JSON.stringify({ max_positions: maxPositions }) }),

  /** [R63] 改单本账的本金。会把这本账一并重置 —— 分母变了历史就读不懂了 */
  paperBookCapital: (id: string, scope: PaperScope, capital: number) =>
    request<{ ok: boolean; scope: PaperScope; initial_capital: number }>(
      `/api/paper-trading/traders/${encodeURIComponent(id)}/books/${scope}/capital`,
      { method: 'PUT', body: JSON.stringify({ initial_capital: capital }) }),

  paperTraderSchedule: (id: string, s: PaperSchedule) =>
    request<{ ok: boolean; schedule: PaperSchedule }>(
      `/api/paper-trading/traders/${encodeURIComponent(id)}/schedule`,
      { method: 'PUT', body: JSON.stringify(s) }),

  /** 不给 scope 就是两本账一起重置 */
  paperTraderReset: (id: string, scope?: PaperScope) =>
    request<{ ok: boolean }>(
      `/api/paper-trading/traders/${encodeURIComponent(id)}/reset${scope ? `?scope=${scope}` : ''}`,
      { method: 'POST' }),

  paperTraderDelete: (id: string) =>
    request<{ deleted: string }>(`/api/paper-trading/traders/${encodeURIComponent(id)}`,
      { method: 'DELETE' }),

  /** 看一眼这本账这次会拿到什么 —— 判断"系统给的信息够不够"得先看清给了什么 */
  paperBookContext: (id: string, scope: PaperScope) =>
    request<{ context: string; system_prompt: string }>(
      `/api/paper-trading/traders/${encodeURIComponent(id)}/books/${scope}/context`),

  /** [R56] 多 AI 档位: 列表顺序即优先级, 前面的先用, 用不了顺位往下 */
  aiProfiles: () =>
    request<{ profiles: AiProfile[] }>('/api/settings/ai/profiles'),

  saveAiProfiles: (profiles: AiProfile[]) =>
    request<{ ok: boolean; profiles: AiProfile[] }>('/api/settings/ai/profiles', {
      method: 'PUT', body: JSON.stringify({ profiles }),
    }),

  /** [R58] 逐个列出数据源 key(明文)。多 key 填在同一字段里, 只看脱敏串分不出哪个失效 */
  tickflowKeys: () =>
    request<{ keys: TickflowKeyRow[]; total: number }>('/api/settings/tickflow-keys'),

  /** 逐个验活 —— 真打一次接口。串行跑, 并发会把活的 key 也打成限流 */
  probeTickflowKeys: () =>
    request<{ keys: TickflowKeyRow[]; total: number; alive: number }>(
      '/api/settings/tickflow-keys/probe', { method: 'POST' }),

  saveTickflowKeys: (keys: string[]) =>
    request<{ ok: boolean; total: number; tier_label: string }>('/api/settings/tickflow-keys', {
      method: 'PUT', body: JSON.stringify({ keys }),
    }),

  saveAiSettings: (ai: { provider?: string; base_url?: string; api_key?: string; model?: string; reasoning_effort?: string; codex_command?: string; codex_reasoning_effort?: string; user_agent?: string; max_output_tokens?: number; context_window?: number }) =>
    request<{ ok: boolean; ai_provider?: string; ai_model?: string; ai_openai_model?: string; ai_reasoning_effort?: string; ai_codex_model?: string; ai_codex_command?: string; ai_codex_reasoning_effort?: string; ai_configured?: boolean; ai_max_output_tokens?: number; ai_context_window?: number }>('/api/settings/ai', {
      method: 'POST',
      body: JSON.stringify(ai),
    }),

  /** 一键清空 AI 配置(保留自定义 UA) */
  clearAiSettings: () =>
    request<{ ok: boolean }>('/api/settings/ai', { method: 'DELETE' }),

  preferences: () => request<Preferences>('/api/settings/preferences'),
  updateExternalPage: (config: {
    enabled: boolean; name: string; url: string
    mode?: 'iframe' | 'fetch'; ai_hint?: string   // [R117] 省略 = 保持原值
  }) =>
    request<Pick<Preferences,
      'external_page_enabled' | 'external_page_name' | 'external_page_url'
      | 'external_page_mode' | 'external_page_ai_hint'>>(
      '/api/settings/preferences/external-page',
      { method: 'PUT', body: JSON.stringify(config) },
    ),
  /** [R117] 抓页面 + AI 整理成固定结构(原文没变时后端直接回缓存, 不重复花钱) */
  externalPageView: (opts?: { url?: string; hint?: string; force?: boolean }) =>
    request<ExternalPageView>('/api/external-page/view', {
      method: 'POST',
      body: JSON.stringify({ url: opts?.url ?? null, hint: opts?.hint ?? null, force: opts?.force ?? false }),
    }),
  /** [R117] 只抓原文不调 AI */
  externalPageRaw: (opts?: { url?: string; force?: boolean }) =>
    request<ExternalPageRaw>('/api/external-page/raw', {
      method: 'POST',
      body: JSON.stringify({ url: opts?.url ?? null, hint: null, force: opts?.force ?? true }),
    }),
  dataSources: () => request<DataSourcesResponse>('/api/settings/data-sources'),
  capabilityMatrix: () => request<CapabilityMatrix>('/api/settings/capability-matrix'),
  dataSource: (name: string) => request<CustomSourceConfig>(`/api/settings/data-sources/${encodeURIComponent(name)}`),
  saveDataSource: (config: CustomSourceConfig) =>
    request<DataSourcesResponse>('/api/settings/data-sources', {
      method: 'POST',
      body: JSON.stringify(config),
    }),
  deleteDataSource: (name: string) =>
    request<DataSourcesResponse>(`/api/settings/data-sources/${encodeURIComponent(name)}`, { method: 'DELETE' }),
  reloadDataSources: () => request<DataSourcesResponse>('/api/settings/data-sources/reload', { method: 'POST' }),
  installPlugin: (name: string) => {
    // npm install 可能耗时较长, 用 6 分钟超时
    const controller = new AbortController()
    const timer = setTimeout(() => controller.abort(), 360_000)
    return request<DataSourcesResponse & { install_ok: boolean; install_message: string }>(
      `/api/settings/plugins/${encodeURIComponent(name)}/install`,
      { method: 'POST', signal: controller.signal },
    ).finally(() => clearTimeout(timer))
  },
  uninstallPlugin: (name: string) =>
    request<DataSourcesResponse & { uninstall_ok: boolean; uninstall_message: string }>(
      `/api/settings/plugins/${encodeURIComponent(name)}/install`,
      { method: 'DELETE' },
    ),
  savePluginKey: (plugin: string, apiKey: string) => {
    // 先探后存: 后端会用候选 Key 实探一次, 探测超时 10s + 余量
    const controller = new AbortController()
    const timer = setTimeout(() => controller.abort(), 30_000)
    return request<PluginKeyResult>('/api/settings/plugin-key', {
      method: 'POST',
      body: JSON.stringify({ plugin, api_key: apiKey }),
      signal: controller.signal,
    }).finally(() => clearTimeout(timer))
  },
  clearPluginKey: (plugin: string) =>
    request<PluginKeyResult>(`/api/settings/plugin-key/${encodeURIComponent(plugin)}`, { method: 'DELETE' }),
  testDataSource: (
    provider: string,
    dataset: string,
    symbols?: string[],
    config?: CustomSourceConfig,
  ) =>
    request<DataSourceTestResult>('/api/settings/data-sources/test', {
      method: 'POST',
      body: JSON.stringify({ provider, dataset, symbols, config }),
    }),
  updateDataProviders: (cfg: Partial<Pick<Preferences, ProviderField>>) =>
    request<Pick<Preferences, ProviderField>>(
      '/api/settings/preferences/data-providers',
      { method: 'PUT', body: JSON.stringify(cfg) },
    ),
  updateDataSourceJobTimeouts: (dataSourceJobTimeoutS: number, dataSourceLongJobTimeoutS: number) =>
    request<Pick<Preferences, 'data_source_job_timeout_s' | 'data_source_long_job_timeout_s'>>(
      '/api/settings/preferences/data-source-job-timeouts',
      {
        method: 'PUT',
        body: JSON.stringify({
          data_source_job_timeout_s: dataSourceJobTimeoutS,
          data_source_long_job_timeout_s: dataSourceLongJobTimeoutS,
        }),

      },
    ),

  /** 分时批量响应 gzip 压缩开关 (网络设置) — 逐请求即时生效 */
  updateMinuteBatchCompress: (enabled: boolean) =>
    request<Pick<Preferences, 'minute_batch_compress'>>('/api/settings/preferences/minute-batch-compress', {
      method: 'PUT',
      body: JSON.stringify({ minute_batch_compress: enabled }),
    }),

  /** 日K批量响应 gzip 压缩开关 (与分时独立) — 逐请求即时生效 */
  updateDailyBatchCompress: (enabled: boolean) =>
    request<Pick<Preferences, 'daily_batch_compress'>>('/api/settings/preferences/daily-batch-compress', {
      method: 'PUT',
      body: JSON.stringify({ daily_batch_compress: enabled }),
    }),
  updateMinuteSync: (enabled: boolean, days: number, segmentDays?: number) =>
    request<Preferences>('/api/settings/preferences/minute-sync', {
      method: 'PUT',
      body: JSON.stringify({
        minute_sync_enabled: enabled,
        minute_sync_days: days,
        ...(segmentDays != null ? { minute_sync_segment_days: segmentDays } : {}),
      }),
    }),

  /** 全量分钟 (盘中全市场分钟落盘) 服务状态 (按能力路由: TickFlow Expert 或声明 full_minute 的插件/自定义源) */
  minuteRefreshStatus: () =>
    request<{
      available: boolean
      enabled?: boolean
      running?: boolean
      /** 读侧 freshness: 本地分区正被服务持续写入 (前端据此切本地读/解除截断) */
      healthy?: boolean
      provider?: string
      provider_effective?: string
      repair_only?: boolean
      interval_seconds?: number
      capability_ok?: boolean
      in_trading_hours?: boolean
      gate_reason?: string | null
      rounds?: number
      last_round_at?: number | null
      last_round_ms?: number | null
      last_rows?: number
      last_symbols?: number
      last_requests?: number
      next_round_at?: number | null
      last_error?: string | null
    }>('/api/settings/minute-refresh/status'),
  updatePipelinePullTypes: (cfg: Partial<Pick<Preferences, 'pipeline_pull_a_share' | 'pipeline_pull_etf' | 'pipeline_pull_index'>>) =>
    request<{
      pipeline_pull_a_share: boolean
      pipeline_pull_etf: boolean
      pipeline_pull_index: boolean
    }>('/api/settings/preferences/pipeline-pull-types', {
      method: 'PUT',
      body: JSON.stringify(cfg),
    }),
  updatePipelineRegimeEnabled: (enabled: boolean) =>
    request<{ pipeline_regime_enabled: boolean }>('/api/settings/preferences/pipeline-regime-enabled', {
      method: 'PUT',
      body: JSON.stringify({ pipeline_regime_enabled: enabled }),
    }),
  updateRegimeBatchParams: (params: { batch_days?: number; warmup_days?: number }) =>
    request<{ regime_batch_days: number; regime_warmup_days: number }>('/api/settings/preferences/regime-batch-params', {
      method: 'PUT',
      body: JSON.stringify(params),
    }),
  updatePipelineIndexSymbols: (symbols: string) =>
    request<{ pipeline_index_symbols: string }>('/api/settings/preferences/pipeline-index-symbols', {
      method: 'PUT',
      body: JSON.stringify({ symbols }),
    }),
  updateRealtimeQuotes: (enabled: boolean) =>
    request<{
      realtime_quotes_enabled: boolean
      realtime_allowed?: boolean
      mode?: string
      error?: string
      /** 历史快照需先修复：跟踪该任务，成功后重试一次开启动作。 */
      repair_required?: boolean
      repair_job_id?: string
      repair_reused?: boolean
      repair_detail?: string
      repair_completed?: boolean
    }>('/api/settings/preferences/realtime-quotes', {
      method: 'PUT',
      body: JSON.stringify({ realtime_quotes_enabled: enabled }),
    }),
  updateRealtimeQuoteScope: (cfg: Partial<Pick<Preferences, 'realtime_pull_stock' | 'realtime_pull_etf'>>) =>
    request<Partial<Preferences>>('/api/settings/preferences/realtime-quote-scope', {
      method: 'PUT',
      body: JSON.stringify(cfg),
    }),
  /** [R118] 开/关「按交易日自动开关行情」(实际开关由后端守护线程在≤30s 内落地) */
  updateRealtimeAuto: (enabled: boolean) =>
    request<{ realtime_auto: boolean; window: string }>('/api/settings/preferences/realtime-auto', {
      method: 'PUT',
      body: JSON.stringify({ realtime_auto: enabled }),
    }),
  updateWatchlistGroupsInNav: (enabled: boolean) =>
    request<{ watchlist_groups_in_nav: boolean }>('/api/settings/preferences/watchlist-groups-in-nav', {
      method: 'PUT',
      body: JSON.stringify({ watchlist_groups_in_nav: enabled }),
    }),
  quoteStatus: () =>
    request<{
      enabled: boolean
      running: boolean
      paused?: boolean
      mode?: 'none' | 'watchlist' | 'full_market'
      realtime_allowed?: boolean
      interval_s: number
      symbol_count: number
      watchlist_symbol_count?: number
      index_symbol_count?: number
      etf_symbol_count?: number
      quote_age_ms: number | null
      is_trading_hours: boolean
      is_polling_window?: boolean
      market_phase?: string
      final_sync_done?: boolean
      final_sync_failed?: string | null
      last_fetch_ms: number | null
    }>('/api/intraday/status'),
  quoteInterval: () =>
    request<{ interval: number; min_interval: number; max_interval: number }>(
      '/api/settings/preferences/quote-interval',
    ),
  updateQuoteInterval: (interval: number) =>
    request<{ interval: number; min_interval: number; max_interval: number }>(
      '/api/settings/preferences/quote-interval',
      { method: 'PUT', body: JSON.stringify({ interval }) },
    ),
  intradayRefresh: () => request<{ status: string }>('/api/intraday/refresh', { method: 'POST' }),
  indexQuotes: (symbols?: string[]) =>
    // [R119] source: realtime=来自行情轮询缓存(会跳) / index_daily=回退到日线收盘(静止)
    request<{ rows: IndexQuote[]; count: number; source?: 'realtime' | 'index_daily' }>(
      `/api/intraday/indices${symbols?.length ? `?symbols=${encodeURIComponent(symbols.join(','))}` : ''}`,
    ),
  updateRealtimeMonitorConfig: (cfg: {
    sse_refresh_pages?: Record<string, boolean>
    strategy_monitor_enabled?: boolean
    strategy_monitor_ids?: string[]
    screener_auto_run?: boolean
    minute_intraday_refresh?: boolean
    minute_intraday_refresh_interval?: number
    monitor_ext_fields?: { concept: MonitorExtFieldItem | null; industry: MonitorExtFieldItem | null }
  }) =>
    request<{
      sse_refresh_pages: Record<string, boolean>
      strategy_monitor_enabled: boolean
      strategy_monitor_ids: string[]
      screener_auto_run: boolean
      minute_intraday_refresh: boolean
      minute_intraday_refresh_interval: number
      monitor_ext_fields: { concept: MonitorExtFieldItem | null; industry: MonitorExtFieldItem | null }
    }>('/api/settings/preferences/realtime-monitor', {
      method: 'PUT',
      body: JSON.stringify(cfg),
    }),
  updateSystemNotify: (enabled: boolean) =>
    request<{ system_notify_enabled: boolean }>('/api/settings/preferences/system-notify', {
      method: 'PUT',
      body: JSON.stringify({ enabled }),
    }),
  updateFeishuWebhook: (url: string, secret: string = '') =>
    request<{ feishu_webhook_url: string; feishu_webhook_secret: string }>('/api/settings/preferences/feishu-webhook', {
      method: 'PUT',
      body: JSON.stringify({ url, secret }),
    }),
  updateWecomWebhook: (url: string) =>
    request<{ wecom_webhook_url: string }>('/api/settings/preferences/wecom-webhook', {
      method: 'PUT',
      body: JSON.stringify({ url }),
    }),
  updateDingtalkWebhook: (url: string, keyword: string = '') =>
    request<{ dingtalk_webhook_url: string; dingtalk_keyword: string }>('/api/settings/preferences/dingtalk-webhook', {
      method: 'PUT',
      body: JSON.stringify({ url, keyword }),
    }),
  updateCustomWebhook: (url: string, secret?: string) =>
    request<{ custom_webhook_url: string; custom_webhook_secret_set: boolean }>('/api/settings/preferences/custom-webhook', {
      method: 'PUT',
      body: JSON.stringify({ url, ...(secret !== undefined ? { secret } : {}) }),
    }),
  updateEmailSmtp: (config: EmailSmtpConfig, password?: string) =>
    request<{ email_smtp_config: EmailSmtpConfig; email_smtp_password_set: boolean }>('/api/settings/preferences/email-smtp', {
      method: 'PUT',
      body: JSON.stringify({ ...config, ...(password !== undefined ? { password } : {}) }),
    }),
  sendTestWebhook: (channel: 'feishu' | 'wecom' | 'dingtalk' | 'custom' | 'email') =>
    request<{ ok: boolean; detail: string }>('/api/settings/preferences/webhook-test', {
      method: 'POST',
      body: JSON.stringify({ channel }),
    }),
  updateWecomBot: (botId: string, secret: string, enabled: boolean = true) =>
    request<{
      wecom_bot_id: string
      wecom_bot_secret: string
      wecom_bot_enabled: boolean
      wecom_bot_status: WecomBotStatus
    }>('/api/settings/preferences/wecom-bot', {
      method: 'PUT',
      body: JSON.stringify({ bot_id: botId, secret, enabled }),
    }),
  toggleWecomBot: (enabled: boolean) =>
    request<{ wecom_bot_enabled: boolean; wecom_bot_status: WecomBotStatus }>('/api/settings/preferences/wecom-bot-toggle', {
      method: 'PUT',
      body: JSON.stringify({ enabled }),
    }),
  updateWebhookDefault: (enabled: boolean) =>
    request<{ webhook_enabled_default: boolean }>('/api/settings/preferences/webhook-enabled-default', {
      method: 'PUT',
      body: JSON.stringify({ enabled }),
    }),
  updateWebhookDefaultChannels: (channels: string[]) =>
    request<{ webhook_default_channels: string[] }>('/api/settings/preferences/webhook-default-channels', {
      method: 'PUT',
      body: JSON.stringify({ channels }),
    }),
  updatePipelineSchedule: (hour: number, minute: number) =>
    request<{ hour: number; minute: number }>('/api/settings/preferences/pipeline-schedule', {
      method: 'PUT',
      body: JSON.stringify({ hour, minute }),
    }),
  updateReviewSchedule: (enabled: boolean, hour: number, minute: number) =>
    request<{ enabled: boolean; hour: number; minute: number }>('/api/settings/preferences/review-schedule', {
      method: 'PUT',
      body: JSON.stringify({ enabled, hour, minute }),
    }),
  updateReviewPush: (channels: string[], mode?: 'auto' | 'manual') =>
    request<{ review_push_channels: string[]; review_push_mode: 'auto' | 'manual' }>('/api/settings/preferences/review-push', {
      method: 'PUT',
      body: JSON.stringify({ channels, mode: mode ?? null }),
    }),
  updateDepthPollingInterval: (interval: number) =>
    request<{ depth_polling_interval: number }>('/api/settings/preferences/depth-polling-interval', {
      method: 'PUT',
      body: JSON.stringify({ interval }),
    }),
  updateLimitLadderMonitor: (enabled: boolean) =>
    request<{ limit_ladder_monitor_enabled: boolean }>('/api/settings/preferences/limit-ladder-monitor', {
      method: 'PUT',
      body: JSON.stringify({ enabled }),
    }),
  runLimitLadderFix: () =>
    request<{ ok: boolean; count: number; msg: string }>('/api/settings/preferences/limit-ladder-monitor/run', {
      method: 'POST',
    }),
  updateDepthFinalizeTime: (hour: number, minute: number) =>
    request<{ hour: number; minute: number }>('/api/settings/preferences/depth-finalize-time', {
      method: 'PUT',
      body: JSON.stringify({ hour, minute }),
    }),
  saveNavOrder: (nav_order: string[]) =>
    request<{ nav_order: string[] }>('/api/settings/preferences/nav-order', {
      method: 'PUT',
      body: JSON.stringify({ nav_order }),
    }),
  saveNavHidden: (nav_hidden: string[]) =>
    request<{ nav_hidden: string[] }>('/api/settings/preferences/nav-hidden', {
      method: 'PUT',
      body: JSON.stringify({ nav_hidden }),
    }),
  updateInstrumentsSchedule: (hour: number, minute: number) =>
    request<{ hour: number; minute: number }>('/api/settings/preferences/instruments-schedule', {
      method: 'PUT',
      body: JSON.stringify({ hour, minute }),
    }),
  updateEnrichedBatchSize: (size: number) =>
    request<{ enriched_batch_size: number }>('/api/settings/preferences/enriched-batch-size', {
      method: 'PUT',
      body: JSON.stringify({ size }),
    }),
  updateIndexDailyBatchSize: (size: number) =>
    request<{ index_daily_batch_size: number }>('/api/settings/preferences/index-daily-batch-size', {
      method: 'PUT',
      body: JSON.stringify({ size }),
    }),

  // 自选列表列配置
  watchlistColumns: () =>
    request<{ columns: any[] | null }>('/api/settings/preferences/watchlist-columns'),
  updateWatchlistColumns: (columns: any[]) =>
    request<{ columns: any[] }>('/api/settings/preferences/watchlist-columns', {
      method: 'PUT',
      body: JSON.stringify({ columns }),
    }),

  // 策略结果列表列配置
  screenerResultColumns: () =>
    request<{ columns: any[] | null }>('/api/settings/preferences/screener-result-columns'),
  updateScreenerResultColumns: (columns: any[]) =>
    request<{ columns: any[] }>('/api/settings/preferences/screener-result-columns', {
      method: 'PUT',
      body: JSON.stringify({ columns }),
    }),

  capabilities: () => request<CapabilitiesResponse>('/api/capabilities'),
  version: () => request<{ version: string }>('/api/data/version'),
  redetectCapabilities: () =>
    request<CapabilitiesResponse>('/api/capabilities/redetect', { method: 'POST' }),

  // [R76] opts.refreshLive 与返回的 live_refresh 是 fork 加的: 弹窗点开先回旧数据,
  // 后台线程拉完再取一次。上游把响应体收成了 KlineDailyResponse, 这里在它之上扩展。
  klineDaily: (symbol: string, days = 120, dateRange?: { start: string; end: string }, extColumns?: string, opts?: { refreshLive?: boolean }) =>
    request<KlineDailyResponse & {
      /** [R76] refreshLive 时返回: started=后台在拉(稍后再取一次) / fresh=已是新的 / off=没 key */
      live_refresh?: 'started' | 'fresh' | 'off'
    }>(
      (dateRange
        ? `/api/kline/daily?symbol=${encodeURIComponent(symbol)}&start_date=${dateRange.start}&end_date=${dateRange.end}`
        : `/api/kline/daily?symbol=${encodeURIComponent(symbol)}&days=${days}`)
      + (extColumns ? `&ext_columns=${encodeURIComponent(extColumns)}` : '')
      // [R74] 服务端先现拉一次该票实时(15s 冷却)再返回 —— 弹窗"点开就是最新"
      + (opts?.refreshLive ? '&refresh_live=1' : ''),
    ),
  klineDailyLatest: (symbol: string) =>
    request<KlineDailyLatestResponse>(
      `/api/kline/daily/latest?symbol=${encodeURIComponent(symbol)}`,
    ),
  klineDailyBatch: (symbols: string[], days = 12) =>
    request<{ data: Record<string, KlineRow[]> }>('/api/kline/daily-batch', {
      method: 'POST',
      body: JSON.stringify({ symbols, days }),
    }),
  klineMinuteBatch: (symbols: string[], date?: string, preferLocal?: boolean, since?: string) =>
    request<{ data: Record<string, MinuteKlineRow[]>; full_minute_local?: boolean; incremental?: boolean }>('/api/kline/minute-batch', {
      method: 'POST',
      body: JSON.stringify({ symbols, date, ...(preferLocal ? { prefer_local: true } : {}), ...(since ? { since } : {}) }),
    }),
  instrumentSearch: (q: string, limit = 20, assetTypes?: string) =>
    request<{ results: { symbol: string; name: string; code: string; asset_type?: string }[] }>(
      `/api/kline/instruments/search?q=${encodeURIComponent(q)}&limit=${limit}${assetTypes ? `&asset_types=${encodeURIComponent(assetTypes)}` : ''}`,
    ),

  /** 批量查股票名称 (传入 symbol 列表, 返回 {symbol: name}) */
  instrumentNames: (symbols: string[]) =>
    request<{ names: Record<string, string> }>('/api/kline/instruments/names', {
      method: 'POST',
      body: JSON.stringify(symbols),
    }),
  klineMinute: (symbol: string, date?: string, live?: boolean) =>
    request<{
      symbol: string
      name?: string
      stock_info?: { name?: string; total_shares?: number; float_shares?: number }
      date: string | null
      rows: MinuteKlineRow[]
      source?: 'local' | 'live' | 'none'
      asset_type?: 'stock' | 'etf' | 'index'
      price_limit?: PriceLimitInfo | null
      prev_close?: number | null
    }>(
      `/api/kline/minute?symbol=${encodeURIComponent(symbol)}${date ? `&date=${date}` : ''}${live ? '&live=1' : ''}`,
    ),
  klineMinuteRange: (symbol: string, days = 10) =>
    request<{
      symbol: string
      name?: string
      asset_type: 'stock' | 'etf' | 'index'
      requested_days: number
      sessions: MinuteKlineSession[]
      source: 'local' | 'none'
    }>(
      `/api/kline/minute-range?symbol=${encodeURIComponent(symbol)}&days=${days}`,
    ),
  indexDaily: (symbol: string, days = 120, dateRange?: { start: string; end: string }) =>
    request<{
      symbol: string
      name?: string
      index_info?: IndexInstrument
      rows: KlineRow[]
      source?: string
    }>(
      dateRange
        ? `/api/index/daily?symbol=${encodeURIComponent(symbol)}&start_date=${dateRange.start}&end_date=${dateRange.end}`
        : `/api/index/daily?symbol=${encodeURIComponent(symbol)}&days=${days}`,
    ),
  indexMinute: (symbol: string, date?: string) =>
    request<{
      symbol: string
      name?: string
      date: string | null
      rows: MinuteKlineRow[]
      source?: string
    }>(
      `/api/index/minute?symbol=${encodeURIComponent(symbol)}${date ? `&date=${date}` : ''}`,
    ),
  syncIndexInstruments: () =>
    request<{ status: string; count: number }>('/api/index/sync_instruments', { method: 'POST' }),
  syncIndexDaily: (days = 365) =>
    request<{ status: string; index_count: number; rows_written: number }>(
      `/api/index/sync_daily?days=${days}`,
      { method: 'POST' },
    ),
  syncSymbol: (symbol: string, days = 250) =>
    request<{ symbol: string; rows_written: number }>(
      `/api/kline/sync?symbol=${encodeURIComponent(symbol)}&days=${days}`,
      { method: 'POST' },
    ),
  syncMinute: (days?: number, extend?: boolean) =>
    request<{ status: string; job_id: string }>('/api/kline/sync_minute', {
      method: 'POST',
      body: JSON.stringify({ ...(days ? { days } : {}), ...(extend ? { extend: true } : {}) }),
    }),
  syncMinuteSingle: (symbol: string, days?: number) =>
    request<{ status: string; symbol: string; rows: number }>('/api/kline/sync_minute_single', {
      method: 'POST',
      body: JSON.stringify({ symbol, ...(days != null ? { days } : {}) }),
    }),
  clearMinute: () =>
    request<{ status: string; removed: number }>('/api/kline/clear_minute', {
      method: 'POST',
      body: JSON.stringify({ confirm: true }),
    }),
  extendHistory: (value: number, unit: 'day' | 'month' | 'year') =>
    request<{ status: string; job_id: string }>('/api/kline/extend_history', {
      method: 'POST',
      body: JSON.stringify({ value, unit }),
    }),
  repairDaily: (startDate: string) =>
    request<{ status: string; job_id: string }>('/api/kline/repair_daily', {
      method: 'POST',
      body: JSON.stringify({ start_date: startDate }),
    }),
  rebuildEnriched: () =>
    request<{ status: string; job_id: string }>('/api/kline/rebuild_enriched', {
      method: 'POST',
    }),

  watchlistList: () => request<{ symbols: WatchlistEntry[] }>('/api/watchlist'),
  watchlistAdd: (symbol: string, note = '', groupId?: string | null) =>
    request<{ symbols: WatchlistEntry[] }>('/api/watchlist', {
      method: 'POST',
      body: JSON.stringify({ symbol, note, group_id: groupId ?? null }),
    }),
  watchlistBatchAdd: (symbols: string[], note = '', groupId?: string | null, groupIds?: string[]) =>
    request<{ symbols: WatchlistEntry[]; added: number }>('/api/watchlist/batch', {
      method: 'POST',
      body: JSON.stringify({
        symbols,
        note,
        group_id: groupId ?? null,
        group_ids: groupIds?.length ? groupIds : null,
      }),
    }),
  watchlistGroups: () =>
    request<{ groups: WatchlistGroup[] }>('/api/watchlist/groups'),
  // [fork 增强] AI 一键分组: suggest 只出方案不落库, apply 才写入
  watchlistAiGroupSuggest: () =>
    request<{
      groups?: { name: string; symbols: string[]; names: string[]; reason: string }[]
      ungrouped?: string[]; ungrouped_names?: string[]; total?: number; error?: string
    }>('/api/watchlist/ai-group', { method: 'POST' }),
  watchlistAiGroupApply: (groups: { name: string; symbols: string[] }[], replaceExisting: boolean) =>
    request<{ ok: boolean; groups_created: number; symbols_assigned: number; groups: WatchlistGroup[] }>(
      '/api/watchlist/ai-group/apply',
      { method: 'POST', body: JSON.stringify({ groups, replace_existing: replaceExisting }) },
    ),
  watchlistGroupCreate: (name: string, color: WatchlistGroupColor) =>
    request<{ groups: WatchlistGroup[]; group: WatchlistGroup }>('/api/watchlist/groups', {
      method: 'POST',
      body: JSON.stringify({ name, color }),
    }),
  watchlistGroupRename: (groupId: string, name: string, color: WatchlistGroupColor) =>
    request<{ groups: WatchlistGroup[] }>(
      `/api/watchlist/groups/${encodeURIComponent(groupId)}`,
      { method: 'PUT', body: JSON.stringify({ name, color }) },
    ),
  watchlistGroupReorder: (orderedIds: string[]) =>
    request<{ groups: WatchlistGroup[] }>('/api/watchlist/groups/reorder', {
      method: 'PUT',
      body: JSON.stringify({ ordered_ids: orderedIds }),
    }),
  watchlistGroupDelete: (groupId: string) =>
    request<{ groups: WatchlistGroup[]; symbols: WatchlistEntry[] }>(
      `/api/watchlist/groups/${encodeURIComponent(groupId)}`,
      { method: 'DELETE' },
    ),
  watchlistGroupClear: (groupId: string) =>
    request<{ symbols: WatchlistEntry[] }>(
      `/api/watchlist/groups/${encodeURIComponent(groupId)}/clear`,
      { method: 'POST' },
    ),
  watchlistSetGroup: (symbol: string, groupId: string | null) =>
    request<{ symbols: WatchlistEntry[] }>(
      `/api/watchlist/${encodeURIComponent(symbol)}/group`,
      { method: 'PUT', body: JSON.stringify({ group_id: groupId }) },
    ),
  watchlistGroupAddMember: (groupId: string, symbol: string) =>
    request<{ symbols: WatchlistEntry[] }>(
      `/api/watchlist/groups/${encodeURIComponent(groupId)}/members/${encodeURIComponent(symbol)}`,
      { method: 'POST' },
    ),
  watchlistGroupRemoveMember: (groupId: string, symbol: string) =>
    request<{ symbols: WatchlistEntry[] }>(
      `/api/watchlist/groups/${encodeURIComponent(groupId)}/members/${encodeURIComponent(symbol)}`,
      { method: 'DELETE' },
    ),
  watchlistOcrStatus: () =>
    request<{ provider: string; available: boolean }>('/api/watchlist/ocr-status'),
  watchlistImportImage: (file: File, signal?: AbortSignal, quiet = false) => {
    const fd = new FormData()
    fd.append('file', file)
    return request<WatchlistImportResult>('/api/watchlist/import-image', {
      method: 'POST',
      body: fd,
      signal,
      quiet,
    })
  },
  watchlistImportCsv: (file: File, signal?: AbortSignal, quiet = false) => {
    const fd = new FormData()
    fd.append('file', file)
    return request<WatchlistImportResult>('/api/watchlist/import-csv', {
      method: 'POST',
      body: fd,
      signal,
      quiet,
    })
  },
  watchlistImportCodes: (text: string, signal?: AbortSignal) =>
    request<WatchlistImportResult>('/api/watchlist/import-codes', {
      method: 'POST',
      body: JSON.stringify({ text }),
      signal,
    }),
  watchlistRemove: (symbol: string) =>
    request<{ symbols: WatchlistEntry[] }>(
      `/api/watchlist/${encodeURIComponent(symbol)}`,
      { method: 'DELETE' },
    ),
  watchlistMoveToTop: (symbol: string) =>
    request<{ symbols: WatchlistEntry[] }>(
      `/api/watchlist/${encodeURIComponent(symbol)}/top`,
      { method: 'POST' },
    ),
  watchlistClear: () =>
    request<{ removed: number }>('/api/watchlist', { method: 'DELETE' }),
  watchlistQuotes: () => request<{ quotes: Quote[] }>('/api/watchlist/quotes'),
  watchlistEnriched: (extColumns?: string) =>
    request<{ rows: any[]; as_of: string | null; elapsed_ms: number }>(
      extColumns
        ? `/api/watchlist/enriched?ext_columns=${encodeURIComponent(extColumns)}`
        : '/api/watchlist/enriched',
    ),
  // [R169] 返回的是「手填 ⊕ 批次登记」的合并视图: held/cost/weight 语义不变,
  // 另附成本来源与批次信息, 供决策台标注来源、提示手填值与批次均价不一致。
  watchlistPositions: () =>
    request<{ positions: Record<string, EffectivePosition> }>('/api/watchlist/positions'),
  setWatchlistPosition: (symbol: string, held: boolean, cost: number | null, weight?: number | null) =>
    request<{ symbol: string; position: { held: boolean; cost: number | null; weight?: number | null; updated_at: string } }>(
      `/api/watchlist/positions/${encodeURIComponent(symbol)}`,
      { method: 'PUT', body: JSON.stringify({ held, cost, weight }) },
    ),
  stockSignals: () =>
    request<{ signals: Record<string, { signal: string; confidence: number; reason: string; close: number | null; created_at: string; watch_points?: { direction: 'up' | 'down'; price: number; label: string; action?: string; confidence?: number; reason: string }[] }> }>('/api/stock-analysis/signals'),
  generateStockSignal: (symbol: string) =>
    request<{ symbol: string; signal?: string; confidence?: number; reason?: string; close?: number | null; created_at?: string; error?: string }>(
      `/api/stock-analysis/signal/${encodeURIComponent(symbol)}`,
      { method: 'POST' },
    ),

  // timeframe='all' 时不传参数 → 后端不过滤周期, 返回日线+分钟合并列表
  screenerStrategies: async (assetType?: 'stock' | 'etf' | 'index', timeframe: '1d' | '1m' | 'all' = '1d') => {
    const data = await request<{ strategies: StrategyDetail[]; load_errors?: StrategyLoadError[] }>(
      `/api/strategies?${assetType ? `asset_type=${assetType}&` : ''}${timeframe !== 'all' ? `timeframe=${timeframe}` : ''}`,
    )
    return { presets: data.strategies, load_errors: data.load_errors }
  },
  screenerRunPreset: (strategy_id: string, pool?: string[], asOf?: string, extColumns?: string, assetType: 'stock' | 'etf' = 'stock', timeframe: '1d' | '1m' = '1d') =>
    request<ScreenerResult>('/api/screener/run_preset', {
      method: 'POST',
      timeoutMs: COMPUTE_REQUEST_TIMEOUT_MS,
      body: JSON.stringify({ strategy_id, pool, as_of: asOf ?? null, ext_columns: extColumns || null, asset_type: assetType, timeframe }),
    }),
  screenerRunCustom: (conditions: string[], orderBy?: string, limit = 30, pool?: string[], extColumns?: string, assetType: 'stock' | 'etf' = 'stock') =>
    request<ScreenerResult>('/api/screener/run', {
      method: 'POST',
      timeoutMs: COMPUTE_REQUEST_TIMEOUT_MS,
      body: JSON.stringify({ conditions, order_by: orderBy, limit, pool, ext_columns: extColumns || null, asset_type: assetType }),
    }),
  screenerRunAll: (asOf?: string, strategyIds?: string[], assetType: 'stock' | 'etf' = 'stock') =>
    request<ScreenerRunAllSummary>(
      '/api/screener/run_all', { method: 'POST', timeoutMs: COMPUTE_REQUEST_TIMEOUT_MS, body: JSON.stringify({ as_of: asOf ?? null, strategy_ids: strategyIds ?? null, asset_type: assetType, timeframe: '1d', summary_only: true }) },
    ),
  screenerCachedSummary: () =>
    request<ScreenerCachedSummary>('/api/screener/cached-summary'),
  screenerCachedResult: (strategyId: string, extColumns?: string) =>
    request<ScreenerCachedResult>(
      extColumns
        ? `/api/screener/cached-result/${encodeURIComponent(strategyId)}?ext_columns=${encodeURIComponent(extColumns)}`
        : `/api/screener/cached-result/${encodeURIComponent(strategyId)}`,
    ),
  screenerCached: (extColumns?: string) =>
    request<{ as_of: string | null; results: Record<string, { total: number; as_of: string; rows: any[] }>; today_ever_matched: Record<string, string[]> | null; today_ever_rows: Record<string, Record<string, any>> | null; updated_at: number | null }>(
      extColumns
        ? `/api/screener/cached?ext_columns=${encodeURIComponent(extColumns)}`
        : '/api/screener/cached',
    ),
  marketSnapshot: () =>
    request<{ as_of: string | null; rows: MarketSnapshotRow[] }>('/api/screener/market-snapshot'),
  overviewMarket: (asOf?: string) => request<OverviewMarket>(`/api/overview/market${asOf ? `?as_of=${asOf}` : ''}`),

  // 概念涨幅轮动矩阵: 每列(日期)各自把所有概念按当天涨幅从高到低排序
  rpsRotation: (days: number, kind?: 'concept' | 'industry', level?: number) =>
    request<RpsRotationData>(`/api/rps/rotation?days=${days}${kind ? `&kind=${kind}` : ''}${level ? `&level=${level}` : ''}`),

  // 市场环境(Regime)
  regimeHistory: (start?: string, end?: string, limit?: number) => {
    const params = new URLSearchParams()
    if (start) params.set('start', start)
    if (end) params.set('end', end)
    if (limit) params.set('limit', String(limit))
    const qs = params.toString()
    return request<RegimeHistory>(`/api/regime/history${qs ? `?${qs}` : ''}`)
  },
  regimeLatest: () => request<{ row: RegimeRow | null }>('/api/regime/latest'),
  regimeStates: (days = 60) => request<RegimeStates>(`/api/regime/states?days=${days}`),
  regimeCoverage: () => request<RegimeCoverage>('/api/regime/coverage'),
  regimePhaseLive: () => request<RegimePhaseLive>('/api/regime/phase/live'),
  regimeRecompute: (start?: string, end?: string) => {
    const params = new URLSearchParams()
    if (start) params.set('start', start)
    if (end) params.set('end', end)
    const qs = params.toString()
    return request<{ ok: boolean; computed: number; phase_days?: number; mainline_rows?: number }>(`/api/regime/recompute${qs ? `?${qs}` : ''}`, { method: 'POST' })
  },
  regimePhases: (start?: string, end?: string) => {
    const params = new URLSearchParams()
    if (start) params.set('start', start)
    if (end) params.set('end', end)
    const qs = params.toString()
    return request<PhaseSegments>(`/api/regime/phases${qs ? `?${qs}` : ''}`)
  },
  regimeMainline: (start?: string, end?: string, top = 10, kind: 'concept' | 'industry' = 'concept') => {
    const params = new URLSearchParams({ top: String(top), kind })
    if (start) params.set('start', start)
    if (end) params.set('end', end)
    return request<MainlineResult>(`/api/regime/mainline?${params.toString()}`)
  },
  regimeMainlineRecompute: () =>
    request<{ ok: boolean; rows: number }>('/api/regime/mainline/recompute', { method: 'POST' }),
  // [fork 增强] R28 板块跷跷板: GET 走规则(免费, 每次开页都算), POST 才调 AI 甄别并留档
  regimeSeesaw: (kind: 'concept' | 'industry' = 'concept') =>
    request<SeesawResult>(`/api/regime/seesaw?kind=${kind}`),
  regimeSeesawDetect: (kind: 'concept' | 'industry' = 'concept') =>
    request<SeesawResult>(`/api/regime/seesaw/detect?kind=${kind}`, { method: 'POST' }),
  mainlineFilterUpdate: (payload: { min_members?: number; max_members?: number; blacklist?: string[]; exclude_st?: boolean }) =>
    request<MainlineFilter>('/api/settings/preferences/mainline-filter', {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),

  limitLadder: (asOf?: string, extColumns?: string, direction?: 'up' | 'down') => {
    const params = new URLSearchParams()
    if (asOf) params.set('as_of', asOf)
    if (extColumns) params.set('ext_columns', extColumns)
    if (direction === 'down') params.set('direction', 'down')
    const qs = params.toString()
    return request<LimitLadderResult>(
      `/api/screener/limit-ladder${qs ? `?${qs}` : ''}`,
    )
  },

  backtestStatus: () => request<{ available: boolean }>('/api/backtest/status'),

  backtestRun: (payload: {
    symbols: string[]
    entries: string[]
    exits: string[]
    start?: string
    end?: string
    stop_loss_pct?: number
    max_hold_days?: number
    matching?: 'close_t' | 'open_t+1'
    asset_type?: 'stock' | 'etf' | 'index'
  }) =>
    request<BacktestResult>('/api/backtest/run', {
      method: 'POST',
      timeoutMs: COMPUTE_REQUEST_TIMEOUT_MS,
      body: JSON.stringify(payload),
    }),

  factorColumns: () =>
    request<{ columns: FactorColumn[] }>('/api/backtest/factor/columns'),

  factorLibrary: (assetType?: 'stock' | 'etf') =>
    request<{ factors: FactorLibraryItem[] }>(
      `/api/factors${assetType ? `?asset_type=${assetType}` : ''}`,
    ),

  factorValidate: (formula: string) =>
    request<FactorValidateResponse>('/api/factors/validate', {
      method: 'POST',
      body: JSON.stringify({ formula }),
    }),

  factorTrial: (payload: { formula: string; asset_type?: 'stock' | 'etf'; days?: number }) =>
    request<FactorTrialResponse>('/api/factors/trial', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  factorCustomCreate: (payload: {
    id?: string
    label: string
    group?: string
    formula: string
    description?: string
    direction?: 'high' | 'low' | 'none'
  }) =>
    request<{ ok: boolean; id: string; version: number }>('/api/factors/custom', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  factorCustomUpdate: (factorId: string, payload: {
    label: string
    group?: string
    formula: string
    description?: string
    direction?: 'high' | 'low' | 'none'
  }) =>
    request<{ ok: boolean; id: string; version: number; status: string }>(
      `/api/factors/custom/${encodeURIComponent(factorId)}/update`,
      { method: 'POST', body: JSON.stringify(payload) },
    ),

  factorCompositeCreate: (payload: {
    id?: string
    label: string
    group?: string
    members: Record<string, number>
    description?: string
    direction?: 'high' | 'low' | 'none'
  }) =>
    request<{ ok: boolean; id: string; version: number }>('/api/factors/composite', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  factorDelete: (factorId: string, force = false) =>
    request<{ ok: boolean; id: string; removed_references?: string[] }>(
      `/api/factors/custom/${encodeURIComponent(factorId)}${force ? '?force=true' : ''}`,
      { method: 'DELETE', quiet: true },
    ),

  factorSetStatus: (factorId: string, status: 'draft' | 'active' | 'watch' | 'retired') =>
    request<{ ok: boolean; id: string; status: string }>(
      `/api/factors/custom/${encodeURIComponent(factorId)}/status`,
      { method: 'POST', body: JSON.stringify({ status }) },
    ),

  factorSetGroup: (factorId: string, group: string) =>
    request<{ ok: boolean; id: string; group: string }>(
      `/api/factors/custom/${encodeURIComponent(factorId)}/group`,
      { method: 'POST', body: JSON.stringify({ group }) },
    ),

  factorRun: (payload: {
    factor_name: string
    symbols?: string[] | null
    start?: string | null
    end?: string | null
    n_groups?: number
    rebalance?: 'daily' | 'weekly' | 'monthly'
    weight?: 'equal' | 'factor_weight'
    fees_pct?: number
    slippage_bps?: number
    asset_type?: 'stock' | 'etf' | 'index'
  }) =>
    request<FactorBacktestResult>('/api/backtest/factor/run', {
      method: 'POST',
      timeoutMs: COMPUTE_REQUEST_TIMEOUT_MS,
      body: JSON.stringify(payload),
    }),

  factorBatch: (payload: {
    factor_names: string[]
    symbols?: string[] | null
    start?: string | null
    end?: string | null
    n_groups?: number
    rebalance?: 'daily' | 'weekly' | 'monthly'
    weight?: 'equal' | 'factor_weight'
    fees_pct?: number
    slippage_bps?: number
    asset_type?: 'stock' | 'etf' | 'index'
  }) =>
    request<FactorBatchResult>('/api/backtest/factor/batch', {
      method: 'POST',
      timeoutMs: COMPUTE_REQUEST_TIMEOUT_MS,
      body: JSON.stringify(payload),
    }),

  // [fork 增强] R35 每轮随机启用几个 key(0 = 全部)
  realtimeKeysPerRound: () =>
    request<{ count: number; total_keys: number }>(
      '/api/settings/preferences/realtime-keys-per-round'),
  setRealtimeKeysPerRound: (count: number) =>
    request<{ count: number; total_keys: number }>(
      '/api/settings/preferences/realtime-keys-per-round',
      { method: 'PUT', body: JSON.stringify({ count }) }),
  miningRuns: () =>
    request<{ items: MiningRun[] }>('/api/backtest/mining/runs'),

  /** [R55] 删一次挖掘运行(连同产物目录)。还没结束的删不掉(409) —— 先取消 */
  miningAvailability: (params: {
    assetType: 'stock' | 'etf'
    budgetProfile: MiningBudgetProfile
    start?: string
    end?: string
  }) => {
    const query = new URLSearchParams({
      asset_type: params.assetType,
      budget_profile: params.budgetProfile,
    })
    if (params.start) query.set('start', params.start)
    if (params.end) query.set('end', params.end)
    return request<MiningAvailability>(`/api/backtest/mining/availability?${query}`, {
      quiet: true,
    })
  },

  miningRun: (runId: string) =>
    request<MiningRun>(`/api/backtest/mining/runs/${encodeURIComponent(runId)}`),

  miningAutoStart: (payload: MiningAutoStartPayload) =>
    request<MiningAutoStartResponse>('/api/backtest/mining/auto', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  miningStart: (payload: MiningRequestV1) =>
    request<MiningRun>('/api/backtest/mining/runs', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  // [fork 增强] R110 竞价一进二扫描(昨日首板 × 当下竞价)
  auctionScan: (refresh = false) =>
    request<AuctionScanPayload>(`/api/abnormal/auction-scan${refresh ? '?refresh=true' : ''}`),
  // [fork 增强] R99 全球指数实时(独立模块, 新浪源)
  globalIndices: () =>
    request<{ items: GlobalIndexQuote[] }>('/api/global-indices'),
  globalIndexOptions: () =>
    request<{ presets: { key: string; name: string }[]; selected: string[] }>('/api/global-indices/options'),
  saveGlobalIndexSelection: (keys: string[]) =>
    request<{ selected: string[] }>('/api/global-indices/selection', { method: 'PUT', body: JSON.stringify({ keys }) }),
  // [fork 增强] R93 使用观察笔记: 纯文本, 增删改
  usageNotesList: () =>
    request<{ items: UsageNote[] }>('/api/usage-notes'),
  usageNoteCreate: (content: string) =>
    request<UsageNote>('/api/usage-notes', { method: 'POST', body: JSON.stringify({ content }) }),
  usageNoteUpdate: (id: string, patch: { content?: string; status?: string; pinned?: boolean; horizon?: string }) =>
    request<UsageNote>(`/api/usage-notes/${encodeURIComponent(id)}`, { method: 'PUT', body: JSON.stringify(patch) }),
  // [R180] 让 AI 凝练这一条(图片走多模态)
  usageNoteDigest: (id: string) =>
    request<UsageNote>(`/api/usage-notes/${encodeURIComponent(id)}/digest`, { method: 'POST' }),

  // [R180] 传图片/文本文件, 建一条带附件的记录。落盘即返回, 凝练是单独一步 ——
  // 上传要立刻有反馈, 不能卡在一次几十秒的 AI 调用上。
  usageNoteUpload: (file: File, content = '') => {
    const fd = new FormData()
    fd.append('file', file)
    return request<UsageNote>(
      `/api/usage-notes/upload?content=${encodeURIComponent(content)}`,
      { method: 'POST', body: fd })
  },

  // [R181] 到了兑现检查点、还没给结论的埋伏 —— 埋伏最容易失败的方式是记了之后忘了
  usageNotesDue: () =>
    request<{ items: UsageNote[] }>('/api/usage-notes/due'),

  usageNotesSummaryGet: () =>
    request<{ summary: NewsDeskSummary | null }>('/api/usage-notes/summary'),

  usageNotesSummaryBuild: () =>
    request<{ summary: NewsDeskSummary }>('/api/usage-notes/summary', { method: 'POST' }),

  usageNoteDelete: (id: string) =>
    request<{ ok: boolean }>(`/api/usage-notes/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  miningResult: (runId: string) =>
    request<MiningResult>(`/api/backtest/mining/runs/${encodeURIComponent(runId)}/result`),

  miningCancel: (runId: string) =>
    request<MiningRun>(`/api/backtest/mining/runs/${encodeURIComponent(runId)}/cancel`, {
      method: 'POST',
    }),

  miningPromote: (runId: string, signature: string) =>
    request<ResearchCandidate>(
      `/api/backtest/mining/runs/${encodeURIComponent(runId)}/candidates/${encodeURIComponent(signature)}/promote`,
      { method: 'POST' },
    ),

  miningPublish: (runId: string, signature: string) =>
    request<{ ok: boolean; strategy_id: string }>(
      `/api/backtest/mining/runs/${encodeURIComponent(runId)}/candidates/${encodeURIComponent(signature)}/publish`,
      { method: 'POST' },
    ),

  miningConfig: () =>
    request<MiningScheduleConfig>('/api/backtest/mining/config'),

  updateMiningConfig: (payload: Partial<MiningScheduleConfig>) =>
    request<MiningScheduleConfig>('/api/backtest/mining/config', {
      method: 'PATCH',
      body: JSON.stringify(payload),
    }),

  researchCandidates: () =>
    request<{ items: ResearchCandidate[] }>('/api/backtest/candidates'),

  researchCandidateCreate: (payload: ResearchCandidateCreate) =>
    request<ResearchCandidate>('/api/backtest/candidates', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  researchCandidateUpdate: (
    id: string,
    payload: { name?: string; status?: ResearchCandidateStatus },
  ) =>
    request<ResearchCandidate>(`/api/backtest/candidates/${encodeURIComponent(id)}`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    }),

  researchCandidateDelete: (id: string) =>
    request<{ ok: boolean }>(`/api/backtest/candidates/${encodeURIComponent(id)}`, {
      method: 'DELETE',
    }),

  strategyBacktestRun: (payload: {
    strategy_id: string
    symbols?: string[] | null
    start?: string | null
    end?: string | null
    params?: Record<string, any> | null
    overrides?: Record<string, any> | null
    matching?: 'close_t' | 'open_t+1'
    entry_fill?: 'close_t' | 'open_t+1' | null
    exit_fill?: 'close_t' | 'open_t+1' | 'signal_next_minute' | null
    fees_pct?: number
    commission_pct?: number
    stamp_tax_pct?: number
    slippage_bps?: number
    max_positions?: number
    initial_capital?: number
    position_sizing?: 'equal' | 'score_weight'
    asset_type?: 'stock' | 'etf' | 'index'
    minute_fill?: boolean
  }) =>
    request<StrategyBacktestResult>('/api/backtest/strategy/run', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  // [R50] 「AI 打板复盘」(原「AI 战法」, 已从连板梯队页搬到复盘页):
  // 梯队快照 → 龙头/二进三/反包候选分组(带置信度);
  // messages 传对话可追问; reportId 传历史报告 id 可对旧报告续问(复用其存档快照)
  ladderAiReview: (payload: { date: string; stats: Record<string, unknown>; tiers: unknown[] }, messages: { role: 'user' | 'assistant'; content: string }[] = [], reportId?: string) =>
    request<{ text: string; report_id: string | null }>('/api/screener/ladder-ai', {
      method: 'POST',
      body: JSON.stringify({ ...payload, messages, report_id: reportId ?? '' }),
    }),
  ladderAiReports: () =>
    request<{ reports: { id: string; date: string; created_at: string; text: string }[] }>('/api/screener/ladder-ai/reports'),
  ladderAiDeleteReport: (id: string) =>
    request<{ ok: boolean }>(`/api/screener/ladder-ai/reports/${id}`, { method: 'DELETE' }),

  pipelineRun: () => request<{ job_id: string; reused: boolean }>(
    '/api/pipeline/run', { method: 'POST' },
  ),
  // [fork] quiet: 轮询期间不弹错误提示 —— 作者这次没动这个入参, 保留
  pipelineJob: (id: string, quiet = false) =>
    request<PipelineJob>(`/api/pipeline/jobs/${id}`, { quiet }),
  /** 手动停止一个 running/pending 的同步任务 (协作式: 当前分块完成后线程自行退出) */
  pipelineJobCancel: (id: string) =>
    request<{ cancelled: string }>(`/api/pipeline/jobs/${id}/cancel`, { method: 'POST' }),
  pipelineJobs: (limit = 20) =>
    request<{ active_id: string | null; jobs: PipelineJobSummary[] }>(
      `/api/pipeline/jobs?limit=${limit}`,
    ),

  dataStatus: () => request<DataStatus>('/api/data/status'),
  dataClear: () => request<{ deleted_files: number }>('/api/data/clear', { method: 'POST' }),
  refreshCache: () => request<{ ok: boolean }>('/api/data/refresh-cache', { method: 'POST' }),
  enrichedSchema: (table: string) => request<EnrichedField[]>(`/api/data/schema/${table}`),

  testEndpoint: (url: string, rounds?: number) =>
    request<{
      ok: boolean
      url: string
      rounds: number
      success: number
      median_ms: number | null
      min_ms?: number | null
      max_ms?: number | null
      /** 兼容旧字段,等于 median_ms */
      latency_ms?: number | null
      error?: string
    }>(
      '/api/settings/test_endpoint', {
        method: 'POST',
        body: JSON.stringify({ url, rounds }),
      },
    ),

  // 端点发现 —— 后端代理拉取 tickflow.org/endpoints.json(前端无法跨域直连)
  listEndpoints: () =>
    request<EndpointManifest>('/api/settings/endpoints'),

  switchEndpoint: (url: string) =>
    request<{ ok: boolean; current_endpoint: string; error?: string }>(
      '/api/settings/switch_endpoint', {
        method: 'POST',
        body: JSON.stringify({ url }),
      },
    ),

  // ===== 扩展数据 =====
  extDataList: () =>
    request<{ items: ExtDataConfig[] }>('/api/ext-data'),

  extDataRows: (id: string, opts?: { date?: string; limit?: number; columns?: string[] }) => {
    const qs = new URLSearchParams()
    if (opts?.date) qs.set('date', opts.date)
    if (opts?.limit) qs.set('limit', String(opts.limit))
    if (opts?.columns?.length) qs.set('columns', opts.columns.join(','))
    const suffix = qs.toString()
    return request<ExtDataRowsResult>(`/api/ext-data/${encodeURIComponent(id)}/rows${suffix ? `?${suffix}` : ''}`)
  },

  dimensionMembers: (id: string, opts: { field: string; value: string; date?: string; limit?: number }) => {
    const qs = new URLSearchParams({ field: opts.field, value: opts.value })
    if (opts.date) qs.set('date', opts.date)
    if (opts.limit) qs.set('limit', String(opts.limit))
    return request<DimensionMembersResult>(`/api/ext-data/${encodeURIComponent(id)}/dimension-members?${qs.toString()}`)
  },

  dimensionIntraday: (id: string, opts: { field: string; value: string; date?: string }) => {
    const qs = new URLSearchParams({ field: opts.field, value: opts.value })
    if (opts.date) qs.set('date', opts.date)
    return request<DimensionIntradayResult>(`/api/ext-data/${encodeURIComponent(id)}/dimension-intraday?${qs.toString()}`)
  },

  analysisMenus: () =>
    request<{ items: AnalysisMenu[] }>('/api/analysis-menus'),

  analysisMenu: (id: string) =>
    request<AnalysisMenu>(`/api/analysis-menus/${encodeURIComponent(id)}`),

  analysisMenuSave: (id: string, body: Omit<AnalysisMenu, 'id' | 'created_at' | 'updated_at' | 'builtin'>) =>
    request<AnalysisMenu>(`/api/analysis-menus/${encodeURIComponent(id)}`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  analysisMenuReorder: (ids: string[]) =>
    request<{ items: AnalysisMenu[] }>('/api/analysis-menus/reorder', {
      method: 'POST',
      body: JSON.stringify({ ids }),
    }),

  analysisMenuDelete: (id: string) =>
    request<{ status: string }>(`/api/analysis-menus/${encodeURIComponent(id)}`, { method: 'DELETE' }),

  extDataCreate: (body: { id: string; label: string; mode: 'snapshot' | 'timeseries'; fields: { name: string; dtype: string; label: string }[]; description?: string; symbol_map?: Record<string, string>; code_map?: Record<string, string> }) =>
    request<ExtDataConfig>('/api/ext-data', {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  extDataUpdate: (id: string, body: { label?: string; fields?: { name: string; dtype: string; label: string }[]; description?: string }) =>
    request<ExtDataConfig>(`/api/ext-data/${id}`, {
      method: 'PUT',
      body: JSON.stringify(body),
    }),

  extDataDelete: (id: string) =>
    request<{ status: string }>(`/api/ext-data/${id}`, { method: 'DELETE' }),

  extDataUpload: (id: string, file: File, snapshotDate?: string) => {
    const fd = new FormData()
    fd.append('file', file)
    return request<{ status: string; rows: number; date: string }>(
      `/api/ext-data/${id}/upload${snapshotDate ? `?snapshot_date=${snapshotDate}` : ''}`,
      { method: 'POST', body: fd },
    )
  },

  extDataIngest: (id: string, body: { date?: string; rows: Record<string, unknown>[] }) =>
    request<{ status: string; rows: number; date: string }>(
      `/api/ext-data/${id}/ingest`,
      { method: 'POST', body: JSON.stringify(body) },
    ),

  extDataSchemaAll: () =>
    request<{ items: { id: string; label: string; mode: string; columns: { name: string; type: string; label: string }[] }[] }>('/api/ext-data/schema-all'),

  extDataPullConfig: (id: string, body: {
    url: string; method?: string; headers?: Record<string, string>; body?: string;
    response_path?: string; field_map?: Record<string, string>;
    schedule_minutes?: number; enabled?: boolean;
    time_window_start?: string | null; time_window_end?: string | null;
    date_param?: string | null;
    auth?: ExtPullAuth;
  }) =>
    request<{ status: string; pull: PullConfig }>(
      `/api/ext-data/${id}/pull`,
      { method: 'PUT', body: JSON.stringify(body) },
    ),

  /** 查询拉取接口 API Key 状态 (脱敏, 不返回明文) */
  extDataApiKey: (id: string) =>
    request<{ key_set: boolean; masked_key: string }>(
      `/api/ext-data/${encodeURIComponent(id)}/api-key`,
    ),

  /** 设置 (或空串清除) 拉取接口的 API Key */
  extDataApiKeySet: (id: string, key: string) =>
    request<{ status: string; key_set: boolean; masked_key: string }>(
      `/api/ext-data/${encodeURIComponent(id)}/api-key`,
      { method: 'PUT', body: JSON.stringify({ key }) },
    ),

  extDataPullTest: (id: string) =>
    request<{ status: string; total_rows: number; preview: Record<string, unknown>[]; has_symbol: boolean }>(
      `/api/ext-data/${id}/pull/test`,
      { method: 'POST' },
    ),

  extDataPullRun: (id: string) =>
    request<{ status: string; rows: number; date: string }>(
      `/api/ext-data/${id}/pull/run`,
      { method: 'POST' },
    ),

  /** 历史回补: 按本地交易日逐日拉取写入 timeseries 分区 (需 pull.date_param) */
  extDataBackfill: (id: string, start: string, end: string) =>
    request<ExtDataBackfillResult>(
      `/api/ext-data/${encodeURIComponent(id)}/backfill?start=${start}&end=${end}`,
      { method: 'POST' },
    ),

  // 内置预设 (概念/行业) 手动获取数据: 走结构转换, 保证 schema 一致
  extDataPresetFetch: (id: string) =>
    request<{ status: string; rows: number }>(
      `/api/ext-data/presets/${id}/fetch`,
      { method: 'POST' },
    ),

  extDataDetectFields: (file: File) => {
    const fd = new FormData()
    fd.append('file', file)
    return request<{ fields: { name: string; dtype: string; label: string }[]; rows: number; symbol_candidates: string[]; code_candidates: string[] }>(
      '/api/ext-data/detect-fields',
      { method: 'POST', body: fd },
    )
  },

  extDataDetectUrl: (body: ExtDataDetectUrlRequest) =>
    request<ExtDataDetectUrlResult>('/api/ext-data/detect-url', {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  extDataFixSymbol: (id: string) =>
    request<{ status: string; fixed_files: number }>(
      `/api/ext-data/${id}/fix-symbol`,
      { method: 'POST' },
    ),

  // ===== Financials =====
  financialStatus: () =>
    request<FinancialStatus>('/api/financials/status'),

  financialMetrics: (symbol?: string) =>
    request<{ data: FinancialMetricRecord[] }>(
      `/api/financials/metrics${symbol ? `?symbol=${encodeURIComponent(symbol)}` : ''}`,
    ),

  financialIncome: (symbol?: string) =>
    request<{ data: FinancialIncomeRecord[] }>(
      `/api/financials/income${symbol ? `?symbol=${encodeURIComponent(symbol)}` : ''}`,
    ),

  financialBalanceSheet: (symbol?: string) =>
    request<{ data: FinancialBalanceSheetRecord[] }>(
      `/api/financials/balance-sheet${symbol ? `?symbol=${encodeURIComponent(symbol)}` : ''}`,
    ),

  financialCashFlow: (symbol?: string) =>
    request<{ data: FinancialCashFlowRecord[] }>(
      `/api/financials/cash-flow${symbol ? `?symbol=${encodeURIComponent(symbol)}` : ''}`,
    ),

  financialShares: (symbol?: string) =>
    request<{ data: FinancialSharesRecord[] }>(
      `/api/financials/shares${symbol ? `?symbol=${encodeURIComponent(symbol)}` : ''}`,
    ),

  /** 触发财务数据同步(后台异步执行,接口立即返回 started 状态) */
  financialSync: (table: string) =>
    request<{ status: string; synced: { started: boolean; reason?: string } }>(
      `/api/financials/sync/${table}`, { method: 'POST' },
    ),

  /** AI 分析报告 CRUD */
  financialReportsList: () =>
    request<{ reports: AiFinancialReport[] }>('/api/financials/reports'),

  financialReportSave: (r: {
    symbol: string; name?: string; focus?: string; content: string
    periods?: number; summary?: string
  }) =>
    request<{ ok: boolean; report: AiFinancialReport }>('/api/financials/reports', {
      method: 'POST', body: JSON.stringify(r),
    }),

  financialReportDelete: (reportId: string) =>
    request<{ ok: boolean }>(`/api/financials/reports/${encodeURIComponent(reportId)}`, { method: 'DELETE' }),

  /**
   * AI 财务分析 — 流式调用。
   *
   * 返回一个可逐行读取的 async generator,每行是 JSON:
   *   {type:"meta",symbol,summary,periods}
   *   {type:"delta",content:"..."}    ← 文本片段,逐个累加
   *   {type:"error",message:"..."}
   *   {type:"done"}
   *
   * 用 ReadableStream 解析(而非 SSE EventSource),支持 POST body 且更简单。
   */
  async *financialAnalyzeStream(symbol: string, focus?: string): AsyncGenerator<{
    type: 'meta' | 'delta' | 'error' | 'done'
    symbol?: string
    summary?: string
    periods?: number
    content?: string
    message?: string
  }> {
    const res = await fetch('/api/financials/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ symbol, focus: focus ?? '' }),
    })
    if (!res.ok) {
      let detail = ''
      try { const j = JSON.parse(await res.text()); detail = j.detail ?? j.message ?? '' } catch { /* ignore */ }
      const msg = detail || `${res.status} ${res.statusText}`
      toast(msg, 'error')
      throw new Error(msg)
    }
    if (!res.body) throw new Error('响应无 body')

    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let buf = ''
    for (;;) {
      const { done, value } = await reader.read()
      if (done) break
      buf += decoder.decode(value, { stream: true })
      // 按行分割(保留最后不完整的行在 buf)
      const lines = buf.split('\n')
      buf = lines.pop() ?? ''
      for (const line of lines) {
        const s = line.trim()
        if (!s) continue
        try {
          yield JSON.parse(s)
        } catch {
          // 忽略无法解析的行
        }
      }
    }
    // 处理残余
    if (buf.trim()) {
      try { yield JSON.parse(buf.trim()) } catch { /* ignore */ }
    }
  },

  // ===== 个股分析 =====
  stockAnalysisLevels: (symbol: string, days = 120) =>
    request<StockLevels>(`/api/stock-analysis/levels?symbol=${encodeURIComponent(symbol)}&days=${days}`),

  // [fork 增强] 今日总览(决策汇聚层)
  todayOverview: () => request<TodayOverview>('/api/today'),
  intradayRefreshFull: () =>
    request<{ full_coverage?: boolean; rounds?: number; live_count?: number | null; error?: string }>(
      '/api/intraday/refresh-full', { method: 'POST' }),
  // [fork 增强] AI 定时配置(今日总览导读·优选 / 个股信号批量)
  todayAiScheduleGet: () => request<TodayAiSchedule>('/api/settings/preferences/today-ai-schedule'),
  todayAiScheduleSet: (body: TodayAiSchedule) =>
    request<TodayAiSchedule>('/api/settings/preferences/today-ai-schedule',
      { method: 'PUT', body: JSON.stringify(body) }),
  signalAiScheduleGet: () => request<SignalAiSchedule>('/api/settings/preferences/signal-ai-schedule'),
  signalAiScheduleSet: (body: SignalAiSchedule) =>
    request<SignalAiSchedule>('/api/settings/preferences/signal-ai-schedule',
      { method: 'PUT', body: JSON.stringify(body) }),
  /** [R147] note 可省 —— 不填就是原来的行为, 填了一起送进这次分析 */
  todayAi: (note?: string) =>
    request<{ brief?: string; picks?: TodayPick[]; analyzed?: number
              verify?: TodayPickVerify; note?: string; error?: string }>(
      '/api/today/ai', { method: 'POST', body: JSON.stringify({ note: note || null }) }),
  /** [R121] AI 优选历史命中率 —— 「靠不靠谱」的硬证据, 纯事后统计 */
  todayAiTrackRecord: () => request<AiTrackRecord>('/api/today/ai/track-record'),
  /** [R133] 规则层把握分体检: 分层胜率/排名段/因子归因/同期基准 */
  todayScoreLedger: () => request<ScoreLedger>('/api/today/score-ledger'),

  // [R175] 显式生成 AI 提炼。今天已经跑过的话服务端直接回存档 —— 打开弹窗
  // 不会自动调它, 免得点一次烧一次。
  todayScoreLedgerDigest: () =>
    request<PatternDigest>('/api/today/score-ledger/digest', { method: 'POST' }),

  todayScoreLedgerDigestHistory: (limit = 30) =>
    request<{ entries: PatternDigest[] }>(
      `/api/today/score-ledger/digest/history?limit=${limit}`),
  /** [R133] 明细 CSV 的地址 —— 交给 <a download>, 不走 fetch(浏览器直接落文件) */
  todayScoreLedgerExportUrl: () => `${BASE}/api/today/score-ledger/export`,
  todaySavePrefs: (body: Partial<TodayPrefs>) =>
    request<TodayPrefs>('/api/today/prefs', { method: 'PUT', body: JSON.stringify(body) }),

  // [fork 增强] 持仓出场线
  watchlistExitLines: () =>
    request<{ lines: Record<string, ExitLine> }>('/api/watchlist/exit-lines'),

  // [fork 增强] 六态趋势
  stockTrend: (symbol: string) =>
    request<TrendDetail>(`/api/stock-analysis/trend?symbol=${encodeURIComponent(symbol)}`),

  stockTrends: (symbols: string[]) =>
    request<{ trends: Record<string, TrendInfo> }>(
      `/api/stock-analysis/trends?symbols=${encodeURIComponent(symbols.join(','))}`),

  /** [R42] 批量 Keltner 三档位置(决策台短/中/长通道三列)。收盘口径, 与图表同一组公式 */
  // [R178] 批量「该动了」判定 —— 决策台默认按它排序
  stockUrgency: (symbols: string[]) =>
    request<{ urgency: Record<string, Urgency>; event?: Record<string, ChannelEvent>
              phase?: Record<string, ChannelPhase>
              playbook?: Record<string, Playbook> }>(
      `/api/stock-analysis/urgency?symbols=${encodeURIComponent(symbols.join(','))}`),

  /** [R203] 27 种组合速查表。无参数、结果恒定 —— 前端按天缓存即可 */
  comboTable: () =>
    request<{ rows: ComboTableRow[] }>('/api/stock-analysis/combo-table'),

  stockKeltner: (symbols: string[]) =>
    request<{ keltner: Record<string, KeltnerBands> }>(
      `/api/stock-analysis/keltner?symbols=${encodeURIComponent(symbols.join(','))}`),

  /** [R48] 单只逐日复盘(趋势 / 三档结论 / 涨停同一条时间轴)。收盘口径 */
  stockReview: (symbol: string, days = 120) =>
    request<StockReview>(
      `/api/stock-analysis/review?symbol=${encodeURIComponent(symbol)}&days=${days}`),

  stockTrendBacktest: (symbol: string, useAi = true) =>
    request<TrendBacktestResult>('/api/stock-analysis/trend/backtest', {
      method: 'POST', body: JSON.stringify({ symbol, use_ai: useAi }),
    }),

  stockTrendSetThreshold: (symbol: string, threshold: number | null, source: 'manual' | 'ai' | 'rule' = 'manual') =>
    request<{ symbol: string | null; threshold: number; source: string }>('/api/stock-analysis/trend/threshold', {
      method: 'PUT', body: JSON.stringify({ symbol, threshold, source }),
    }),

  stockAnalysisReportsList: () =>
    request<{ reports: AiStockReport[] }>('/api/stock-analysis/reports'),

  stockAnalysisReportSave: (r: {
    symbol: string; name?: string; focus?: string; content: string
    summary?: string; close?: number | null
    levels?: Record<LevelType, PriceLevel[]>
  }) =>
    request<{ ok: boolean; report: AiStockReport }>('/api/stock-analysis/reports', {
      method: 'POST', body: JSON.stringify(r),
    }),

  stockAnalysisReportDelete: (reportId: string) =>
    request<{ ok: boolean }>(`/api/stock-analysis/reports/${encodeURIComponent(reportId)}`, { method: 'DELETE' }),

  /**
   * AI 个股四维分析 — 流式调用(NDJSON,与财务分析同协议)。
   * meta 里额外带 levels(关键价位)供图表回放。
   */
  async *stockAnalyzeStream(symbol: string, focus?: string): AsyncGenerator<{
    type: 'meta' | 'delta' | 'error' | 'done'
    symbol?: string
    summary?: string
    levels?: Record<LevelType, PriceLevel[]>
    close?: number | null
    content?: string
    message?: string
  }> {
    const res = await fetch('/api/stock-analysis/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ symbol, focus: focus ?? '' }),
    })
    if (!res.ok) {
      let detail = ''
      try { const j = JSON.parse(await res.text()); detail = j.detail ?? j.message ?? '' } catch { /* ignore */ }
      const msg = detail || `${res.status} ${res.statusText}`
      toast(msg, 'error')
      throw new Error(msg)
    }
    if (!res.body) throw new Error('响应无 body')

    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let buf = ''
    for (;;) {
      const { done, value } = await reader.read()
      if (done) break
      buf += decoder.decode(value, { stream: true })
      const lines = buf.split('\n')
      buf = lines.pop() ?? ''
      for (const line of lines) {
        const s = line.trim()
        if (!s) continue
        try { yield JSON.parse(s) } catch { /* ignore */ }
      }
    }
    if (buf.trim()) {
      try { yield JSON.parse(buf.trim()) } catch { /* ignore */ }
    }
  },

  // ===== 大盘复盘 =====
  reviewReportsList: () =>
    request<{ reports: AiReviewReport[] }>('/api/market-recap/reports'),

  /** 龙虎榜三榜 (fuyao 专有; 历史日按服务端缓存, 当日未发布自动回退上一期) */
  dragonTiger: (date?: string) =>
    request<DragonTigerPayload>(
      `/api/market-recap/dragon-tiger${date ? `?date=${encodeURIComponent(date)}` : ''}`,
    ),

  /** 盘前风向标 (fuyao 专有; 同花顺竞价筛选名单, 含当日/次日真实收益) */
  auctionBenchmark: (date?: string) =>
    request<AuctionBenchmarkPayload>(
      `/api/market-recap/auction-benchmark${date ? `?date=${encodeURIComponent(date)}` : ''}`,
    ),

  reviewReportSave: (r: {
    as_of: string; focus?: string; content: string
    summary?: string; emotion_score?: number | null; emotion_label?: string
    mode?: 'today' | 'continuity' | 'week'
    push?: boolean
  }) =>
    request<{ ok: boolean; report: AiReviewReport }>('/api/market-recap/reports', {
      method: 'POST', body: JSON.stringify(r),
    }),

  reviewReportDelete: (reportId: string) =>
    request<{ ok: boolean }>(`/api/market-recap/reports/${encodeURIComponent(reportId)}`, { method: 'DELETE' }),

  /**
   * AI 大盘复盘 — 流式调用(NDJSON,与个股/财务分析同协议)。
   * meta 里带 as_of / emotion_score / emotion_label / summary,供前端先渲染信号灯。
   */
  async *reviewStream(asOf?: string, focus?: string, mode: 'today' | 'continuity' | 'week' = 'today'): AsyncGenerator<{
    type: 'meta' | 'delta' | 'error' | 'done'
    as_of?: string
    emotion_score?: number
    emotion_label?: string
    summary?: string
    content?: string
    message?: string
  }> {
    const res = await fetch('/api/market-recap/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ as_of: asOf ?? null, focus: focus ?? '', mode }),
    })
    if (!res.ok) {
      let detail = ''
      try { const j = JSON.parse(await res.text()); detail = j.detail ?? j.message ?? '' } catch { /* ignore */ }
      const msg = detail || `${res.status} ${res.statusText}`
      toast(msg, 'error')
      throw new Error(msg)
    }
    if (!res.body) throw new Error('响应无 body')

    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let buf = ''
    for (;;) {
      const { done, value } = await reader.read()
      if (done) break
      buf += decoder.decode(value, { stream: true })
      const lines = buf.split('\n')
      buf = lines.pop() ?? ''
      for (const line of lines) {
        const s = line.trim()
        if (!s) continue
        try { yield JSON.parse(s) } catch { /* ignore */ }
      }
    }
    if (buf.trim()) {
      try { yield JSON.parse(buf.trim()) } catch { /* ignore */ }
    }
  },

  /** AI 概念轮动分析 — 流式 NDJSON。 */
  async *rotationAnalyzeStream(days: number, focus?: string, kind?: 'concept' | 'industry', level?: number): AsyncGenerator<{
    type: 'meta' | 'delta' | 'error' | 'done'
    days?: number
    summary?: string
    content?: string
    message?: string
  }> {
    const res = await fetch('/api/rps/rotation-analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ days, focus: focus ?? '', kind: kind ?? 'concept', level: level ?? null }),
    })
    if (!res.ok) {
      let detail = ''
      try { const j = JSON.parse(await res.text()); detail = j.detail ?? j.message ?? '' } catch { /* ignore */ }
      const msg = detail || `${res.status} ${res.statusText}`
      toast(msg, 'error')
      throw new Error(msg)
    }
    if (!res.body) throw new Error('响应无 body')

    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let buf = ''
    for (;;) {
      const { done, value } = await reader.read()
      if (done) break
      buf += decoder.decode(value, { stream: true })
      const lines = buf.split('\n')
      buf = lines.pop() ?? ''
      for (const line of lines) {
        const s = line.trim()
        if (!s) continue
        try { yield JSON.parse(s) } catch { /* ignore */ }
      }
    }
    if (buf.trim()) {
      try { yield JSON.parse(buf.trim()) } catch { /* ignore */ }
    }
  },

  // ===== Strategy Engine =====
  strategyList: (assetType?: 'stock' | 'etf', timeframe: '1d' | '1m' | 'all' = '1d', includeResearch = false) => {
    const params = new URLSearchParams()
    if (assetType) params.set('asset_type', assetType)
    if (timeframe && timeframe !== 'all') params.set('timeframe', timeframe)
    if (includeResearch) params.set('include_research', 'true')
    const qs = params.toString()
    return request<{ strategies: StrategyDetail[]; load_errors?: StrategyLoadError[] }>(
      `/api/strategies${qs ? `?${qs}` : ''}`,
    )
  },

  strategyGet: (id: string) =>
    request<StrategyDetail>(`/api/strategies/${id}`),

  /** 发布 research_only 的 AI 草稿策略(翻转为公开) */
  strategyPublish: (strategyId: string) =>
    request<{ ok: boolean; strategy_id: string }>(`/api/strategies/${encodeURIComponent(strategyId)}/publish`, { method: 'POST' }),

  strategyRun: (strategyId: string, params?: Record<string, any>, asOf?: string, pool?: string[]) =>
    request<ScreenerResult>('/api/strategies/run', {
      method: 'POST',
      body: JSON.stringify({ strategy_id: strategyId, params, as_of: asOf ?? null, pool }),
    }),

  strategyRunAll: (asOf?: string) =>
    request<{ as_of: string | null; results: Record<string, { total: number; as_of: string }> }>(
      '/api/strategies/run-all',
      { method: 'POST', body: JSON.stringify({ as_of: asOf ?? null }) },
    ),

  strategySaveConfig: (strategyId: string, overrides: Record<string, any>) =>
    request<{ ok: boolean }>('/api/strategies/config', {
      method: 'POST',
      body: JSON.stringify({ strategy_id: strategyId, overrides }),
    }),

  strategyPatchConfig: (strategyId: string, overrides: Record<string, any>) =>
    request<{ ok: boolean }>('/api/strategies/config', {
      method: 'PATCH',
      body: JSON.stringify({ strategy_id: strategyId, overrides }),
    }),

  strategyResetConfig: (strategyId: string) =>
    request<{ ok: boolean }>(`/api/strategies/config/${strategyId}`, { method: 'DELETE' }),

  /** 删除自定义策略（内置策略不可删除） */
  strategyDelete: (strategyId: string) =>
    request<{ ok: boolean }>(`/api/strategies/${strategyId}`, { method: 'DELETE' }),

  strategyReload: () =>
    request<{ ok: boolean; count: number }>('/api/strategies/reload', { method: 'POST' }),

  // ===== Custom Signals (自定义信号) =====
  customSignalsList: () =>
    request<{ signals: CustomSignal[] }>('/api/custom-signals'),

  customSignalsOptions: () =>
    request<CustomSignalOptions>('/api/custom-signals/options'),

  customSignalSave: (signal: CustomSignal) =>
    request<{ ok: boolean; signal: CustomSignal }>('/api/custom-signals', {
      method: 'POST',
      body: JSON.stringify(signal),
    }),

  customSignalDelete: (id: string) =>
    request<{ ok: boolean }>(`/api/custom-signals/${encodeURIComponent(id)}`, { method: 'DELETE' }),

  customSignalsAiGenerate: (description: string) =>
    request<CustomSignalAIGenerateResult>('/api/custom-signals/ai/generate', {
      method: 'POST',
      body: JSON.stringify({ description }),
    }),

  // ===== Abnormal Moves (异动监控: 竞价/盘中/偏移) =====
  abnormalOverview: (minCloseness = 0.5, limit = 200) =>
    request<AbnormalOverview>(
      `/api/abnormal/overview?min_closeness=${minCloseness}&limit=${limit}`,
    ),

  /** 盘中异动: enriched 当日信号命中行 (涨停/炸板/翘板/跌停/新高/新低/放量) */
  abnormalIntraday: (limit = 500) =>
    request<AbnormalIntradayPayload>(`/api/abnormal/intraday?limit=${limit}`),

  // ===== Monitor Rules (监控规则) =====
  // [R159] 推送焦点名单
  focusList: () => request<FocusView>('/api/focus'),
  focusOverride: (symbol: string, mode: 'pin' | 'mute' | null) =>
    request<FocusView>('/api/focus/override', { method: 'PUT', body: JSON.stringify({ symbol, mode }) }),
  focusPrefs: (focus_only: boolean) =>
    request<FocusView>('/api/focus/prefs', { method: 'PUT', body: JSON.stringify({ focus_only }) }),
  monitorRulesList: () =>
    request<{ rules: MonitorRule[] }>('/api/monitor-rules'),

  monitorRuleOptions: () =>
    request<MonitorRuleOptions>('/api/monitor-rules/options'),

  monitorRuleSave: (rule: MonitorRule) =>
    request<{ ok: boolean; rule: MonitorRule }>('/api/monitor-rules', {
      method: 'POST',
      body: JSON.stringify(rule),
    }),

  monitorRuleDelete: (id: string) =>
    request<{ ok: boolean }>(`/api/monitor-rules/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  monitorRulesBatchChannels: (body: { rule_ids?: string[] | null; channels: string[]; mode: 'set' | 'add' | 'remove' }) =>
    request<{ ok: boolean; updated: number }>('/api/monitor-rules/batch-channels', {
      method: 'POST', body: JSON.stringify(body),
    }),

  // ===== Lots (批次登记, 页面名"持仓提醒"; 保存/删除自动同步监控规则) =====
  lotsList: () =>
    request<{ lots: Lot[] }>('/api/lots'),

  lotSave: (lot: Lot) =>
    request<{ ok: boolean; lot: Lot }>('/api/lots', {
      method: 'POST',
      body: JSON.stringify(lot),
    }),

  lotDelete: (id: string) =>
    request<{ ok: boolean }>(`/api/lots/${encodeURIComponent(id)}`, { method: 'DELETE' }),

  /** 模拟触发 ladder 封单监控 (Dev 调试, 不落盘不推送) */
  monitorRuleTestLadder: () =>
    request<{
      ok: boolean
      as_of: string
      sealed_count: number
      triggered: Array<{
        rule_id: string; rule_name: string; symbol: string; name?: string
        type: string; message: string; severity: string
        sealed_value: number; sealed_metric: string
        current_sealed_vol?: number; current_sealed_amount?: number
      }>
      not_triggered: Array<{
        rule_id: string; rule_name: string; symbol: string
        metric: string; threshold: number; current_value: number | null
        current_sealed_vol?: number; current_sealed_amount?: number | null
        reason: string
      }>
    }>('/api/monitor-rules/test-ladder', { method: 'POST' }),

  /** 真实触发 ladder 预警 (落盘+飞书+SSE), Dev 调试用 */
  monitorRuleTriggerLadder: () =>
    request<{
      ok: boolean
      triggered: number
      events: Array<{ symbol: string; name: string; message: string }>
    }>('/api/monitor-rules/trigger-ladder', { method: 'POST' }),

  /** 生成演示监控规则 (Dev 页用) */
  monitorRuleSeed: () =>
    request<{ ok: boolean; generated: number }>('/api/monitor-rules/seed', { method: 'POST' }),

  // ===== Alerts (触发记录) =====
  alertsList: (params?: { days?: number; limit?: number; source?: string; type?: string; extColumns?: string; focus?: boolean }) => {
    const qs = new URLSearchParams()
    if (params?.focus) qs.set('focus', '1')   // [R160] 只要焦点内的, total 也按过滤后算
    if (params?.days) qs.set('days', String(params.days))
    if (params?.limit) qs.set('limit', String(params.limit))
    if (params?.source) qs.set('source', params.source)
    if (params?.type) qs.set('type', params.type)
    if (params?.extColumns) qs.set('ext_columns', params.extColumns)
    const s = qs.toString()
    return request<{ alerts: AlertEvent[]; total: number }>(`/api/alerts${s ? `?${s}` : ''}`)
  },

  alertsClear: () =>
    request<{ ok: boolean; cleared: number }>('/api/alerts', { method: 'DELETE' }),

  alertDelete: (ts: number) =>
    request<{ ok: boolean }>(`/api/alerts/${ts}`, { method: 'DELETE' }),

  /** 生成演示触发记录 (Dev 页用) */
  alertSeed: (count = 12, recent = true) =>
    request<{ ok: boolean; generated: number }>(`/api/alerts/seed?count=${count}&recent=${recent}`, { method: 'POST' }),

  /** 检查 AI 配置状态 */
  strategyAiStatus: () =>
    request<{ configured: boolean; has_key: boolean; has_model: boolean; provider?: string }>('/api/strategies/ai/status'),

  /** 测试 AI 连通性 */
  strategyAiTest: () =>
    request<{ ok: boolean; error?: string; model?: string; response?: string; usage?: { prompt: number; completion: number } }>(
      '/api/strategies/ai/test',
      { method: 'POST' },
    ),

  /** 获取策略源文件内容 */
  strategyGetSource: (id: string) =>
    request<{ code: string; source: string }>(`/api/strategies/${id}/source`),
  strategyBuild: (step: number, payload: Record<string, any>) =>
    request<StrategyBuildResult>(
      '/api/strategies/build',
      { method: 'POST', body: JSON.stringify({ step, ...payload }) },
    ),

  async *strategyBuildStream(step: number, payload: Record<string, any>): AsyncGenerator<StrategyBuildStreamEvent> {
    const res = await fetch('/api/strategies/build/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ step, ...payload }),
    })
    if (!res.ok) {
      let detail = ''
      try { const j = JSON.parse(await res.text()); detail = j.detail ?? j.message ?? '' } catch { /* ignore */ }
      const msg = detail || `${res.status} ${res.statusText}`
      toast(msg, 'error')
      throw new Error(msg)
    }
    if (!res.body) throw new Error('响应无 body')

    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let buf = ''
    for (;;) {
      const { done, value } = await reader.read()
      if (done) break
      buf += decoder.decode(value, { stream: true })
      const lines = buf.split('\n')
      buf = lines.pop() ?? ''
      for (const line of lines) {
        const s = line.trim()
        if (!s) continue
        try { yield JSON.parse(s) } catch { /* ignore */ }
      }
    }
    if (buf.trim()) {
      try { yield JSON.parse(buf.trim()) } catch { /* ignore */ }
    }
  },

  strategyValidateCode: (payload: { code: string; strategy_id?: string; name?: string; description?: string }) =>
    request<StrategyBuildResult>('/api/strategies/code/validate', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  strategySaveCodeV2: (payload: {
    strategy_id: string
    code: string
    target_source: 'ai' | 'custom'
    mode: 'create' | 'update'
    name?: string
    description?: string
  }) =>
    request<StrategyCodeSaveResult>('/api/strategies/code/save', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  /** 创建/更新叠加策略(composite): 声明式引用多个子策略 */
  strategySaveComposite: (payload: {
    strategy_id: string
    name: string
    description?: string
    children: { strategy_id: string; weight: number }[]
    merge_mode: 'union' | 'intersect'
    min_confirm?: number
    mode: 'create' | 'update'
  }) =>
    request<StrategyCodeSaveResult>('/api/strategies/composite/save', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  /** 保存 AI 生成的策略文件 */
  strategySaveCode: (strategyId: string, code: string, meta?: { name?: string; description?: string }) =>
    request<{ ok: boolean; path: string }>('/api/strategies/ai/save', {
      method: 'POST',
      body: JSON.stringify({ strategy_id: strategyId, code, name: meta?.name ?? '', description: meta?.description ?? '' }),
    }),
}

// ===== Pipeline =====
export interface PipelineJob {
  id: string
  status: 'pending' | 'running' | 'succeeded' | 'failed'
  stage: string
  progress: number          // 0-100 整体进度
  stage_pct: number         // 0-100 当前阶段内进度
  log: { ts: string; stage: string; msg: string }[]
  started_at: string | null
  finished_at: string | null
  duration_s: number | null
  result: {
    universe_size: number
    today_daily_rows?: number
    today_daily_incomplete?: boolean
    daily_days: number
    adj_factor_symbols: number
    enriched_days: number
    index_count?: number
    index_daily_rows?: number
    minute_rows: number
    skipped_stages?: string[]
  } | null
  error: string | null
}

export type PipelineJobSummary = Omit<PipelineJob, 'log'>

// ===== Data status =====
interface TableStats {
  rows: number
  earliest_date: string | null
  latest_date: string | null
  symbols_covered: number
  trading_days: number
}

interface InstrumentsStats {
  rows: number
  symbols_covered: number
  latest_as_of: string | null
  named: number
}

export interface DataStatus {
  daily: TableStats | null
  enriched: TableStats | null
  index_daily: TableStats | null
  index_enriched: TableStats | null
  index_instruments: InstrumentsStats | null
  etf_daily: TableStats | null
  etf_enriched: TableStats | null
  etf_instruments: InstrumentsStats | null
  minute: TableStats | null
  adj_factor: TableStats | null
  instruments: InstrumentsStats | null
  financials: { rows: number; tables: Record<string, { rows: number; symbols: number }> } | null
  storage: {
    daily_files: number
    daily_size_mb: number
    enriched_files: number
    enriched_size_mb: number
    index_daily_files?: number
    index_daily_size_mb?: number
    index_enriched_files?: number
    index_enriched_size_mb?: number
    index_instruments_files?: number
    index_instruments_size_mb?: number
    etf_daily_files?: number
    etf_daily_size_mb?: number
    etf_enriched_files?: number
    etf_enriched_size_mb?: number
    etf_instruments_files?: number
    etf_instruments_size_mb?: number
    etf_adj_factor_files?: number
    etf_adj_factor_size_mb?: number
    minute_files: number
    minute_size_mb: number
    adj_factor_files: number
    adj_factor_size_mb: number
    instruments_files: number
    instruments_size_mb: number
    financials_files?: number
    financials_size_mb?: number
    ext_data_files?: number
    ext_data_size_mb?: number
    total_size_mb: number
  }
  next_pipeline_run: string | null
  next_instruments_run: string | null
  last_pipeline_run: string | null
  last_instruments_run: string | null
  checked_at: string
  indicators_ready?: boolean
  /** 数据目录持久化自检: false = 容器内未挂载卷, 重建容器会丢全部数据 */
  data_dir_persistent?: boolean
  data_dir_path?: string
}

export interface EnrichedField {
  name: string
  type: string
  desc: string
}

// ===== 扩展数据 =====
export interface ExtDataField {
  name: string
  dtype: string
  label: string
}

/** 拉取接口鉴权方式; Key 本体存 secrets_store, 不出现在配置里 */
export interface ExtPullAuth {
  type: 'none' | 'bearer' | 'header' | 'query'
  header?: string
  param?: string
}

export interface PullConfig {
  url: string
  method: string
  headers?: Record<string, string>
  body?: string | null
  response_path: string
  field_map?: Record<string, string>
  schedule_minutes: number
  enabled: boolean
  last_run?: string | null
  last_status?: string | null
  last_message?: string | null
  last_rows?: number | null
  next_run?: string | null
  time_window_start?: string | null
  time_window_end?: string | null
  /** 接口按日查询的参数名 (如 "date"): 配置后支持历史回补 */
  date_param?: string | null
  auth?: ExtPullAuth | null
}

export interface ExtDataBackfillResult {
  status: string
  total_days: number
  fetched: number
  skipped_existing: number
  empty: number
  failed: { date: string; reason: string }[]
  rows_written: number
}

export interface ExtDataDetectUrlRequest {
  url: string
  method?: string
  headers?: Record<string, string>
  body?: string
  response_path?: string
  field_map?: Record<string, string>
}

export interface ExtDataDetectUrlResult {
  status: string
  total_rows: number
  response_path: string
  response_path_candidates: string[]
  fields: ExtDataField[]
  symbol_candidates: string[]
  code_candidates: string[]
  preview: Record<string, unknown>[]
}

export interface ExtDataConfig {
  id: string
  label: string
  mode: 'snapshot' | 'timeseries'
  fields: ExtDataField[]
  description?: string
  symbol_map?: Record<string, string>
  code_map?: Record<string, string>
  created_at: string
  updated_at: string
  latest_sync_date?: string | null
  date_range?: string[] | null
  pull?: PullConfig | null
}

export interface ExtDataRowsResult {
  id: string
  label: string
  mode: 'snapshot' | 'timeseries'
  date: string | null
  total: number
  limit: number
  fields: ExtDataField[]
  rows: Record<string, any>[]
}

export interface DimensionMembersResult {
  id: string
  label: string
  date: string | null
  field: string
  value: string
  total: number
  limit: number
  rows: Record<string, any>[]
}

export interface DimensionIntradayPoint {
  time: string
  sector: number | null
  market: number | null
}

export interface DimensionIntradayResult {
  status: 'ok' | 'no_data' | 'empty'
  reason?: string | null
  date?: string | null
  basis?: 'prev_close' | 'first_close' | 'mixed' | null
  member_count?: number
  members_with_minute?: number
  points: DimensionIntradayPoint[]
}

export interface AnalysisColumn {
  field: string
  label?: string
  type?: 'string' | 'number' | 'percent' | 'amount' | 'date'
  width?: number | null
  sortable?: boolean
  precision?: number | null
  format?: string | null
  aggregate?: 'count' | 'avg' | 'sum' | 'min' | 'max' | null
  visible?: boolean
}

export interface AnalysisMenu {
  id: string
  label: string
  icon: string
  data_source: string
  template: 'dimension_rank' | 'ranking' | 'table'
  dimension_field?: string | null
  rank_field?: string | null
  group_columns: AnalysisColumn[]
  detail_columns: AnalysisColumn[]
  default_sort?: { field: string; order: 'asc' | 'desc' } | null
  visible: boolean
  order: number
  created_at?: string | null
  updated_at?: string | null
  builtin?: boolean
}
