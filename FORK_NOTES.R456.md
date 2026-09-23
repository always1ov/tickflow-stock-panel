# R456 — 全站迁移 · 选股(策略); 新增共用的分段切换

| # | 改动 | 涉及文件 | 冲突风险 | 单独回退 |
|---|------|---------|:---:|---------|
| R456 | 全站迁移第八步(规范见 `docs/ui-hierarchy.md`)。新增共用的分段切换 `components/ui/segmented.ts`(外面一圈描边, 选中那格反相, 总高 32px, 与个股弹窗「日 K / 分时 / 关键价位」同一个样子)。选股页头: 「股票 / ETF」「全部 / 日线 / 分钟」「隐藏 / 紧凑 / 标准 / 详细」三组换成它(最后一组原来 10px), 选中从强调色换成反相; 重载、全部个股开关、策略池换成全站按钮; 「叠加策略」「创建策略 · AI」原来各带一层青 / 琥珀色底, 那是装饰, 统一成描边按钮; 策略池计数角标 11px。结果区标题走 L3。策略卡、筛选、结果表以及一整套弹窗(策略池、策略设置、策略构建、叠加策略、默认参数、策略商店)共 181 处写死字号按角色落档; 弹窗标题升到 L2, 弹窗里的小节标题(子策略与权重、自定义策略代码)走 L3; 共用弹窗外壳 `SettingsModal` 的标题统一升到 L2(大盘首次使用弹窗等一起变)。棘轮 任意字号与硬编码色下调到当前数 | `frontend/src/pages/Screener.tsx`、`frontend/src/components/screener/*`、`frontend/src/components/ui/{segmented,index}.ts`、`frontend/src/components/data/SettingsModal.tsx`、`docs/ui-hierarchy.md`、`backend/tests/test_ui_hierarchy.py`、`backend/tests/test_design_spec.py` | 中(`Screener.tsx` 与策略弹窗与上游同源, 上游改这些文件时字号类会冲突, 以本 fork 的档位为准) | 回退本提交即回到原样式 |
