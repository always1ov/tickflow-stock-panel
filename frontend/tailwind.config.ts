import type { Config } from 'tailwindcss'
import animate from 'tailwindcss-animate'

// 设计语言 §6.0:暗色为主 + 低饱和靛蓝强调([R155] Radix Slate 骨架 / Indigo 强调) + 等宽数字
export default {
  darkMode: ['class'],
  // [R168] 把所有 hover: / group-hover: / peer-hover: 变体包进
  // `@media (hover: hover)`(emil-design-eng「Touch device hover states」)。
  // 触屏上点一下会触发 hover 并**粘住**, 于是本仓库那些 hover 高亮行、
  // hover 才显形的操作按钮, 在平板上点完一行会一直亮着, 看盘时非常干扰。
  // Tailwind 官方开关, 不用逐处加媒体查询; 桌面端零变化。
  future: { hoverOnlyWhenSupported: true },
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    container: { center: true, padding: '1rem' },
    extend: {
      // [R155] text-accent 单独走 --accent-text: 暗色里"深底上的靛蓝文字"要亮、
      // "靛蓝实底上的白字"要暗, 一个 token 兼顾不了(Radix 也是 9 档实底 / 11 档文字)。
      // 只覆盖文字; bg-/border-/ring-accent 仍走下面 colors.accent。
      textColor: {
        accent: 'oklch(var(--accent-text) / <alpha-value>)',
      },
      colors: {
        // §6.0.1 色板 — CSS variables 见 src/index.css
        base:      'oklch(var(--base) / <alpha-value>)',
        surface:   'oklch(var(--surface) / <alpha-value>)',
        elevated:  'oklch(var(--elevated) / <alpha-value>)',
        border:    'oklch(var(--border) / <alpha-value>)',
        foreground: 'oklch(var(--fg-primary) / <alpha-value>)',
        secondary:  'oklch(var(--fg-secondary) / <alpha-value>)',
        muted:      'oklch(var(--fg-muted) / <alpha-value>)',
        accent:     'oklch(var(--accent) / <alpha-value>)',
        // A 股语义色:仅用于价格 / K 线,不用于 UI 状态
        bull:       'oklch(var(--bull) / <alpha-value>)',
        bear:       'oklch(var(--bear) / <alpha-value>)',
        warning:    'oklch(var(--warning) / <alpha-value>)',
        danger:     'oklch(var(--danger) / <alpha-value>)',

        // [R138] Tailwind 强调色改走 CSS 变量, 好让**亮色模式单独压暗**。
        //
        // 起因: 全站一千多处用的是 text-amber-300 / text-sky-300 / text-emerald-400
        // 这类**为深色背景挑的浅色**, 放到白底上普遍只有 2~3:1, 用户的原话是
        // "太白了好多东西都看不见"。逐个文件改不现实(涉及一百多个组件), 但把
        // 色值收进变量之后, 组件一个字都不用动 —— 换主题自动切。
        //
        // 只覆盖 300~600 这四档: 50/100/200 本来就是该淡的浅底(亮色模式里用作
        // 背景), 700+ 已经足够暗, 动它们只会把亮色模式弄糟。
        // 暗色一侧的值 = Tailwind 原值, 视觉零变化。
        amber: { 300: 'oklch(var(--t-amber-300) / <alpha-value>)', 400: 'oklch(var(--t-amber-400) / <alpha-value>)', 500: 'oklch(var(--t-amber-500) / <alpha-value>)', 600: 'oklch(var(--t-amber-600) / <alpha-value>)' },
        blue: { 300: 'oklch(var(--t-blue-300) / <alpha-value>)', 400: 'oklch(var(--t-blue-400) / <alpha-value>)', 500: 'oklch(var(--t-blue-500) / <alpha-value>)' },
        cyan: { 300: 'oklch(var(--t-cyan-300) / <alpha-value>)', 400: 'oklch(var(--t-cyan-400) / <alpha-value>)', 500: 'oklch(var(--t-cyan-500) / <alpha-value>)', 600: 'oklch(var(--t-cyan-600) / <alpha-value>)' },
        emerald: { 300: 'oklch(var(--t-emerald-300) / <alpha-value>)', 400: 'oklch(var(--t-emerald-400) / <alpha-value>)', 500: 'oklch(var(--t-emerald-500) / <alpha-value>)' },
        fuchsia: { 300: 'oklch(var(--t-fuchsia-300) / <alpha-value>)', 400: 'oklch(var(--t-fuchsia-400) / <alpha-value>)', 500: 'oklch(var(--t-fuchsia-500) / <alpha-value>)' },
        green: { 400: 'oklch(var(--t-green-400) / <alpha-value>)', 500: 'oklch(var(--t-green-500) / <alpha-value>)' },
        indigo: { 400: 'oklch(var(--t-indigo-400) / <alpha-value>)' },
        lime: { 400: 'oklch(var(--t-lime-400) / <alpha-value>)' },
        orange: { 300: 'oklch(var(--t-orange-300) / <alpha-value>)', 400: 'oklch(var(--t-orange-400) / <alpha-value>)', 500: 'oklch(var(--t-orange-500) / <alpha-value>)' },
        purple: { 300: 'oklch(var(--t-purple-300) / <alpha-value>)', 400: 'oklch(var(--t-purple-400) / <alpha-value>)', 500: 'oklch(var(--t-purple-500) / <alpha-value>)' },
        red: { 300: 'oklch(var(--t-red-300) / <alpha-value>)', 400: 'oklch(var(--t-red-400) / <alpha-value>)', 500: 'oklch(var(--t-red-500) / <alpha-value>)' },
        rose: { 300: 'oklch(var(--t-rose-300) / <alpha-value>)', 400: 'oklch(var(--t-rose-400) / <alpha-value>)', 500: 'oklch(var(--t-rose-500) / <alpha-value>)' },
        sky: { 300: 'oklch(var(--t-sky-300) / <alpha-value>)', 400: 'oklch(var(--t-sky-400) / <alpha-value>)', 500: 'oklch(var(--t-sky-500) / <alpha-value>)' },
        teal: { 300: 'oklch(var(--t-teal-300) / <alpha-value>)', 400: 'oklch(var(--t-teal-400) / <alpha-value>)', 500: 'oklch(var(--t-teal-500) / <alpha-value>)' },
        violet: { 300: 'oklch(var(--t-violet-300) / <alpha-value>)', 400: 'oklch(var(--t-violet-400) / <alpha-value>)', 500: 'oklch(var(--t-violet-500) / <alpha-value>)' },
        yellow: { 400: 'oklch(var(--t-yellow-400) / <alpha-value>)', 500: 'oklch(var(--t-yellow-500) / <alpha-value>)', 600: 'oklch(var(--t-yellow-600) / <alpha-value>)' },
      },
      fontFamily: {
        // 中文优先字体栈。MiSans 不随仓库分发，设备未安装时依次回退到各平台
        // 原生中文 UI 字体。
        // [R125] 拉丁字形交给打包进产物的 Inter(skill §2 首选之一): 它没有 CJK
        // 字形, 浏览器遇到中文会自然落到后面的中文字体 —— 这正是混排字体栈的
        // 工作方式, 一个声明同时管好中英文。字体文件自托管, 不请求 Google。
        sans: [
          'Inter Variable',
          'MiSans',
          '"HarmonyOS Sans SC"',
          '"PingFang SC"',
          '"Microsoft YaHei UI"',
          '"Segoe UI"',
          'Roboto',
          '"Noto Sans SC"',
          'system-ui',
          'sans-serif',
        ],
        mono: [
          // [R125] 之前这里写着 JetBrains Mono 但没人提供它 —— 只有本机装过的
          // 人看得到, 其余人静默回落 Consolas。现在打包进产物, 所有人一致。
          '"JetBrains Mono"',
          '"Cascadia Code"',
          '"SFMono-Regular"',
          '"IBM Plex Mono"',
          'Consolas',
          'ui-monospace',
          'monospace',
        ],
      },
      // FluxDown 桌面端以 13px 为主字号、12px 为辅助字号。保留显式像素字号
      // 给图表工具条使用，只统一语义字号，避免 K 线和表格几何发生漂移。
      // [R283] 整档上调一级。用户: 「全局的字体也适当调整, 太小了不方便看」。
      //
      // **这里是最安全的那个杠杆**: 这套刻度全部写成 px, 不含 rem —— 所以调它
      // 只放大字, 一个间距盒子都不动。相比之下改 `html { font-size }` 会把
      // Tailwind 的 rem 间距(p-2 = 0.5rem 之类)一起缩放, 那是整页重排, 风险完全不同。
      //
      // 行高按 1.5~1.55 跟着走 —— 只加字号不加行高, 字挤在一起反而更难读,
      // 「压抑」有一半来自行高而不是字号。
      fontSize: {
        xs: ['13px', { lineHeight: '20px' }],
        sm: ['14px', { lineHeight: '22px' }],
        base: ['15px', { lineHeight: '24px' }],
        lg: ['17px', { lineHeight: '26px' }],
        xl: ['19px', { lineHeight: '28px' }],
        '2xl': ['23px', { lineHeight: '32px' }],
      },
      letterSpacing: {
        tighter: '-0.015em',
        tight: '-0.008em',
        normal: '0.005em',
        wide: '0.025em',
        wider: '0.045em',
        widest: '0.08em',
      },
      spacing: {
        // 常用表单 h-9 从 36px 收到 FluxDown regular 控件的 32px。
        9: '2rem',
      },
      borderRadius: {
        // [R126] skill Quick Reference 建议 0.5~1rem; Modern Dark Mode 那段给的是
        // --radius: 0.625rem(10px)。卡片按它走, 按钮/输入框按比例小一档 ——
        // 密集交易界面里控件多且小, 圆角跟卡片一样大会显得肉。
        card: '10px',
        btn: '7px',
        input: '7px',
        dialog: '14px',
      },
      transitionTimingFunction: {
        // §6.0.4 Linear/Vercel 同款缓动
        smooth: 'cubic-bezier(0.16, 1, 0.3, 1)',
      },
      // [R168] `transition-ui` —— 用来替掉全项目 105 处 `transition-all`。
      //
      // 问题出在 `all` 上: 它把 height / width / padding / margin / top / left
      // 这些**布局属性**也一起过渡了。布局属性每一帧都要重新排版 + 重绘 + 合成,
      // 而 transform / opacity 只走合成(GPU)。密集表格一屏几百个单元格, 只要有
      // 一处 hover 顺手改了内边距, 整屏就得重排 —— 这是 emil-design-eng
      // 「Only animate transform and opacity」那条规则的实际代价。
      //
      // 但直接换成 `transition-colors` 会**改掉现有观感**(阴影、透明度、位移就不动了)。
      // 所以这里列出「现状实际用到的全部非布局属性」: 视觉上是 no-op,
      // 唯一的差别就是布局属性不再参与过渡 —— 而那正是要修的 bug。
      //
      // 真心想动布局的两处已单独写明属性(见 ExtDataStatCard 的 transition-[height]
      // 与 AbnormalMoves 进度条的 transition-[width]), 没有被这次替换波及。
      transitionProperty: {
        ui: 'color, background-color, border-color, text-decoration-color, fill, stroke, opacity, box-shadow, transform, filter, backdrop-filter',
      },
      // [R122/R124] 动效时长档位 —— 此前全项目 136 处手写 duration-150/200/300,
      // 同一类交互在不同页面快慢不一, 也无从统一调。按"交互越轻越快"分四档。
      //
      // 取值刻意**沿用现状里的多数派**(150 出现 82 次、200 出现 43 次、300 出现
      // 7 次), 所以这次全项目替换在视觉上是个 no-op —— 只是把散落的数字换成语义
      // 名字, 顺便把 4 处 100ms、2 处 500ms 两个异类收进档位。想整体调快调慢,
      // 以后改这里一处就行。
      transitionDuration: {
        press: '120ms',   // 按下反馈
        hover: '150ms',   // 悬停、着色
        expand: '200ms',  // 展开收起、旋转
        enter: '300ms',   // 元素入场
      },
      keyframes: {
        // 列表项入场: 轻微上移 + 淡入(配 stagger 用)
        'rise-in': {
          from: { opacity: '0', transform: 'translateY(6px)' },
          to: { opacity: '1', transform: 'translateY(0)' },
        },
      },
      animation: {
        'rise-in': 'rise-in 320ms cubic-bezier(0.16, 1, 0.3, 1) both',
      },
    },
  },
  plugins: [animate],
} satisfies Config
