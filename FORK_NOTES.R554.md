# R554 — 浏览器标签页: 图标改红、标题去掉英文

| # | 改动 | 涉及文件 | 冲突风险 | 单独回退 |
|---|---|---|---|---|
| R554 | 用户截图标签页「[紫色图标] 牛来 · Quant Terminal」: 「改成红色, 和删掉英文」。① 标签页标题 `牛来 · Quant Terminal` → `牛来`; ② 标签页图标 favicon.svg 的紫(#5B21B6)换成红涨 #D92D20(`--bull` 亮色值), 主屏图标四张 PNG(apple-touch-icon / icon-192 / icon-512 / icon-maskable-512)里的紫(#8B5CF6)逐像素换成同一个红, 透明度原样保留; ③ 顺带: 入口页 `theme-color` 也是紫(#8B5CF6, 手机浏览器地址栏的底色), 按硬约束第 15 条改为与 manifest 一致的 #0B0B0F。这几处紫一直没被 R514 的守卫抓到 —— 它只扫 src 下的 ts/tsx/css, public 与 index.html 在外面; 新守卫补上这几个文件。侧栏里的 logo 是 currentColor(跟正文色), 用户没点, 没动 | frontend/index.html; frontend/public/favicon.svg; frontend/public/apple-touch-icon.png; frontend/public/icon-192.png; frontend/public/icon-512.png; frontend/public/icon-maskable-512.png; backend/tests/test_brand_icon_r554.py | 低: 只动图标颜色与标题文字 | 可以: git revert 本提交 |
