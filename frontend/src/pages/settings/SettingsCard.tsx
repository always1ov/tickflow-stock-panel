/**
 * [R535] 设置区的卡片 —— 八个分栏同一种卡头: 图标 + 标题 + (一行说明) + 右侧动作。
 *
 * 用户: 「设置里面的每个子页面也要整改」。整改前同一个位置有四种长相:
 *   · AI、实时监控各手写一份 `Card`(两份逐字相同, 带高亮定位);
 *   · 系统五张卡各自手搓卡头;
 *   · 菜单、扩展页面用的是大号开篇块(小标签 + 24px 大标题 + 一段话), 与其余六栏像两个系统;
 *   · 网络那张卡的标题叫「超时设置」, 里面却装着传输压缩。
 * 收成这一个产地(AGENTS.md 硬约束第 12 条「同一个读数只许有一个产地」, 版式同理)。
 *
 * `anchor` 给 `?highlight=<key>` 深链定位用: 打开时滚到这张卡并闪一下(useCardFlash)。
 */
import { useContext, createContext, type ReactNode } from 'react'
import { useCardFlash, cardFlashCls } from '@/lib/useCardFlash'
import { TYPE } from '@/components/ui'
import { cn } from '@/lib/cn'

/** 当前的 `?highlight=` 值 —— 面板在最外层 Provider 一次, 里面的卡各自对自己的 anchor */
export const SettingsHighlight = createContext('')

export function SettingsCard({ icon: Icon, title, badge, desc, right, children, anchor, className, bodyClassName }: {
  icon: React.ComponentType<{ className?: string }>
  title: string
  /** 标题右边的小灰标(如「五档盘口不可用」) */
  badge?: ReactNode
  /** 标题下一行说明 —— 只写这张卡管什么, 细节放进各行自己的说明里 */
  desc?: ReactNode
  /** 卡头右侧动作(保存 / 新建 / 状态) */
  right?: ReactNode
  children?: ReactNode
  anchor?: string
  className?: string
  /** 卡身的额外类名; 表格类卡片传 `p-0` 让行贴边 */
  bodyClassName?: string
}) {
  const highlight = useContext(SettingsHighlight)
  const { ref, flash } = useCardFlash(anchor ? highlight : undefined, anchor ?? '')
  const inner = (
    <section className={cn('rounded-card border border-border bg-surface', className)}>
      <header className="flex items-start justify-between gap-4 px-5 pt-4">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <Icon className="h-4 w-4 shrink-0 text-secondary" />
            <h2 className={TYPE.card}>{title}</h2>
            {badge && (
              <span className="rounded bg-elevated px-1.5 py-0.5 text-micro text-muted">{badge}</span>
            )}
          </div>
          {desc && <p className="mt-1 pl-6 text-xs leading-5 text-muted">{desc}</p>}
        </div>
        {right && <div className="flex shrink-0 items-center gap-2">{right}</div>}
      </header>
      {children !== undefined && <div className={cn('px-5 pb-5 pt-3', bodyClassName)}>{children}</div>}
    </section>
  )
  if (!anchor) return inner
  return (
    <div ref={ref} id={anchor} className={cardFlashCls(flash)}>
      {inner}
    </div>
  )
}

/** 卡内一行设置: 左边名称 + 说明, 右边控件 —— 与各栏原有的开关行同一个版式(py-2, 不画分隔线)。 */
export function SettingRow({ label, desc, children, className }: {
  label: ReactNode
  desc?: ReactNode
  children?: ReactNode
  className?: string
}) {
  return (
    <div className={cn('flex items-center justify-between gap-4 py-2', className)}>
      <div className="min-w-0">
        <div className="text-sm text-foreground">{label}</div>
        {desc && <div className="text-xs text-muted">{desc}</div>}
      </div>
      {children}
    </div>
  )
}
