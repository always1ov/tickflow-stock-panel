# R463 — 全站迁移 · 概念 / 行业分析

| # | 改动 | 涉及文件 | 冲突风险 | 单独回退 |
|---|------|---------|:---:|---------|
| R463 | 全站迁移第十五步(规范见 `docs/ui-hierarchy.md`)。概念分析与行业分析(两页同一套写法)的五个指标卡: 数值 15px → 读数级 21px, 标签与说明 11px 留在标签级。共用的「盘中轮动」卡片: 标题 13px → L3(15px); 那一排下拉框、筛选输入框 10px / 24px 高 → 正文级 13px / 28px 高(可点的控件按正文级), 「过滤」按钮换成全站小号按钮。两页、轮动卡、外部维度分析、分区引言共 82 处写死字号按角色落档。棘轮 任意字号下调到当前数 | `frontend/src/pages/{ConceptAnalysis,IndustryAnalysis}.tsx`、`frontend/src/components/{SectorRotationCard,ExtDimensionAnalysis,SectionIntro}.tsx`、`docs/ui-hierarchy.md`、`backend/tests/test_ui_hierarchy.py`、`backend/tests/test_design_spec.py` | 中(与上游同源, 上游改这几处时字号类会冲突, 以本 fork 的档位为准) | 回退本提交即回到原样式 |
