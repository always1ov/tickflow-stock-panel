/**
 * [fork 增强 R170] 仓位中心 —— 把「持仓提醒」(真钱批次)与「AI 操盘手」(模拟盘)
 * 收进同一个页面的两个 tab。
 *
 * ## 为什么是 tab 而不是揉成一张表
 *
 * 一边是**真钱**(每笔买入的成本/数量/止盈止损/到期), 一边是**模拟盘**(模型拿虚拟
 * 资金跑, 目的是体检这套系统给的信息够不够用)。在一个看盘系统里把真仓和假仓混排,
 * 迟早有一天早上会把 AI 的模拟持仓当成自己的仓 —— 所以两侧内容**永不同表**,
 * AI 那侧还常驻一条"模拟盘·非真实资金"的横幅。
 *
 * ## 为什么外壳单独一个文件
 *
 * `Lots.tsx` 是上游的文件。把 tab 逻辑写进去会让每次同步上游都在这一块起冲突。
 * 外壳放在这个 fork 独有的文件里, 上游那份只多了一个 `embedded` 开关(嵌入时不画
 * 自己的页头), 冲突面压到最小。
 */
import { useEffect } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Bot, Layers2 } from 'lucide-react'
import { PageHeader } from '@/components/PageHeader'
import { Lots } from '@/pages/Lots'
import { PaperTrading } from '@/pages/PaperTrading'
import { cn } from '@/lib/cn'

const TABS = [
  { key: 'lots', label: '我的批次', icon: Layers2, hint: '真实买入记录 · 自动生成止盈止损与到期监控' },
  { key: 'paper', label: 'AI 操盘手', icon: Bot, hint: '模拟盘 · 体检这套系统给的信息够不够模型做决定' },
] as const

type TabKey = (typeof TABS)[number]['key']

export function PositionsHub() {
  const [params, setParams] = useSearchParams()
  const raw = params.get('tab')
  const tab: TabKey = raw === 'paper' ? 'paper' : 'lots'

  // 老书签 /lots?symbol=xxx 是 R169 的批次定位, 必须落在批次 tab 上。
  // 这里不做任何跳转, 只是把默认值说清楚: 没写 tab 就是批次。
  useEffect(() => {
    if (raw && raw !== 'lots' && raw !== 'paper') {
      const next = new URLSearchParams(params)
      next.delete('tab')
      setParams(next, { replace: true })
    }
  }, [raw, params, setParams])

  const go = (key: TabKey) => {
    const next = new URLSearchParams(params)
    if (key === 'lots') next.delete('tab')
    else next.set('tab', key)
    // 切 tab 时把批次定位参数丢掉 —— 它只对批次 tab 有意义, 留着会在切回来时
    // 又滚一次, 用户没要求却动了视口
    if (key !== 'lots') next.delete('symbol')
    setParams(next, { replace: true })
  }

  const active = TABS.find(t => t.key === tab)!

  return (
    <div className="flex h-full min-h-0 flex-col bg-base">
      <PageHeader title="仓位中心" subtitle={active.hint} />

      {/* tab 条。切 tab 是高频键鼠操作, 按 emil-design-eng 的频次规则不加任何入场动画,
          只有配色过渡(transition-colors)。 */}
      <div className="shrink-0 px-5 pt-1">
        <div
          role="tablist"
          aria-label="仓位中心"
          className="inline-flex items-center gap-0.5 rounded-btn border border-border/50 bg-surface/70 p-0.5"
        >
          {TABS.map(t => {
            const Icon = t.icon
            const on = t.key === tab
            return (
              <button
                key={t.key}
                type="button"
                role="tab"
                aria-selected={on}
                onClick={() => go(t.key)}
                title={t.hint}
                className={cn(
                  'inline-flex items-center gap-1.5 rounded-btn px-3.5 py-1.5 text-xs transition-colors cursor-pointer',
                  on ? 'bg-accent/15 font-medium text-accent shadow-sm' : 'text-secondary hover:text-foreground',
                )}
              >
                <Icon className="h-3.5 w-3.5" />
                {t.label}
              </button>
            )
          })}
        </div>
      </div>

      {/* 两个 tab 各自挂载/卸载而不是靠 CSS 隐藏: 模拟盘那侧有轮询与定时配置,
          藏着不卸载等于在批次页后台一直跑。 */}
      <div className="min-h-0 flex-1">
        {tab === 'lots' ? <Lots embedded /> : <PaperTrading embedded />}
      </div>
    </div>
  )
}
