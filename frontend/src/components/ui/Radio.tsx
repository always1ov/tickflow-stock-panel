/**
 * [R824] 单选。
 *
 * R823 收口时全仓只剩一处手写 radio（监控页的「批量渠道」）, 但那处仍是
 * `tap-target h-4 w-4 accent-accent` 现场拼的 —— 和 `Checkbox` 是同一套取值
 * 却写着两遍, 下一个页面照抄时随手改成 `h-3.5` 就又分叉了。
 *
 * **用原生 `<input type="radio">`**: 键盘方向键换选项、读屏语义、`name` 分组
 * 全靠它, 自己画一个 div 要补的恰恰是这些。这里只统一三件事: 尺寸、着色、
 * 禁用态 —— 与 `Checkbox` 完全一致（16px 视觉, 点击区由 `tap-target` 撑到 28px）。
 */
import { cn } from '@/lib/cn'

export function Radio({ className, ...rest }: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      type="radio"
      className={cn(
        'tap-target h-4 w-4 shrink-0 cursor-pointer accent-accent',
        'disabled:cursor-not-allowed disabled:opacity-50',
        className,
      )}
      {...rest}
    />
  )
}
