# R483 — 粗细档回测改评图上真画的那一组线

| # | 改动 | 涉及文件 | 冲突风险 | 单独回退 |
|---|---|---|---|---|
| R483 | 斐波那契Ⅱ型的画法 R473~R480 改了七轮(波段切段、上攻起点、重新启动根作锚、最近锚只画 F3、1% 聚类), 粗细档回测(dinapoli_fit)一轮没跟: 它仍按 R473 之前「连续 8 根站上短期均线」切段、只拿摆点当锚、0.5×ATR 当容差 —— 粗细档建议评的是图上早已不画的线。改成: 按波段(新拆出的 upswings, 与 latest_upswing 同一段 ZigZag)切出每段上涨, 截到顶那根用画图的同一个 compute 重画当时的图, 评那一组线; 「落在线上」的容差改用聚焦点的 ZONE_PCT(与密集带同一把尺子)。顺带: ① pullback_low 的「至少 3 根」只在数据到头时才要(它的 docstring 本来就这么说), 原来急跌急拉的完整回踩也被扔出样本; ② 挑锚那段循环拆成 pick_anchors, 图上与 reactions_before 共用; ③ 撤掉再没人调用的 thrust_segments / _emit / THRUST_MIN / THRUST_MIN_ATR / TOL_ATR 及其 4 条用例, 换成「截到顶那根重跑认出的还是这一段」的用例; ④ 改掉三处说假话的注释(863.52 / 932.41 当 F3、A 取最近反应点、每对都画两条)。守卫 test_R483_评的就是图上那一组线_用对照图那一段验(拿旧实现跑是红的)。750 根三档 74ms | backend/app/indicators/dinapoli.py; backend/app/indicators/dinapoli_fit.py; backend/tests/test_dinapoli_fit.py; backend/tests/test_dinapoli_pivots.py | 低(两个都是 fork 自有文件) | 可以: git revert 本提交 |
