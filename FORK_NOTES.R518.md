# R518 — 模拟盘分栏「今日信号」改名「信号」

| # | 改动 | 涉及文件 | 冲突风险 | 单独回退 |
|---|---|---|---|---|
| R518 | 用户截图指着分栏:「今日信号改成信号」。渲染出来的两处一起改: 分栏名(FLIP_TABS.signals)与栏里那张卡的标题(R512 定下卡片标题与栏同名)。名词表那一行正名改成「信号」, 「今日信号」收进别名列, 以后再渲染出来守卫会红; 核查过全站渲染文本里没有别处用「今日信号」。隐藏功能登记簿里那一条的名字跟着改成「信号栏的「盯着」一段」(STILL_THERE 锚点同步)。注释与 docstring 里复述旧名不动。(R517 自选精简方案仍待用户确认, 不在本提交里) | frontend/src/pages/FlipPaper.tsx; backend/tests/test_terminology.py; backend/tests/test_flip_tabs_r512.py; backend/tests/test_flip_today.py; docs/hidden-features.md; backend/tests/test_hidden_features_registry.py | 无 | 可以: git revert 本提交 |
