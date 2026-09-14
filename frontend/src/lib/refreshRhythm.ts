/**
 * [fork 增强 R333] 自动刷新的节奏 —— **一处定义**。
 *
 * 用户: 「整个系统类似这些按钮要周期自己刷新, 不能等我手动点, 合理规格周期」。
 *
 * ## 在这之前是什么样
 *
 * 全项目 45 处 `refetchInterval`, 取值从 2 秒到 1 小时, **每一处都是各页各定的
 * 魔数**, 没有统一口径。后果是两头都不对:
 *
 *   · 模拟盘、复盘、连板梯队、消息面 **一次都不自动刷新** —— 打开就定格在
 *     那一刻, 要看新的只能手动重来;
 *   · 收盘之后还有一堆按盘中节奏轮询的, 而那些数据收盘后一整晚不会变。
 *
 * ## 按「数据本身多久变一次」分档, 不按页面
 *
 * 页面会改、会合并、会拆开; 而"这份数据多久变一次"是它自己的性质。所以档位挂在
 * 数据上, 页面只管挑一档。
 *
 *   LIVE      盘中每分钟都在变     —— 盘中 60s / 盘后 30min
 *   DERIVED   日线派生, 收盘才定   —— 盘中 5min / 盘后 1h
 *   SLOW      一天变不了几次       —— 统一 30min
 *   STATIC    不会变(词表、规则)  —— 不轮询
 *
 * **盘中与盘后分开**, 依据是 `inRealtimeWindow()`(工作日 09:15~15:05, 与后端
 * `realtime_schedule` 同一边界 —— 竞价与收盘定版那几分钟正是数字在变的时候)。
 * 收盘后把节奏放慢不是省电, 是**省后端**: 决策台一次重算是全部自选的六态 + 打分,
 * 盘后每分钟跑一遍纯属白烧。
 *
 * ## 两件这里**不管**的事
 *
 *   · **实时行情本身**走 SSE(`useQuoteStream`)与后端 6 秒轮询, 比任何前端定时
 *     都快, 不该再叠一层;
 *   · **任务进行中的轮询**(挖矿、同步、回测跑批)是"等一件事做完", 节奏由那件
 *     事的粒度决定(2~5 秒), 与这里的"数据多久变一次"不是一回事。
 *
 * ## 标签页切走时不轮询
 *
 * React Query 的 `refetchIntervalInBackground` 默认就是 `false` —— 页面不可见时
 * 定时器不发请求, 切回来再按 `refetchOnWindowFocus` 补一次。**这里不去打开它**:
 * 打开等于后台挂着的标签页整夜在打接口。
 */
import { inRealtimeWindow } from '@/lib/marketClock'

/** 数据变化的快慢 —— 页面挑一档, 不自己写数。 */
export type Rhythm = 'live' | 'derived' | 'slow' | 'static'

const MIN = 60_000

/** 各档在「盘中 / 盘外」两种情形下的间隔(毫秒)。`false` = 不轮询。 */
const TABLE: Record<Rhythm, { open: number | false; closed: number | false }> = {
  // 盘中判定: 决策台、今日总览、模拟盘的今日信号 —— 跟着现价走
  live: { open: 1 * MIN, closed: 30 * MIN },
  // 日线派生: 回测曲线、复盘、梯队 —— 收盘落盘才会变, 盘中只有实时叠加层在动
  derived: { open: 5 * MIN, closed: 60 * MIN },
  // 一天变不了几次: AI 信号、笔记、名单
  slow: { open: 30 * MIN, closed: 30 * MIN },
  // 词表、规则口径 —— 变了也要重新部署才生效
  static: { open: false, closed: false },
}

/**
 * 把一个档位翻成 `refetchInterval`。
 *
 * **返回的是函数不是数**: React Query 只在拿它当函数时才会每次重新问 —— 给个
 * 常数的话, 盘中打开的页面到了收盘仍按盘中节奏轮询一整晚(定时器是挂载那一刻
 * 就定死的)。
 */
export function refreshEvery(rhythm: Rhythm): () => number | false {
  return () => {
    const row = TABLE[rhythm]
    return inRealtimeWindow() ? row.open : row.closed
  }
}

/**
 * 只有当这份数据**确实在实时口径下**时才用盘中节奏。
 *
 * 今日总览与模拟盘都有这种情况: 后端会说这次算出来的是不是带实时叠加层的
 * (`live` 字段)。实时开关关着时, 盘中盘后其实是同一份收盘数据 —— 那就没有理由
 * 按分钟刷。R319 给今日总览定的就是这条, 这里把它提成通用的。
 */
export function refreshEveryWhenLive(
  rhythm: Rhythm,
  isLive: (data: unknown) => boolean,
): (query: { state: { data?: unknown } }) => number | false {
  return (query) => {
    const row = TABLE[rhythm]
    const live = isLive(query.state.data)
    return live && inRealtimeWindow() ? row.open : row.closed
  }
}

/** 给界面用的一句话 —— 「多久自己刷一次」。**不让各页各写一份措辞。** */
export function rhythmHint(rhythm: Rhythm): string {
  const row = TABLE[rhythm]
  const say = (v: number | false) =>
    v === false ? '不自动刷新' : v >= MIN * 60 ? `${v / (MIN * 60)} 小时` : `${v / MIN} 分钟`
  if (row.open === row.closed) return `每 ${say(row.open)} 自动刷新一次`
  return `盘中每 ${say(row.open)}、盘后每 ${say(row.closed)} 自动刷新一次`
}
