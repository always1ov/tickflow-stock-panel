import type { Config } from 'tailwindcss'
import animate from 'tailwindcss-animate'

// 设计语言 §6.0:暗色为主 + 低饱和靛蓝强调([R155] Radix Slate 骨架 / Indigo 强调) + 等宽数字
// [R317] 「分层清晰 · 语义唯一」重做: token 层是本次视觉重构的主战场 ——
// 组件里的类名一个字不动, 改这里的值就能全站生效(含六态相关的页面)。
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
        // [R368] 侧栏单独一档: 比白面板略灰、比页面底略白, 三层有分界
        sidebar:   'oklch(var(--sidebar) / <alpha-value>)',
        // [R368] 选中背景(浅蓝)。蓝色只用于必要的交互强调, 不铺大面板
        'accent-soft': 'oklch(var(--accent-soft) / <alpha-value>)',
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
      //
      // [R317] **拉开档位差, 重建字阶**。
      // 起因: 全站 `text-xs` 用了 993 次、`text-sm` 350 次, 而两档只差 1px
      // (13 / 14) —— 相邻两级在屏幕上几乎分辨不出, 「层级」等于没有。字号是
      // 冻结面里改不动的那些组件唯一能共用的层级杠杆, 所以必须在这一层拉开。
      //
      // xs 保持 13px **不动**: 它是密集表格的主力字号, 一动就是全站表格重排。
      // 往上每档至少拉开 2px, 相邻两级才有明确的"级别感":
      //   xs 13 → sm 15 → base 16 → lg 18 → xl 21 → 2xl 25 → 3xl 31
      // 3xl 是补上的: 原本没定义, 落到 Tailwind 默认的 rem 值(会随根字号变),
      // 与这套 px 刻度不是一套体系。
      fontSize: {
        xs: ['13px', { lineHeight: '20px' }],
        sm: ['15px', { lineHeight: '23px' }],
        base: ['16px', { lineHeight: '25px' }],
        lg: ['18px', { lineHeight: '27px' }],
        xl: ['21px', { lineHeight: '30px' }],
        '2xl': ['25px', { lineHeight: '34px' }],
        '3xl': ['31px', { lineHeight: '40px' }],
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
        //
        // [R317] 整体上调一档(btn/input 7→8, card 10→12, dialog 14→16)。
        // 半径与元素尺寸同向变化时才"稳": 原有刻度里 10px 的卡片配 7px 的按钮
        // 比例是对的, 但 14px 的弹窗只比卡片大 4px, 大面上显得方。现在每一级
        // 保持约 1.33 的比例(8 / 12 / 16), 控件仍然明显小于卡片。
        //
        // [R379] 再上一档, 照 WavMint 的圆角分层(输入 8 / 主按钮 10 / 工具卡 14 /
        // 弹窗 18)。手册 §8.4 的告诫是「圆角有层次, 但不任意」—— 小控件用 30px
        // 胶囊、大卡却用 4px 直角会明显改变风格。这一版仍保持约 1.3~1.4 的级差,
        // 控件明显小于卡片; 输入框留在 8px 不动, 密集表单里再大会显得肉。
        card: '14px',
        btn: '10px',
        input: '8px',
        dialog: '18px',
      },
      // [R317] 阴影走 CSS 变量, **两套模式各一份**。
      //
      // 起因: 全站 shadow-sm/lg/xl/2xl 共 148 处, 用的都是 Tailwind 默认值 ——
      // 那是**为浅色背景调的黑色半透明投影**(shadow-2xl = rgb(0 0 0 / 0.25))。
      // 放在近黑的主题上等于没有: 黑投影落在黑面板上, 什么也看不出来, 于是
      // 弹窗和浮层"浮不起来"。而亮色模式又需要更柔和的投影, 硬编码一个值
      // 必然顾此失彼。
      //
      // 现在两端都指向 --shadow-*: 亮色是低透明度冷灰投影(不脏), 暗色是更深的
      // 纯黑投影 + 一道极淡的内高光(模拟受光的边缘)。组件里的 shadow-lg 之类
      // 一个字没改, 换主题自动切。值见 src/index.css。
      boxShadow: {
        sm: 'var(--shadow-sm)',
        DEFAULT: 'var(--shadow-sm)',
        md: 'var(--shadow-md)',
        lg: 'var(--shadow-lg)',
        xl: 'var(--shadow-xl)',
        '2xl': 'var(--shadow-2xl)',
        card: 'var(--shadow-md)',
        pop: 'var(--shadow-lg)',
        dialog: 'var(--shadow-2xl)',
      },
      transitionTimingFunction: {
        // §6.0.4 Linear/Vercel 同款缓动
        smooth: 'cubic-bezier(0.16, 1, 0.3, 1)',
        // [R317] 按 emil-design-eng §3 补三条「比 CSS 内置更有力」的曲线:
        // 内置 ease-out 收得太软, 入场缺"手感应答"的感觉。
        'out-strong': 'var(--ease-out-strong)',
        'in-out-strong': 'var(--ease-in-out-strong)',
        drawer: 'var(--ease-drawer)',
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
        //
        // [R317] 终态写成 `transform: none` 而不是 `translateY(0)` —— 两者视觉
        // 完全一样, 但差别在于**任何一个非 none 的 transform 都会让元素成为
        // position:fixed 后代的包含块**。这几个动画都带 `both`, 动画结束后
        // 终态会一直挂着, 于是列表项/弹窗内部的 fixed 元素(下拉、tooltip)会
        // 相对这个祖先定位, 而不是相对视口 —— 一个平时看不出来、一旦出现就
        // 很难查的错位。写成 none 之后动画结束不残留包含块。
        'rise-in': {
          from: { opacity: '0', transform: 'translateY(6px)' },
          to: { opacity: '1', transform: 'none' },
        },
        // [R317] 补两个基础入场。emil-design-eng §Component Building Principles:
        // **绝不从 scale(0) 入场** —— 现实里没有东西会凭空出现又凭空消失,
        // 从 0.96 起手已经足够"有形", 观感自然得多。
        'fade-in': {
          from: { opacity: '0' },
          to: { opacity: '1' },
        },
        // 弹窗/浮层: 从 0.96 放大到 1。模态框保持 transform-origin 居中
        // (它不挂在某个触发器上, 而是相对视口居中), 所以不做 origin 修正。
        'pop-in': {
          from: { opacity: '0', transform: 'scale(0.96)' },
          to: { opacity: '1', transform: 'none' },
        },
        // 通知条从下方推入(与 toast 的堆叠方向一致, 退出走同一路径)
        'toast-in': {
          from: { opacity: '0', transform: 'translateY(8px)' },
          to: { opacity: '1', transform: 'none' },
        },
      },
      animation: {
        // [R317] 320ms → 260ms。skill §4 的硬线是「UI 动效不超过 300ms」——
        // 列表入场是高频操作, 超过这条线会让界面显钝。
        'rise-in': 'rise-in 260ms cubic-bezier(0.16, 1, 0.3, 1) both',
        'fade-in': 'fade-in 160ms ease-out both',
        'pop-in': 'pop-in 180ms cubic-bezier(0.23, 1, 0.32, 1) both',
        'toast-in': 'toast-in 220ms cubic-bezier(0.23, 1, 0.32, 1) both',
      },
    },
  },
  plugins: [animate],
} satisfies Config
