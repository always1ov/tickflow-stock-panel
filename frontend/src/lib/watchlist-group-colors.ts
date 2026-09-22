import type { WatchlistGroupColor } from '@/lib/api'

export interface WatchlistGroupColorOption {
  id: WatchlistGroupColor
  label: string
  text: string
  border: string
  background: string
  dot: string
  ring: string
}

export const DEFAULT_WATCHLIST_GROUP_COLOR: WatchlistGroupColor = 'sky'

export const WATCHLIST_GROUP_COLORS: readonly WatchlistGroupColorOption[] = [
  { id: 'sky', label: '天蓝', text: 'text-sky-400', border: 'border-sky-400/40', background: 'bg-sky-400/10', dot: 'bg-sky-400', ring: 'ring-sky-400/60' },
  { id: 'blue', label: '蓝色', text: 'text-blue-400', border: 'border-blue-400/40', background: 'bg-blue-400/10', dot: 'bg-blue-400', ring: 'ring-blue-400/60' },
  { id: 'indigo', label: '靛蓝', text: 'text-indigo-400', border: 'border-indigo-400/40', background: 'bg-indigo-400/10', dot: 'bg-indigo-400', ring: 'ring-indigo-400/60' },
  { id: 'violet', label: '紫色', text: 'text-violet-400', border: 'border-violet-400/40', background: 'bg-violet-400/10', dot: 'bg-violet-400', ring: 'ring-violet-400/60' },
  { id: 'orange', label: '橙色', text: 'text-orange-400', border: 'border-orange-400/40', background: 'bg-orange-400/10', dot: 'bg-orange-400', ring: 'ring-orange-400/60' },
  { id: 'amber', label: '金色', text: 'text-amber-400', border: 'border-amber-400/40', background: 'bg-amber-400/10', dot: 'bg-amber-400', ring: 'ring-amber-400/60' },
  { id: 'lime', label: '青柠', text: 'text-lime-400', border: 'border-lime-400/40', background: 'bg-lime-400/10', dot: 'bg-lime-400', ring: 'ring-lime-400/60' },
  { id: 'emerald', label: '绿色', text: 'text-emerald-400', border: 'border-emerald-400/40', background: 'bg-emerald-400/10', dot: 'bg-emerald-400', ring: 'ring-emerald-400/60' },
  { id: 'teal', label: '墨绿', text: 'text-teal-400', border: 'border-teal-400/40', background: 'bg-teal-400/10', dot: 'bg-teal-400', ring: 'ring-teal-400/60' },
  { id: 'cyan', label: '青色', text: 'text-cyan-400', border: 'border-cyan-400/40', background: 'bg-cyan-400/10', dot: 'bg-cyan-400', ring: 'ring-cyan-400/60' },
]

/**
 * [R421] 「品红」「玫红」两个选项下架 —— 用户: 「整个系统禁止少女系风格, 比如粉色」。
 * 后端仍认这两个 id(`services/watchlist.py`, 接口不动), 已经存成这两色的分组
 * 按下表显示成相邻的严肃色, 下次改色时自然换掉。
 */
const RETIRED_COLORS: Record<string, WatchlistGroupColor> = {
  fuchsia: 'violet',
  rose: 'orange',
}

export function resolveWatchlistGroupColor(color?: string | null): WatchlistGroupColorOption {
  const id = (color && RETIRED_COLORS[color]) || color
  return WATCHLIST_GROUP_COLORS.find(option => option.id === id)
    ?? WATCHLIST_GROUP_COLORS[0]
}
