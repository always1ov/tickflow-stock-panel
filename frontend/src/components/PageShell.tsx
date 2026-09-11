/**
 * [R60] 统一页面骨架 —— 把"一页长什么样"的决定收在一处。
 *
 * 改这个之前, 每一页的外壳都是各写各的, 量出来是这样:
 *
 *   内容宽度  1500px / 1440px / 1280px / 1100px / max-w-6xl / max-w-7xl / 完全不限
 *   页面留白  px-3 pt-3 pb-3 / px-4 py-5 / px-6 py-5 / p-4 md:p-6 / px-3 py-2 …
 *   页面头部  多数用 PageHeader, 今日总览和市场环境各自手搓了一个
 *
 * 后果不是"某一页丑", 而是**切页面时内容边界每次都在跳** —— 同一块卡片在
 * 今日总览宽 1500、在复盘宽 1280、在自选顶到边; 眼睛每次都要重新找基准线。
 * 这种不齐单看任何一页都不明显, 只有连着翻才难受, 所以也最容易一直没人改。
 *
 * 这里只定三件事, 别的都交给页面自己:
 *   1. **内容宽度**。三档, 按页面性质选, 不是按谁写的时候顺手。
 *   2. **页面留白**。一档, 小屏 12px 大屏 16px, 不再每页各拍一个。
 *   3. **纵向节奏**。区块之间 12px, 与卡片内部的 8/10px 拉开层级。
 *
 * 页头仍走 PageHeader —— 它本来就够用, 只是有两页没用它。
 */
import type { ReactNode } from 'react'
import { cn } from '@/lib/cn'
import { PageHeader } from '@/components/PageHeader'

/**
 * 内容宽度三档。选哪一档看**内容需要多宽才好读**, 不看这页碰巧有多少东西:
 *
 *   `full`    表格页。列多且要横向对齐, 限宽只会逼出横向滚动条 —— 自选、
 *             筛选器、连板梯队都属于这一类。
 *   `wide`    看板页。多列卡片/图表, 宽一点能多放一列, 但不该无限拉伸,
 *             否则一行文字横跨 2000px 没法读。
 *   `read`    以文字为主的页。报告、设置、说明 —— 一行太长眼睛回不到行首。
 */
export type ShellWidth = 'full' | 'wide' | 'read'

const WIDTH: Record<ShellWidth, string> = {
  full: 'max-w-none',
  wide: 'max-w-[1440px]',
  read: 'max-w-[1100px]',
}

/** 页面留白: 小屏窄一点(手机上每一个像素都是内容), 大屏给到 20px。
 *
 * [R317] 两处修正:
 *   1. **与页头对齐**。PageShell 传给 PageHeader 的 className 里写的是
 *      `lg:px-5`(20px), 而正文这里原本是 `lg:px-4`(16px) —— 大屏上页标题
 *      与下方卡片左边缘差 4px。单看一页几乎察觉不到, 但"基准线不齐"正是
 *      这个骨架当初要解决的问题, 留 4px 等于把问题留回去。现在两边都是 20px。
 *   2. **纵向留白加一档**。字号刻度本次整体上移(sm 14→15 / base 15→16),
 *      同一档留白在新字号下会显得更挤, 所以 pt-3→pt-4、pb-4→pb-5。
 *      区块间距同步从 12px 提到 16px(见下方 space-y-4)。 */
const PAD = 'px-3 pb-5 pt-4 lg:px-5'

export function PageShell({
  title, subtitle, titleExtra, right, width = 'wide', className, bodyClassName, children,
}: {
  title: string
  subtitle?: ReactNode
  titleExtra?: ReactNode
  right?: ReactNode
  /** 见 ShellWidth —— 按内容需要多宽才好读来选 */
  width?: ShellWidth
  /** 加在滚动容器上(极少用到, 如需要 overflow-hidden 的整页表格) */
  className?: string
  /** 加在限宽的内容层上 */
  bodyClassName?: string
  children: ReactNode
}) {
  return (
    <div className="flex min-h-full flex-col bg-base">
      <PageHeader
        title={title}
        subtitle={subtitle}
        titleExtra={titleExtra}
        right={right}
        className="shrink-0 flex-wrap gap-x-4 gap-y-2 bg-base/95 px-3 lg:flex-nowrap lg:px-5"
      />
      <main className={cn('min-h-0 flex-1 overflow-auto', PAD, className)}>
        {/* 限宽层与留白层分开: 合成一层的话, 宽屏上内容会贴着限宽边缘,
            左右留白反而消失 —— 那正是原来几页看着"顶到边"的原因 */}
        {/* [R317] 区块间距 12px -> 16px。字号整体上移之后, 12px 的区块间隙
            与 8/10px 的卡片内间距已经拉不开层级, 上下两块会读成一整块。 */}
        <div className={cn('mx-auto w-full space-y-4', WIDTH[width], bodyClassName)}>
          {children}
        </div>
      </main>
    </div>
  )
}
