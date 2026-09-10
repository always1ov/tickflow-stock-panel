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

/** 两张卡共用的外框: 一条细分割线隔开每一行 */
export const HEAD_CARD = 'mx-4 mt-3 divide-y divide-border/40 rounded-lg border border-border/60'

/**
 * [R301] 一行里的**子条目**: 「该盯什么」「这一格历来」这类"小标签 + 一句话"。
 *
 * 用户: 「内容显示整理好划分好卡片布局, 现在的显示不对齐」。
 *
 * 它们原来是各写各的 `<p><span>该盯什么: </span>…</p>` —— 小标签宽度各不相同
 * (「该盯什么」三字、「这一格历来」五字), 于是**正文的起点一行一个样**。
 * `HeadRow` 在外层已经用一条固定左栏把三行对齐了; 这里做的是同一件事, 只是
 * 降了一级 —— **同一条规矩用两次, 而不是两套写法。**
 */
export function SubRow({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="mt-1 flex gap-2">
      <span className="w-[3.75rem] shrink-0 text-[10px] text-muted/70">{label}</span>
      <div className="min-w-0 flex-1 text-[10px] leading-relaxed">{children}</div>
    </div>
  )
}
