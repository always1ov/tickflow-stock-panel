/**
 * [R430] 个股弹窗「图表与价位」右边那张卡片: 关键价位一类一行, 点开哪一类就画到左边图上。
 *
 * 用户给的排版图 + 三条答复:
 *   · 枢轴点「档位」、二型「粗细 / 上攻推算位 / 回测这三档」这些小开关 →
 *     **放在这张列表里, 点开那一类时就在它下面展开**, 关掉就收起;
 *   · 左边正在看日 K / 分时时点某一类 → 切到关键价位并把它打开(只开不关:
 *     那一下的意思是「给我看它」, 若是关掉就等于点了没反应)。
 *
 * 数怎么算、能不能点、悬停写什么, 与图上方那一排开关同一个产地(`levelGroupStat`)。
 */
import { useState } from 'react'
import { FIB2_ROLE_TARGET, fib2RoleColor, levelColors, useTheme } from '@/lib/theme'
import { LEVEL_GROUPS, useShownLevels, type LevelType, type PriceLevel } from '@/components/stock-analysis/AnalysisKChart'
import { Fib2GrainDialog } from '@/components/stock-analysis/Fib2GrainDialog'
import { useAnalysisKline, useStockLevels } from '@/components/stock-analysis/StockLevelsPanel'
import {
  FIB2_BACKTEST_TITLE, FIB2_GRAINS, FIB2_TARGETS_TITLE, PIVOT_RANK_TITLES,
  levelGroupStat, type LevelControls,
} from '@/components/stock-analysis/levelControls'

const ROW = 'flex h-10 w-full items-center gap-2.5 rounded-btn border px-3 text-left text-sm '
  + 'transition-colors duration-hover disabled:cursor-not-allowed disabled:opacity-40'
const ROW_IDLE = 'border-border bg-surface text-foreground hover:bg-elevated disabled:hover:bg-surface'
const ROW_ON = 'border-foreground bg-foreground text-surface font-medium'
/** 展开的小开关: 与图上方那一排同一个样子(选中态用这一类自己的颜色) */
const CHIP = 'h-6 whitespace-nowrap rounded-btn border px-2 text-micro transition-colors duration-hover'
const CHIP_IDLE = 'border-border/60 bg-base/40 text-muted hover:border-border hover:text-foreground'

