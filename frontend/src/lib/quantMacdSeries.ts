/**
 * [R415] 量化MACD 副图 —— 把后端算好的逐根数值, 照原文的 STICKLINE / DRAWICON
 * 翻成 ECharts 的系列。**画法的唯一产地。**
 *
 * 原文里画东西的只有这几行(`:=` 的中间变量一律不画, 见后端模块说明):
 *
 *   STICKLINE(DIFF< 0,0,DIFF,2,0),COLORGREEN;    DIFF 实心柱: <0 绿
 *   STICKLINE(DIFF>=0,0,DIFF,2,0),COLORRED;      DIFF 实心柱: ≥0 红   ← 等于 0 算红
 *   STICKLINE(DEA>=0,0,DEA,2,-1),COLOR0000CC;    DEA 空心柱: ≥0 深红  ← 等于 0 算深红
 *   STICKLINE(DEA< 0,0,DEA,2,-1),COLORGREEN;     DEA 空心柱: <0 绿
 *   DRAWICON(CROSS(DIFF,DEA),柱2,1);             金叉图标 1
 *   DRAWICON(CROSS(DEA,DIFF),DEA*1.1,2);         死叉图标 2
 *   STICKLINE(...,0,DEA/4,2,0),COLORYELLOW;      黄柱(实心)
 *
 * [R417] 下面几条**全部是对着用户发来的通达信截图逐像素量出来的**, 不是按文档推的
 * (R415 按文档推, 柱宽和空心柱都推错了):
 *
 * - **柱宽 66%**: 截图里 K 线间距 15.1px, 实心柱 10px。通达信手册说「宽度 10 为
 *   标准间距」, 照字面 2 就是 20% —— 与实际显示不符, 以实测为准。
 * - **空心柱会盖住底下的东西**: 通达信画空心柱是先用底色把整块填掉、再描边。
 *   DIFF 实心柱先画、DEA 空心柱后画, 所以 DIFF 只露出**超出 DEA 的那一截**;
 *   DIFF 没 DEA 长时整根被盖住, 只看得见 DEA 的框。截图里「上面一截实心、下面
 *   一个空框」就是这么来的。这里不去猜页面底色是什么, 而是直接只画露出来的那一截
 *   (`diffExposed`) —— 结果与"先画再盖"逐像素相同。
 * - **空心柱的边框是点线**(1 点 1 空), 不是实线。
 * - **图标**: 带箭杆的箭头, 约 13×18px, **图标顶端对准数值**、水平居中于那根 K 线;
 *   1 号红色朝上, 2 号绿色朝下。2 号的绿比柱子的绿暗一档(截图三个死叉箭头都在
 *   #00DC00 附近, 而绿柱是 #00FF00) —— 那是通达信图标自带的颜色。
 * - **画的先后 = 原文语句的先后**: DIFF → DEA → 图标 → 黄柱, 后画的盖在上面。
 *
 * 颜色取 `lib/theme.ts` 的 `QUANT_MACD_COLORS`: 逐字照抄通达信, 亮暗两套主题
 * 同一份 —— 用户: 「颜色和柱子类型都得一样」。
 *
 * **只画原文画的, 不多一样也不少一样**: 没有悬停提示, 原文没有的一律不加。
 * [R560] 图**外面**的标题带里加了图例与悬停说明(用户要的), 图里仍然只画原文画的。
 */

export interface QuantMacdAligned {
  diff: (number | null)[]
  dea: (number | null)[]
  yellow: (number | null)[]
  gold_icon: (number | null)[]
  dead_icon: (number | null)[]
}

/**
 * 按日期把后端那份(约 400 根)对到图上的 x 轴。图上有、后端没有的那几根
 * (主图更早的日期、二型开着时右边的「未来」空槽)一律 null —— 不画, 不补。
 */
export function alignQuantMacd(
  dates: string[],
  q: { dates: string[] } & QuantMacdAligned | undefined,
): QuantMacdAligned {
  const idx = new Map((q?.dates ?? []).map((d, i) => [d, i]))
  const pick = (arr: (number | null)[] | undefined) => dates.map(d => {
    const i = idx.get(d)
    return i == null || !arr ? null : (arr[i] ?? null)
  })
  return {
    diff: pick(q?.diff), dea: pick(q?.dea), yellow: pick(q?.yellow),
    gold_icon: pick(q?.gold_icon), dead_icon: pick(q?.dead_icon),
  }
}

