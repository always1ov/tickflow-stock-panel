/**
 * [fork 增强] R182 决策台导出的**列注册表**。
 *
 * 改这一版之前有**两套**导出, 各自把列写死在自己的 HTML 模板里:
 *   · 决策台的「导出 HTML」—— 11 个列, 且只导「结论」列有内容的行;
 *   · 六态汇总弹窗里另一个「导出 HTML」—— 另一套 7 列、另一套模板。
 * 两套模板必然长成两个样子, 加一列要改两处, 而且用户没法决定导什么。
 *
 * 现在合成一个: **列由这张表定义, 导出只是按选中的列渲染。**
 * 六态汇总因此不再需要单独存在 —— 它就是"只勾趋势那几列的导出"。
 *
 * 一条约束: **导出的格式要跟屏幕上一致。** 同一个字段在界面上显示成"贴上轨",
 * 导出件里就不该变成 0.87 —— 用户拿导出件和屏幕对不上, 就会怀疑哪个是错的。
 * 所以每列的 `text` 就是屏幕上那个读法, 需要上色的用 `tone` 单独给。
 *
 * 导出件是**浅色**排版(要能打印), 深色主题那套配色搬过去看不清, 所以颜色在
 * 这里单独定义, 不复用界面的 class。
 */
import type { ExitLine, KeltnerBand, KeltnerBands, TrendInfo, Urgency, ChannelPhase } from '@/lib/api'

/** 导出用的一行 —— 与决策台 sortedRows 的形状一致(结构化取用, 不强耦合) */
export type ExportRow = {
  symbol: string
  name: string
  close: number | null
  changePct: number | null
  held: boolean
  cost: number | null
  pnl: number | null
  weight?: number | null
  trend?: TrendInfo
  exit?: ExitLine
  kc?: KeltnerBands
  urg?: Urgency
  sig?: { signal: string; confidence: number; reason: string } | null
  /** [R201] 现在处在哪一段 —— 决策台「通道态势」那一列的第一行 */
  ph?: ChannelPhase | null
}

/** 单元格: 文本 + 可选的行内样式(浅色排版用) + 对齐 */
export type Cell = { text: string; style?: string }

const BULL = '#d03050'
const BEAR = '#18a058'
const MUTED = '#8a919f'

const num = (v: number | null | undefined, digits = 2) =>
  v == null ? '—' : v.toFixed(digits)
const pct = (v: number | null | undefined, digits = 1) =>
  v == null ? '—' : `${(v * 100).toFixed(digits)}%`
const upDown = (v: number | null | undefined) =>
  v == null ? MUTED : v > 0 ? BULL : v < 0 ? BEAR : MUTED

const TONE_STYLE: Record<string, string> = {
  sell: 'background:#fdecec;color:#c0392b',
  buy: 'background:#e6f4fb;color:#1c6ea4',
  hold: 'background:#fdf0e3;color:#c78326',
  avoid: 'background:#f0f1f3;color:#8a919f',
  watch: 'background:#f0f1f3;color:#5b6472',
}

const URGENCY_STYLE: Record<Urgency['level'], string> = {
  triggered: 'background:#fdecec;color:#c0392b;font-weight:600',
  near: 'background:#fdf0e3;color:#c78326',
  flip: 'background:#f3ecfd;color:#7b4fc0',
  band: 'background:#e6f4fb;color:#1c6ea4',
  idle: 'color:#b6bcc7',
}

const band = (b?: KeltnerBand): Cell => ({ text: b ? b.pos_cn : '—' })

export type ExportColumn = {
  key: string
  label: string
  /** 表头对齐; 数值列右对齐, 与屏幕一致 */
  align?: 'left' | 'right' | 'center'
  /** 默认是否勾选。默认 = 屏幕上那套列 */
  on: boolean
  /** 分组, 仅用于选列面板里的归类 */
  group: '决策' | '行情' | '持仓' | '通道' | '趋势' | 'AI'
  cell: (r: ExportRow) => Cell
}

/**
 * 全部可导出的列。
 *
 * 前 15 个是决策台屏幕上的列(默认全开 = "跟随列的格式")。
 * 后 4 个 `dur`/`flipDown`/`flipUp`/`trendSignal` 是**原六态汇总独有**的字段 ——
 * 屏幕上没有单独成列(藏在「趋势」列的悬停里), 但它们正是那个弹窗存在的理由,
 * 所以做成可勾选的列保留下来, 默认不开。勾上它们、取消其余, 导出的就是原来的
 * 六态汇总。
 */
