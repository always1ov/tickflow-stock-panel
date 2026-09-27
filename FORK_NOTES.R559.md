# R559 — 趋势量化: 八种字挪进图顶 / 图底两条字道, 不再压线、不再互叠

| # | 改动 | 涉及文件 | 冲突风险 | 单独回退 |
|---|---|---|---|---|
| R559 | 用户对 R558 的截图: 「字还是重叠」。R558 只让字与字互相避让, 字本身仍按原文 DRAWTEXT 的高度写在图里(平均线处、0.75、1、1.75、3.1), 那些高度正是线和柱子所在的地方: 「顶」压着紫线、「建仓」压着绿线和柱子、同一天连出的「逃逃」「下顶」竖着贴在一起。改为字道: 卖出一侧(顶 / 逃 / 下)写在图顶上一条字道, 买入一侧(升 / 建仓 / 见底 / 绝底 / 极底)写在图底下一条(在狗头上面), 每个字**水平对准它那一天**, 各两行; 一个自定义系列在第一根可见 K 线上画整组, 按真实像素宽度从左到右排(`laneLayout`), 挤不下才换第二行, 缩放后重排。出不出字、在哪一天、颜色一概不变, 变的只是竖直位置(原文高度 `at` 留在 TREND_MARKS 里作出处)。纵轴上下界改由 `tqYRange(副图高)` 把两条字道与狗头的像素换算成数值加到 0~4 两头(替掉 R558 的固定 −0.45 ~ 4.35); 趋势量化副图因此比量化MACD 高 50px(`TREND_LANES_EXTRA`), 中间的图不被挤扁。R558 的 `markOffsets` 撤掉。250 日全景下验证无重叠。公式、狗头画法没动 | frontend/src/lib/trendQuantSeries.ts; frontend/src/lib/trendQuantSeries.test.ts; frontend/src/lib/levelsChartLayout.ts; frontend/src/lib/levelsChartLayout.test.ts; frontend/src/components/stock-analysis/AnalysisKChart.tsx; backend/tests/test_subpanes_r558.py | 低: 只动趋势量化字的位置与副图高度 | 可以: git revert 本提交(回到 R558) |
