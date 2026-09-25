// capability 内部名 → 用户能理解的中文标签
import { useNavigate } from 'react-router-dom'
import type { CapabilityMatrix, CapabilityRoute } from './api'

export const CAP_LABELS: Record<string, { name: string; hint: string }> = {
  'quote.by_symbol':         { name: '自选股实时监控', hint: 'Free 可按标的查询实时行情,用于少量自选股监控' },
  'quote.batch':             { name: '实时行情(批量)',   hint: '一次拿多只股票的价' },
  'quote.pool':              { name: '标的池查询',        hint: '按沪深300等池子拿行情' },
  'kline.daily.by_symbol':   { name: '日 K(按标的)',    hint: '单只股票历史日 K' },
  'kline.daily.batch':       { name: '日 K(批量)',      hint: '一次拿多只股票的日 K — 选股 / 信号扫描 必需' },
  'kline.minute.by_symbol':  { name: '分钟 K(按标的)',  hint: '单股 1m/5m/15m/30m/60m K 线' },
  'kline.minute.batch':      { name: '分钟 K(批量)',    hint: '多股分钟 K' },
  'intraday.universe':       { name: '全量分钟',        hint: '标的池单请求拉全市场当日分钟K (盘中增量落盘, Expert 专有)' },

  'depth5':                  { name: '五档盘口',          hint: '买卖五档报价' },
  'depth5.batch':            { name: '五档盘口(批量)',   hint: '批量买卖五档快照' },
  'websocket':               { name: '实时推送(WS)',    hint: '免轮询的实时行情订阅' },
  'financial':               { name: '财务数据',          hint: '利润表 / 资负表 / 现金流 / 关键指标' },
  'adj_factor':              { name: '复权因子',          hint: '让 MA/MACD 等指标在分红送转日不失真' },
}

// ===== 数据源无关的能力提示 (所有数据源共用一套标准) =====
// 功能门槛一律以能力键表达, 不再出现 TickFlow 档位词 (档位仅出现在 TickFlow 专属界面)。

/** 能力键 → 用户可读能力名 */
export function capName(capKey: string): string {
  return CAP_LABELS[capKey]?.name ?? capKey
}

/** 数据不可用标准徽章: 「分钟 K(批量) · 不可用」, 通用状态陈述, 默认点击跳转 设置→数据源 (to=null 关闭跳转) */
export function MissingCapChip({ capKey, label, to = '/settings?tab=data-sources', className = '' }: {
  capKey?: string
  label?: string
  to?: string | null
  className?: string
}) {
  const navigate = useNavigate()
  const text = label ?? (capKey != null ? capName(capKey) : '')
  const content = (
    <>
      {text ? `${text} · 不可用` : '不可用'}
    </>
  )
  if (to == null) {
    return (
      <span className={`text-micro text-warning/90 bg-warning/8 rounded px-1.5 py-px font-medium ${className}`} title="该数据当前不可用">
        {content}
      </span>
    )
  }
  return (
    <button
      type="button"
      onClick={(e) => { e.stopPropagation(); navigate(to) }}
      className={`text-micro text-warning/90 bg-warning/8 rounded px-1.5 py-px font-medium hover:bg-warning/15 transition-colors ${className}`}
      title="前往 设置 → 数据源"
    >
      {content}
    </button>
  )
}

// ===== 能力路由门控 (各页统一判定) =====
// usable = 生效源当前能否提供该能力 (区别于 TickFlow 套餐视角):
// 路由到可用插件/自定义源时同样可用; 路由到 TickFlow 但档位不足时不可用。
// 矩阵未加载时返回 undefined, 调用方回退 TickFlow 套餐视角, 避免首屏闪烁。
// 数据来自 useCapabilityMatrix (设置页与其他页面共享同一缓存)。

export type RouteCapId = 'realtime' | 'daily' | 'minute' | 'adj_factor' | 'financial'

export function routeCap(matrix: CapabilityMatrix | undefined, id: RouteCapId): CapabilityRoute | undefined {
  return matrix?.capabilities.find(c => c.id === id)
}

export function routeCapUsable(matrix: CapabilityMatrix | undefined, id: RouteCapId): boolean | undefined {
  return routeCap(matrix, id)?.usable
}

/** 生效源非 TickFlow 且当前可用时返回其展示名 (卡片徽章显示实际数据源), 否则 null */
export function routeProviderDisplay(matrix: CapabilityMatrix | undefined, id: RouteCapId): string | null {
  const cap = routeCap(matrix, id)
  return cap && cap.usable && cap.effective !== 'tickflow' ? cap.effective_display : null
}

// ===== TickFlow 档位 (仅 TickFlow 专属界面) =====

