/**
 * [R814] 弹窗的三样固定件: 面板皮肤、标题行、右上角关闭叉。
 *
 * 现状是 `Modal` 的 `panelClassName` 每个调用点各传一份: 宽度五花八门,
 * 底色有的 `bg-surface` 有的 `bg-elevated`, 圆角有的 `rounded-card` 有的
 * 裸 `rounded-lg`, 关闭按钮有的在标题行、有的在底部、有的干脆没有。
 *
 * 这里**不包装 `Modal`**(它管焦点陷阱和 ESC, 属于行为层), 只出三样看得见的东西:
 *
 *   <Modal panelClassName={dialogPanel('md')} …>
 *     <div className={DIALOG_HEADER}>
 *       <h2 className={DIALOG_TITLE}>标题</h2>
 *       <DialogClose onClose={onClose} />
 *     </div>
 *     …
 *   </Modal>
 *
 * 宽度只有四档, 按"里面装什么"选, 不按个人喜好选:
 *   sm 24rem —— 一句话确认(删除/清空)
 *   md 32rem —— 表单、设置(默认)
 *   lg 42rem —— 表格、列表
 *   xl 56rem —— 整页级(个股弹窗这种另走整页面板, 不用这里)
 */
import { X } from 'lucide-react'
import { cn } from '@/lib/cn'
import { Button } from './Button'
import { TYPE } from './type'

export type DialogSize = 'sm' | 'md' | 'lg' | 'xl'

const SIZE: Record<DialogSize, string> = {
  sm: 'max-w-sm',
  md: 'max-w-lg',
  lg: 'max-w-2xl',
  xl: 'max-w-4xl',
}

/** 面板皮肤: 实底、实边框、弹窗档圆角、只有浮层才有的投影。 */
const PANEL = 'w-[92vw] bg-surface border border-border rounded-dialog shadow-dialog'

/** 只要面板 class —— 传给 `<Modal panelClassName={…}>`。 */
export function dialogPanel(size: DialogSize = 'md', extra?: string) {
  return cn(PANEL, SIZE[size], extra)
}

/** 标题行: 标题左、关闭叉右, 内边距与卡片同一档。 */
export const DIALOG_HEADER = 'flex items-start justify-between gap-s2 px-s2 pt-s2'
export const DIALOG_TITLE = cn(TYPE.section, 'min-w-0 flex-1')
/** 内容区与底部操作区。底部只有一道淡分隔线, 与 `CardSection` 同一档。 */
export const DIALOG_BODY = 'px-s2 py-s2'
export const DIALOG_FOOTER = 'flex items-center justify-end gap-g2 border-t border-border/40 px-s2 py-s2'

/**
 * 右上角关闭叉。**全站弹窗都要有**(用户 R812 明确要求过): 只有 ESC 和点遮罩
 * 是不够的 —— 鼠标用户找不到出口。
 */
export function DialogClose({ onClose, className, label = '关闭' }: {
  onClose: () => void
  className?: string
  label?: string
}) {
  return (
    <Button
      icon
      variant="ghost"
      size="sm"
      aria-label={label}
      title={label}
      onClick={onClose}
      className={cn('shrink-0', className)}
    >
      <X className="h-4 w-4" />
    </Button>
  )
}
