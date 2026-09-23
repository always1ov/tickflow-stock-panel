# R484 — 斐波那契二型的线加深

| # | 改动 | 涉及文件 | 冲突风险 | 单独回退 |
|---|---|---|---|---|
| R484 | 用户:「斐波那契2型的线颜色不够深」。浅的来源有两处: ① 亮色组色 #7B07CE 对页底 7.1:1; ② 不在密集带里的线按强弱叠了 BF 再乘常态 0.9, 实际只剩 0.68, 色值再深画出来也是浅的。改: 亮色组色压深一档到 #6A0DAD(对页底 8.6:1; 在守卫的算法下量过 —— 再深一档就与缺口位的靛 ΔE < 10, 更深成了近黑), 后端角色键 C_RETR 同步换、旧键 #7B07CE 进退役表; 二型的线不按强弱淡化、常态实色(悬停聚焦时照样淡到 0.12)—— 哪几条挤在一起已由密集带底色表达。暗色那一份 #724EA0 未动(暗色下更深就看不见, 更艳的几个离作者的枢轴紫太近)。守卫: test_level_palette.py 的常态透明度下限改成认得新写法, 新增 test_R484_斐波那契二型的线够深_不再叠透明度(拿旧图表代码跑 2 条红) | frontend/src/lib/theme.ts; frontend/src/components/stock-analysis/AnalysisKChart.tsx; backend/app/indicators/dinapoli.py; backend/tests/test_level_palette.py | 低 | 可以: git revert 本提交 |
