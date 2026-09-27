# R557 — 趋势量化副图: 超买 / 超卖右端标签去掉数值

| # | 改动 | 涉及文件 | 冲突风险 | 单独回退 |
|---|---|---|---|---|
| R557 | 用户: 「超买超卖不需要显示数值了」。R556 两条黄线右端的「超买 3.2」「超卖 0.5」改为「超买」「超卖」; 悬停说明那一段的标题跟着改叫「超买 / 超卖」, 3.2 / 0.5 两个数只留在说明正文里。公式与画法没动 | frontend/src/lib/trendQuantSeries.ts; frontend/src/lib/trendQuantSeries.test.ts; backend/tests/test_trend_quant_legend_r555.py | 低: 只改两个标签的文字 | 可以: git revert 本提交 |
