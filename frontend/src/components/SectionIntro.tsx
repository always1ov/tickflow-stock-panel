import type { ReactNode } from 'react'
import { cn } from '@/lib/cn'

/**
 * [R379 第二层] 设置类页面的开篇块 —— 小号大写标签 + 大标题 + 一段说明。
 *
 * 这个版式本来就在仓库里, 只是**手搓了两份**(菜单设置、扩展页面), 字号、
 * 间距、标签颜色各写各的: 一处 `text-accent/80`、另一处 `text-cyan-400/80`
 * (后者还是照深色底调的, 白卡片上偏淡)。两份的下场是必然的 —— 谁也不会
 * 记得同时改两处, 于是同一个位置在两页长得不一样, **而且不报错**。
 *
 * 所以收成一个产地。这是 WavMint 那套里最有辨识度的一块版式, 它做的事就是
 * 让一页**先说清自己是干什么的**, 再开始摆控件 —— 后台系统的观感, 很大一部分
 * 来自打开就是一堆表单, 没有一句话告诉你这一页在管什么。
 *
 * **只给外围页用。** 看盘的页面不摆这块: 那里每一行都是信息, 用一整屏宽的
 * 标题去换"舒展"不划算, 它们的页头走 `PageHeader`。
 */
export function SectionIntro({ eyebrow, title, children, right, icon, className }: {
  /** 小号大写标签 —— 说明这块归哪一类 */
  eyebrow: string
  title: string
  /** 一段说明。留空就只有标签和标题 */
  children?: ReactNode
  /** 右侧动作区(如「新建」按钮) */
  right?: ReactNode
  /** 标签左边的小图标 */
  icon?: ReactNode
  className?: string
}) {
  return (
    <section className={cn('rounded-card border border-border bg-surface p-6 lg:p-7', className)}>
      <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
        <div className="max-w-3xl">
          <div className="flex items-center gap-2 text-micro font-semibold uppercase tracking-wider text-accent">
            {icon}
            {eyebrow}
          </div>
          <h2 className="mt-2.5 text-2xl font-semibold leading-tight tracking-tight text-foreground">
            {title}
          </h2>
          {children && <p className="mt-2.5 text-sm leading-6 text-secondary">{children}</p>}
        </div>
        {right}
      </div>
    </section>
  )
}
