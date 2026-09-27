/**
 * [R548] 开关 —— 设置区(与复盘定时)原来各手写一份, 四五份手感一致纯属巧合, 改任何一份就走样。
 * 收成这一个产地(动效评审 R535–R547 的 cohesion 一条)。
 *
 * 动效取值(emil-design-eng / review-animations STANDARDS):
 *   · 滑块是屏上位移 → `ease-in-out-strong`(cubic-bezier(0.77, 0, 0.175, 1)), 200ms(duration-expand);
 *     原来吃的是 Tailwind 默认曲线, 收得太软, 滑过去像在「飘」;
 *   · 轨道只变颜色 → `ease`, 150ms(duration-hover), 与悬停着色同一档;
 *   · 只动 transform / 颜色, 连点时 CSS transition 从当前位置折返, 不会从头重播;
 *   · 减少动态效果: index.css 的全局兜底把 transform 移出过渡属性, 滑块瞬时到位, 只剩颜色渐变。
 */
import type { MouseEvent } from 'react'
import { cn } from '@/lib/cn'

const SIZES = {
  md: { track: 'h-5 w-9', knob: 'h-3.5 w-3.5', on: 'translate-x-[18px]', off: 'translate-x-[3px]' },
  sm: { track: 'h-4 w-7', knob: 'h-3 w-3', on: 'translate-x-[14px]', off: 'translate-x-[2px]' },
} as const

export function Switch({ checked, onChange, disabled, size = 'md', title, label, className }: {
  checked: boolean
  /** 点一下: 拿到切换后的值; 事件也给出来(嵌在可点的行里时要 stopPropagation) */
  onChange: (next: boolean, e: MouseEvent<HTMLButtonElement>) => void
  disabled?: boolean
  size?: keyof typeof SIZES
  title?: string
  /** 读屏用的名字; 旁边已有可见文字标签时可不传 */
  label?: string
  className?: string
}) {
  const s = SIZES[size]
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      title={title}
      disabled={disabled}
      onClick={e => onChange(!checked, e)}
      className={cn(
        'tap-target relative inline-flex shrink-0 items-center rounded-full transition-colors duration-hover [transition-timing-function:ease]',
        'disabled:cursor-not-allowed disabled:opacity-40',
        s.track,
        checked ? 'bg-accent' : 'bg-elevated',
        className,
      )}
    >
      <span
        className={cn(
          'inline-block rounded-full bg-white shadow-sm transition-transform duration-expand ease-in-out-strong',
          s.knob,
          checked ? s.on : s.off,
        )}
      />
    </button>
  )
}
