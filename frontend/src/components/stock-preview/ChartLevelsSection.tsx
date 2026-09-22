/**
 * [R430] 个股弹窗重做第二块:「图表与价位」。
 *
 * 用户给的排版图: 一行小标题, 下面左右两张卡片 —— 左边是图(日 K / 分时 / 关键价位
 * 三个视图), 右边是关键价位一类一行的列表(`LevelSideList`)。这里只管版面:
 * 图本身、右侧列表、工具栏右侧那一格都由弹窗传进来(它们要用的状态都在弹窗里)。
 *
 * 窄屏(< lg)两张卡片上下叠, 列表落到图下面。
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

export function ChartLevelsSection({ view, onViewChange, levelsEnabled = true, toolbar, side, children }: {
  view: ChartView
  onViewChange: (v: ChartView) => void
  /** 弹窗的 `enableLevelsView`: 关掉时没有「关键价位」这个视图, 也没有右侧列表 */
  levelsEnabled?: boolean
  /** 工具栏右侧那一格: 随视图换(分时的天数 / 关键价位的一句用法) */
  toolbar?: ReactNode
  /** 右侧卡片 */
  side?: ReactNode
  children: ReactNode
}) {
  const tabs = levelsEnabled ? TABS : TABS.filter(t => t.key !== 'levels')
  const withSide = levelsEnabled && side
  return (
    <section>
      <SectionTitle title="图表与价位" sub="价格、通道与关键价位" />

      <div className={`mt-3 grid gap-4 ${withSide ? 'lg:grid-cols-[minmax(0,1fr)_300px]' : ''}`}>
        <div className="min-w-0 rounded-card border border-border bg-surface p-4">
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
        {withSide}
      </div>
    </section>
  )
}