/** 柱宽占 K 线间距的比例 —— 实测: 10px / 15.1px。三种柱子同宽(原文宽度都是 2)。 */
export const STICK_RATIO = 0.66

/** 空心柱的边框: 1 点 1 空的点线(实测, 见 DEA 那一条的说明)。 */
export const HOLLOW_DASH = [1, 1]

/** 图标外框(px), 实测。 */
export const ICON_W = 13
export const ICON_H = 18
/** 1 号图标: 红色朝上箭头(箭头在上、箭杆在下)。坐标系 13×18。 */
export const ICON_UP = 'path://M6.5,0 L13,9 L7.5,9 L7.5,18 L5.5,18 L5.5,9 L0,9 Z'
/** 2 号图标: 绿色朝下箭头(箭杆在上、箭头在下)。 */
export const ICON_DOWN = 'path://M5.5,0 L7.5,0 L7.5,9 L13,9 L6.5,18 L0,9 L5.5,9 Z'

/**
 * DIFF 实心柱被 DEA 空心柱盖住之后, 还露在外面的那一截 `[起, 止]`; 全被盖住为 null。
 *
 * - DEA 与 DIFF **同在 0 的一侧**且 DIFF 更长: 露出 DEA→DIFF 那一截;
 * - 同侧但 DIFF 不比 DEA 长: 整根被盖住;
 * - **分在 0 的两侧**(或 DEA 为 0): 空心柱盖的是另一侧, DIFF 整根都露着。
 */
export function diffExposed(diff: number | null, dea: number | null): [number, number] | null {
  if (diff == null) return null
  if (dea == null || dea === 0 || (diff >= 0) !== (dea >= 0)) return [0, diff]
  return Math.abs(diff) > Math.abs(dea) ? [dea, diff] : null
}

/**
 * [R560] 标题带里的图例 + 悬停说明 —— 五样东西各代表什么。**只此一个产地**。
 *
 * 用户: 「量化macd也加标注」(趋势量化 R555 已有)。只讲每样东西是怎么来的、怎么读,
 * 不添判定; 公式(`indicators/quant_macd.py`)与画法一个字节没动。图例画在副图**外面**的
 * 标题带里, 所以不违背上面那条「图里只画原文画的」。
 */
export const QUANT_MACD_LEGEND: { key: 'diff' | 'dea' | 'yellow' | 'gold' | 'dead'; name: string; desc: string }[] = [
  {
    key: 'diff', name: 'DIFF',
    desc: '实心柱, 从 0 画到 DIFF(12 日与 26 日指数均线之差, 与标准 MACD 的 DIFF 同一个算法); '
      + '0 上红、0 下绿。它被 DEA 的点线框盖住, 只露出比 DEA 长的那一截: '
      + '露出实心 = DIFF 走在 DEA 前面, 动能在加速; 只剩空框 = 动能在减弱。柱尖就是 DIFF 的值。',
  },
  {
    key: 'dea', name: 'DEA',
    desc: '点线空心框, 从 0 画到 DEA(DIFF 的 9 日指数均线); 0 上深红、0 下绿。比 DIFF 慢半拍。',
  },
  {
    key: 'yellow', name: '共振',
    desc: '黄柱: 能量潮(按涨跌累计的成交量)的短线强度在增加, 同时 3 日均价在上升 —— 量和价同一天转好。'
      + '从 0 画到 DEA 的 1/4, 只看出没出现, 长短没有含义。',
  },
  {
    key: 'gold', name: '金叉',
    desc: '红色向上箭头: DIFF 上穿 DEA 的那一根, 箭头顶端对准 DEA。',
  },
  {
    key: 'dead', name: '死叉',
    desc: '绿色向下箭头: DIFF 下穿 DEA 的那一根, 画在 DEA 的 1.1 倍处。',
  },
]

/** 悬停说明全文(五段) */
export const QUANT_MACD_HELP = QUANT_MACD_LEGEND.map(l => `${l.name}: ${l.desc}`).join('\n\n')

