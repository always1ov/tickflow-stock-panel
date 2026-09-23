# R458 — 全站迁移 · 指数

| # | 改动 | 涉及文件 | 冲突风险 | 单独回退 |
|---|------|---------|:---:|---------|
| R458 | 全站迁移第十步(规范见 `docs/ui-hierarchy.md`)。指数页: 左侧列表的标题「核心指数」11px 大写灰字 → L3(15px); 列表里的涨跌与代码小字落到标签级 11px; 空态提示落档。共用的分时图 `EChartsIntraday`(指数页与个股弹窗的分时都用)那两个小切换 10px → 13px, 均价 / 成交信息行 11px → 13px。棘轮 任意字号下调到当前数 | `frontend/src/pages/Indices.tsx`、`frontend/src/components/EChartsIntraday.tsx`、`docs/ui-hierarchy.md`、`backend/tests/test_ui_hierarchy.py`、`backend/tests/test_design_spec.py` | 中(两文件与上游同源, 上游改这两处时字号类会冲突, 以本 fork 的档位为准) | 回退本提交即回到原字号 |
