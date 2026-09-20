# R374 — 窄屏适配三处兜底

| # | 改动 | 涉及文件 | 冲突风险 | 单独回退 |
|---|------|---------|:---:|---------|
| R374 | 22 个内置页面在 375px 窄屏下整体审计后, 三处兜底修复: PageHeader 工具栏根因加 flex-wrap、指数页主网格与日期选择器窄屏堆叠、设置页窄屏默认收起侧栏。 | `frontend/src/components/PageHeader.tsx`、`frontend/src/pages/Indices.tsx`、`frontend/src/pages/Settings.tsx`、本记录 | 低 | 回退本次独立提交 |

## 背景

用户问 "所有页面是否适配手机端显示完整"。调研时发现 R366 已定下口径
("手机端我只需要模拟盘页面和模拟盘里面的那两个弹窗, 只看这三个"),
PWA `start_url` 直接指 `/lots`, 严格按此口径其他页面不是目标。

但审计过程中发现**三类会真的出问题**的页面, 优先级:

| # | 问题 | 现状 |
|---|------|------|
| 1 | `Indices.tsx:194` 主网格 `grid-cols-[15rem_1fr]` 固定 240px 左栏 | 手机 375px 上左栏吃掉 65% 屏宽, K线主区只剩 119px |
| 2 | `Settings.tsx:76` 两栏布局 + nav 默认展开 | 手机上 nav 224px (144 + 80 gap), 内容区剩 151px 几乎不可读 |
| 3 | PageHeader 的 right 工具栏 `shrink-0` 不换行 | 全站影响 (Screener / Review / Indices 等所有用 PageHeader 的页面), 多按钮会被压缩或溢出 |

## 改法 (按 emil-design-eng Before/After)

### 1. PageHeader.tsx (根因修法)

| Before | After |
|--------|-------|
| `<div className="shrink-0">{right}</div>` | `<div className="flex min-w-0 flex-wrap items-center justify-end gap-x-2 gap-y-1">{right}</div>` |

- `flex-wrap` 让工具栏按钮/date input 组合在窄屏自动换行
- `min-w-0` 替换 `shrink-0`, 让 right 可压缩 —— 与 left 已有的 `min-w-0 truncate` 配合, 窄屏上 left 优先压短, right 内部自然换行
- `gap-y-1` 限制换行后行间距, 不让 PageHeader 被撑高
- **一处改, 全站受益**: 所有 `PageHeader right={...}` 调用方不动, 自动获得窄屏行为

### 2. Indices.tsx 主网格 + 日期选择器

| Before | After |
|--------|-------|
| `<div className="grid grid-cols-[15rem_1fr] gap-4">` | `<div className="grid grid-cols-1 gap-4 lg:grid-cols-[15rem_1fr]">` |
| 日期工具栏 `<div className="flex items-center gap-2 text-xs">` | `<div className="flex flex-wrap items-center gap-2 text-xs">` |

- 默认 grid-cols-1 让左侧指数列表折到顶部堆叠; lg 才回两栏
- 日期选择器加 flex-wrap, 两个 input + "至" 标签窄屏自动换行

### 3. Settings.tsx 窄屏默认收起

| Before | After |
|--------|-------|
| `localStorage.getItem(...) === '1' \|\| false` | 已有存值用存值; 首次访问按 viewport: 窄屏默认收起, 桌面默认展开 |

```tsx
const [collapsed, setCollapsed] = useState(() => {
  try {
    const stored = localStorage.getItem('tf-settings-nav-collapsed')
    if (stored !== null) return stored === '1'
    return !window.matchMedia('(min-width: 768px)').matches
  } catch { return false }
})
```

- 用户已有的偏好不覆盖; 首次访问窄屏直接收起, 避免 nav 挤掉内容
- SSR 安全: useState lazy init 只在 client 跑; `window.matchMedia` 直接调不引 hook, 不引入额外重渲染
- resize 不重新评估 —— 用户可手动 toggle, 之后存进 localStorage

## 没改的页面与原因

| 页面 | 现状 | 不动的原因 |
|------|------|-----------|
| FlipPaper / Watchlist / Dashboard / Monitor / Regime / Signals / Financials / Data / Backtest / Factors / Onboarding / Branding / ExternalPage / Lots / Dev / ConceptAnalysis / IndustryAnalysis / StockAnalysis / AbnormalMoves / LimitUpLadder | 顶层布局已用 `grid-cols-1 ... md:...` 或 `flex-col ... lg:flex-row`, 工具栏已 `flex-wrap` | 已 OK; 改了反而是噪声 |

## 故意不做的 (扩大范围 / 背离 R366)

- **抽屉式侧栏手势关闭**: Layout.tsx 的 drawerOpen 只有按钮触发, 没有 swipe-to-close —— 那是新功能不是 bug 修复
- **Settings nav 在窄屏改成水平 tab bar 或下拉 select**: 当前用"窄屏默认收起 + 仅图标", 用户可手动展开; 改造成本与收益不匹配 R366 的"手机端只做模拟盘"口径
- **AppIcon / PWA 启动屏在 18:9 / 19.5:9 刘海屏的 safe-area**: 与本次"内容区不被切"目标无关

## 验证

- ✅ 三冻结区 diff 为空 (`git diff --stat backend/app/strategy/ backend/app/services/opportunity_score.py ...`) — 作者内置指标 / 六态 / 评分系统全部未动
- ✅ 前端 `npm run build` (tsc -b → vite → compress) 退出码 0, 10.32s 完成
- ✅ 守卫 `backend/tests/test_terminology.py` 不需要更新 (本次没改任何用户可见中文名词, 守卫规则不变)
- ⚠️ 后端 pytest 本机未装, 不影响本次 (前端纯展示)
- ⚠️ 没在真机或 Chrome DevTools 模拟器上跑过; Tailwind 的 `lg:` 阈值 1024px, `md:` 768px, 与 `useIsDesktop` 一致; 375px/414px/iPad 各档都已在 class 计算覆盖范围内

## 不影响

- 数据契约 / 接口 / 依赖 / 后端 / 打包 / 镜像构建 / 公共 API
- 横向滚动行为 / 动画时序 / 主题 (明暗切换) / 点击股票弹窗
- 已存的 `nav_order` 与所有 localStorage key

本记录沿用 R371/R372 独立补充方式; 主 `FORK_NOTES.md` 保持原样, 不用片段覆盖历史。
