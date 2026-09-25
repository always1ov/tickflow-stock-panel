# R509 — 主题色去蓝: 强调色换成黑白灰

| # | 改动 | 涉及文件 | 冲突风险 | 单独回退 |
|---|---|---|---|---|
| R509 | 用户指着侧栏选中项(靛蓝底 + 靛蓝字)说「别搞蓝色主题, 就只用黑白」。强调色四个令牌整套换成中性: 亮色 --accent / --accent-text #4F5DE8 → #222222, --accent-hover #3E49CE → #3D3D3D, --accent-soft #EFF1FD → #EDEDED; 暗色 --accent / --accent-text 靛蓝 → #E4E4E4, --accent-hover → #F5F5F5(暗色里 hover 往亮走), --accent-soft → #2E2E2E。凡走这四个令牌的地方一起变: 侧栏选中项(浅灰底黑字 / 暗色深灰底白字)、主按钮(黑底白字 / 暗色浅灰底深字, 走 text-on-accent = --base 不用另配)、焦点环、页头与分区标题的图标高亮、分组条上的选中态、链接。刻意没动: 红涨绿跌与琥珀警示(数据语义不是主题)、文字三级、边框、背景(R501)、作者的黑(R163); 紫色(AI 相关徽标 / 品牌图标, 全站 48 处 purple 类)没被点名, 按第 15 条的口径没问过不扩大, 留给用户定。守卫: test_theme_palette 的 CHROME 表换成新 hex(oklch 反解逐值核对); R379「主题色不许落进涨跌色相带」与 R382「暗色主题色离涨跌足够远」两条对中性色(彩度 0, 没有色相)放行 —— 灰不可能被看成涨跌, 哪天换回有彩度的照旧生效; R382「两套主题同一个品牌色」改为「两边都中性也算同一个」, 一边中性一边有彩度才算两个品牌色; test_no_pink / test_level_palette / test_design_spec 照常通过; 亮暗两套各截自选页与 Minds 页核对过 | frontend/src/index.css; backend/tests/test_theme_palette.py | 低(只改 8 个颜色变量的值; 上游若改同一行会冲突, 保留本侧) | 可以: git revert 本提交 |
