/**
 * [fork 增强 R270] 复盘弹窗里那条「▸ 依据」—— 三个页签共用一处实现。
 *
 * 三个页签(趋势状态 / 通道结论 / 组合速查)得的是同一个病: **结论上面挂一句,
 * 底下压着一大片测量与参考资料, 而真正要翻的正文被顶到屏外**。
 *
 *   趋势状态   四张 `text-2xl` 的涨跌停计数卡 + 封板率 + 涨停出现在
 *   通道结论   七行读数表(R269 已收)
 *   组合速查   其余 26 格组合 —— 那是查表用的参考, 和这只票今天的状态无关
 *
 * 三处的处理是同一个: **收起来, 要用时展开一次**。所以抽成一个件, 免得同一段
 * 折叠逻辑抄三遍(这个仓库刚为「抄了四遍的 `_code_lines`」付过一次代价)。
 *
 * 两条刻意的选择:
 *
 * - **收起时不渲染 children**, 不是 `hidden`。后者照样进 DOM、照样参与布局计算,
 *   而这里收的恰恰是长表格与二十多行卡片。
 * - **展开状态由调用方持久化**。每个页签记自己的一份 —— 常看读数的人和常查
 *   27 格的人不是同一种用法, 混成一个开关等于谁都不合适。
 */
import { useState, type ReactNode } from 'react'
import { ChevronDown } from 'lucide-react'
import { cn } from '@/lib/cn'

interface Props {
  /** 折叠条上的主标题, 如「依据」「其余 26 格」 */
  label: string
  /** 跟在标题后的灰字说明 —— 说清"这里面是什么、为什么收起来" */
  note?: string
  defaultOpen?: boolean
  onOpenChange?: (open: boolean) => void
  className?: string
  children: ReactNode
}

export function ReviewDisclosure({
  label, note, defaultOpen = false, onOpenChange, className, children,
}: Props) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div className={cn('mx-4 mt-2', className)}>
      <button
        type="button"
        onClick={() => { const v = !open; setOpen(v); onOpenChange?.(v) }}
        aria-expanded={open}
        className="inline-flex items-center gap-1 text-[10px] text-muted transition-colors hover:text-secondary"
      >
        <ChevronDown className={cn('h-3 w-3 transition-transform', open && 'rotate-180')} />
        {label}
        {!!note && <span className="opacity-60">{note}</span>}
      </button>
      {open && <div className="mt-1.5">{children}</div>}
    </div>
  )
}
