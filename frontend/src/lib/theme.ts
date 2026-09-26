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
  infoBarBg: 'rgba(255,255,255,0.85)',  // --base       页面底(R501 起纯白)
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
//   ④ **斐波那契二型整组从金色挪开。** 一型(作者的)保住金 —— 斐波那契
//      配金是约定; 二型是 R405 新加的, 由它让路。两个名字只差一个字, 再同色
//      就是最容易混的一对。二型组内仍分三种意思: 回撤(靛青)/目标(蓝)/
//      失效位(暖褐), 见下面 FIB2_ROLE。
//   ⑤ [R421] **全站不许有粉 / 洋红 / 玫红。** 用户: 「整个系统禁止少女系风格,
//      比如粉色, 投资是一件很严肃的事情」。原来二型是洋红、ATR 是玫红、六态关键点
//      是品紫(暗色那一份就是兰花粉紫), 三个一起换: 二型 → 靛青, 六态关键点 →
//      宝蓝, ATR → 赭橙(警示色, 不借红 —— 红是涨)。守卫 `backend/tests/test_no_pink.py`
//      扫整个前端与后端发出的颜色。
//   ⑥ [R424] **不许浅、不许挨得近, 两套整张重排。** 用户: 「关键价位指标的颜色
//      不能用浅色的, 要用深色, 而且不能很接近」。量出来的两处毛病:
//      · 暗色那一份是一整套粉彩(浅桃 #FCB177、浅天蓝 #86C0FC、浅靛 #7F96FA、
//        近白 #DBE6F2) —— 在黑底上"看得见", 但是淡;
//      · R421 为了躲粉色, 把六态关键点 / 二型 / 布林 / 推算位四个组全挤进了蓝靛一带,
//        最近的一对只差 ΔE 8。
//      重排之后: **暗色一律饱和色**(彩色的色度 ≥ 0.10, 不再有粉彩), **亮色一律深色**
//      (明度 ≤ 0.65); 两两 ΔE **暗色 ≥ 12、亮色 ≥ 11**(原来 8)。量化通道三档仍同族,
//      三档之间 ≥ 9.5。三个中性色按明度拉开占掉三档: 六态关键点 = 最强(暗白 / 亮黑)、
//      前高前低 = 次强、整数关口 = 中灰 —— 这样冷暖两侧各让出一个位置, 否则 15 种
//      深色在「避开红绿粉」之后排不开。亮色做不到 12 是白底的物理限制: 黄 / 金一压深
//      就成了橄榄土色, 暖色那侧挤不下。
//
// 守卫在 `backend/tests/test_level_palette.py`: 两两 ΔE、离涨跌色的距离、
// 两套主题的对比度下限、不浅、键与 LEVEL_GROUPS 对不对得上, 全部钉住。
// **改任何一个值都要先跑那组守卫** —— 颜色改坏了屏幕上只是"有点怪", 不报错。
//   ⑦ [R443] **作者的指标回到作者原来的颜色, 自定的另选深色。** 用户: 「关键指标的
//      颜色还是用作者原来的颜色, 然后自定的你再帮我选深色的」。①~⑥ 的重排整张作废:
//      · 作者的 11 组(压力支撑 ... 整数关口)逐字取自上游 `upstream/main` 的
//        `AnalysisKChart.tsx`, **两套主题同一个值**(作者就是一个值); 布林中轨、ATR上轨
//        两条曲线作者另有颜色, 也照回(`LEVEL_CURVE_COLOR`)。作者那几处「撞色 / 偏浅 /
//        ATR 像阳线」是作者原样, 不再替他改。
//      · **唯一的例外是缺口位**: 作者原色 #EC4899 是粉, 全站禁粉(AGENTS.md 第 15 条)
//        —— 归到自定那一类, 另选深色。
//      · 自定的: 六态关键点、斐波那契二型(回踩位 / 上攻推算位 / 这组作废三种线)、
//        缺口位。**亮色取 Tailwind 700~800 一档、暗色取 500~700 一档** —— 都是饱和的
//        深色, 没有粉彩; 暗色不再往下压, 800 那档在黑底上就看不见了。
//        作者的颜色占掉了橙 / 黄 / 金 / 紫 / 青 / 红 / 灰, K 线又占掉红和绿, 剩下
//        蓝、天蓝、靛、青、暗褐黄五族, 一族给一种线。绿色族(深绿、橄榄绿)试过,
//        离「跌」绿只有 ΔE 8 多, 会被读成下跌, 不用。量出来: 彼此 ≥ ΔE 10、
//        离作者的颜色 ≥ 9.8、离 K 线涨跌色 ≥ 10.4、对页底对比 亮 ≥ 5.5 / 暗 ≥ 3.1。
//
// 守卫在 `backend/tests/test_level_palette.py`。
export const LEVEL_PALETTE: Record<string, { light: string; dark: string }> = {
  // ── 作者的(上游原色, 两套主题同一个值) ──
  sr:        { light: '#F97316', dark: '#F97316' },  // 橙(成交密集区,价量驱动)
  pivot:     { light: '#8B5CF6', dark: '#8B5CF6' },  // 紫
  extreme:   { light: '#EAB308', dark: '#EAB308' },  // 黄
  boll:      { light: '#F97316', dark: '#F97316' },  // 橙(布林 26 日 ±2σ 曲线, R528)
  keltner_s: { light: '#06B6D4', dark: '#06B6D4' },  // 青(MA20±2ATR 曲线)
  keltner_m: { light: '#22D3EE', dark: '#22D3EE' },  // 浅青(MA60±2.5ATR 曲线)
  keltner_l: { light: '#67E8F9', dark: '#67E8F9' },  // 更浅青(MA120±3ATR 曲线)
  atr_stop:  { light: '#EF4444', dark: '#EF4444' },  // 红(警示)
  fib:       { light: '#F59E0B', dark: '#F59E0B' },  // 金
  round:     { light: '#71717A', dark: '#71717A' },  // 灰(心理位,弱视觉)
  // ── 自定的(深色; 亮色 800 一档 / 暗色 600~700 一档) ──
  gap:       { light: '#3730A3', dark: '#4F46E5' },  // 靛 —— 作者原色是粉, 禁粉, 另选
  livermore: { light: '#1D4ED8', dark: '#3B82F6' },  // 蓝 —— 六态关键点
  fib2:      { light: '#6A0DAD', dark: '#724EA0' },  // 深紫 —— 斐波那契二型(= FIB2_ROLE_RETRACE; 离一型的金隔 ≥ 60°)。[R472] 用户: 「斐波那契二型用深紫色」。[R484] 「线颜色不够深」: 亮色再压深一档(对页底 7.1 → 8.6); 再深就与缺口位的靛 ΔE < 10, 更深则成了近黑
}

