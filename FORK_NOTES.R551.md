# R551 — 个股弹窗: 「关键价位」图上方的六态条与「现状」卡重复, 撤掉

| # | 改动 | 涉及文件 | 冲突风险 | 单独回退 |
|---|---|---|---|---|
| R551 | 用户圈出现状卡的六态格与关键价位图上方的六态条: 「圈出来的部分重复了, 整改」。两处读同一个查询(useStockTrend), 状态名 / 已 N 天 / 由谁转入 / 跌破转弱 / 站上转强逐字相同 → 个股弹窗里的 `StockLevelsPanel` 传 `trendBar={false}` 不再印那条; 六态条独有的三样搬进现状卡的六态格, 不丢: ① 「回测调参 N%(已定制)」按钮(连同调参弹窗)放在「自 … 转入」下面; ② 当天的转折信号徽标(转多 / 转空 / 回升 / 回撤)跟在「已 N 天」后面; ③ 操作建议(观望, 上破 … 确认转多 …)与本轮高低收盘 / 上下关键点 / 阈值 / 价格口径放进状态名的悬停 —— 建议那句是把两条翻转价再念一遍, 印出来就又重复了。按钮、徽标、悬停文案从 `TrendStateBar.tsx` 抽成 `TrendBacktestButton` / `TrendSignalBadge` / `trendPivotTitle` 共用, 不复制第二份。独立的「关键价位」弹窗(LevelsDialog)上面没有现状卡, 六态条照旧 | frontend/src/components/stock-analysis/TrendStateBar.tsx; frontend/src/components/stock-analysis/StockLevelsPanel.tsx; frontend/src/components/StockPreviewDialog.tsx; frontend/src/components/stock-preview/StatusSection.tsx; backend/tests/test_preview_trend_dedupe_r551.py | 低: 只动个股弹窗的版面, 六态数据与判定不变 | 可以: git revert 本提交 |
