# R464 — 全站迁移 · 财务分析

| # | 改动 | 涉及文件 | 冲突风险 | 单独回退 |
|---|------|---------|:---:|---------|
| R464 | 全站迁移第十六步(规范见 `docs/ui-hierarchy.md`)。财务分析页与它的组件(AI 财务分析弹窗、报告气泡、历史报告、个股财务详情、财务搜索)共 25 处写死字号按角色落档; 「财务数据不可用」提示标题、「该个股已有分析报告」确认框标题、AI 财务分析弹窗标题升到 L2(18px)。页面清单里「财务 / 数据 / 因子 / 回测」原来并在一行, 拆成四行分别打勾。棘轮 任意字号下调到当前数 | `frontend/src/pages/Financials.tsx`、`frontend/src/components/financials/*`、`docs/ui-hierarchy.md`、`backend/tests/test_ui_hierarchy.py`、`backend/tests/test_design_spec.py` | 中(与上游同源, 上游改这几处时字号类会冲突, 以本 fork 的档位为准) | 回退本提交即回到原字号 |
