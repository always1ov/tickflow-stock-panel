# R560 — 量化MACD: 标题带里的图例 + 悬停说明

| # | 改动 | 涉及文件 | 冲突风险 | 单独回退 |
|---|---|---|---|---|
| R560 | 用户: 「量化macd也加标注」(趋势量化 R555 已有)。量化MACD 标题带里「量化MACD」右边加一行图例, 每项 = 照图里画法缩小的色块 + 正文灰名字: DIFF(红绿各半的实心块) / DEA(深红点线框) / 共振(黄块, 加细灰边 —— 亮色主题标题带是白底) / 金叉(红色向上箭头) / 死叉(绿色向下箭头); 两个箭头从图里 ICON_UP / ICON_DOWN 同一份路径取顶点画成多边形(ECharts graphic 没有 path 类型, 首版用 path 整张图报错, 已改)。图例上盖透明热区, 悬停走 R553 的全站提示, 五段说明逐条对照 `indicators/quant_macd.py`: DIFF = 12 日与 26 日指数均线之差、被 DEA 框盖住只露出比 DEA 长的一截(露出实心 = 动能加速, 只剩空框 = 减弱); DEA = DIFF 的 9 日指数均线; 共振黄柱 = 能量潮短线强度增加且 3 日均价上升、从 0 画到 DEA/4 只看有无; 金叉箭头顶端对准 DEA; 死叉画在 DEA×1.1。图例与说明只在 `lib/quantMacdSeries.ts` 一处(单测钉住图例名 = 图里系列名)。R415「图里只画原文画的」仍成立: 图例在副图外面。公式与画法一个字节没动 | frontend/src/lib/quantMacdSeries.ts; frontend/src/lib/quantMacdSeries.test.ts; frontend/src/components/stock-analysis/AnalysisKChart.tsx; backend/tests/test_quant_macd_legend_r560.py | 低: 只在标题带加字与热区 | 可以: git revert 本提交 |
