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

// [R368] 亮色画布跟着新 token 重抄一遍。
//
// **R317 那条规矩在这儿最要紧**: canvas 不吃 CSS 变量, 所以这些 hex 是
// index.css 的一份手抄件 —— 抄的时候要对得上, 否则同一屏里「轴上的灰」与
// 「界面上的灰」是两种灰, **而两边看上去都没坏**。
// 每个值后面标着它对应的 token, 改 token 就得回来改这里。
// [R379] 跟着 index.css 的铬色一起换。**canvas 不吃 CSS 变量**, 这份 hex 是
// index.css 的手抄件 —— 对不上就会出现「轴上的灰和界面上的灰是两种灰」,
// 而且不会有任何东西报错(R317 立的规矩)。
// 换的全是铬色(文字/网格/边框/十字线/浮层底), **涨跌那两个色不在这里**,
// 它们在各自的图表组件里, 这一轮一个字没动。
// [R408] 亮色那四档 token 压深了(用户: 「总之觉得颜色都浅了」), 这份手抄件
// **必须跟着改** —— 上面那条规矩说的就是这种情况: 不跟, 轴上的灰和界面上的灰
// 就是两种灰, 而两边都不报错。跟着 index.css 走的是 text / border /
// crosshairLabelBg 三个; grid 与 crosshair 是 fg-primary 的透明度, 没动。
const LIGHT: ChartTheme = {
  text: '#5A6377',        // --fg-muted    辅助文字(R408: #6B7488 → 压深)
  textStrong: '#222738',  // --fg-primary  主要文字
  grid: 'rgba(34,39,56,0.06)',          // = fg-primary 的低透明度, 不用纯黑
  border: '#D1D4DD',      // --border      普通边框(R408: #E7EAF2 → 压深)
  crosshair: 'rgba(34,39,56,0.28)',
  crosshairLabelBg: '#4B5569',          // --fg-secondary: 十字线标签是深底白字(R408)
  tooltipBg: 'rgba(255,255,255,0.97)',  // --surface
  tooltipBorder: 'rgba(34,39,56,0.10)',
  tooltipText: '#222738', // --fg-primary
  infoBarBg: 'rgba(246,247,251,0.85)',  // --base       页面底
  zoomFill: 'rgba(34,39,56,0.06)',
  fillSubtle: 'rgba(34,39,56,0.04)',
}

export function chartTheme(theme: Theme): ChartTheme {
  return theme === 'dark' ? DARK : LIGHT
}

/** hook: 当前主题的图表调色板 (主题切换自动触发重渲染)。 */
export function useChartTheme(): ChartTheme {
  return chartTheme(useTheme())
}

