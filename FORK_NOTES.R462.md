# R462 — 全站迁移 · 信号库

| # | 改动 | 涉及文件 | 冲突风险 | 单独回退 |
|---|------|---------|:---:|---------|
| R462 | 全站迁移第十四步(规范见 `docs/ui-hierarchy.md`)。信号库: 「自定义信号 / 内置信号」页签换成全站分段切换, 选中从琥珀色实底换成反相, 计数角标 11px; 「新建信号」去掉琥珀底, 换成全站按钮; 每张信号卡的名称走 L3; 自定义信号弹窗标题升到 L2, 字段下拉里的当前项从强调色换成反相; 页内与弹窗 28 处写死字号按角色落档。棘轮 任意字号与硬编码色下调到当前数 | `frontend/src/pages/Signals.tsx`、`frontend/src/components/signals/CustomSignalDialog.tsx`、`docs/ui-hierarchy.md`、`backend/tests/test_ui_hierarchy.py`、`backend/tests/test_design_spec.py` | 中(两文件与上游同源, 上游改这两处时字号 / 按钮样式会冲突, 以本 fork 的档位为准) | 回退本提交即回到原样式 |
