# R461 — 全站迁移 · AI 复盘

| # | 改动 | 涉及文件 | 冲突风险 | 单独回退 |
|---|------|---------|:---:|---------|
| R461 | 全站迁移第十三步(规范见 `docs/ui-hierarchy.md`)。AI 复盘页头那一排: 「板块 RPS 轮动」「刷新」「定时」原来 11px 小按钮(轮动还带一层琥珀底)换成全站按钮, 「定时」开着时反相; 「当日 / 连读昨日 / 近 7 日」换成全站分段切换; 「AI 打板复盘」去掉琥珀底; 「生成复盘」用主按钮。定时复盘弹窗标题升到 L2, 自动 / 手动推送的选中从强调色实底换成反相(推送渠道那几个勾选框保持强调色 —— 那是勾选框自己的样子)。打板复盘弹窗、板块轮动弹窗标题升到 L2, 轮动弹窗里维度 / 档位 / 翻转排序的选中换成反相。页内 75 处与两个弹窗 36 处写死字号按角色落档。棘轮 任意字号与硬编码色下调到当前数 | `frontend/src/pages/Review.tsx`、`frontend/src/components/{LadderAiReview,RpsRotationDialog}.tsx`、`frontend/src/components/financials/MarkdownRenderer.tsx`、`docs/ui-hierarchy.md`、`backend/tests/test_ui_hierarchy.py`、`backend/tests/test_design_spec.py` | 中(`Review.tsx` 与上游同源, 上游改这一页时字号 / 按钮样式会冲突, 以本 fork 的档位为准) | 回退本提交即回到原样式 |
