/**
 * [R400 · 阶段三 3.2] 「标签 + 输入 + 单位」这一组。
 *
 * 现状: 光 `TodayControls` 一个文件里, 这串
 *
 *     w-14 rounded border border-border bg-surface px-2 py-1 font-mono
 *     text-foreground outline-none focus:border-sky-400/50
 *
 * 就手抄了 **8 遍**, 而同一个文件里另外 4 个输入框的聚焦色写的是
 * `focus:border-violet-400/50` —— **同一页上的输入框, 聚焦时一半变蓝一半变紫**。
 * 那不是设计, 那是抄漏了。收进来之后聚焦色只有强调色一种说法。
 *
 * ## 这个组件**不碰行为**
 *
 * 它不接管 `value` / `onChange` / `onBlur`, 输入元素仍然由调用方自己写。
 * 原因很实在: 现状里这些框有的是受控(`value`)、有的是非受控(`defaultValue`
 * + `onBlur` 落库), 提交时机各不相同, **而阶段三的前提是「不改变任何功能」**。
 * 把取值逻辑收进来就必然要统一提交时机, 那是功能改动, 不属于这一批。
 *
 * 所以这里只出两样: 外层那个 `<label>` 的排版, 和输入框的 class 串。
 */
import { cn } from '@/lib/cn'

/**
 * 输入框的统一 class。**不含宽度** —— 宽度是每个框自己的事(填百分比的
 * `w-14` 和填时间的框本来就不该一样宽), 调用方传进 `className`。
 *
 * ## 这里**故意没有** `focus:border-…`
 *
 * 原来那几个框写的是 `focus:border-sky-400/50` / `focus:border-violet-400/50`,
 * 而**那两行一直是死的**, 谁也没生效过。`index.css` 里给输入框定边框深一档的
 * 那条规则是
 *
 *     input:not([type='checkbox']):not([type='radio'])   → 权重 (0,2,1)
 *
 * 而 Tailwind 的 `.focus\:border-accent\/50:focus` 只有 (0,2,0) —— **低一档,
 * 永远抢不过**。(单独起一页复现过: 两条规则并存时聚焦读到的始终是前者。)
 *
 * 所以这里不把那句话原样抄进基础件: **抄进来就是又一行"看起来在做事、其实
 * 什么也没做"的代码**, 而且它会被后面几十个调用点跟着抄。
 *
 * 聚焦指示本来就有, 而且是好的那个: `index.css` 的全局 `:focus-visible` 给
 * 所有输入类控件加了 2px 强调色轮廓(R124, 带 `!important`, 抢得过)。边框再变
 * 个色只是装饰。要让边框也跟着变, 得改 `index.css` 那条规则的适用范围 ——
 * 那是全站每一个输入框都会受影响的改动, 不该夹在一次基础件收口里顺手做。
 */
export const fieldInput = cn(
  'rounded-input border border-border bg-surface px-g4 py-g2',
  'font-mono text-foreground outline-none',
)

/** 下拉与输入同一套外观, 只是不用等宽字形(选项是中文)。 */
export const fieldSelect = cn(
  'rounded-input border border-border bg-surface px-g4 py-g2',
  'text-foreground outline-none',
)

export function Field({ label, unit, disabled, className, children, ...rest }: {
  label: React.ReactNode
  /** 跟在输入框后面的单位(「条」「%」「日」)。 */
  unit?: React.ReactNode
  /** 只管变灰; 真正的禁用要写在里面那个 input 上, 不然还点得动。 */
  disabled?: boolean
  children: React.ReactNode
} & Omit<React.LabelHTMLAttributes<HTMLLabelElement>, 'children'>) {
  return (
    <label
      className={cn('flex items-center gap-g4 text-micro text-muted',
                    disabled && 'opacity-60', className)}
      {...rest}
    >
      <span className="whitespace-nowrap">{label}</span>
      {children}
      {unit != null && <span className="whitespace-nowrap">{unit}</span>}
    </label>
  )
}
