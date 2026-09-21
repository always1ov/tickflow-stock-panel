import { cn } from '@/lib/cn'

interface Props {
  title: string
  subtitle?: React.ReactNode
  /** 标题右侧、subtitle 之前的额外节点(如状态徽标) */
  titleExtra?: React.ReactNode
  right?: React.ReactNode
  className?: string
}

/**
 * 所有页面共用的页头。**改这一处, 24 个页面一起受益** —— 逐页改必然漂, 而且碰不全。
 *
 * ## [R379 第二层] 它原来「像后台系统」
 *
 * 52px 高、上下 8px、一条实边框, 那是工具栏不是页头。三处改动, 每一处都克制:
 * 高度 52 → 60(一屏只付出 8px, 换来标题不再贴着内容); 标题 18 → 20px(页头里只有
 * 它一行, 放大不挤任何东西); 底边框 `border-border` → `/60`(页底本来就比页头浅
 * 一档, 分界不需要一条实线)。**密度一点没动**: 正文字号、表格行高、列宽、卡片
 * 内边距全没碰。
 *
 * ## [R394] 手机上整个页头是塌的
 *
 * 用户: 「我用手机看网页显示排版非常不正常, 所有页面都是」。三件事叠在一起:
 *
 * 1. **页头不换行**。`flex-wrap` 当初只写在 `PageShell` 传进来的 className 里,
 *    而有 10 个页面(策略、自选、复盘、数据…)是**直接用 `PageHeader`** 的, 拿不到
 *    那份 className。于是页头是一行不换的 flex: 工具栏要么被压成一个字宽(中文
 *    竖着排), 要么整个溢出到视口外(实测按钮 x=391, 屏幕才 390 宽, 被根节点的
 *    `overflow-hidden` 吃掉)。**根因是这一条。**
 * 2. **没人给悬浮汉堡让位**。`Layout` 在 <768px 时把菜单按钮做成
 *    `fixed left-3 top-3`(34×34, 右缘到 x=46), 而页头从 x=12/16 起排 ——
 *    标题正好压在按钮底下, 24 个页面同一个症状。
 * 3. **工具栏一换行, 标题就飘到半空**。原来是 `items-center`, 而窄屏上右边那块
 *    能有三四行高。
 *
 * 断点取 `md`(768px), 与 `useIsDesktop()` 的 `min-width: 768px` 是同一个数 ——
 * 按钮在哪个宽度出现, 位置就在哪个宽度让出来, 不能各写各的。
 */
export function PageHeader({ title, subtitle, titleExtra, right, className }: Props) {
  return (
    <header
      className={cn(
        'min-h-[60px] px-4 py-3 border-b border-border/60 flex flex-wrap gap-4',
        // 窄屏顶对齐(右边那块可能三四行高), 宽屏回到居中 —— 宽屏本来就是一行。
        'items-start justify-between md:items-center lg:flex-nowrap',
        className,
      )}
    >
      {/*
        `pl-11` 是给那个悬浮汉堡让的位置。**让位写在这一层, 不写在 `header` 上** ——
        `className` 是调用方传的, `PageShell` 那份里写着 `px-3 lg:px-5`, 经 `twMerge`
        合并后会把基础类里的左内边距整个吃掉: 加了不生效, 而且不报错。

        **也不用占位元素**: 占位只顶开第一行, 副标题换行之后那几行照样贴回左边缘、
        钻到按钮底下; 内边距是整块让位, 换行的每一行都对齐。

        `basis-full` 还要连 `shrink-0` 一起给 —— 只给 basis 的话, 默认 `shrink:1`
        会让它宁可压扁自己也不换行(实测左边只分到 110px, 副标题被 `truncate` 吃到
        一个字不剩)。宽屏还原成原来的自适应宽度。
      */}
      <div className="flex min-w-0 shrink-0 basis-full flex-wrap items-center gap-x-2.5 gap-y-0.5 pl-11 md:shrink md:basis-auto md:pl-0">
        <h1 className="shrink-0 text-xl font-semibold leading-tight tracking-tight">{title}</h1>
        {titleExtra}
        {subtitle && <span className="min-w-0 truncate text-xs leading-[18px] text-muted">{subtitle}</span>}
      </div>
      {/* [R374] 窄屏兜底: 工具栏多个按钮 + date input 等组合, 默认 shrink-0 会顶破
          375px。改为 flex-wrap + 允许压缩, 窄屏上内部自然换行, 整行不会被撑出去。
          gap-y-1 让换行不致把页头撑太高。
          [R394] 窄屏左对齐: 换行之后右对齐会留一条参差的左缘, 读起来更乱。 */}
      {right && (
        <div className="flex min-w-0 flex-wrap items-center justify-start gap-x-2 gap-y-1 md:justify-end">
          {right}
        </div>
      )}
    </header>
  )
}
