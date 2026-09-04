/**
 * [fork 增强 R170] 「我的批次」行上的 AI 对照标记 —— 这只票有几个 AI 操盘手也拿着。
 *
 * ## 为什么只有一个数字
 *
 * `paper_trader.py` 开头写着一条设计约束: 界面**刻意不做**「所有人持仓一览」,
 * 因为看完所有操作员的持仓再去调提示词, 操作员之间的隔离就没了 —— 而隔离正是
 * 这个模拟盘实验的全部价值。
 *
 * 所以这里只显示计数, 不显示是谁、成本多少、什么理由。它能回答的问题仅限
 * 「AI 那边也看上这只了吗」; 想知道具体是谁怎么做的, 得自己切到 AI tab 再点进
 * 某一个操作员 —— 那道门槛是作者留的, 不该由一个小标绕过去。
 *
 * ## 这不是买卖信号
 *
 * 模拟盘的目的是体检"这套系统给的信息够不够模型做决定", 不是选股。所以标记做得
 * 很轻(灰底小字), 也不参与任何排序与打分 —— 免得日子久了被当成一种推荐。
 */

export function AiHoldMark({ count, traderTotal }: {
  /** 有几个操作员持有这只票 */
  count: number
  /** 操作员总数, 用来给分母 */
  traderTotal: number
}) {
  if (!count) return null

  const all = traderTotal > 0 && count >= traderTotal
  return (
    <span
      title={
        `${count}/${traderTotal} 个 AI 操盘手的模拟盘里也持有这只。`
        + '\n仅作对照 —— 模拟盘是拿来体检这套系统信息够不够用的, 不是选股信号。'
        + '\n具体是谁、成本多少、什么理由, 需要切到「AI 操盘手」tab 点进某个操作员看'
        + '(这道门槛是刻意留的: 一览无余会破坏操作员之间的隔离)。'
      }
      className={`ml-1.5 inline-flex items-center rounded border px-1 text-[9px] font-mono leading-tight ${
        all ? 'border-accent/35 bg-accent/[0.08] text-accent/85' : 'border-border bg-base text-muted'
      }`}
    >
      AI {count}
    </span>
  )
}
