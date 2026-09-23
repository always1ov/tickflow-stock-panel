# R453 — 全站迁移 · 大盘(市场看板)

| # | 改动 | 涉及文件 | 冲突风险 | 单独回退 |
|---|------|---------|:---:|---------|
| R453 | 全站迁移第五步(规范见 `docs/ui-hierarchy.md`)。市场看板: 页标题「市场看板」16px → L1(21px), 页头条去掉渐变底、投影、毛玻璃与左侧色条, 换成全站卡片; 各卡片标题(涨跌分布、情绪雷达、趋势强度、涨停梯队、概念 / 行业热度、各排行榜…)13px → L3(15px), 标题前那道装饰小竖条撤掉; 七处卡片外框「半透明底 + 投影 + 毛玻璃 + 悬停加投影」统一成实边框实底(与弹窗同一套), 内边距放宽; 六个指标卡的数值 18px → 读数级 21px; 重载按钮换成全站按钮; 情绪雷达中心分数 24px → 25px 档; 其余 65 处写死字号按角色落档。子组件: 封板徽标、板块成分弹窗(标题升 L2)、任务进度卡、复权同步提示(标题升 L2)、日期选择器的写死字号落档, 写死的黄 / 琥珀色换成语义色 warning。棘轮 任意字号与硬编码色下调到当前数 | `frontend/src/pages/Dashboard.tsx`、`frontend/src/components/{SealedBadge,DimensionMembersDialog,AdjFactorSyncGate,DatePicker}.tsx`、`frontend/src/components/data/ActiveJobCard.tsx`、`docs/ui-hierarchy.md`、`backend/tests/test_ui_hierarchy.py`、`backend/tests/test_design_spec.py` | 中(`Dashboard.tsx` 与上游同源, 上游改看板时字号 / 卡片类会冲突, 以本 fork 的档位为准) | 回退本提交即回到原样式 |
