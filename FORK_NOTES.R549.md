# R549 — 动效复审两条: 开关按压有过渡、数据源编辑器的开关不再嵌在行按钮里

| # | 改动 | 涉及文件 | 冲突风险 | 单独回退 |
|---|---|---|---|---|
| R549 | 用户对 R548 跑 `/review-animations` 复审(结论「通过」附两条), 用户「修」。① 共用开关轨道原来只过渡颜色, 全站按下规则(index.css `:active` → scale(0.97))给的缩放不在过渡属性里, 按下 / 松开都是瞬间跳变 → 轨道改为 `[transition:background-color_150ms_ease,transform_160ms_var(--ease-out-strong)]`(按压反馈 STANDARDS 100–160ms + 有力 ease-out; 按住期间全局规则把时长压到 120ms, 松开 160ms, 进快出稳); ② 数据源编辑器的数据集行: 开关嵌在整行 `<button>` 里(按钮套按钮不合法), 按下开关时祖先也进 `:active`, 整行跟着缩到 0.97 且瞬间跳 → 改成一行两个并排控件(行按钮切数据集, 开关管启用), 顺带删掉只为传事件存在的 Toggle 薄壳、给开关补读屏名。减少动态效果: 全局兜底照旧把 transform 移出过渡、取消按压缩放 | frontend/src/components/ui/Switch.tsx; frontend/src/pages/settings/DataSourceEditor.tsx; backend/tests/test_switch_r548.py | 低: 只动开关过渡与一处行结构 | 可以: git revert 本提交 |