/**
 * [R443] 作者给两条曲线单独配过色(不跟组色): 布林中轨、ATR上轨。照原样回来。
 * 键是 `CURVE_DEFS` 的 alignedKey; 不在这里的曲线用所属组的颜色。
 */
export const LEVEL_CURVE_COLOR: Record<string, string> = {
  boll_mid: '#FB923C',
  atr_tp: '#F87171',
}

// 斐波那契二型组内的另外两种线。回撤线用组色, 所以这里只有两条。
//
// **键是后端 `indicators/dinapoli.py` 里那三个常量的字面值。** 后端按角色发
// `color` 字段(R405 定的契约), 前端不能按主题改后端发来的 hex, 于是把后端那三个
// 值当作**角色标识**用: 它们本身就是亮色那一份, 这里只补上暗色那一份。
// 这层耦合是隐式的, 所以 `test_level_palette.py` 专门钉了一条
// 「前后端三个角色键逐字对得上」—— 后端改常量而前端没跟, 会当场红。
//
// [R410] 三个角色键各给一个具名常量 —— 不只是好看: 前端要按角色过滤时
// (比如「推算位默认不画」)如果去比对**标签文字**, 就等于把后端的中文名
// 抄了一份到前端, 后端改名前端必漏。比角色键不会。
export const FIB2_ROLE_RETRACE = '#6A0DAD'
export const FIB2_ROLE_TARGET = '#0369A1'
export const FIB2_ROLE_VOID = '#854D0E'

export const FIB2_ROLE: Record<string, { light: string; dark: string }> = {
  [FIB2_ROLE_RETRACE]: { light: '#6A0DAD', dark: '#724EA0' },  // 回踩位 = 组色
  [FIB2_ROLE_TARGET]: { light: '#0369A1', dark: '#0369A1' },  // 上攻推算位一/二/三 —— 天蓝(规格 §12 要蓝)
  [FIB2_ROLE_VOID]: { light: '#854D0E', dark: '#A16207' },     // 这组作废 —— 暗褐黄, 退色(R443 深色)
}

/** 当前主题下每个价位组的颜色。 */
export function levelColors(theme: Theme): Record<string, string> {
  const out: Record<string, string> = {}
  for (const [k, v] of Object.entries(LEVEL_PALETTE)) out[k] = v[theme]
  return out
}

/**
 * [R421] 已退役的角色键 → 现在的角色键。回撤位原来是洋红 `#E01DB5`, 换色之前
 * 算好、还留在缓存里的响应仍带着它; 不认的键会**原样画出来** —— 那就是一条洋红线。
 * [R424] 三个角色键又整体换了一次, 旧键一并收进来。[R443] 第三次, 同上。[R472] 回撤位第四次(深青 → 深紫)。
 * [R484] 回撤位第五次(深紫再压深一档)。
 * (不放进 FIB2_ROLE: 那张表的键必须与后端常量逐字相等, 有守卫钉着。)
 */
