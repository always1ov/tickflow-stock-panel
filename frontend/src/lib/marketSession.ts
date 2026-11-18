/**
 * 北京时间与 A 股交易时段判定 (看板的实时轮询启停、轮动卡片共用)。
 *
 * [R814] 这里原来自己写了一份北京时区格式化(Intl.DateTimeFormat 带上海时区),
 * 成了 R319「市场时钟只有一处产地」之外的第二个时区来源。现在只从
 * `lib/marketClock.ts` 取读数 —— 时区换算全仓只有那一个文件做。
 */
import { cnClock, cnDate } from './marketClock'

/** 北京时间的日期与「当天第几分钟」。留给只需要日期字符串的调用方。 */
export function beijingDateParts(): { date: string; minutes: number } {
  const { mins } = cnClock()
  return { date: cnDate(), minutes: mins }
}

/** 此刻是否处于 A 股连续竞价时段 (9:30-11:30 / 13:00-15:00, 北京时间)。 */
export function isMarketSessionNow(): boolean {
  const { mins } = cnClock()
  return (mins >= 570 && mins < 690) || (mins >= 780 && mins < 900)
}
