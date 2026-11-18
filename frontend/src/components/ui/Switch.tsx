/**
 * [R548] 开关 —— 设置区(与复盘定时)原来各手写一份, 四五份手感一致纯属巧合, 改任何一份就走样。
 * 收成这一个产地(动效评审 R535–R547 的 cohesion 一条)。
 *
 * 动效取值(emil-design-eng / review-animations STANDARDS):
 *   · 滑块是屏上位移 → `ease-in-out-strong`(cubic-bezier(0.77, 0, 0.175, 1)), 200ms(duration-expand);
 *     原来吃的是 Tailwind 默认曲线, 收得太软, 滑过去像在「飘」;
 *   · 轨道只变颜色 → `ease`, 150ms(duration-hover), 与悬停着色同一档;
 *   · [R549] 轨道的按下缩放(全站 :active 规则)→ 160ms 有力的 ease-out, 不再瞬间跳变;
 *   · 只动 transform / 颜色, 连点时 CSS transition 从当前位置折返, 不会从头重播;
 *   · 减少动态效果: index.css 的全局兜底把 transform 移出过渡属性, 滑块瞬时到位, 只剩颜色渐变。
 */
import type { MouseEvent } from 'react'
import { cn } from '@/lib/cn'

const SIZES = {
  md: { track: 'h-5 w-9', knob: 'h-3.5 w-3.5', on: 'translate-x-[18px]', off: 'translate-x-[3px]' },
  sm: { track: 'h-4 w-7', knob: 'h-3 w-3', on: 'translate-x-[14px]', off: 'translate-x-[2px]' },
} as const

/**
 * [R821] 纯视觉轨道 —— 只画"轨道 + 白点", 不接事件、不进 tab 序。
 *
 * 给"整行可点的按钮借开关外观"那一类用（策略构建器的「AI 迭代」行）: 整行是
 * `<button aria-pressed>`, 右边再塞一只真开关就会变成按钮套按钮、键盘要按两下。
 * 抽出来是为了让轨道样式仍然只有一个产地 —— 谁再手写 `h-5 w-9 rounded-full`
 * 就是两套外观各走各的。
 */
export function SwitchTrack({ checked, size = 'md', tone = 'accent', className }: {
  checked: boolean
  size?: keyof typeof SIZES
  /** [R822] 开启态配色。默认 accent; `warning` 给"打开它是有代价的"那一类
   *  (备份的「覆盖已存在的同名项」—— 开了会盖掉本机文件), 让警示留在开关本体上,
   *  而不是回页面手写一份新轨道。 */
  tone?: 'accent' | 'warning'
  className?: string
}) {
  const s = SIZES[size]
  return (
    <span
      aria-hidden="true"
      className={cn(
        'relative inline-flex shrink-0 items-center rounded-full transition-colors duration-hover ease-out',
        s.track,
        checked ? (tone === 'warning' ? 'bg-warning' : 'bg-accent') : 'border border-border bg-surface',
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
    </span>
  )
}

export function Switch({ checked, onChange, disabled, size = 'md', tone = 'accent', title, label, className }: {
  checked: boolean
  /** 点一下: 拿到切换后的值; 事件也给出来(嵌在可点的行里时要 stopPropagation) */
  onChange: (next: boolean, e: MouseEvent<HTMLButtonElement>) => void
  disabled?: boolean
  size?: keyof typeof SIZES
  title?: string
  /** 读屏用的名字; 旁边已有可见文字标签时可不传 */
  label?: string
  /** 开启态配色, 默认 accent; 见 SwitchTrack 的说明 */
  tone?: 'accent' | 'warning'
  className?: string
}) {
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
        // [R549] 轨道同时过渡颜色与 transform: 全站按下规则(index.css :active → scale(0.97))给的缩放原来不在过渡属性里,
        // 按下 / 松开都是瞬间跳变; 按压反馈按 STANDARDS 取 160ms + 有力的 ease-out, 颜色仍是 150ms ease
        'tap-target inline-flex shrink-0 cursor-pointer items-center rounded-full [transition:background-color_150ms_ease,transform_160ms_var(--ease-out-strong)]',
        // [R814] 禁用态全站只有一个值(50), 原来这里是 40, 与 Button 不一致
        'disabled:cursor-not-allowed disabled:opacity-50',
        className,
      )}
    >
      <SwitchTrack checked={checked} size={size} tone={tone} />
    </button>
  )
}