export function LevelSideList({ symbol, controls, showing, onReveal }: {
  symbol: string
  controls: LevelControls
  /** 左边此刻画的是不是关键价位图 */
  showing: boolean
  /** 左边不在关键价位时, 点了某一类就切过去 */
  onReveal: () => void
}) {
  const theme = useTheme()
  const kline = useAnalysisKline(symbol)
  const levelsQ = useStockLevels(symbol)
  const [fitOpen, setFitOpen] = useState(false)
  const { activeTypes, pivotRank, fib2Grain, fib2ShowTargets } = controls
  const fib2 = levelsQ.data?.fib2
  const { effLevels, fib2Raw } = useShownLevels(
    levelsQ.data?.levels as Record<LevelType, PriceLevel[]> | undefined,
    fib2, kline.data?.rows ?? [], fib2Grain, fib2ShowTargets)

  const LC = levelColors(theme)
  // 选中那一行是反相的(亮色主题黑底、暗色主题白底)。圆点换用**另一套主题**的
  // 那份颜色 —— 调色板本来就是按底色分两套调的: 黑底上该用暗色主题那份亮色,
  // 白底上该用亮色主题那份深色。不换的话, 暗色主题里六态关键点那个近白的点
  // 画在白底上就没了。
  const LC_ON = levelColors(theme === 'dark' ? 'light' : 'dark')
  const targetColor = fib2RoleColor(FIB2_ROLE_TARGET, theme)
  const tint = (c: string) => ({ borderColor: c + '66', backgroundColor: c + '26', color: c })

  const pick = (t: LevelType) => {
    if (showing) controls.toggleType(t)
    else { controls.turnOn(t); onReveal() }
  }

  return (
    <div className="flex flex-col rounded-card border border-border bg-surface p-4">
      <div className="flex items-center justify-between gap-2">
        <span className="text-base font-semibold text-foreground">关键价位</span>
        <button type="button" onClick={controls.clearAll} disabled={activeTypes.size === 0}
                className="h-7 rounded-btn border border-border bg-surface px-2.5 text-xs text-foreground transition-colors duration-hover hover:bg-elevated disabled:opacity-40">
          全部清除
        </button>
      </div>
      <p className="mt-1 text-xs text-muted">点开哪一类, 价位就画到图上</p>

      <div className="mt-3 flex flex-col gap-2">
        {LEVEL_GROUPS.map(g => {
          const on = activeTypes.has(g.key)
          const { count, total, title } = levelGroupStat(g.key, g.label, effLevels, fib2Raw, pivotRank)
          return (
            <div key={g.key}>
              <button type="button" onClick={() => pick(g.key)} disabled={total === 0}
                      aria-pressed={on} title={title}
                      className={`${ROW} ${on ? ROW_ON : ROW_IDLE}`}>
                <span className="h-2 w-2 shrink-0 rounded-full"
                      style={{ backgroundColor: on ? LC_ON[g.key] : LC[g.key] }} />
                <span className="min-w-0 flex-1 truncate">{g.label}</span>
                <span className={`font-mono text-xs tabular-nums ${on ? 'opacity-70' : 'text-muted'}`}>{count}</span>
              </button>

              {/* 枢轴点: 显示到第几档 */}
              {on && g.key === 'pivot' && (
                <div className="mt-1.5 flex flex-wrap items-center gap-1 pl-3">
                  <span className="mr-1 text-micro text-muted">档位</span>
                  {([1, 2, 3] as const).map(r => (
                    <button key={r} type="button" onClick={() => controls.setPivotRank(r)}
                            title={PIVOT_RANK_TITLES[r]} aria-pressed={pivotRank === r}
                            className={`${CHIP} font-mono ${pivotRank === r ? '' : CHIP_IDLE}`}
                            style={pivotRank === r ? tint(LC.pivot) : undefined}>
                      {r}
                    </button>
                  ))}
                </div>
              )}

              {/* 斐波那契二型: 粗细 / 上攻推算位 / 回测这三档 */}
              {on && g.key === 'fib2' && fib2?.grain && (
                <div className="mt-1.5 flex flex-wrap items-center gap-1 pl-3">
                  <span className="mr-1 text-micro text-muted">粗细</span>
                  {FIB2_GRAINS.map(([k, cn, tip]) => (
                    <button key={k} type="button" onClick={() => controls.setFib2Grain(k)}
                            title={tip} aria-pressed={fib2Grain === k}
                            className={`${CHIP} ${fib2Grain === k ? '' : CHIP_IDLE}`}
                            style={fib2Grain === k ? tint(LC.fib2) : undefined}>
                      {cn}
                      <span className="ml-1 font-mono opacity-50">{fib2.grain?.[k]?.levels.length ?? 0}</span>
                    </button>
                  ))}
                  <button type="button" onClick={() => controls.setFib2ShowTargets(v => !v)}
                          title={FIB2_TARGETS_TITLE} aria-pressed={fib2ShowTargets}
                          className={`${CHIP} ${fib2ShowTargets ? '' : CHIP_IDLE}`}
                          style={fib2ShowTargets ? tint(targetColor) : undefined}>
                    上攻推算位
                  </button>
                  <button type="button" onClick={() => setFitOpen(true)} title={FIB2_BACKTEST_TITLE}
                          className={`${CHIP} ${CHIP_IDLE}`}>
                    回测这三档
                  </button>
                </div>
              )}
            </div>
          )
        })}
      </div>

      <p className="mt-3 text-micro leading-5 text-muted">
        数字 = 这一类会画几条价位; 灰掉 = 这一类眼下没有价位。
      </p>

      {fitOpen && (
        <Fib2GrainDialog symbol={symbol} current={fib2Grain}
                         onPick={controls.setFib2Grain} onClose={() => setFitOpen(false)} />
      )}
    </div>
  )
}
