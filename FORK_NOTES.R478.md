# R478 — 个股弹窗: 「加监控」搬到新头部

| # | 改动 | 涉及文件 | 冲突风险 | 单独回退 |
|---|---|---|---|---|
| R478 | 用户准备删弹窗最底下的旧内容, 先要把「加监控」保下来:「先帮我移植保留监控按钮到新的里面的合适的位置」。新头部在自选星标旁边加一个同尺寸方框图标钮(RadioTower, 标题「加监控」)—— 两个都是对这只票做的事, 旧顶栏里它们也挨着; 右侧那一组(天数 / AI 四维分析 / 导出复盘 / 刷新)是怎么看这一页。点它打开的仍是弹窗层级那一个 RuleEditor 弹层(不在旧内容里, 之后删旧内容不受影响)。颜色按新版统一(原来的琥珀染色不带)。旧顶栏里那个按钮暂不动, 等用户确认删除清单。守卫 test_R478_新头部有加监控_打开的是弹窗那一个规则编辑器 | frontend/src/components/stock-preview/PreviewHero.tsx; frontend/src/components/StockPreviewDialog.tsx; backend/tests/test_preview_hero.py | 低 | 可以: git revert 本提交 |
