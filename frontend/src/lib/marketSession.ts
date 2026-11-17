/** 北京时间与 A 股交易时段判定 (看板的实时轮询启停、轮动卡片共用)。 */

export function beijingDateParts(): { date: string; minutes: number } {
  const parts = new Intl.DateTimeFormat('zh-CN', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', hour12: false,
  }).formatToParts(new Date())
  const get = (type: string) => parts.find(p => p.type === type)?.value ?? '00'
  return {
    date: `${get('year')}-${get('month')}-${get('day')}`,
    minutes: Number(get('hour')) * 60 + Number(get('minute')),
  }
}

/** 此刻是否处于 A 股连续竞价时段 (9:30-11:30 / 13:00-15:00, 北京时间)。 */
export function isMarketSessionNow(): boolean {
  const { minutes } = beijingDateParts()
  return (minutes >= 570 && minutes < 690) || (minutes >= 780 && minutes < 900)
}
