# R468 — 全站迁移 · 设置

| # | 改动 | 涉及文件 | 冲突风险 | 单独回退 |
|---|---|---|---|---|
| R468 | 设置页七个面板按 R449 层级迁移: 写死字号全部落到 text-micro / text-xs; 面板与卡片标题(h2 / h3)统一 L3, 清空 AI 配置 / 删除数据源 / 清除 API Key 三个确认弹窗标题改 L2; 保存 / 测试 / 新增等主按钮走 buttonClass primary, 解绑类小按钮走 danger 描边; 能力路由的提供方标签选中态改黑白反相、未选中字色提到 secondary; 扩展页面的模式卡与字段勾选改 SELECTED 一套; 设置左侧导航选中态与应用侧栏同一种(accent-soft), 徽标琥珀改 warning; emerald 绿一律换 bear、琥珀一律换 warning; rounded-lg / md / xl / 2xl 收成 rounded-btn / rounded-card。顺手修: ExtPages 与 MiningWorkbench 里写的 text-success / bg-success / border-success 在色板里不存在, 实际什么颜色都没有(已启用、达标、正收益折都显示成默认色), 换成 bear。棘轮: 裸圆角 860→829, 任意字号 574→347, 硬编码色 877→846 | frontend/src/pages/Settings.tsx; frontend/src/pages/settings/*.tsx; frontend/src/pages/backtest/MiningWorkbench.tsx; backend/tests/test_design_spec.py; backend/tests/test_ui_hierarchy.py; docs/ui-hierarchy.md | 中: 上游改设置面板时 className 行会冲突, 取上游逻辑、保留本处样式 | 可以: git revert 本提交, 同时把棘轮三个数字改回 |