export const EXPORT_COLUMNS: ExportColumn[] = [
  {
    key: 'urgency', label: '该动', group: '决策', align: 'center', on: true,
    // [R193] 导出里也得把话说清楚, 而且**这里比屏幕上更要紧**: 导出的 HTML
    // 是拿去存档/打印/转发的, 一个纸面上的「逼近 0.5%」连悬停都没有 ——
    // 看的人无从知道那是该买还是该卖。所以带上方向与那条线。
    cell: (r) => (r.urg && r.urg.level !== 'idle'
      ? {
          text: [
            r.urg.label + (r.urg.distance != null
              ? ` ${(r.urg.distance * 100).toFixed(1)}%` : ''),
            r.urg.side_cn ? `[${r.urg.side_cn}]` : '',
            r.urg.what ?? '',
          ].filter(Boolean).join(' '),
          style: URGENCY_STYLE[r.urg.level],
        }
      : { text: '—' }),
  },
  {
    key: 'name', label: '标的', group: '决策', on: true,
    cell: (r) => ({ text: `${r.name}  ${r.symbol}` }),
  },
  {
    key: 'close', label: '现价', group: '行情', align: 'right', on: true,
    cell: (r) => ({ text: num(r.close) }),
  },
  {
    key: 'changePct', label: '涨跌', group: '行情', align: 'right', on: true,
    cell: (r) => ({ text: pct(r.changePct, 2), style: `color:${upDown(r.changePct)}` }),
  },
  {
    key: 'held', label: '仓位', group: '持仓', align: 'center', on: true,
    cell: (r) => ({ text: r.held ? (r.weight != null ? `持有 ${r.weight}%` : '持有') : '—' }),
  },
  {
    key: 'cost', label: '成本', group: '持仓', align: 'right', on: true,
    cell: (r) => ({ text: num(r.cost) }),
  },
  {
    key: 'pnl', label: '浮盈', group: '持仓', align: 'right', on: true,
    cell: (r) => ({ text: pct(r.pnl), style: `color:${upDown(r.pnl)}` }),
  },
  {
    key: 'exit', label: '止盈线', group: '持仓', align: 'right', on: true,
    // 与屏幕一致: 报的是线价 + 离触发多远, 而不是只报一个线价
    cell: (r) => (r.exit
      ? {
          text: `${num(r.exit.line)} (${r.exit.stage_cn} ${pct(r.exit.distance_pct)})`,
          style: r.exit.distance_pct > -0.03 ? `color:${BULL}` : undefined,
        }
      : { text: '—' }),
  },
  {
    key: 'trend', label: '趋势', group: '趋势', on: true,
    cell: (r) => (r.trend
      ? {
          text: `${r.trend.state_cn} ${r.trend.duration}天`,
          style: `color:${r.trend.side === '多头' ? BULL : BEAR}`,
        }
      : { text: '—' }),
  },
  { key: 'ks', label: '短通道', group: '通道', align: 'center', on: true, cell: (r) => band(r.kc?.s) },
  { key: 'km', label: '中通道', group: '通道', align: 'center', on: true, cell: (r) => band(r.kc?.m) },
  { key: 'kl', label: '长通道', group: '通道', align: 'center', on: true, cell: (r) => band(r.kc?.l) },
  // [R201] 通道态势 —— 与屏幕上那一列同源: 阶段 + 三线间距 + 快慢 + 挤了几天。
  // 默认**不勾选**: 导出是拿去发给别人的, 默认给最少的必要信息;
  // 要带上它是一次有意识的选择, 不是顺手带出去。
  {
    key: 'chanState', label: '通道态势', group: '通道', align: 'center', on: false,
    cell: (r) => {
      const g = r.kc?.geo
      if (!g) return { text: '—' }
      const fast = g.accel?.level === 'accel' ? '提速'
        : g.accel?.level === 'decel' ? '变慢' : '匀速'
      const days = r.kc?.runs?.compress_days
      return {
        text: [r.ph?.cn, `间距 ${g.spread.toFixed(1)}`, fast,
               days ? `挤 ${days} 天` : null].filter(Boolean).join(' · '),
      }
    },
  },
  {
    key: 'verdict', label: '结论', group: '通道', on: true,
    cell: (r) => (r.kc?.verdict
      ? { text: r.kc.verdict.title, style: TONE_STYLE[r.kc.verdict.tone] }
      : { text: '—' }),
  },
  {
    key: 'confidence', label: '置信', group: 'AI', align: 'right', on: true,
    cell: (r) => ({ text: r.sig ? `${Math.round(r.sig.confidence * 100)}%` : '—' }),
  },
  {
    key: 'signal', label: 'AI 信号', group: 'AI', on: true,
    cell: (r) => ({ text: r.sig ? `${r.sig.signal} · ${r.sig.reason}` : '—' }),
  },

  // ↓ 原「六态汇总」独有的四列。屏幕上藏在「趋势」列的悬停里, 这里做成可勾选的
  //   列 —— 勾上这四个、取消其余, 就是原来那个弹窗导出的东西。
  {
    key: 'dur', label: '持续', group: '趋势', align: 'right', on: false,
    cell: (r) => ({ text: r.trend ? `${r.trend.duration} 天` : '—' }),
  },
  {
    key: 'flipDown', label: '跌破转弱', group: '趋势', align: 'right', on: false,
    cell: (r) => ({ text: num(r.trend?.flip_down), style: `color:${BEAR}` }),
  },
  {
    key: 'flipUp', label: '站上转强', group: '趋势', align: 'right', on: false,
    cell: (r) => ({ text: num(r.trend?.flip_up), style: `color:${BULL}` }),
  },
  {
    key: 'trendSignal', label: '近期信号', group: '趋势', on: false,
    cell: (r) => ({ text: r.trend?.signal_desc || '—' }),
  },
]

export const DEFAULT_EXPORT_KEYS = EXPORT_COLUMNS.filter(c => c.on).map(c => c.key)

export function columnsFor(keys: string[]): ExportColumn[] {
  // 按注册表顺序输出, 不按用户勾选顺序 —— 列序是版面设计, 不该因为勾选先后而变
  const want = new Set(keys)
  return EXPORT_COLUMNS.filter(c => want.has(c.key))
}
