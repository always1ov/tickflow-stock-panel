/**
 * [R432] 关键价位开关 —— 回到图的上方, 一排方形按钮。
 *
 * R430 把开关挪到了图右边一张列表卡片里。用户: 「关键价位还是按照以前那样显示吧,
 * 在右侧很不方便, 可以保留方形按钮」。所以:
 *   · 位置回到以前那排小开关的地方(`AnalysisKChart` 里, 图的正上方);
 *   · 样子保留右侧列表那套方形按钮: 色点 + 名称 + 条数, 点开的反相, 没有价位的灰掉;
 *   · 枢轴点「档位」、二型「粗细 / 上攻推算位 / 回测这三档」照以前, 那一类开着时
 *     接在这排后面。
 *
 * 数怎么算、能不能点、悬停写什么, 仍然只有一个产地(`levelGroupStat` 与那几句说明)。
 * 状态由个股弹窗持有(`useLevelControls`): 切到日 K 再切回来, 开着的那几类还在。
 */
import type { Fib2Overlay } from '@/lib/api'
import { FIB2_ROLE_TARGET, fib2RoleColor, levelColors, useTheme } from '@/lib/theme'
import type { LevelType, PriceLevel } from './AnalysisKChart'
import {
  FIB2_BACKTEST_TITLE, FIB2_GRAINS, FIB2_TARGETS_TITLE, PIVOT_RANK_TITLES,
  levelGroupStat, type LevelControls,
} from './levelControls'

const SQ = 'inline-flex h-8 shrink-0 items-center gap-1.5 whitespace-nowrap rounded-btn border px-2.5 text-xs '
  + 'transition-colors duration-hover disabled:cursor-not-allowed disabled:opacity-40'
const SQ_IDLE = 'border-border bg-surface text-foreground hover:bg-elevated disabled:hover:bg-surface'
const SQ_ON = 'border-foreground bg-foreground text-surface font-medium'
/** 跟在后面的小开关: 比那排方形按钮矮一截, 一眼看得出是从属的 */
const CHIP = 'h-7 whitespace-nowrap rounded-btn border px-2 text-micro transition-colors duration-hover'
const CHIP_IDLE = 'border-border/60 bg-base/40 text-muted hover:border-border hover:text-foreground'
const SUB = 'inline-flex shrink-0 items-center gap-1 border-l border-border/60 pl-2'

export function LevelToolbar({ groups, controls, effLevels, fib2Raw, fib2, onOpenFit }: {
  groups: { key: LevelType; label: string }[]
  controls: LevelControls
  effLevels: Record<LevelType, PriceLevel[]> | undefined
  fib2Raw: PriceLevel[] | null
  fib2?: Fib2Overlay
  /** 「回测这三档」; 不传就不显示那个按钮 */
  onOpenFit?: () => void
}) {
  const theme = useTheme()
  const { activeTypes, pivotRank, fib2Grain, fib2ShowTargets } = controls
  const LC = levelColors(theme)
  // 点开的那个按钮是反相的(亮色主题黑底、暗色主题白底)。色点换用**另一套主题**的
  // 颜色 —— 调色板按底色分两套调: 黑底上该用暗色那份亮色, 白底上该用亮色那份深色。
  // 不换的话, 暗色主题里六态关键点那个近白的点画在白底上就没了。
  const LC_ON = levelColors(theme === 'dark' ? 'light' : 'dark')
  const targetColor = fib2RoleColor(FIB2_ROLE_TARGET, theme)
  const tint = (c: string) => ({ borderColor: c + '66', backgroundColor: c + '26', color: c })

  return (
    <div className="mb-2 flex flex-wrap items-center gap-1.5">
      {groups.map(g => {
        const on = activeTypes.has(g.key)
        const { count, total, title } = levelGroupStat(g.key, g.label, effLevels, fib2Raw, pivotRank)
        return (
          <button key={g.key} type="button" onClick={() => controls.toggleType(g.key)}
                  disabled={total === 0} aria-pressed={on} title={title}
                  className={`${SQ} ${on ? SQ_ON : SQ_IDLE}`}>
            <span className="h-2 w-2 shrink-0 rounded-full"
                  style={{ backgroundColor: on ? LC_ON[g.key] : LC[g.key] }} />
            {g.label}
            <span className={`font-mono tabular-nums ${on ? 'opacity-70' : 'text-muted'}`}>{count}</span>
          </button>
        )
      })}

      {/* 枢轴点: 显示到第几档 —— 仅当枢轴点开着 */}
      {activeTypes.has('pivot') && (effLevels?.pivot?.length ?? 0) > 0 && (
        <div className={SUB}>
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

      {/* 斐波那契二型: 粗细 / 上攻推算位 / 回测这三档 —— 仅当二型开着 */}
      {activeTypes.has('fib2') && fib2?.grain && (
        <div className={SUB}>
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
          {onOpenFit && (
            <button type="button" onClick={onOpenFit} title={FIB2_BACKTEST_TITLE}
                    className={`${CHIP} ${CHIP_IDLE}`}>
              回测这三档
            </button>
          )}
        </div>
      )}

      <button type="button" onClick={controls.clearAll} disabled={activeTypes.size === 0}
              className={`${SQ} ${SQ_IDLE} ml-auto`}>
        全部清除
      </button>
    </div>
  )
}
