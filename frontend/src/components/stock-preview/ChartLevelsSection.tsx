/**
 * [R430] 个股弹窗重做第二块:「图表与价位」。
 *
 * 一行小标题, 下面一张卡片: 日 K / 分时 / 关键价位三个视图。这里只管版面:
 * 图本身、工具栏右侧那一格都由弹窗传进来(它们要用的状态都在弹窗里)。
 *
 * [R432] 右边那张关键价位列表撤了 —— 用户: 「关键价位还是按照以前那样显示吧,
 * 在右侧很不方便, 可以保留方形按钮」。开关回到图的正上方(`LevelToolbar`),
 * 图于是占满整张卡片的宽度。
 */
import type { ReactNode } from 'react'
import { CandlestickChart, Clock, Crosshair } from 'lucide-react'
import { SectionTitle } from './SectionTitle'

export type ChartView = 'daily' | 'intraday' | 'levels'

const TABS: { key: ChartView; label: string; Icon: typeof Clock }[] = [
  { key: 'daily', label: '日 K', Icon: CandlestickChart },
  { key: 'intraday', label: '分时', Icon: Clock },
  { key: 'levels', label: '关键价位', Icon: Crosshair },
]

export function ChartLevelsSection({ view, onViewChange, levelsEnabled = true, toolbar, children }: {
  view: ChartView
  onViewChange: (v: ChartView) => void
  /** 弹窗的 `enableLevelsView`: 关掉时没有「关键价位」这个视图 */
  levelsEnabled?: boolean
  /** 工具栏右侧那一格: 随视图换(分时的天数 / 关键价位的一句用法) */
  toolbar?: ReactNode
  children: ReactNode
}) {
  const tabs = levelsEnabled ? TABS : TABS.filter(t => t.key !== 'levels')
  return (
    <section>
      <SectionTitle title="图表与价位" sub="价格、通道与关键价位" />

      <div className="mt-3 min-w-0 rounded-card border border-border bg-surface p-4">
        <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
          <div role="tablist" aria-label="图表视图"
               className="inline-flex shrink-0 items-center gap-1 rounded-btn border border-border bg-elevated/60 p-1">
            {tabs.map(({ key, label, Icon }) => (
              <button key={key} type="button" role="tab" aria-selected={view === key}
                      onClick={() => onViewChange(key)}
                      className={`inline-flex h-8 items-center gap-1.5 rounded-btn px-3 text-sm transition-colors duration-hover ${
                        view === key ? 'bg-foreground font-medium text-surface' : 'text-secondary hover:text-foreground'
                      }`}>
                <Icon className="h-3.5 w-3.5" />
                {label}
              </button>
            ))}
          </div>
          {toolbar}
        </div>
        <div className="mt-3">{children}</div>
      </div>
    </section>
  )
}
