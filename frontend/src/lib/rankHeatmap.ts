/**
 * [R761] 板块排名热力图的纯计算部分（组件在 components/SectorRankHeatmap.tsx）。
 * 抽出来是为了能在 vitest 里直接钉住「行序 / 名次 / 缺席留空 / 色阶」，
 * 不必把 React 与 Query 一起拉进测试。
 */

export interface RankCell {
  rank: number
  pct: number
}

export interface RankRow {
  name: string
  /** 最新一日的排名（行序即按它排） */
  rank: number
  /** 与 dates 同序; 该日没有这个板块的数据时为 null */
  cells: (RankCell | null)[]
}

/**
 * 每列日期各自是一份「按涨幅降序」的榜单，所以行 = 最新一日榜单的前 N 名，
 * 其余日期按名字回查名次；查不到留空，横着看就是它什么时候掉出榜单。
 */
export function buildRankRows(
  dates: string[],
  columns: Record<string, [string, number][]>,
  topN = 50,
): RankRow[] {
  const index = new Map<string, Map<string, RankCell>>()
  for (const date of dates) {
    const byName = new Map<string, RankCell>()
    ;(columns[date] ?? []).forEach(([name, pct], i) => byName.set(name, { rank: i + 1, pct }))
    index.set(date, byName)
  }
  return (columns[dates[0]] ?? []).slice(0, topN).map(([name], i) => ({
    name,
    rank: i + 1,
    cells: dates.map(date => index.get(date)?.get(name) ?? null),
  }))
}

/**
 * 参考图实测的色阶：**10 档、每 5 名一档**，不是渐变。
 * 从截图里逐档取像素得到原色（第 1 档 #E53935 → 第 10 档 #2E7D31），
 * 名次越靠后越绿。超出 1..50 的名次按两端夹住（掉出前 50 的格子仍是深绿）。
 */
const RANK_BANDS: [maxRank: number, color: string][] = [
  [5, '#E53935'],
  [10, '#F4511E'],
  [15, '#F57C00'],
  [20, '#F79803'],
  [25, '#F9C10B'],
  [30, '#FCEB3C'],
  [35, '#CDDC39'],
  [40, '#8BC34A'],
  [45, '#4CAF50'],
  [50, '#2E7D31'],
]

/** 图例用：10 档底色，顺序即名次由前到后。 */
export const RANK_BAND_COLORS = RANK_BANDS.map(([, color]) => color)

/**
 * [R769] 档位宽度跟着总行数走：前 45 名时仍是参考图的「每 5 名一档」，
 * 展开成全部 257 名时改成「每 26 名一档」—— 否则 46~257 名会挤在最后一档，
 * 一整片同色等于没有信息。total ≤ 50 时结果与 R761 逐档一致。
 */
function bandSpan(total: number) {
  return Math.max(1, Math.ceil(total / RANK_BANDS.length))
}

function bandIndex(rank: number, total = 50) {
  const span = bandSpan(total)
  const r = Math.min(Math.max(rank, 1), span * RANK_BANDS.length)
  return Math.min(RANK_BANDS.length - 1, Math.floor((r - 1) / span))
}

/** 名次 → 格子底色。total 为当日榜单总行数，缺省按前 50 名分档。 */
export function rankColor(rank: number, total = 50) {
  return RANK_BANDS[bandIndex(rank, total)][1]
}

/**
 * 名次 → 格子文字色。中间四档（黄/黄绿）底色太亮，白字会糊，
 * 参考图那几档用的是深色字；红段和绿段仍是白字。
 */
export function rankTextColor(rank: number, total = 50) {
  const i = bandIndex(rank, total)
  return i >= 3 && i <= 6 ? '#1F2A37' : '#FFFFFF'
}

/** 格内第二行：当日涨幅，一位小数带符号（参考图写法 +1.6 / +0.0 / -0.0）。 */
export function formatRankDelta(pct: number) {
  const v = pct * 100
  const s = v.toFixed(1)
  return v > 0 ? `+${s}` : s
}
