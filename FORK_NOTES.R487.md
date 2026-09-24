# R487 — 趋势量化: 原文没写颜色的三样对着通达信截图校准

| # | 改动 | 涉及文件 | 冲突风险 | 单独回退 |
|---|---|---|---|---|
| R487 | R486 时原文没写颜色的平均线 / 吸筹线 / 升顶下暂取白 / 浅灰。用户发来通达信截图(长飞光纤, 主力趋势雷达)后校准: 平均线通达信里是洋红(顶部数值栏也是), 全站禁粉 → 换成离洋红最近、不进禁粉范围的紫 #B84DFF(OKLCH 色相 308°, 距 315° 的边界留余量; #D000FF 317° 与 #FF00FF 328° 都会被 test_no_pink 拦下); 吸筹线是绿 #00FF00(贴 0.5 黄线上方那条与沿白柱顶端那条); 升 / 顶 / 下是白, 与原取值相同。只动 theme.ts 的 TREND_QUANT_COLORS 两个值与说明、CONTEXT.md 一句; 加前端测试 1 条钉住三种色 | frontend/src/lib/theme.ts; frontend/src/lib/trendQuantSeries.test.ts; CONTEXT.md | 低 | 可以: git revert 本提交 |
