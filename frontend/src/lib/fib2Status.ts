/**
 * [R411] 斐波那契二型「形态走到哪一步」——**把图上那四样串成一句话**。
 *
 * 用户: 「要串起来, 你内部可以表示 f3f5cop 这些, 但是前端要显示通俗易懂一点」。
 *
 * ## 为什么值得串
 *
 * 图上本来就有四个部件, 它们其实是**一个有先后顺序的形态**, 而不是四样零件:
 *
 *     上攻段底色(推进发生过) → ▼首次回踩(回撤开始了)
 *       → 回踩位 / 密集带(可能停下的地方) → 这组作废(停不住就别看了)
 *
 * 但图上是按"位置"摆的, 顺序要用户自己在脑子里拼。拼这一步本不该存在。
 *
 * ## 边界: 只报事实, 一个动词都不出
 *
 * 用户在这一处明确选过「只报形态走到哪一步」, 而不是出「等待/买入」。这条边界
 * 不是洁癖, 有两个硬理由:
 *
 *   1. **R405 立这一组时定的口径就是「只有位置, 没有动作」**, 用户原话:
 *      「是否共振我自己人工判断, 不打算代码判断」。
 *   2. **这个指标根本产生不了"卖出"那一侧。** 它的卖出逻辑是 COP/OP/XOP
 *      三个目标价, 而那三条与「趋势没坏就不给卖出理由」冲突, 用户已经定了不用。
 *      本仓库的卖出口径是 生命线 / 止盈线 / 六态转弱, 与二型毫无关系 ——
 *      所以这行字里若出现「卖出」, 它要么是假的, 要么就得把砍掉的半套接回来。
 *
 * 于是这里出的每一段都是**可以直接对着图数出来的事实**: 上攻几天、回踩第几天、
 * 下方最近那条是多少、现价在不在密集带里。**一个"该不该"都没有。**
 *
 * ## 黑话留在代码里
 *
 * F3 / F5 / COP / OP / XOP / FOCUS 这些**一个都不出现在返回值里**。
 * 对照关系(免得下一个人去翻原书):
 *
 *     F3  = 38.2% 回撤 → 界面「浅回踩」
 *     F5  = 61.8% 回撤 → 界面「深回踩」
 *     COP/OP/XOP       → 界面「第一站/第二站/第三站」(默认不画)
 *     FOCUS            → 上攻段的最高点, 界面上不出现, 只体现为"位置定没定"
 *
 * ## 措辞只有这一个产地
 *
 * 返回的是**成品短语**, 不是一堆数让组件自己拼 —— 措辞散在两处必然漂移
 * (R277/R278 栽过两次)。组件只负责把这几段用「·」摆开。
 */
import { FIB2_ROLE_RETRACE, FIB2_ROLE_VOID } from '@/lib/theme'

/** 只要这三个字段 —— 特意不 import 组件里的 PriceLevel, 免得绕回一个循环依赖。 */
export interface Fib2StatusLevel {
  value: number
  label: string
  color?: string
}

export interface Fib2StatusInput {
  /** 与 rows 对齐的日期, 用来把标记的日期换算成"第几天" */
  dates: string[]
  close: number | undefined
  thrust: { start: string; end: string; days: number } | null | undefined
  /** 叠加层的标记, 这里只关心「首次回踩」那一个 */
  markers: { date: string; label: string }[] | undefined
  zone: { low: number; high: number; strength: number } | null
  /** 当前档算出来的那一组线(已经是按档选过的) */
  levels: Fib2StatusLevel[]
}

const FIRST_PULLBACK = '首次回踩'

function pct(v: number, close: number): string {
  const p = ((v - close) / close) * 100
  return `${p >= 0 ? '+' : ''}${p.toFixed(1)}%`
}

/**
 * 形态走到哪一步 —— 返回几段成品短语; `null` = 没有形态, 这一行整条不显示。
 *
 * **没有推进段就什么都不说。** 那时候图上本来也一条线都没有, 硬挤一句
 * 「暂无形态」只是多一行要读的字。
 */
export function fib2Status(input: Fib2StatusInput): string[] | null {
  const { dates, close, thrust, markers, zone, levels } = input
  if (!thrust) return null

  const out: string[] = []

  // ① 上攻那一段。**「还在走」这件事必须说** —— 推进段没结束时, 聚焦点每创一次
  //    新高就抬一次, 下面所有位置跟着往上挪。那时候的线不是能挂单的价位。
  const pullback = (markers ?? []).find(m => m.label === FIRST_PULLBACK)
  const running = !pullback
  if (running) {
    // **说完就停, 不往下报任何具体价位。** 第一版这里接着报了「下方最近
    // 浅回踩 13.98」, 一边说位置每天在变、一边给一个精确到分的数 —— 那个数
    // 明天就不是它了, 而读的人会把它记住。既然这一段的结论是"现在还不能用",
    // 就不该同时递出一个看起来能用的价格。
    return [`上攻 ${thrust.days} 天 · 还在走`, '这组位置每天都在变']
  } else {
    out.push(`上攻 ${thrust.days} 天已结束`)
    const i = dates.indexOf(pullback!.date)
    if (i >= 0) out.push(`回踩第 ${dates.length - i} 天`)
  }

  if (close == null || !Number.isFinite(close)) return out

  // ② 现价在这组位置的哪一层。**顺序是从坏到好地判**: 先看有没有作废,
  //    再看有没有跌穿密集带 —— 否则"在密集带里"会盖掉"其实已经破了"。
  // **用词与图上逐字一致**: 图上那条线叫「这组作废」、那块带叫「回踩密集带」,
  // 这里就不许简写成「作废线」「密集带」—— 一个东西两个名字, 读的人得先确认
  // 它们是不是一回事, 而那一步本不该存在。
  const voidAt = levels.find(p => p.color === FIB2_ROLE_VOID)?.value ?? null
  if (voidAt != null && close < voidAt) {
    out.push(`已跌破这组作废 ${voidAt.toFixed(2)}`)
    return out
  }
  if (zone && close < zone.low) {
    out.push('已跌穿回踩密集带')
    if (voidAt != null) out.push(`这组作废 ${voidAt.toFixed(2)}（${pct(voidAt, close)}）`)
    return out
  }
  if (zone && close <= zone.high) {
    out.push(`现价在回踩密集带内（${zone.strength} 条挤在一起）`)
    return out
  }

  // ③ 还在密集带上方 —— 报下方最近的那条回踩位。
  //    **只报一条**: 报一串等于把"好多根线"那个问题原样搬到文字里。
  const below = levels
    .filter(p => p.color === FIB2_ROLE_RETRACE && p.value < close)
    .sort((a, b) => b.value - a.value)[0]
  if (below) {
    out.push(`下方最近 ${below.label} ${below.value.toFixed(2)}（${pct(below.value, close)}）`)
  }
  // 没有密集带本身就是一条读数, 而且是有信息量的那种: 这一波上涨底下没有
  // 结构支撑, 真回踩了不知道停哪。**这句话让人少动一次, 所以值得说。**
  if (!zone) out.push('没有重合')
  return out
}
