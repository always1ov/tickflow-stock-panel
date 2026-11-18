/**
 * [R814] 复选框。
 *
 * 现状是 `accent-accent h-3 w-3 cursor-pointer` 这类串散在十几处, 尺寸有
 * `h-3 / h-3.5 / h-4` 三种, 点击区也没有统一处理。
 *
 * **用原生 `<input type="checkbox">`**: 它自带键盘操作、读屏语义与表单行为,
 * 自己画一个 div 要去补的不是样式而是这些。这里只统一三件事: 尺寸、着色、
 * 禁用态。
 *
 * 16px 的视觉尺寸在密集表格里够用, 点击区由 `tap-target` 撑到 28px
 * (见 `index.css` R317 —— 桌面密集界面的既定底线)。
 */
import { cn } from '@/lib/cn'

export function Checkbox({ className, ...rest }: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      type="checkbox"
      className={cn(
        'tap-target h-4 w-4 shrink-0 cursor-pointer accent-accent',
        'disabled:cursor-not-allowed disabled:opacity-50',
        className,
      )}
      {...rest}
    />
  )
}
