# R499 — 转折页不再显示「有信号但没做成」

| # | 改动 | 涉及文件 | 冲突风险 | 单独回退 |
|---|---|---|---|---|
| R499 | 用户:「有信号没做成的就不要放出来了」。只撤页面上那一块: 删掉 Skipped 组件、它的原因翻译表 WHY_CN 与并排判据 hasSkipped, 成交流水改为独占整行; 页首版面说明里的第⑤块标成已撤。后端 flip_paper 照旧算并返回 skipped / missing / pending(模拟盘的封板顺延成交靠它们), 前端类型也不动。连带不再显示的还有那块里的两行: 取不到日线的票、还在等成交的单。守卫: 改了 test_flip_fusion(R343 版面顺序、R381 两条)、test_flip_today(R329)、test_flip_layout_r498 各处对「没做成」的引用, 新增一条钉住页面上不再出现且接口字段保留; 全量验证通过 | frontend/src/pages/FlipPaper.tsx; backend/tests/test_flip_fusion.py; backend/tests/test_flip_today.py; backend/tests/test_flip_layout_r498.py | 低(fork 自有页面) | 可以: git revert 本提交 |
