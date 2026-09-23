# R472 — 斐波那契Ⅱ型换深紫; 新头部加回刷新

| # | 改动 | 涉及文件 | 冲突风险 | 单独回退 |
|---|---|---|---|---|
| R472 | 两件。一: 用户「斐波那契二型用深紫色」—— 组色(= 回踩位角色键)由深青 #115E59 / #0F766E 换成深紫 #7B07CE / #724EA0(色相都约 302°, 离禁粉的 315° 留出余量; 暗色饱和度压低是为了与作者枢轴点的紫拉开); 后端 dinapoli.C_RETR 与前端 FIB2_ROLE_RETRACE 同步改(两边是逐字对齐的角色键), 旧键 #115E59 进 FIB2_ROLE_RETIRED, 缓存里的旧响应照样画成新色; 其余自定色、推算位、作废线不动, R443 那组「深 / 不粉 / 分得开」守卫全过。二: 用户指着量化MACD 副图上「稍后点右上角刷新重试」: 「刷新按钮没有了, 加回来」—— 刷新原来只在旧顶栏, 旧顶栏自 R432 起排在新块后面, 右上角看不见; 新头部右侧加一个方形刷新钮, 接的就是弹窗那一个 handleRefresh; 同时修掉它的一个漏洞: 关键价位视图下只重取 K 线 / 价位 / 趋势, 没有重取量化MACD, 那句「点右上角刷新重试」点了也不会重取, 现在一并失效 stockQuantMacd。守卫: test_R472_斐波那契二型是深紫、test_R472_新头部有刷新_与旧顶栏是同一个函数(已做变异验证: 删掉量化MACD 那一行会红) | frontend/src/lib/theme.ts; backend/app/indicators/dinapoli.py; frontend/src/components/stock-preview/PreviewHero.tsx; frontend/src/components/StockPreviewDialog.tsx; backend/tests/test_level_palette.py; backend/tests/test_preview_hero.py | 低: 配色只动一组的两个值与一个后端常量; 头部多一个可选按钮 | 可以: git revert 本提交(配色与按钮互不依赖, 也可只撤其一) |
