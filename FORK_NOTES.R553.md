# R553 — 全站悬停提示: 浏览器原生 `title` 提示换成本系统画的一层

| # | 改动 | 涉及文件 | 冲突风险 | 单独回退 |
|---|---|---|---|---|
| R553 | 用户「整改所有悬浮」, 看过方案图后「确认」。全站 126 个文件 741 处 `title=` 走的都是浏览器原生提示: 要停一秒多才弹、深色主题里弹一块浅灰底(字号圆角阴影都不是本系统的)、多行说明挤成一坨 —— 与 R49 给「结论」列自己画悬停卡时列的毛病相同。新增 `lib/titleTooltip.ts`, 入口装一次, 调用方一处不改、以后新写的 `title=` 也自动走这层: 事件委托, 鼠标进到带 `title` 的元素先把它暂存到 `data-tt-title`(挡住原生提示), 离开原样放回(读屏读的仍是 title); 悬停中 React 改写 title 时取新值再挡; 元素被卸掉时收起。本系统底色 / 边框 / 圆角 / 字号, 深浅两色跟主题, 多行按行排开, 最宽 320px, 放不下自动上下翻面、水平夹进视口, 宽元素对准指针。动效: 首次停 400ms 弹(防误触), 弹过 300ms 内移到下一个立即出现不做动画; 入场 125ms opacity + scale(0.97)→1 有力 ease-out, 从触发元素那侧长出; 离开即消失、点击即收起; 只在 `(hover: hover) and (pointer: fine)` 接管, 触屏不碰; 减少动态效果只剩透明度。键盘 Tab 聚焦(:focus-visible)到带 title 的元素也显示。不含: 「结论」列等自己画的悬停卡、图表 tooltip、悬停才显的行内按钮 | frontend/src/lib/titleTooltip.ts; frontend/src/lib/titleTooltip.test.ts; frontend/src/main.tsx; backend/tests/test_title_tooltip_r553.py | 低: 入口多一行安装, 不改任何调用方 | 可以: git revert 本提交(或删 main.tsx 那一行即回到原生提示) |
