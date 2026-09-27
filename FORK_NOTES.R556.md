# R556 — 趋势量化副图: 超买 / 超卖写在黄线右端

| # | 改动 | 涉及文件 | 冲突风险 | 单独回退 |
|---|---|---|---|---|
| R556 | 用户: 「超买超卖想在黄线右端注明」。两条黄线各加 ECharts `endLabel`「超买 3.2」「超卖 0.5」, 落在副图右侧的留白带里, 平移 / 缩放时跟着线的右端走; 亮色主题下留白带是白底、纯黄字看不见 → 标签垫一块与副图同色的黑底(#000, 2/4 内边距, 2 圆角), 两个主题下都是黑底黄字。R555 图例行里的「超买 3.2 / 超卖 0.5」随之撤掉(名字已写在线上, 一行里再印一遍就重复了), 悬停说明里那一段保留(`labelledOnLine` 标记, 图例与说明仍是同一个产地)。公式与画法没动 | frontend/src/lib/trendQuantSeries.ts; frontend/src/lib/trendQuantSeries.test.ts; backend/tests/test_trend_quant_legend_r555.py | 低: 只动两条参考线的标签 | 可以: git revert 本提交 |
