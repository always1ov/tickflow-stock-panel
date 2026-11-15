/**
 * [R430] 个股弹窗「图表与价位」。
 * [R612] 双栏改版后, 视图切换条(日K / 分时 / 关键价位 / 复盘)提到右栏顶部,
 * 这一块退化成一张只装图的卡片 —— 不再自带小标题, 也不再自己管页签。
 *
 * [R432] 右边那张关键价位列表撤了 —— 用户: 「关键价位还是按照以前那样显示吧,
 * 在右侧很不方便, 可以保留方形按钮」。开关回到图的正上方(`LevelToolbar`),
 * 图于是占满整张卡片的宽度。
 *
 * [R670] 卡框撤了: 里面的 `StockPanel` / 多日分时图各自已经画了圆角边框, 这里再包一层
 * 就是卡片套卡片 —— 两层边框之间只剩 4px, 看着像图被框了两道。这一块只留 `min-w-0`。
 */
import type { ReactNode } from 'react'

export function ChartLevelsSection({ children }: { children: ReactNode }) {
  return <div className="min-w-0">{children}</div>
}
