/**
 * [fork 增强 R292, R294 抽出] 复盘弹窗头部那张卡的一行。
 *
 * **左栏宽度写死**, 三行的内容才会从同一条竖线开始 —— 「对齐」这件事得有个依据,
 * 不能靠每行各自的 padding 凑(R289 那一版散就散在这儿, 用户: 「感觉太乱了,
 * 没有边界感」)。
 *
 * [R294] 从 `StockReviewDialog` 抽到单独文件: 「组合速查」那一页也要用它, 而它
 * 是被弹窗 import 的 —— 留在原处就成了循环依赖。三个页签共用一份实现, 这样
 * 「三张卡长得一样」是**结构上保证的**, 不是靠三处各自抄对。
 */
import type { ReactNode } from 'react'

export function HeadRow({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex gap-3 px-3 py-2">
      <span className="w-[4.5rem] shrink-0 pt-px text-[10px] text-muted">{label}</span>
      <div className="min-w-0 flex-1">{children}</div>
    </div>
  )
}

/** 三张卡共用的外框: 一条细分割线隔开每一行 */
export const HEAD_CARD = 'mx-4 mt-3 divide-y divide-border/40 rounded-lg border border-border/60'
