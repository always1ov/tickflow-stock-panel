/**
 * [R400 · 阶段三 3.2] 全站唯一的按钮取值表。
 *
 * ## 为什么必须有这一处
 *
 * 动手前先数过: 995 个 `<button>`, 其中能被静态解析出 class 串的 232 个里,
 * **有 193 种互不相同的写法** —— 平均每 1.2 个按钮一种样式。所谓"风格不统一"
 * 不是感觉, 是这个数。逐页去改只会得到第 194 种。
 *
 * ## 取值从哪来
 *
 * **不是我发明的, 是从现状里数出来的多数派**, 再折到 R399 的规范档位上:
 *
 *   primary    `bg-accent … text-base`(现状 39 处) —— 用户定的「全页只保留一个
 *              主色实心主按钮」, 指的就是这一档
 *   outline    `border border-border bg-base text-muted hover:text-foreground`
 *              —— 现状最常见的一种, 工具条按钮几乎都是它
 *   secondary  `bg-elevated text-secondary`
 *   ghost      无边框无底, 只有 hover 才显形 —— 表格行内那些图标按钮
 *   danger     outline 的红色 hover 变体(删除/清空)
 *
 * `selected` 不是第六个 variant 而是一个**正交开关**: 现状里那些"选中就换个
 * 颜色"的药丸各写各的(`sky-400/15`、`accent/10`、`violet-500/20`…), 同一件事
 * 三四种颜色。收成一处之后**只有强调色一种说法**。
 *
 * ## 两条容易踩的
 *
 * 1. **主按钮的字色写 `text-on-accent` 不写 `text-base`。** 后者同时是颜色和
 *    字号(Tailwind 出厂 16px), 进 `cn()` 会和字号撞组、颜色被静默丢掉。
 *    见 `tailwind.config.ts` 里 `on-accent` 那段。
 * 2. **按下反馈、焦点环、`prefers-reduced-motion` 全都不在这里写。**
 *    `index.css` 有三条全局规则兜着(R124/R128/R317), 这里再写一遍只会写岔。
 *    所以下面只有 `transition-colors` 一条过渡 —— 按 AGENTS.md 前端动效硬规则
 *    第 1 条, 写明属性, 不用 `transition-all`。
 */
import { forwardRef } from 'react'
import { cn } from '@/lib/cn'

export type ButtonVariant = 'primary' | 'secondary' | 'outline' | 'ghost' | 'danger'
export type ButtonSize = 'xs' | 'sm' | 'md'

const BASE =
  'inline-flex items-center justify-center whitespace-nowrap rounded-btn font-medium ' +
  'transition-colors duration-hover ease-out cursor-pointer ' +
  'disabled:cursor-not-allowed disabled:opacity-50'

const VARIANT: Record<ButtonVariant, string> = {
  primary: 'bg-accent text-on-accent hover:bg-accent/90',
  secondary: 'bg-elevated text-secondary hover:bg-elevated/70 hover:text-foreground',
  outline: 'border border-border bg-base text-muted hover:text-foreground',
  ghost: 'text-muted hover:bg-elevated hover:text-foreground',
  danger: 'border border-border bg-base text-muted hover:border-danger/40 hover:text-danger',
}

/** 选中态 —— 与 variant 正交。全站只有强调色这一种说法。 */
const SELECTED = 'border border-accent/40 bg-accent-soft text-accent'

/**
 * 横向取骨架刻度(8/16/24), 纵向取行内密度刻度(4/6/8)。
 *
 * **纵向单独一套是有意的**: 这是密集看盘界面, 按钮高度直接决定一屏能排几行
 * 工具条。8 基套进纵向会让每个按钮长高 8~10px, 而 R399 已经就"两套刻度"
 * 给过理由(`test_design_spec.py`)。
 */
const SIZE: Record<ButtonSize, string> = {
  xs: 'gap-g2 px-s1 py-g2 text-micro',
  sm: 'gap-g3 px-s2 py-g3 text-body',
  md: 'gap-g4 px-s3 py-g4 text-body',
}

/** 方形图标钮: 四边等距, 不然图标不在正中。 */
const ICON_SIZE: Record<ButtonSize, string> = {
  xs: 'gap-g2 p-g2 text-micro',
  sm: 'gap-g3 p-g3 text-body',
  md: 'gap-g4 p-g4 text-body',
}

export interface ButtonStyleProps {
  variant?: ButtonVariant
  size?: ButtonSize
  /** 选中态(药丸/开关式按钮)。与 variant 正交, 会盖掉它的配色。 */
  selected?: boolean
  /** 方形图标钮: 四边等距 */
  icon?: boolean
}

/**
 * 只要 class 串、不要 `<button>` 元素时用它 —— 比如目标其实是 `<a>`,
 * 或者外层已经是 `<label>`。**逃生口只有这一个**, 免得有人因为"这里用不了
 * `<Button>`"又去手写第 194 种。
 */
export function buttonClass(
  { variant = 'outline', size = 'sm', selected = false, icon = false }: ButtonStyleProps = {},
  extra?: string,
) {
  return cn(
    BASE,
    (icon ? ICON_SIZE : SIZE)[size],
    selected ? SELECTED : VARIANT[variant],
    extra,
  )
}

type Props = ButtonStyleProps & React.ButtonHTMLAttributes<HTMLButtonElement>

export const Button = forwardRef<HTMLButtonElement, Props>(function Button(
  { variant, size, selected, icon, className, type, ...rest }, ref,
) {
  return (
    <button
      ref={ref}
      // 不写 type 的 <button> 在 <form> 里默认是 submit —— 全站绝大多数按钮
      // 只是普通操作, 默认 button 才对; 真要提交的显式传 type="submit"。
      type={type ?? 'button'}
      className={buttonClass({ variant, size, selected, icon }, className)}
      {...rest}
    />
  )
})
