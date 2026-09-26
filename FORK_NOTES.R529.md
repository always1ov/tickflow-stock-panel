# R529 — 布林线的名字按用户定的写法: 「26日布林」, 周期在前

| # | 改动 | 涉及文件 | 冲突风险 | 单独回退 |
|---|---|---|---|---|
| R529 | 用户:「名称叫做26日布林」。R528 写的是「布林(26日)」, 改成周期在前: 关键价位图开关「26日布林」, 端点标签「26日布林上轨 / 中轨 / 下轨」, 价位列表同名; 日K图叠加开关原来是英文「BOLL(26)」, 三条线叫「BOLL上 / 中 / 下」, 悬停「BOLL(26):」, 统一改成「26日布林」「26日布林上轨 / 中轨 / 下轨」「26日布林:」。20 日那组跟着同一个形状: 「20日布林上轨」「20日布林下轨」(自选 / 策略结果表的列、条件字段名)。名字仍只在 `indicators/bollinger.py` 一处产出, 前端与守卫对齐; NOT_A_CONFLICT 那条同步改写 | backend/app/indicators/bollinger.py; backend/app/indicators/levels.py; backend/app/api/stock_analysis.py; frontend/src/components/stock-analysis/AnalysisKChart.tsx; frontend/src/components/EChartsCandlestick.tsx; frontend/src/lib/watchlist-columns.ts; frontend/src/lib/screener-columns.ts; frontend/src/lib/signals.ts; frontend/src/pages/backtest/StrategyBacktest.tsx; frontend/src/components/screener/StrategySettingsDialog.tsx; backend/tests/test_boll26_chart.py; backend/tests/test_terminology.py | 低: 只是文案 | 可以: git revert 本提交 |
