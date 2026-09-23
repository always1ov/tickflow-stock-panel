# R465 — 全站迁移 · 数据

| # | 改动 | 涉及文件 | 冲突风险 | 单独回退 |
|---|---|---|---|---|
| R465 | 数据页按 R449 层级迁移: 写死字号全部落到 text-micro / text-xs; 「数据画像」「同步历史」分区标题从 12px 灰色大写字距改成 L2(TYPE.section); 实时行情 / 自动调度 / 存储 / 各数据卡标题改 L3(TYPE.card), 数据卡大读数从 24px 粗体收到 21px(读数档); 页头按钮全部换 buttonClass —— 立即同步为全页唯一主按钮, 停止为红字描边, 清除数据走 danger, 其余描边; 两个确认弹窗标题 L2、按钮走 buttonClass; 月/年、拉取/推送/上传、URL/文件/手动三组切换换成 SEG 分段控件; 轮询间隔与重算批次预设换成 buttonClass 选中态(黑白反相); 扩展数据新增 / 编辑弹窗标题 L2、小节标题 L3、输入框字号统一 13px、琥珀色警示换 warning、绿色成功换 bear; 扩展数据卡去掉按类型染色的底与边(类型色只留在徽标上); 分钟 K「获取最近 1 年」由琥珀染色改描边。棘轮: 裸圆角 917→865, 任意字号 1140→914, 硬编码色 943→909 | frontend/src/pages/Data.tsx; frontend/src/components/data/*.tsx; frontend/src/components/ext-data/*.tsx; backend/tests/test_design_spec.py; backend/tests/test_ui_hierarchy.py; docs/ui-hierarchy.md | 中: 上游改数据页或扩展数据组件时 className 行会冲突, 逐行取上游逻辑、保留本处样式即可 | 可以: git revert 本提交, 同时把棘轮三个数字改回 |
