import { cn } from '@/lib/cn'

interface Props {
  title: string
  subtitle?: React.ReactNode
  /** 标题右侧、subtitle 之前的额外节点(如状态徽标) */
  titleExtra?: React.ReactNode
  right?: React.ReactNode
  className?: string
}

export function PageHeader({ title, subtitle, titleExtra, right, className }: Props) {
  return (
    <header
      // [R379 第二层] 页头是「像后台系统」最大的那个口音 —— 52px 高、上下 8px、
      // 一条实边框, 那是工具栏不是页头。**改这一处, 24 个页面一起受益**, 不用
      // 逐页去动(逐页改必然漂, 而且碰不全)。
      //
      // 三处改动, 每一处都克制:
      //   · 高度 52 → 60, 上下留白 8 → 12px。一屏只付出 8px, 换来标题不再贴着
      //     内容 —— 这是 WavMint §8.2 那条「靠留白分组, 不靠线」的最小落法。
      //   · 标题 18 → 20px。页头里只有它一行, 放大不挤任何东西, 但层级立刻出来。
      //   · 底边框 `border-border` → `/60`。页底本来就比页头浅一档, 分界不需要
      //     一条实线来画; 实线正是后台表格的观感。
      //
      // **密度一点没动**: 正文字号、表格行高、列宽、卡片内边距全没碰。
      className={cn(
        'min-h-[60px] px-4 py-3 border-b border-border/60 flex items-center justify-between gap-4',
        className,
      )}
    >
      <div className="flex min-w-0 items-center gap-2.5">
        <h1 className="shrink-0 text-xl font-semibold leading-tight tracking-tight">{title}</h1>
        {titleExtra}
        {subtitle && <span className="min-w-0 truncate text-xs leading-[18px] text-muted">{subtitle}</span>}
      </div>
      {/* [R374] 窄屏兜底: 工具栏多个按钮 + date input 等组合, 默认 shrink-0
          会顶破 375px。改为 flex-wrap + 允许压缩 — left 已经 min-w-0 + truncate,
          窄屏上 left 优先压短, right 内部自然换行, 整行不会被外层 flex 撑出去。
          gap-y-1 让换行不致把 PageHeader 撑太高。 */}
      {right && (
        <div className="flex min-w-0 flex-wrap items-center justify-end gap-x-2 gap-y-1">
          {right}
        </div>
      )}
    </header>
  )
}
