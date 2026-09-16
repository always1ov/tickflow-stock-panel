// 主题管理 — 亮色(默认) / 暗色切换
//
// [R368] **默认从 dark 改成 light。** 用户: 「前端采用浅色蓝白配色」。
//
// 这是这次唯一一处默认值改动, 而且非改不可: 两套配色都在, 不把默认翻过来,
// 新配色一个像素都不会出现在屏幕上 —— 那等于没做。暗色一套**原封不动**留着,
// 切换按钮也没动, 想回去一下就回去。
//
// 机制:
//   - 状态存 localStorage('tf-theme'), 默认 light; 显式存过 'dark' 才是暗色
//   - 生效方式: html.dark class (index.css 的 CSS variables + Tailwind darkMode:class)
//   - index.html 里有预渲染内联脚本, 首屏前就设好 class, 避免闪烁 (FOUC)
//   - UI token (bg-surface/text-foreground 等) 自动跟随;
//     图表画布不吃 CSS 变量, 统一走 useChartTheme() 取调色板
import { useEffect, useState } from 'react'

const KEY = 'tf-theme'
const EVENT = 'tf-theme-change'

export type Theme = 'dark' | 'light'

export function getTheme(): Theme {
  try {
    // [R368] 判据翻过来: **显式存过 'dark' 才是暗色**, 其余(含没存过)一律亮色。
    // 之前存过 'light' 的人不受影响 —— 他们本来就要亮色。
    return localStorage.getItem(KEY) === 'dark' ? 'dark' : 'light'
  } catch {
    return 'light'
  }
}

export function setTheme(theme: Theme) {
  try { localStorage.setItem(KEY, theme) } catch { /* ignore */ }
  document.documentElement.classList.toggle('dark', theme === 'dark')
  window.dispatchEvent(new CustomEvent(EVENT, { detail: theme }))
}

export function toggleTheme(): Theme {
  const next: Theme = getTheme() === 'dark' ? 'light' : 'dark'
  setTheme(next)
  return next
}

/** 订阅当前主题 (本页切换 + 其他标签页切换均同步)。 */
export function useTheme(): Theme {
  const [theme, set] = useState<Theme>(getTheme)
  useEffect(() => {
    const onChange = () => set(getTheme())
    window.addEventListener(EVENT, onChange)
    window.addEventListener('storage', onChange)  // 跨标签页同步
    return () => {
      window.removeEventListener(EVENT, onChange)
      window.removeEventListener('storage', onChange)
    }
  }, [])
  return theme
}

// ================================================================
// 图表调色板 — ECharts / lightweight-charts 画布不吃 CSS 变量,
// 所有图表组件统一从这里取色, 主题切换时依赖 useTheme 重建 option。
//
// [R317] 关于**涨跌红绿**: 这里仍然不定义 bull/bear。K 线画布的涨跌色是
// 各图表组件里硬编码的 `#C74040`(涨) / `#2D9B65`(跌), 分布在 9 个文件
// (EChartsCandlestick / EChartsIntraday / EChartsMultiDayIntraday /
//  StockInfoBar / MiniCandlestick / MiniIntraday / price-alerts /
//  TradeKlineModal / stock-analysis/AnalysisKChart)。最后那个在六态冻结面内,
// 所以这次**一个都没动** —— 只改其中 8 个反而会让"个股分析主图"与其它图
// 的涨跌色不一致, 比不改更糟。
//
// 好消息是它们本来就不用改: 实测那两个硬编码值的色相是 **24.47° / 157.30°**,
// 而本次重做后的语义 token 是 **22° / 158°** —— 相差 ≤2.5°, 本来就是同一个
// 红绿族。(改之前 UI 侧的暗色 bull 是 28.54°、Tailwind emerald-400 是
// 163.22°, 那才是真的"两个红、两个绿"。)所以这次重做反而把 UI 文字与
// K 线画布拉到了同一族里。
// ================================================================

export interface ChartTheme {
  /** 轴刻度/图例等常规文字 */
  text: string
  /** 信息条/图例里的强调文字 */
  textStrong: string
  /** 网格线 */
  grid: string
  /** 轴线/边框 */
  border: string
  /** 十字光标线 */
  crosshair: string
  /** 十字光标轴标签背景 */
  crosshairLabelBg: string
  /** tooltip 背景 */
  tooltipBg: string
  /** tooltip 边框 */
  tooltipBorder: string
  /** tooltip 文字 */
  tooltipText: string
  /** 半透明信息条背景 (K线图左上角 OHLC 条) */
  infoBarBg: string
  /** dataZoom 滑块填充 */
  zoomFill: string
  /** 分时图均价线以外的弱填充 */
  fillSubtle: string
}

// [R163] 暗色回到作者原版(Tailwind Zinc 灰阶) —— 与 index.css 的 html.dark 块一起还原。
// 亮色仍是 R155 的 Radix Slate。
//
// [R317] 画布颜色与 UI token 重新对齐。canvas 不吃 CSS 变量, 所以这里必须把
// index.css 的值抄一份成 hex —— 抄的时候要对得上, 否则同一屏里"轴上的灰"与
// "界面上的灰"会是两种灰。下面每个值后面标了它对应的 token。
const DARK: ChartTheme = {
  text: '#8e8e96',        // --fg-muted   (原 #A1A1AA, 那是旧的 zinc-400, 已与 token 脱节)
  textStrong: '#fafafa',  // --fg-primary (原 #E4E4E7)
  grid: 'rgba(255,255,255,0.06)',
  border: '#3e3e42',      // --border     (原 #27272A)
  crosshair: 'rgba(255,255,255,0.28)',
  crosshairLabelBg: '#242429', // --elevated (原 #333)
  tooltipBg: 'rgba(24,24,27,0.96)',   // --surface
  tooltipBorder: 'rgba(255,255,255,0.12)',
  tooltipText: '#fafafa', // --fg-primary (原 #E4E4E7)
  infoBarBg: 'rgba(36,36,41,0.75)',   // --elevated (原 rgba(39,39,42,0.6))
  zoomFill: 'rgba(255,255,255,0.06)',
  fillSubtle: 'rgba(255,255,255,0.04)',
}

const LIGHT: ChartTheme = {
  text: '#5a5e66',        // --fg-muted   (原 #60646c, 旧的 slate11)
  textStrong: '#1c2024',  // --fg-primary
  grid: 'rgba(0,0,0,0.06)',
  border: '#cdced6',      // --border
  crosshair: 'rgba(0,0,0,0.3)',
  crosshairLabelBg: '#8b8d98', // slate9
  tooltipBg: 'rgba(255,255,255,0.97)',
  tooltipBorder: 'rgba(0,0,0,0.1)',
  tooltipText: '#1c2024', // --fg-primary
  infoBarBg: 'rgba(240,240,243,0.85)',  // --base
  zoomFill: 'rgba(0,0,0,0.06)',
  fillSubtle: 'rgba(0,0,0,0.04)',
}

export function chartTheme(theme: Theme): ChartTheme {
  return theme === 'dark' ? DARK : LIGHT
}

/** hook: 当前主题的图表调色板 (主题切换自动触发重渲染)。 */
export function useChartTheme(): ChartTheme {
  return chartTheme(useTheme())
}
