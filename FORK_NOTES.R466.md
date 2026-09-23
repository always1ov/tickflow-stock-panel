# R466 — 全站迁移 · 因子

| # | 改动 | 涉及文件 | 冲突风险 | 单独回退 |
|---|---|---|---|---|
| R466 | 因子页按 R449 层级迁移(含因子页里嵌的检验 / 挖掘 / 候选方案三块): 写死字号全部落到 text-micro / text-xs; 页头五个视图切换、批量筛选 / 单因子检验、股票 / ETF、候选方案的全部 / 因子 / 策略、相关矩阵的入选 / 全部改成 SEG 分段控件(选中黑白反相); 预设、组合成员、组合模式、评分方向、打分方向的选中态统一成 SELECTED; 主按钮(开始挖掘 / 检验此因子 / 注册 / 生成等)走 buttonClass primary, 其余描边; 编辑器、试算、组合构建器、挖掘侧栏各小节、筛选结果标题改 L3, 候选方案与因子详情弹窗标题改 L2; 因子库与筛选结果表头换 THEAD + TH_ROW; 挖掘侧栏与检验侧栏的勾选项从 9~10px 提到 13px; 「边缘」「点时」与策略徽标的琥珀色换 warning, 挖掘里「加入信号条件」的琥珀 hover 改中性。棘轮: 裸圆角 865→863, 任意字号 914→752, 硬编码色 909→897 | frontend/src/pages/Factors.tsx; frontend/src/pages/factors/*.tsx; frontend/src/pages/backtest/FactorDiscovery.tsx; frontend/src/pages/backtest/MiningWorkbench.tsx; frontend/src/pages/backtest/ResearchCandidatesDialog.tsx; backend/tests/test_design_spec.py; backend/tests/test_ui_hierarchy.py; docs/ui-hierarchy.md | 中: 上游改因子页或挖掘工作台时 className 行会冲突(MiningWorkbench 多为单行长 JSX), 取上游逻辑、保留本处样式 | 可以: git revert 本提交, 同时把棘轮三个数字改回 |
