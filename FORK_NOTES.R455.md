# R455 — 全站迁移 · 模拟盘 / 持仓提醒; 小号按钮字号回到正文级

| # | 改动 | 涉及文件 | 冲突风险 | 单独回退 |
|---|------|---------|:---:|---------|
| R455 | 全站迁移第七步(规范见 `docs/ui-hierarchy.md`)。**转折模拟盘**写死字号只有 2 处, 但它在 R400 那一轮已经被迁到 11px 那一档, 结果正文、控件、表格内容全挤在 11px —— 这次按角色逐处看: 规则说明、原因统计、列表里的名称与持有 / 盯着状态、展开按钮、输入框、表格内容 15 处升到正文级 13px, 徽标、代码、表头、单位留在 11px; 指标卡数值 18px → 读数级 21px。**全站按钮小号**原来是 11px 字, 与「按钮一律正文级」的规范不符(R449 的疏漏), 改成 28px 高、13px 字 —— 模拟盘顶部的板块切换 / 体检 / 门槛、页头的刷新, 以及全站其余用小号的按钮一起变。**持仓提醒**: 表单字段名、提示、表格内容落 13px, 表头与徽标落 11px, 表头换成浅灰实底条; 日期快捷按钮 10px → 13px。今日组件(打分格、健康条、趋势格)与 Hint 的写死字号落档。规范补两条: 小号按钮字仍是 13px; R400 已落到 11px 的正文要按角色升回 13px。棘轮 裸圆角、任意字号下调到当前数 | `frontend/src/pages/{FlipPaper,Lots}.tsx`、`frontend/src/components/ui/Button.tsx`、`frontend/src/components/today/{ScoreCell,TodayHealthBar,TrendCell}.tsx`、`frontend/src/components/{Hint,DateShortcuts}.tsx`、`docs/ui-hierarchy.md`、`backend/tests/test_ui_hierarchy.py`、`backend/tests/test_design_spec.py` | 中(`Lots.tsx` 与上游同源; 模拟盘是 fork 自己的) | 回退本提交即回到原字号 |
