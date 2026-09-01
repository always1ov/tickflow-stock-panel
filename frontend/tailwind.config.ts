import type { Config } from 'tailwindcss'
import animate from 'tailwindcss-animate'

// 设计语言 §6.0:暗色为主 + 电光蓝强调 + 等宽数字
export default {
  darkMode: ['class'],
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    container: { center: true, padding: '1rem' },
    extend: {
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
      fontSize: {
        xs: ['12px', { lineHeight: '18px' }],
        sm: ['13px', { lineHeight: '20px' }],
        base: ['14px', { lineHeight: '22px' }],
        lg: ['16px', { lineHeight: '24px' }],
        xl: ['18px', { lineHeight: '26px' }],
        '2xl': ['22px', { lineHeight: '30px' }],
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
