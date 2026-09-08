/**
 * [fork 增强] R186 模拟盘净值曲线。
 *
 * 参考 MarketPulse 的 `EquityChart`: 一个模拟盘页面**最该有的就是这条线**。
 * 本系统的 `nav_history` 从 R59 起就一直在存, 但从来没画出来过 —— 界面上只有
 * 「总资产 98,933」这样一个数。那个数只说明现在几块钱, **曲线才说明这一路是
 * 怎么走过来的**: 是一直平着走, 还是冲到 +30% 又跌回来。两者在总资产上看不出
 * 任何区别, 而它们完全是两回事。
 *
 * 两本账画在同一张图里(全市场 / 我的自选) —— 这一页要回答的本来就是
 * 「同一个模型, 两个股票池, 哪边走得好」, 分成两张图会让人只看其中一边。
 *
 * 刻意的取舍:
 *   · **归一到本金**, 纵轴是收益率而不是净值绝对值 —— 两本账本金可以设成不同的
 *     数, 画绝对值就没法比;
 *   · 画一条 0% 基线, 亏损区间比盈利区间更显眼(A 股红涨绿跌, 这里跟随系统配色);
 *   · 数据少于 2 个点不画, 显示一句"还没跑够" —— 一个点连不成线, 硬画一条平线
 *     会让人以为它稳。
 */
import ReactECharts from 'echarts-for-react'
import { useMemo } from 'react'
import type { PaperBook } from '@/lib/api'

type Curve = { date: string; nav: number }

const SERIES_COLOR: Record<string, string> = {
  market: '#60a5fa',     // 全市场 — 蓝
  watchlist: '#f59e0b',  // 我的自选 — 琥珀(与页面里「持有」那类暖色一致)
}

export function PaperEquityChart({ books, height = 180 }: {
  books: PaperBook[]
  height?: number
}) {
  const option = useMemo(() => {
    const series = books
      .map(b => {
        const curve = (b.nav_curve ?? []) as Curve[]
        const cap = b.initial_capital || 1
        return {
          scope: b.scope,
          name: b.scope_cn,
          // 归一到本金: 两本账本金可以不同, 画绝对值没法比
          points: curve.map(p => [p.date, +((p.nav / cap - 1) * 100).toFixed(2)] as [string, number]),
        }
      })
      .filter(s => s.points.length >= 2)

    if (!series.length) return null

    return {
      grid: { top: 16, right: 12, bottom: 20, left: 40 },
      tooltip: {
        trigger: 'axis',
        backgroundColor: 'rgba(20,22,28,.95)',
        borderColor: 'rgba(255,255,255,.12)',
        textStyle: { color: '#e5e7eb', fontSize: 11 },
        valueFormatter: (v: number) => `${v > 0 ? '+' : ''}${v}%`,
      },
      legend: {
        show: series.length > 1,
        top: 0, right: 0,
        itemWidth: 10, itemHeight: 2,
        textStyle: { color: '#8a919f', fontSize: 10 },
      },
      xAxis: {
        type: 'category',
        boundaryGap: false,
        axisLine: { lineStyle: { color: 'rgba(255,255,255,.12)' } },
        axisLabel: { color: '#6b7280', fontSize: 9, hideOverlap: true },
      },
      yAxis: {
        type: 'value',
        axisLabel: { color: '#6b7280', fontSize: 9, formatter: '{value}%' },
        splitLine: { lineStyle: { color: 'rgba(255,255,255,.06)' } },
      },
      series: series.map(s => ({
        name: s.name,
        type: 'line',
        data: s.points,
        showSymbol: false,
        smooth: false,          // 净值不该被平滑 —— 那会把回撤的尖角磨圆
        lineStyle: { width: 1.5, color: SERIES_COLOR[s.scope] ?? '#9ca3af' },
        itemStyle: { color: SERIES_COLOR[s.scope] ?? '#9ca3af' },
        // 0% 基线: 一眼看出在水上还是水下
        markLine: {
          silent: true, symbol: 'none',
          data: [{ yAxis: 0 }],
          lineStyle: { color: 'rgba(255,255,255,.25)', width: 1, type: 'dashed' },
          label: { show: false },
        },
      })),
    }
  }, [books])

  if (!option) {
    return (
      <div className="flex items-center justify-center rounded border border-border/40 bg-base/30 text-[10px] text-muted"
           style={{ height }}>
        还没跑够两天 —— 净值曲线要有两个点才连得成线
      </div>
    )
  }
  return <ReactECharts option={option} style={{ height }} notMerge lazyUpdate />
}
