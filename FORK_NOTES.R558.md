# R558 — 趋势量化 / 量化MACD 两张副图: 不挤、字看得清

| # | 改动 | 涉及文件 | 冲突风险 | 单独回退 |
|---|---|---|---|---|
| R558 | 用户: 「需要整改, 感觉空间有点挤, 有些东西看不清楚了, 量化macd也要整改」, 看过方案图后「确认」。只改显示: ① 每张副图顶上加一条 18px 标题带, 「趋势量化」「量化MACD」连同图例写在那里(11px / 10px、正文灰), 不再压在图里 —— 原来图例压着走到顶的柱子与「顶」字; 图例的悬停热区跟着挪进标题带; ② 副图高由主图的 40%(130~200)改为 48%(160~220), 个股预览 146 → 175px, 主图一像素不变(R419「不能让主图变矮」), 整张图变长靠弹窗滚动; ③ 趋势量化纵轴由自动改为固定 −0.45 ~ 4.35: 波动线恒在 0~4, 上面给走到顶的「顶」字留地方, 下面让狗头(贴副图底边画, 庄现冻结没动)落到两条底线下方, 不再压着线和「建仓」; ④ 八种字 12px → 11px, z 从 5 提到 8 压在吸筹白柱(z 6)之上并加 3px 黑描边 —— 原文的先后是白柱盖字, 可白柱在这里有间距的 1/3 宽, 「建仓」「绝底」整个被盖住; ⑤ 字的避让(`markOffsets`): 相邻两三根里纵向不到 12px 的两个字, 后一个让开一行(顶上放不下就往下), 出不出字、写在哪一根一概不变; ⑥ 量化MACD 只动标题带与高度, 柱子 / 图标是 R417 对着通达信逐像素量的, 没动。公式没动 | frontend/src/lib/levelsChartLayout.ts; frontend/src/lib/levelsChartLayout.test.ts; frontend/src/lib/trendQuantSeries.ts; frontend/src/lib/trendQuantSeries.test.ts; frontend/src/components/stock-analysis/AnalysisKChart.tsx; backend/tests/test_subpanes_r558.py | 低: 只动副图版面与字的画法 | 可以: git revert 本提交 |
