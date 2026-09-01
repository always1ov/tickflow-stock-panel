/**
 * [fork 增强] R128 按钮样式配方 —— skill §8「Clear visual hierarchy
 * (primary, secondary, ghost)」的落地。
 *
 * 现状与取舍(重要, 别照着"全项目替换"去做):
 * 全项目 917 个按钮的类名都是手写的。全部改成组件是个几百处的机械改动, 在一个
 * 每天用来做交易决策的界面上, 收益不抵回归风险 —— 所以**这里只提供配方, 不做
 * 大规模替换**: 新写的按钮、以及顺手路过要改的按钮用它, 存量慢慢收敛。
 *
 * 已经全局兜住、**不需要**每个按钮各写一遍的东西(见 index.css):
 *   - 键盘焦点环([R124])
 *   - 按下缩放反馈([R128])
 *   - 减少动效的适配([R124])
 * 所以下面的配方只管三件事: 层级配色、尺寸、禁用态。
 *
 * 用法:
 *   <button className={btn('primary')}>生成复盘</button>
 *   <button className={btn('ghost', 'sm')} disabled={busy}>取消</button>
 *   <button className={btn('secondary', 'icon')} aria-label="设置"><Cog/></button>
 */
import { cn } from '@/lib/cn'

export type BtnVariant = 'primary' | 'secondary' | 'ghost' | 'danger'
export type BtnSize = 'sm' | 'md' | 'icon' | 'icon-sm'

const VARIANT: Record<BtnVariant, string> = {
  // 一屏只该有一个主按钮 —— 它代表"这个界面希望你做的那件事"
  primary: 'bg-accent text-white hover:brightness-110',
  // 次要动作: 有边框但不抢眼
  secondary: 'border border-border bg-surface text-secondary hover:bg-elevated hover:text-foreground',
  // 幽灵: 工具条、图标按钮, 平时几乎看不见
  ghost: 'text-muted hover:bg-elevated hover:text-foreground',
  // 危险: 删除/清空这类不可逆动作, 与主按钮互斥出现
  danger: 'border border-danger/40 bg-danger/10 text-danger hover:bg-danger/20',
}

const SIZE: Record<BtnSize, string> = {
  sm: 'h-7 gap-1 px-2.5 text-[11px]',
  md: 'h-8 gap-1.5 px-3 text-xs',
  // 图标按钮做成正方形, 与同排的文字按钮等高, 一排控件底边才齐
  icon: 'h-8 w-8 justify-center',
  'icon-sm': 'h-7 w-7 justify-center',
}

export function btn(variant: BtnVariant = 'secondary', size: BtnSize = 'md', extra?: string): string {
  return cn(
    'inline-flex items-center rounded-btn font-medium transition-colors duration-hover',
    // 禁用态统一口径: 变淡 + 禁止光标; 按下缩放由全局规则按 :disabled 自动跳过
    'disabled:cursor-not-allowed disabled:opacity-50',
    VARIANT[variant],
    SIZE[size],
    extra,
  )
}
