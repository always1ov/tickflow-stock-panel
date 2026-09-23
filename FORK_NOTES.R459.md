# R459 — 全站迁移 · 异动监控

| # | 改动 | 涉及文件 | 冲突风险 | 单独回退 |
|---|------|---------|:---:|---------|
| R459 | 全站迁移第十一步(规范见 `docs/ui-hierarchy.md`)。异动监控: 顶部页签(竞价 / 盘中 / 偏移)与板块切换(全板块 / 主板 / …)换成全站分段切换, 选中从强调色换成反相; 信号筛选胶囊(全部 / 涨停 / 炸板 …)11px → 全站按钮(32px 高、13px 字), 自带颜色的信号选中仍亮它的颜色, 其余选中反相; 规则说明、刷新、告警规则、监控开关换成全站按钮, 「开启实时计算」是主按钮; 两张表的表头换成浅灰实底条、去掉大写字距; 其余 44 处写死字号按角色落档。R402 那条窄屏守卫(分段控件不许被挤扁)规矩不变, 改成认新写法(外壳是全站 `SEG` 自带 shrink-0、按钮 `cn(SEG_ITEM, …)` 带不换行); 变异 1/1 杀死。棘轮 裸圆角、任意字号下调到当前数 | `frontend/src/pages/AbnormalMoves.tsx`、`backend/tests/test_mobile_text_and_scroll.py`、`docs/ui-hierarchy.md`、`backend/tests/test_ui_hierarchy.py`、`backend/tests/test_design_spec.py` | 中(`AbnormalMoves.tsx` 与上游同源, 上游改这一页时字号 / 切换样式会冲突, 以本 fork 的档位为准) | 回退本提交即回到原样式 |