// ================================================================
// [R409] 关键价位的配色 —— **一个指标一个颜色, 两套主题各一份**
//
// 用户: 「关键价位的所有指标的各个指标的颜色都要不一样, 因为重叠的时候容易
// 混淆是视觉, 而且不能搞浅色, 也要符合自身含义」。
//
// 改之前是 13 个组各自在组件里写死一个 hex, **量出来是这样的**
// (ΔE 用 OKLab 距离 ×100 算; 对比度是 WCAG, 底色分别是亮色页底 #F6F7FB 与
//  暗色页底 #0a0a0b):
//
//   · 压力支撑与布林带**是同一个 #F97316** —— ΔE 0.0, 两组线叠在一起
//     完全分不出谁是谁;
//   · 另有 32 对 ΔE < 20, 其中 5 对 < 8.5(前高前低×一型 5.3、通道中期×长期
//     7.1、整数关口×失效位 7.4、通道短期×中期 8.3、布林×一型/压力×一型 9.6);
//   · **亮色主题下四个组几乎看不见**: 通道长期 1.35、通道中期 1.69、
//     前高前低 1.79、一型 2.01 —— 一个 1px 虚线在这种对比度下等于没画;
//   · ATR 波动通道 #EF4444 离 K 线的涨红 #C74040 只有 ΔE 5~6 ——
//     **一条指标线长得像一根阳线**, 这是最要命的一个。
//
// 现在的做法:
//
//   ① **每个主题一份值。** 一个 hex 要同时在近白底和近黑底上站住, 只能挤在
//      很窄的一段明度里 —— 那正是"浅"的来源。分成两份之后, 亮色整体压深
//      (对白底对比 3.0~9.7)、暗色整体提亮(对黑底 5.1~15.7), 两头都不浅。
//   ② **色相按语义排开**, 见下表最后一列。红(涨)与绿(跌)那两段**整个让开**,
//      任何指标色离 K 线涨红/跌绿的 ΔE ≥ 10。
//   ③ **量化通道三档留在同一个青族**, 靠明度走档(短→中→长 依次压深) ——
//      它们本来就是一个指标的三个周期, 换成三个色相反而读不出"同一家";
//      但**不再靠"更浅"区分**(原来长期是 #67E8F9, 亮底对比 1.35)。
//   ④ **斐波那契二型整组从金色挪到洋红。** 一型(作者的)保住金 —— 斐波那契
//      配金是约定; 二型是 R405 新加的, 由它让路。两个名字只差一个字, 再同色
//      就是最容易混的一对。二型组内仍分三种意思: 回撤(洋红)/目标(蓝)/
//      失效位(暖灰), 见下面 FIB2_ROLE。
//
// 守卫在 `backend/tests/test_level_palette.py`: 两两 ΔE、离涨跌色的距离、
// 两套主题的对比度下限、键与 LEVEL_GROUPS 对不对得上, 全部钉住。
// **改任何一个值都要先跑那组守卫** —— 颜色改坏了屏幕上只是"有点怪", 不报错。
export const LEVEL_PALETTE: Record<string, { light: string; dark: string }> = {
  // 横线组
  sr:        { light: '#C46D16', dark: '#FCB177' },  // 橙 —— 成交密集区, 热度
  extreme:   { light: '#38414A', dark: '#DBE6F2' },  // 中性最强 —— 前高前低是硬事实, 不加色彩判断
  fib:       { light: '#7D650E', dark: '#EDC327' },  // 金 —— 斐波那契一型(作者的), 保住金
  gap:       { light: '#8E9618', dark: '#AAB520' },  // 橄榄 —— 跳空缺口
  round:     { light: '#758290', dark: '#93A0AE' },  // 中性中档 —— 整数关口是心理位
  pivot:     { light: '#9362F9', dark: '#9968FA' },  // 紫 —— 算出来的中枢(暗色第一版 #CABDFC 离二型目标只有 ΔE 8.4, 压饱和)
  livermore: { light: '#9414B3', dark: '#D75AFA' },  // 品紫 —— 六态关键点
  fib2:      { light: '#E01DB5', dark: '#FCA2DF' },  // 洋红 —— 斐波那契二型(让出金色那一组)
  // 曲线组(跟着行情漂的带/通道)
  boll:      { light: '#3D39F7', dark: '#7F96FA' },  // 靛蓝 —— 统计带
  keltner_s: { light: '#1C9DAE', dark: '#2EE2F9' },  // 青 · 短期(同族最亮一档)
  keltner_m: { light: '#147F86', dark: '#26C4CF' },  // 青 · 中期
  keltner_l: { light: '#0D626B', dark: '#1EA3B1' },  // 青 · 长期(同族最深一档)
  // 玫红 —— 警示, 但**避开 K 线的正红**。暗色这一份第一版写的是 #FB4F9A,
  // 守卫当场红: 它离暗色的 `--bull`(#FE595F, 界面上的"涨")只有 ΔE 8.9 ——
  // 我挑色时只比了 K 线画布那两个 hex, 忘了界面文字用的是另一对。往洋红再推一档。
  atr_stop:  { light: '#B31364', dark: '#F845AF' },
}

// 斐波那契二型组内的另外两种线。回撤线用组色(洋红), 所以这里只有两条。
//
// **键是后端 `indicators/dinapoli.py` 里那三个常量的字面值。** 后端按角色发
// `color` 字段(R405 定的契约), 前端不能按主题改后端发来的 hex, 于是把后端那三个
// 值当作**角色标识**用: 它们本身就是亮色那一份, 这里只补上暗色那一份。
// 这层耦合是隐式的, 所以 `test_level_palette.py` 专门钉了一条
// 「前后端三个角色键逐字对得上」—— 后端改常量而前端没跟, 会当场红。
export const FIB2_ROLE: Record<string, { light: string; dark: string }> = {
  '#E01DB5': { light: '#E01DB5', dark: '#FCA2DF' },  // 回撤位 = 组色
  '#1889E6': { light: '#1889E6', dark: '#86C0FC' },  // 目标一二三 —— 蓝(规格 §12)
  '#6B4D41': { light: '#6B4D41', dark: '#937E6D' },  // 失效位 —— 暖褐, 退色(亮色第一版 #6A5746 离一型的金只有 ΔE 8.4, 往褐里压)
}

/** 当前主题下每个价位组的颜色。 */
export function levelColors(theme: Theme): Record<string, string> {
  const out: Record<string, string> = {}
  for (const [k, v] of Object.entries(LEVEL_PALETTE)) out[k] = v[theme]
  return out
}

/** 后端按角色发来的那个 hex → 当前主题该用的颜色(认不出来就原样用)。 */
export function fib2RoleColor(backendHex: string, theme: Theme): string {
  return FIB2_ROLE[backendHex]?.[theme] ?? backendHex
}

/** hook: 当前主题下的价位组配色 (主题切换自动触发重渲染)。 */
export function useLevelColors(): Record<string, string> {
  return levelColors(useTheme())
}
