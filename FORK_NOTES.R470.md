# R470 — 全站迁移 · 共用组件(二): 弹窗与小件

| # | 改动 | 涉及文件 | 冲突风险 | 单独回退 |
|---|---|---|---|---|
| R470 | 「其余共用组件」第二批按 R449 层级迁移: 写死字号全部落到 text-micro / text-xs; 把握分台账、名词说明、端点测速三个弹窗标题改 L2, 台账各表小标题与「AI 提炼」、外部视图区块标题改 L3、外部视图页标题改 L2; 台账里天蓝 / 紫色染色的「复制体检摘要」「AI 提炼」按钮与紫色底的摘要框改中性描边 / 实底; 分组统计的指标 / 排序、打分编辑的高值 / 低值选中态统一黑白反相, 打分权重条与「编辑方案」按钮的琥珀改主色 / 描边, 权重合计不等于 100 时的提示改 warning; 端点测速主按钮与切换钮走 buttonClass, 「当前使用」一行加 nowrap / truncate 防止大字号下折行; 告警弹出卡与 AI 助手抽屉去掉半透明 + 背景模糊改实底, 助手发送钮走 primary 图标钮。告警卡里按类型区分的徽标色(身份色)不动。棘轮: 裸圆角 786→781, 任意字号 211→123, 硬编码色 804→779 | frontend/src/components/{ScoreLedgerDialog,EndpointTestDialog,AlertToast,GroupStatsSettings,ScoringEditor,ExternalViewRender,NavPager,GlossaryDialog,CollapsibleText,PageErrorBoundary}.tsx; frontend/src/lib/capability-labels.tsx; frontend/src/custom/assistant/ui/{messages,AssistantDrawer,DailyChartCard}.tsx; backend/tests/test_design_spec.py; backend/tests/test_ui_hierarchy.py | 低: 多为小组件, 冲突时取上游逻辑、保留本处样式 | 可以: git revert 本提交, 同时把棘轮三个数字改回 |
