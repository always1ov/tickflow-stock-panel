# 全站文字层级与样式(R449 起)

用户: 「全局都想要像弹窗这样大的字体和样式, 看着舒服」;「你要按照标题级别, 别无脑全部
一样, 样式是肯定要改的」;「全部都要」。

取值就是个股弹窗重做(R429~R448)那一套, 折到 R399 的字号刻度上。代码里的唯一产地是
`frontend/src/components/ui/`(`type.ts` / `SectionTitle.tsx` / `table.ts` / `Button.tsx` /
`Card.tsx`), 调用处不要再手写这些 class 串。

## 层级

| 级别 | 用在哪 | 字号 | 取法 |
|---|---|---|---|
| L1 页面标题 | 页头; 弹窗里的票名 | 21px 粗 | `PageHeader` / `TYPE.page` |
| L2 弹窗标题 | 普通弹窗的标题(比弹窗里的卡片、正文高一级; 个股弹窗那种整页大小的弹窗按页面算) | 18px 粗 | `TYPE.section` |
| L2 分区标题 | 一页里分几块时每块顶上那一行(标题 + 副标题 + 细线) | 18px 粗 | `<SectionTitle>` |
| L3 卡片标题 | 一张卡片自己的标题 | 15px 粗 | `TYPE.card` |
| 正文 | 正文、说明、按钮、表格内容 | 13px | `TYPE.body` / `text-xs` |
| 标签 | 表头、小标签、单位、徽标、角标 | 11px 灰 | `TYPE.label` / `text-micro` |
| 读数 | 一块里最重要的那个数(价格、状态) | 21px 粗 | `TYPE.reading` |

相邻两级至少差 2px, 否则肉眼分不出是两级。

## 样式

- **按钮**: `<Button>` / `buttonClass()`。默认 32px 高、13px 字、描边实底(小号 28px 高, 字仍是 13px —— 按钮一律正文级); 选中是黑白反相
  (亮色黑底白字、暗色白底黑字), 全站只有这一种选中态。
- **分段切换**(「股票 / ETF」「全部 / 日线 / 分钟」这一类): `segmented.ts` 的 `SEG` / `SEG_ITEM` / `SEG_ON` / `SEG_OFF`。
  外面一圈描边, 选中那一格反相, 总高 32px, 与旁边按钮齐平。
- **卡片**: `<Card>`。实边框、实底、6px 圆角、无投影。
- **表格**: `table.ts`。表头 11px 灰字浅灰底条, 内容 13px, 行间一道细线。
  **整页主列表**(自选、选股那张 `StockDataTable`)内容保持 15px —— 那是整页的主体, 本来就够大;
  表头照样落到 11px 灰字(R452 之前是 15px 中粗, 比内容还显眼)。

## 迁移规则(写死的字号按**角色**落档, 不是按数字一刀切)

| 原来 | 是什么 | 落到 |
|---|---|---|
| `text-[7~10.5px]` | 标签、表头、单位、徽标 | `text-micro`(11) |
| `text-[11~13px]` | 正文、表格内容、按钮 | `text-xs`(13) |
| `text-[11~13px]` | 表头、标签 | `text-micro`(11) |
| 手写的页标题 | | `PageHeader` |
| 手写的分区标题 | | `<SectionTitle>` |
| 与正文同字号的卡片标题 | 放大正文之后标题和正文一样大, 层级就塌了 | `TYPE.card`(15) |
| 手写按钮 class 串 | | `buttonClass()` |
| 各写各的选中色 | | `selected` |
| `text-micro`(R400 那一轮已经落到 11px 的) | 正文、控件、表格内容、说明段落 | `text-xs`(13) —— **不能只看写死的字号**, R400 迁过的页面(模拟盘等)正文挤在 11px, 要按角色逐处看 |

每迁完一个文件, 把它加进 `backend/tests/test_ui_hierarchy.py` 的 `MIGRATED`: 那里面的文件
**一处写死字号都不许再有**。`test_design_spec.py` 的棘轮跟着往下调。

## 页面清单(按使用频率)

旧个股弹窗里待删的那部分(旧顶栏以下、`StockReviewDialog`)不迁 —— 等「统一删除」。

- [x] 个股弹窗新块(R429~R448 已是这套; R449 修正分区 / 卡片标题的级别)
- [x] 外壳: 侧栏 / 导航(`Layout`)、`PageHeader`、`PageShell`
- [x] 自选决策台(`StockAnalysis` + `WatchlistDecisionBoard` + `decision-board/*`)
- [x] 自选(`Watchlist`)
- [x] 大盘(`Dashboard`)
- [x] 监控(`Monitor` + `monitor/RuleEditor`)
- [x] 模拟盘 / 批次(`FlipPaper` / `Lots`)
- [x] 选股(`Screener` + `screener/*`)
- [x] 市场环境(`Regime` + `regime/*`)
- [x] 指数(`Indices`)
- [x] 异动(`AbnormalMoves`)
- [x] 连板梯队(`LimitUpLadder`)
- [x] 复盘(`Review`)
- [x] 信号(`Signals` + `signals/*`)
- [ ] 概念 / 行业分析(`ConceptAnalysis` / `IndustryAnalysis`)
- [ ] 财务 / 数据 / 因子 / 回测(`Financials` / `Data` / `factors/*` / `backtest/*`)
- [ ] 设置(`Settings` + `settings/*`)
- [ ] 其余共用组件与弹窗
