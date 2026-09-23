# R471 — 全站迁移 · 共用组件(三): 独立页, 全站迁移收尾

| # | 改动 | 涉及文件 | 冲突风险 | 单独回退 |
|---|---|---|---|---|
| R471 | 「其余共用组件」最后一批 —— 消息面、首次引导、登录、外部网页、品牌五个独立页按 R449 层级迁移: 写死字号全部落到 text-micro / text-xs(消息面输入框 13px 原样); 消息面的筛选改 SEG 分段控件, 「消息面总览」区块去掉紫色底改实底卡片、标题改 L3、「生成总览 / 重新综合」改描边小按钮; 引导页的大按钮走 buttonClass(primary / ghost, 保留 44px 高), 半透明 + 模糊的卡片改实底, 「配置数据源」步骤标题改 L1; 登录卡片改实底、紫色图标底改中性; 圆角收成令牌。引导页开场的大标题(24~30px)是落地页的主视觉, 不压。至此 docs/ui-hierarchy.md 清单全部打勾; 全站剩下的 64 处写死字号全在 StockReviewDialog / StateTimeline / ReviewHeadRow / StockPreviewDialog 旧顶栏以下 —— 只有待删的旧部分在用, 等「统一删除」一起走。棘轮: 裸圆角 781→764, 任意字号 123→64, 硬编码色 779→769 | frontend/src/pages/{UsageNotes,Onboarding,Auth,ExternalPage,Branding}.tsx; backend/tests/test_design_spec.py; backend/tests/test_ui_hierarchy.py; docs/ui-hierarchy.md | 低: 独立页上游改动少 | 可以: git revert 本提交, 同时把棘轮三个数字改回 |
