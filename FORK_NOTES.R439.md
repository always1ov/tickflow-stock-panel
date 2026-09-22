# R439 — 量化MACD 副图的红色横线整套撤掉

| # | 改动 | 涉及文件 | 冲突风险 | 单独回退 |
|---|------|---------|:---:|---------|
| R439 | 用户: 「量化macd还是有红线划分间距, 我不需要红线删掉」。R434(四行等高 + 红框)与 R436(三格等间距的暗红点线)在副图里加的横格整套撤掉, 回到 R423 的样子: 副图纵轴恢复 `scale: false, splitNumber: 2` + 不画背景横线; 删掉那支画横格的空系列(markLine)、缩放后重算横格的 `datazoom` 监听与 `qmacdGridRef`; 删掉 `quantMacdGrid` / `QMACD_GRID_SPLIT` / `QMACD_GRID_PAD` 及其 vitest 一组、调色板里的 `gridLine`。`quantMacdSeries.ts` 与它的测试逐字回到 R434 之前(c2bcedea), 柱子、图标、颜色、亮色主题下的黑底一个没动。截图核对: 亮暗两套主题、缩放前后副图里都没有横线也没有框。守卫 `test_R439_量化MACD副图不画红线` 替掉 R436 那条; 变异 3/3 杀死(背景横线打开 / 外框回来 / 红色回到调色板) | `frontend/src/components/stock-analysis/AnalysisKChart.tsx`、`frontend/src/lib/quantMacdSeries.ts`、`frontend/src/lib/quantMacdSeries.test.ts`、`frontend/src/lib/theme.ts`、`backend/tests/test_status_section.py` | 低(只在 fork 自己加的量化MACD 副图里) | 回退本提交即回到 R436 的三格等间距红点线 |