// 套餐等级 —— 仅用于 TickFlow 专属界面 (Key 配置 / 端点测速 / 引导页 tickflow 分支)。
// 通用功能门槛一律用能力键 (capName/needCapText/MissingCapChip), 不用档位词。
// 基础档提取与后端 quote_service.py 一致:取 label 第一个词("Pro +" → "pro")。
// none = None 档(无 key / 无效 key),低于 free,仅历史日K无实时行情。
export const TIER_RANK: Record<string, number> = { none: -1, free: 0, starter: 1, pro: 2, expert: 3 }
export const EXPERT_RANK = TIER_RANK.expert

export function tierRank(label: string): number {
  const base = (label.split(' ')[0] ?? '').split('+')[0].trim().toLowerCase()
  return TIER_RANK[base] ?? -1
}

export function isExpertOrAbove(label: string): boolean {
  return tierRank(label) >= EXPERT_RANK
}

/** 档位完整样式(tag 背景 + 圆点 + 文字渐变), 与左侧菜单 TierBadge 一致 */
export interface TierStyle {
  tagBg: { background: string }
  dotStyle: { background: string }
  labelTextStyle: { color?: string; background?: string; WebkitBackgroundClip?: string; backgroundClip?: string }
  desc: string
}

const TIER_STYLE: Record<string, TierStyle> = {
  // [R368] 五档全部改成**平色**, 并压到白底上读得清。
  //
  // 两件事一起修:
  //   ① pro/expert 原本是紫→品红 / 蓝→紫→琥珀的**渐变标签 + 渐变文字**
  //      (`WebkitBackgroundClip: 'text'`)—— 用户明令不要蓝紫渐变。
  //   ② 这五档的色值全是**照着深色底调的**: `#a1a1aa`(free)、`#60a5fa`
  //      (starter)、`#c084fc`(pro) 落在白卡片上对比只有 2 点几, 是看不清的。
  //      换色本来就要把它们压下来。
  //
  // 档位之间仍然分得开 —— 靠色相(灰 / 蓝 / 墨绿 / 琥珀), 不靠渐变。
  none: {
    desc: '未配置 Key · 仅历史日K',
    tagBg: { background: 'rgba(102,112,133,0.10)' },
    dotStyle: { background: '#98A2B3' },
    labelTextStyle: { color: '#667085' },
  },
  free: {
    desc: '历史日K · 自选实时',
    tagBg: { background: 'rgba(102,112,133,0.16)' },
    dotStyle: { background: '#667085' },
    labelTextStyle: { color: '#475467' },
  },
  // [R379] 这一档的蓝跟着主题色一起换成靛蓝; [R514] 靛蓝落在紫区(色相 273°), 用户: 「不要紫色」,
  // 而 R509 起主题色是黑白, 当初「跟主题色同一个色相」的理由也没了 —— 回到蓝。
  starter: {
    desc: '除权因子 · 全市场实时',
    tagBg: { background: 'rgba(37,99,235,0.10)' },
    dotStyle: { background: '#2563EB' },
    labelTextStyle: { color: '#1D4ED8' },
  },
  // [R514] 原来是紫 #6D28D9 → 墨绿。档位之间仍靠色相分开: 灰 / 蓝 / 墨绿 / 琥珀。
  pro: {
    desc: '分钟K · 盘口',
    tagBg: { background: 'rgba(15,118,110,0.10)' },
    dotStyle: { background: '#0F766E' },
    labelTextStyle: { color: '#0F766E' },
  },
  expert: {
    desc: 'WebSocket · 财务数据',
    tagBg: { background: 'rgba(181,71,8,0.10)' },
    dotStyle: { background: '#B54708' },
    labelTextStyle: { color: '#B54708' },
  },
}

/** 从档位 label 提取基础档位名(小写): "Expert +" → "expert" */
export function tierBaseName(label: string): string {
  return (label.split(' ')[0] ?? '').split('+')[0].trim().toLowerCase()
}

/** 返回档位完整样式 */
export function tierStyle(label: string): TierStyle {
  return TIER_STYLE[tierBaseName(label)] ?? TIER_STYLE.free
}

/** 所有档位(有序, 供档位列表渲染) */
export const ALL_TIERS = ['none', 'free', 'starter', 'pro', 'expert'] as const

/** 返回档位标签的渐变文字样式(用于大字显示, 如 Keys 页档位) */
export function tierTextStyle(label: string): { color?: string; background?: string; WebkitBackgroundClip?: string; backgroundClip?: string } {
  return tierStyle(label).labelTextStyle
}

/** 渲染档位 tag(与左侧菜单一致的胶囊样式) */
export function TierTag({ label, className = '' }: { label: string; className?: string }) {
  const t = tierStyle(label)
  const base = tierBaseName(label)
  // none 档显示英文「None」,其余档显示英文档名
  const display = base === 'none' ? 'None' : base
  return (
    <span
      className={`inline-flex h-[18px] max-w-[80px] shrink-0 items-center overflow-hidden rounded px-1.5 text-micro font-bold font-mono leading-none ${className}`}
      style={t.tagBg}
    >
      <span className="truncate capitalize" style={t.labelTextStyle}>{display}</span>
    </span>
  )
}

