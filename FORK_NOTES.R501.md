# R501 — 日间主题背景换成参考图的中性白灰

| # | 改动 | 涉及文件 | 冲突风险 | 单独回退 |
|---|---|---|---|---|
| R501 | 用户给了四张白底宏观看板截图:「参考这个图片的风格, 日间主题就用这种颜色背景色」。从截图逐点取色: 页面 #FFFFFF / 侧栏 #FAFAFA / 侧栏选中 #F6F6F6 / 卡片 #FFFFFF / 卡片边框 #EEEEEE。只换背景这一层且改成中性灰(彩度 0, 参考图没有蓝调): --base #F6F7FB → #FFFFFF, --sidebar #FFFFFF → #FAFAFA(页底纯白之后白侧栏会与页面糊成一片, 参考图正是白页面 + 浅灰侧栏 + 竖线), --elevated 明度 0.91 不动只去掉蓝调(R408 为看得见压到这一档; hover 行多为 /40, 叠在白底上约 #F2F2F2, 与参考图选中档同量级); K 线信息条的亮色底跟着改成白。刻意没动: 边框(参考图 #EEEEEE 更淡, 但 R408 用户嫌颜色淡, 且页底与卡片都白之后卡片只剩边框分界)、文字三级、主题色、红涨绿跌与全部指标色、暗色主题。守卫: test_theme_palette 的 CHROME 表改为新值并加入 elevated, 新增 R501 一条(三档中性、侧栏比页底灰、次级面明度没被调浅、边框没跟着换淡); test_level_palette 的亮色页底改为 #FFFFFF(更亮, 价位线对比只升不降); 全量验证通过 | frontend/src/index.css; frontend/src/lib/theme.ts; backend/tests/test_theme_palette.py; backend/tests/test_level_palette.py | 低(只改三个颜色变量的值) | 可以: git revert 本提交 |
