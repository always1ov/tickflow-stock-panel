/**
 * [R430] 关键价位图的「开了哪几类、枢轴点到第几档、二型粗细、推算位画不画」。
 *
 * 原来这几样是 `AnalysisKChart` 自己的 state。个股弹窗里由弹窗持有(切到日 K 再切
 * 回来, 开着的那几类还在): 图不传就自己持有(个股分析页等老入口一字不变), 传了就
 * 听外面的。[R432] 开关一度挪到图右边的列表里, 用户嫌不方便, 回到了图的上方
 * (`LevelToolbar`, 方形按钮)。
 *
 * 每一类旁边那个数也在这里算(`levelGroupStat`), 老的那排小开关与方形按钮那排
 * 共用 —— 数散在两处写, 迟早一处按粗细档算、一处按中档算(R406 就踩过)。
 */
import { useCallback, useMemo, useState, type Dispatch, type SetStateAction } from 'react'
import type { Fib2Grain } from '@/lib/api'
import type { LevelType, PriceLevel } from './AnalysisKChart'

export type PivotRank = 1 | 2 | 3

/**
 * [R208] 默认只开**量化通道短期**。用户: 「关键价位的指标默认选量化通道短期」——
 * 它是唯一每天都在动、且决策台整张表都在用的那一类。
 */
export const DEFAULT_LEVEL_TYPES: LevelType[] = ['keltner_s']

export interface LevelControls {
  activeTypes: Set<LevelType>
  toggleType: (t: LevelType) => void
  clearAll: () => void
  /** 枢轴点显示到第几档: 1 = 只 P + R1/S1, 2 = 到 R2/S2, 3 = 全档 */
  pivotRank: PivotRank
  setPivotRank: (r: PivotRank) => void
  /** [R406] 二型粗细档; [R410] 默认粗档 */
  fib2Grain: Fib2Grain
  setFib2Grain: (g: Fib2Grain) => void
  /** [R410] 上攻推算位一 / 二 / 三默认不画 */
  fib2ShowTargets: boolean
  setFib2ShowTargets: Dispatch<SetStateAction<boolean>>
}

export function useLevelControls(defaultTypes: LevelType[] = DEFAULT_LEVEL_TYPES): LevelControls {
  const [activeTypes, setActiveTypes] = useState<Set<LevelType>>(() => new Set(defaultTypes))
  const [pivotRank, setPivotRank] = useState<PivotRank>(1)
  const [fib2Grain, setFib2Grain] = useState<Fib2Grain>('coarse')
  const [fib2ShowTargets, setFib2ShowTargets] = useState(false)

  const toggleType = useCallback((t: LevelType) => setActiveTypes(prev => {
    const next = new Set(prev)
    if (next.has(t)) next.delete(t)
    else next.add(t)
    return next
  }), [])
  const clearAll = useCallback(() => setActiveTypes(new Set()), [])

  return useMemo(() => ({
    activeTypes, toggleType, clearAll,
    pivotRank, setPivotRank, fib2Grain, setFib2Grain, fib2ShowTargets, setFib2ShowTargets,
  }), [activeTypes, toggleType, clearAll, pivotRank, fib2Grain, fib2ShowTargets])
}

/**
 * 一类价位旁边那个数, 以及它能不能点。
 *
 *   count: 图上**现在画了几条**。枢轴点按当前档位过滤; 二型读粗细档换过、
 *          减线之后的那份(`effLevels`)—— 切了档, 数必须跟着变。
 *   total: 这一类**一共有几条**。能不能点按它算: 二型减线藏掉的不算"没有"。
 */
export function levelGroupStat(
  key: LevelType,
  label: string,
  effLevels: Record<LevelType, PriceLevel[]> | undefined,
  fib2Raw: PriceLevel[] | null,
  pivotRank: PivotRank,
): { count: number; total: number; title: string } {
  const raw = effLevels?.[key] ?? []
  const count = key === 'pivot'
    ? raw.filter(p => p.rank === undefined || p.rank <= pivotRank).length
    : raw.length
  // [R410] 二型只画其中一部分, **要如实写出藏了几条**, 否则会以为这一档就这么多线
  const total = key === 'fib2' ? (fib2Raw?.length ?? 0) : raw.length
  const title = key === 'fib2' && total > count
    ? `${label}: 画了 ${count} 条 / 这一档共 ${total} 条`
      + `\n只画「挤在一起的」「这组作废」和「离现价最近的几条」——`
      + `\n其余的对当下没有意义。想全看就切到更细的档。`
    : `${label} (${count} 个)`
  return { count, total, title }
}

// ===== 两个小开关组的文案(图上方那一排与右侧列表共用, 一个产地) =====

/** 枢轴点「档位」三个按钮的悬停说明 */
export const PIVOT_RANK_TITLES: Record<PivotRank, string> = {
  1: 'P + R1/S1(3 个)',
  2: '到 R2/S2(5 个)',
  3: '全档 R3/S3(7 个)',
}

/**
 * [R406] 二型「粗细」三档: 键 / 按钮字 / 悬停说明。
 * [R430] 中档的说明原来写「默认档」—— R410 早把默认改成了粗档, 这句一直在说假话。
 */
export const FIB2_GRAINS: readonly (readonly [Fib2Grain, string, string])[] = [
  ['coarse', '粗', '只认大级别回调 —— 线少而稳, 重合更难出现但出现了更硬(默认档)'],
  ['mid', '中', '介于粗细之间'],
  ['fine', '细', '小回调也算 —— 线多而密, 更容易看到重合'],
]

/** [R410] 上攻推算位开关的悬停说明 */
export const FIB2_TARGETS_TITLE = '上攻推算位一 / 二 / 三\n'
  + '由这一波的起点、最高点、回踩最低点三点推算, 是"涨上去会路过哪",\n'
  + '不是"该不该去" —— 默认不画, 免得和眼下要看的位置混在一起。'

/** [R412] 粗细档回测按钮的悬停说明 */
export const FIB2_BACKTEST_TITLE = '回看这只票近三年每一次上攻, 看当时画出来的线有没有说中\n'
  + '之后实际回踩的最低点 —— 评的是「线画得准不准」, 不是「赚不赚」。'
