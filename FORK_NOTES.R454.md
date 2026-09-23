# R454 — 全站迁移 · 监控中心(含规则编辑器)

| # | 改动 | 涉及文件 | 冲突风险 | 单独回退 |
|---|------|---------|:---:|---------|
| R454 | 全站迁移第六步(规范见 `docs/ui-hierarchy.md`)。监控中心: 触发记录那排过滤标签(全部 / 策略监控 / 信号 …)10px → 正文级 13px、28px 高, 选中从强调色换成全站反相(可点的控件按正文级, 不按徽标级); 「只看焦点」开关、「前往数据源配置」换成全站按钮; 「触发记录 / 监控规则」卡片标题走 L3; 批量推送渠道、字段配置、个股通知标签三个弹窗标题升到 L2; 页内 60 处写死字号按角色落档(来源 / 板块 / 信号徽标与时间戳 → 11px, 消息与数值 → 13px)。焦点条 9 处落档。规则编辑器(全站写死字号最多的单文件, 127 处)按角色落档, 两个标题(加入监控 / 新建监控规则)升到 L2, 写死的琥珀色一律换成语义色 warning。信号点选(`screener/SignalPicker`, 选股的策略弹窗也用)的小按钮 10~11px → 13px, 与全站按钮同高, 未选中样子与全站描边按钮一致, 选中仍按进场蓝 / 出场橙(颜色有含义)。棘轮 裸圆角、任意字号、硬编码色下调到当前数 | `frontend/src/pages/Monitor.tsx`、`frontend/src/components/monitor/{FocusBar,RuleEditor}.tsx`、`frontend/src/components/screener/SignalPicker.tsx`、`docs/ui-hierarchy.md`、`backend/tests/test_ui_hierarchy.py`、`backend/tests/test_design_spec.py` | 中(`Monitor.tsx` / `RuleEditor.tsx` 与上游同源, 上游改这两处时字号类会冲突, 以本 fork 的档位为准) | 回退本提交即回到原样式 |
