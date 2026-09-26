# R521 — 决策台「只看要动的」默认开着并记住

| # | 改动 | 涉及文件 | 冲突风险 | 单独回退 |
|---|---|---|---|---|
| R521 | R520 方案里留给用户定的一条, 用户:「等我的事件, 你帮我选择最优解拍板」。定: 默认开。理由: 这一页叫决策台, 回答「今天该动谁」; 一百多只里天天真该看的就那几只, 先列全部是让人先过一遍噪音再找信号 —— 与模拟盘「没事是常态」同一条取舍(代码注释里 R178 起就写着「默认列 80 行本身就是噪音」, 只是一直没改默认)。开关存 localStorage(boardActionableOnly), 关了就一直关着, 不会每次打开都替人做一遍决定。定位(搜索 / 从别页跳来)到一只被它挡住的票时, R330 那段兜底照旧自动关掉并提示。守卫 test_board_default_actionable_r521 | frontend/src/components/stock-analysis/WatchlistDecisionBoard.tsx; frontend/src/lib/storage.ts; backend/tests/test_board_default_actionable_r521.py | 低 | 可以: git revert 本提交(回到默认关) |
