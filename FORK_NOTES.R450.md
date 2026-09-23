# R450 — 全站迁移 · 外壳(侧栏 / 导航)

| # | 改动 | 涉及文件 | 冲突风险 | 单独回退 |
|---|------|---------|:---:|---------|
| R450 | 全站迁移第二步(规范见 `docs/ui-hierarchy.md`, R449)。`Layout.tsx` 的 34 处写死字号按角色落档: 角标、计数、涨跌幅、单位、状态小字(9~10px)→ 标签级 11px; 侧栏子菜单、弹出菜单项、「AI 配置」行、提示文字、底部通知(11~12px)→ 正文级 13px; 主导航项本来就是 15px 不动。三处写死的琥珀色换成语义色 `warning`。`PageHeader`(页标题本来就是 L1 21px)与 `PageShell` 没有写死字号, 一并登记为已迁。截图核对侧栏宽度没被撑破。守卫: 三个文件进 `test_ui_hierarchy.py` 的 `MIGRATED`; 棘轮 任意字号 2266→2232、硬编码色 1022→1016 | `frontend/src/components/Layout.tsx`、`backend/tests/test_ui_hierarchy.py`、`backend/tests/test_design_spec.py`、`docs/ui-hierarchy.md` | 中(`Layout.tsx` 与上游同源, 上游改侧栏时这几处字号会冲突, 以本 fork 的档位为准) | 回退本提交即回到原字号 |
