/**
 * [R512 · fork 增强] 页头右侧的分栏条 —— Minds 与模拟盘共用这一份。
 *
 * 用户指着 Minds 的分栏(笔记 4 / 洞见 / 交易计划 / 对话)说「模拟盘的内容分类整理成图片这样的表达方式」。
 * 两页各写一遍的话迟早长成两个样子(「同一个读数只许有一个产地」), 所以从 Minds 里抽出来。
 *
 * 当前栏写在 `?tab=` 里(可收藏、刷新不丢), 切栏用 replace 不堆历史。
 * **切栏是瞬时的, 不加过渡** —— 这是高频操作(AGENTS.md 动效硬规则第 4 条)。
 * 手机上图标收起、整条横向滚动, 不换行。
 */
import { useSearchParams } from 'react-router-dom'
import type { LucideIcon } from 'lucide-react'
import { cn } from '@/lib/cn'
import { SEG, SEG_ITEM, SEG_OFF, SEG_ON } from '@/components/ui'

export interface PageTabDef {
  title: string
  icon: LucideIcon
}

/** 读 `?tab=`, 不认识的值落回 `fallback`; 返回当前栏与切栏函数。 */
export function usePageTab<T extends string>(tabs: Record<T, PageTabDef>, fallback: NoInfer<T>): [T, (tab: T) => void] {
  const [searchParams, setSearchParams] = useSearchParams()
  const requested = searchParams.get('tab')
  const active = requested != null && Object.prototype.hasOwnProperty.call(tabs, requested)
    ? requested as T
    : fallback
  const change = (tab: T) => {
    const next = new URLSearchParams(searchParams)
    next.set('tab', tab)
    setSearchParams(next, { replace: true })
  }
  return [active, change]
}

export function PageTabs<T extends string>({ tabs, active, onChange, counts, label }: {
  tabs: Record<T, PageTabDef>
  active: T
  onChange: (tab: T) => void
  /** 挂在栏名后面的小数字; 缺省或 null 不画 */
  counts?: Partial<Record<T, number | null>>
  /** 读屏用的分栏名 */
  label: string
}) {
  return (
    <nav className="min-w-0 max-w-full overflow-x-auto" aria-label={label}>
      <div className={cn(SEG, 'min-w-max')}>
        {(Object.keys(tabs) as T[]).map(tab => {
          const { title, icon: Icon } = tabs[tab]
          const on = active === tab
          const n = counts?.[tab]
          return (
            <button
              key={tab}
              type="button"
              onClick={() => onChange(tab)}
              aria-current={on ? 'page' : undefined}
              className={cn(SEG_ITEM, 'sm:gap-1.5', on ? SEG_ON : SEG_OFF)}
            >
              <Icon className="hidden h-3.5 w-3.5 sm:block" />
              {title}
              {n != null && <span className="text-micro tabular-nums opacity-70">{n}</span>}
            </button>
          )
        })}
      </div>
    </nav>
  )
}