const FIB2_ROLE_RETIRED: Record<string, string> = {
  '#E01DB5': FIB2_ROLE_RETRACE,   // R405~R420 的回撤位(洋红)
  '#322097': FIB2_ROLE_RETRACE,   // R421~R423 的回撤位(靛青)
  '#1889E6': FIB2_ROLE_TARGET,    // R405~R423 的推算位
  '#6B4D41': FIB2_ROLE_VOID,      // R405~R423 的作废线
  '#004631': FIB2_ROLE_RETRACE,   // R424~R442 的回撤位
  '#2F51A7': FIB2_ROLE_TARGET,    // R424~R442 的推算位
  '#472005': FIB2_ROLE_VOID,      // R424~R442 的作废线
  '#115E59': FIB2_ROLE_RETRACE,   // R443~R471 的回撤位(深青)
  '#7B07CE': FIB2_ROLE_RETRACE,   // R472~R483 的回撤位(深紫, 浅一档)
}

/** 后端按角色发来的那个 hex → 当前主题该用的颜色(认不出来就原样用)。 */
export function fib2RoleColor(backendHex: string, theme: Theme): string {
  const key = FIB2_ROLE_RETIRED[backendHex.toUpperCase()] ?? backendHex
  return FIB2_ROLE[key]?.[theme] ?? backendHex
}

/** hook: 当前主题下的价位组配色 (主题切换自动触发重渲染)。 */
export function useLevelColors(): Record<string, string> {
  return levelColors(useTheme())
}

// ================================================================
// [R415] 量化MACD 副图的配色 —— **照用户的通达信公式原样**
//
// 原文用的是通达信的四个颜色名, 换算成 RGB(通达信是 BBGGRR 序):
//
//   COLORRED      → FF0000   DIFF ≥ 0 的实心柱
//   COLORGREEN    → 00FF00   DIFF < 0 实心柱、DEA < 0 空心柱(两者**同一个绿**)
//   COLOR0000CC   → CC0000   DEA ≥ 0 的空心柱 —— **是深红不是蓝**: BB=00 GG=00 RR=CC
//   COLORYELLOW   → FFFF00   黄柱
//
// **两套主题都逐字照抄, 一个色都不改。** 用户: 「显示必须得和通达信显示的一样」
// 「颜色和柱子类型都得一样」。R415 首版曾把亮色主题的绿、黄压深(纯绿、纯黄在
// 白底上对比度只有 1.3 和 1.0), 那是自作主张, 已撤回 —— 白底上黄柱淡是通达信
// 这组颜色放到白底上本来的样子, 不在这里替用户改。
//
// [R417] `icon2` 是 2 号图标(死叉那个绿色朝下箭头)自带的绿。它不是公式里写的颜色,
// 是通达信图标本身的颜色; 对着用户的通达信截图量: 三个死叉箭头都在 #00DC00 附近,
// 而同一张图上的绿柱是纯 #00FF00 —— 两者确实不是同一个绿。
export const QUANT_MACD_COLORS = {
  red: '#FF0000', darkRed: '#CC0000', green: '#00FF00', yellow: '#FFFF00',
  icon2: '#00DC00',
  // [R418] 通达信的底色。亮色主题下这张副图铺这个底 —— 纯黄在白底上对比度只有
  // 1.0, 放多大都看不见; 颜色一个不改, 改的是它们脚下的底, 让它回到通达信的样子。
  paneBg: '#000000',
  // [R439] R434 / R436 在这里加过横格的暗红 `gridLine`; 用户: 「我不需要红线删掉」—— 撤了
} as const

/**
 * [R486] 趋势量化副图的颜色 —— 原文写了颜色的逐字照抄通达信(与量化MACD 同一套纯色),
 * 亮暗两套主题同一份, 底色同样铺通达信的黑。
 *
 * 原文**没写颜色**的四样用的是通达信的默认色, 对着用户发来的截图(长飞光纤, 主力趋势雷达)校准:
 *   · 平均线: 截图上是**洋红**(顶部数值栏「平均线」也是洋红)。全站禁粉(AGENTS.md 第 15 条),
 *     换成离洋红最近、又不进禁粉范围的紫 #B84DFF(色相 308°, 离 315° 的边界留了余量);
 *   · 吸筹那条线: 截图上是**绿**(贴着 0.5 黄线上方那条、以及沿白柱顶端那条);
 *   · 「升」「顶」「下」: 截图上是**白**。
 */
export const TREND_QUANT_COLORS = {
  red: '#FF0000', green: '#00FF00', yellow: '#FFFF00', white: '#FFFFFF',
  lightRed: '#FF8080',   // COLORLIRED(「见底」); 色相 21.5°, 不在禁粉的 315°~12° 里
  avg: '#B84DFF',        // 平均线: 通达信是洋红, 禁粉 → 最近的紫
  xichou: '#00FF00',     // 吸筹那条线: 通达信默认的绿
  text: '#FFFFFF',       // 升 / 顶 / 下: 通达信默认的白
  paneBg: '#000000',
} as const
