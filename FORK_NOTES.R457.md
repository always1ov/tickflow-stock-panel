# R457 — 全站迁移 · 市场环境

| # | 改动 | 涉及文件 | 冲突风险 | 单独回退 |
|---|------|---------|:---:|---------|
| R457 | 全站迁移第九步(规范见 `docs/ui-hierarchy.md`)。市场环境: 卡片标题 13px → L3(15px), 标题前的装饰小竖条撤掉; 卡片外框「半透明底 + 投影 + 毛玻璃 + 悬停加投影」换成实边框实底; 时间范围(1年 / 2年 / 全部 / 自定义)、视图(市场环境 / 情绪周期)、主线(概念 / 行业)三组切换换成全站分段切换, 选中从强调色实底换成反相; 重算换成全站按钮; 页内 57 处与跷跷板面板 19 处写死字号按角色落档。R401 那三条窄屏守卫(定高药丸的字不许断 / 药丸组不许被挤扁 / 区块标题不许被腰斩)规矩不变, 改成认新写法: 药丸是 `cn(SEG_ITEM, …)` 且带不换行、外框是全站 `SEG`(自带 shrink-0)且所在行可换行、标题走 `TYPE.card` 且带不换行与 shrink-0; 变异 2/2 杀死。棘轮 任意字号下调到当前数 | `frontend/src/pages/Regime.tsx`、`frontend/src/components/regime/SeesawPanel.tsx`、`backend/tests/test_regime_mobile_text.py`、`docs/ui-hierarchy.md`、`backend/tests/test_ui_hierarchy.py`、`backend/tests/test_design_spec.py` | 中(`Regime.tsx` 与上游同源, 上游改这一页时字号 / 切换样式会冲突, 以本 fork 的档位为准) | 回退本提交即回到原样式 |
