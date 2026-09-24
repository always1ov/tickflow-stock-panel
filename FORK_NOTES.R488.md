# R488 — 庄现狗头从量化MACD 挪到趋势量化

| # | 改动 | 涉及文件 | 冲突风险 | 单独回退 |
|---|---|---|---|---|
| R488 | 用户:「把狗头剥离量化macd, 放到趋势量化里面去」。后端: /quant-macd 撤掉 zhuang 字段与为它多取的高 / 低列, 端点函数与 R485 之前逐字一致; /trend-quant 多一个 zhuang 字段, 仍由独立冻结的 indicators/zhuang_xian.py 单独算、不经过 trend_quant.compute。前端: QuantMacdResult 去掉 zhuang, TrendQuantData 加上; AnalysisKChart 里狗头改读 trendQuant、画在第三张 grid(趋势量化)的底边, 压在趋势量化最上面。庄现算法、狗头画法一个字没改。守卫改指向: test_zhuang_xian 的端点测试改打 /trend-quant, 「副图算法怎么变庄现都不变」改成把 trend_quant 与 quant_macd 的计算都换成胡乱结果; 新增「狗头画在趋势量化、不在量化MACD」与「量化MACD 接口不再带庄现」两条; 前端画法守卫扩到也不许读趋势量化的数值。CONTEXT.md 庄现词条跟着改 | backend/app/api/stock_analysis.py; backend/app/indicators/zhuang_xian.py(只改说明); backend/tests/test_zhuang_xian.py; frontend/src/lib/api.ts; frontend/src/lib/trendQuantSeries.ts; frontend/src/lib/zhuangXianSeries.ts(只改说明); frontend/src/components/stock-analysis/AnalysisKChart.tsx; CONTEXT.md | 低 | 可以: git revert 本提交(狗头回到量化MACD) |
