# 隐藏与撤下的功能登记簿

用户：「要登记好哪些功能等于隐藏了，以后说不定用得上」（2026-09-24）。

**想找回某个功能，先查这里。** 每一条写清五件事：它是什么、为什么撤、现在还剩什么、怎么找回、出自哪一轮（R 行）。

分三类，找回的难度依次变大：

| 类 | 意思 | 找回要做什么 |
|---|---|---|
| 一、隐藏 | 后端还在算、接口还在，只是页面上没入口 | 只补前端 |
| 二、撤下 | 代码删了；有的存档还在磁盘上 | 从 git 取回代码（写了提交号） |
| 三、收起 | 功能完整，只是不在显眼处 | 知道去哪找就行 |

> 取回旧代码的通用写法：`git show <提交号>^:<文件路径>` 看删之前的版本，
> 或整轮回退 `git revert <提交号>`。提交号都在 `claude/upstream-clean` 上。
>
> 这份登记由 `backend/tests/test_hidden_features_registry.py` 守着：
> 「一、隐藏」里说「还在」的接口和字段真被删了，或者登记的存档不在数据体检的名单上，测试就会红。
> 提醒你把那一条挪到「二、撤下」。

---

## 一、隐藏：后端还在，页面没入口

| 功能 | 为什么撤 | 现在还剩什么 | 怎么找回 | 出处 |
|---|---|---|---|---|
| **情绪周期**（冰点 / 启动 / 主升 / 高潮 / 退潮 / 修复） | 全部由涨停梯队算出，衡量的是打板情绪；和综合分的「投机」维是同一批数；节奏比趋势持仓短。用户试用一段时间判定对自己没用 | 阶段照算（宏观分析「重算」里的 `refresh_phase_labels`）；接口 `GET /api/regime/phases`（阶段分段 + 各段主线）、`GET /api/regime/phase/live`（盘中临时阶段，需付费全市场档）；对话里 AI 助手的 `get_regime` 工具还读阶段 | 补回宏观分析页那一组：`git show 6011eedf^:frontend/src/pages/Regime.tsx`，搜「情绪周期」 | R506 |
| **主线排行**（区间内哪条主线持续最久）、**阶段 × 主线** | 随情绪周期一起撤；「当前主线」保留，搬进了宏观分析「现在」卡 | `GET /api/regime/mainline`（逐日排名 + 区间 leaders，可切概念 / 行业）、`POST /api/regime/mainline/recompute` | 同上，搜「主线排行」 | R506 |
| **状态分布饼图 / 状态时间轴 / 日历热力图 / 状态转换次数** | 后三块跟趋势图背景色带是同一份「每天哪一档」画了三遍；换档次数是纯统计 | `GET /api/regime/states`（作者的，状态分布）；另外三块是前端用 `GET /api/regime/history` 画的，数据全在 | `git show 983b641b^:frontend/src/pages/Regime.tsx` | R505 |
| **转折页「有信号但没做成」**（封板没买进 / 取不到日线 / 还在等成交） | 用户：「有信号没做成的就不要放出来了」 | 转折模拟盘接口照旧返回 `skipped` / `missing` / `pending`（封板顺延成交靠它们）；前端类型 `FlipSkipped` 还在 | `git show 1af6d7ea^:frontend/src/pages/FlipPaper.tsx`，搜 `function Skipped` | R499 |
| **今日总览没人显示的几块**：需要行动（`actions`）、持仓体检（`holdings`）、中观快照（`meso`：两市成交额分位、全市场涨跌家数）、仓位上限提示（`position_hint`）、组合（`portfolio`） | 今日总览页 R351 删了，内容逐块并进转折页；这几块没有并进去（R340 撤了需要行动与持仓体检；R506 把主线搬去了宏观分析） | `GET /api/today` 每次仍算并返回这几个字段 | 旧页面：`git show 4fdce3fe^:frontend/src/pages/Today.tsx`。其中**成交额分位和涨跌家数**跟宏观分析最相关，要接就接到「现在」卡 | R340 / R351 / R506 |
| **AI 导读 · 优选**（盘前导读正文 + 从候选里精选 1~3 只） | 用户：「这部分和 ai 导读都不用了」 | 接口 `POST /api/today/ai`（生成）、`GET /api/today/ai/track-record`（优选战绩）仍能用；存档 `user_data/today_ai.json`、`user_data/ai_pick_ledger.json` | 前端按钮与定时开关：`git show 8b224af3^`（`lib/api.ts` 的 `todayAi`、设置里的定时导读） | R352 |
| **批次登记页**（作者的真钱批次：成本 / 数量 / 止盈止损 / 到期提醒） | 模拟盘换成转折模拟盘后不在菜单里 | 路由 `/lots-registry` 能直接打开，代码一行没动；数据 `user_data/lots/` | 地址栏输入 `/lots-registry`，或在侧栏菜单里加回一行 | R327 |
| **模拟盘信号栏的「盯着」一段**(没拿着、离触发价 5% 以内还没转的票; 分离转多 / 离转空) | R515 先收成只列离转多 2% 以内的几只(用户: 「模拟盘的只需要展示最重要的, 像"盯着"这部分, 这么多没有精力看」), 再整段撤掉(「不要盯着」)。交易只在收盘转折那一刻发生, 还没转的票转了那天会出现在「要动手」里 | 接口 `GET /api/flip-paper` 的 `today` 照旧全发(`flip_today.evaluate` 的 watch 档) | 全列两组的版面: `git show 260c2ee1:frontend/src/pages/FlipPaper.tsx`, 看 `WatchGroup`; 只列快转多的版面: `git show 258c07a0:frontend/src/pages/FlipPaper.tsx` | R515 / R516 |
| **决策台「持仓」格的手填成本输入框**(持有那几行旁边那个「成本」框, 出场线按它算) | 用户:「不需要成本这一列」。成本改由「持仓提醒」页的批次提供(数量加权均价) | 后端 `PUT /api/watchlist/positions/{symbol}` 仍收 `cost`; 已经手填过的成本还在 `user_data/positions.json` 里, 出场线照旧按它算, 决策台切换持有 / 空仓时原样带着 | `git show 5a19c723:frontend/src/components/stock-analysis/WatchlistDecisionBoard.tsx`, 搜 `type="number"` | R527 |
| **开发者工具** | 调试用，从来不进菜单 | 路由 `/dev` | 地址栏输入 `/dev` | 作者原有 |

---

## 二、撤下：代码删了，存档还在或能从 git 取回

| 功能 | 为什么撤 | 磁盘上的存档 | 怎么找回 | 出处 |
|---|---|---|---|---|
| **AI 打板复盘**（连板梯队 → AI 出龙头 / 二进三 / 反包候选，可追问） | 打板是高频短线，和「少动」的纪律相反；用户要先把复盘页收干净再整改 | `user_data/ladder_ai_reports.json`（最近 30 份） | `git revert f3f937b2`（整轮接回，含下面两条）。**整改复盘页前先读** `.scratch/review-page-rework/issues/01-ladder-ai-and-friends.md`，逐项问用户 | R504 |
| **板块跷跷板**（一边熄火另一边点火的板块对，AI 甄别） | 唯一入口藏在打板复盘弹窗里，一起撤 | `user_data/seesaw_history.json` | 同上 | R504 |
| **复盘三模式**（当日 / 连读昨日 / 近 7 日） | 复盘页回到作者的样子 | 旧复盘存档里的 `mode` 字段还在，只是不显示 | 同上。「连读昨日」是唯一一个让复盘核对自己昨天说的话兑现没有的机制，值得单独考虑 | R504 |
| **情绪周期阶段切换推送**（「主升 → 退潮」，退潮 / 冰点按警告级别推） | 读起来像卖出理由，违反「趋势没坏就不给卖出理由」 | 无（阶段数据照算，见一） | `git show 6011eedf^:backend/app/jobs/daily_pipeline.py`，搜 `_push_phase_change_alert` | R506 |
| **AI 个股信号**（决策台那一列、定时个股信号） | 用户：「清除了 ai 信号这部分，后续我打算用斐波那契二型重做这部分，但现在不做」 | `user_data/signals.json` | `git show afdcf885^`（`services/stock_signal.py` 等）。**用户说过以后要用斐波那契二型重做**，重做时先看这里 | R435 |
| **关键价位上的「持仓止盈」那组线** | 用户：「持仓止盈可以删除掉了」 | 无；出场线判定本身（`position_exit.py`，含生命线）**没删**，六态与离场纪律照旧 | `git show 732085ec^`，关键价位图那一段 | R403 |
| **全球指数**（设置里的全球指数卡与轮询） | 用户：「删除这部分，不需要了」 | 无 | `git show 57ad11da^`（`services/global_indices.py`、`api/global_indices.py`） | R369 |
| **今日总览页** | 内容已逐块并进转折页，留着是两个入口说同一件事 | 后端接口还在（见一） | `git show 4fdce3fe^:frontend/src/pages/Today.tsx` | R351 |
| **AI 操盘手**（多个 AI 操作员拿虚拟资金每天自己买卖，两本账） | 换成只按六态转折买卖的转折模拟盘，里面没有 AI | `user_data/paper_traders.json`（旧账本） | `git show 2ca39afa^`（`services/paper_trader.py`、`api/paper_trading.py` 等） | R327 |
| **「怎么办」列**（五套判定收敛成一句话） | 用户看过影响清单后决定删 | 无 | `git show 547769f1^` | R310 |
| **决策台词汇表**（角上那个感叹号） | 用户：「删除掉感叹号」 | 无 | `git show 8b7925c9^:frontend/src/components/stock-analysis/decision-board/GlossaryDialog.tsx` | R259 |
| **策略页「策略体检」** | 用户：「策略体检删除掉，我不要了」 | 无 | `git show 627ea827^` | R176 |
| **自选页的三种视图**：卡片视图（大字价格 + 换手/量比/RSI）、分组卡片（每组前 N 名，可配指标/排序/条数）、分组统计条（各组涨跌横条图） | 同一份涨跌幅的三种画法；默认视图换成「按小分队」网格后重复 | 无（`watchlist_groupStats` 那条本地偏好不再读） | `git show 8d8ba655:frontend/src/components/WatchlistGroupCards.tsx`（R508 之前最后一个提交；另两个：`WatchlistGroupStatsBar.tsx`、`GroupStatsSettings.tsx`；卡片视图的 `StockCard` 在同一提交的 `pages/Watchlist.tsx` 里）。整轮回退：`git log --grep R508` 找到那个提交再 `git revert` | R508 |
| **决策台的四个筛选**(只看要动的 R178·R521 / 只看转折 R330 / 只看持有 / 只看哪个分组 R276, 含「筛掉了谁」的空表提示与定位时自动撤筛选) | 用户:「个股分析页面只显示那些我需要看的, 不然一大堆。自选页面里面才是一大堆, 当做个收藏夹」—— 这一页改成三段固定名单(今天要动的 / 持有·无事 / 计划中·贴轨), 其余票不再上桌, 筛选没有对象了 | 无(`board-group-filter`、`board-actionable-only` 两条本地偏好不再读) | `git show c0bda83b:frontend/src/components/stock-analysis/WatchlistDecisionBoard.tsx`(R530 之前最后一个提交), 搜 `actionableOnly` / `groupFilter`; 那一轮的守卫 `git show c0bda83b:backend/tests/test_board_group_filter.py` | R530 |
| **策略卡片的四档尺寸**(隐藏 / 紧凑 / 标准 / 详细, 标准与详细带一行描述) | 同一件事四种画法; 统一成一颗芯片(名字 · 命中数 · 失效数, 描述进悬停)后重复 | 无(`screener_card_size` 那条本地偏好不再读) | `git show f81e5d00:frontend/src/components/screener/StrategyCard.tsx`(R522 之前最后一个提交, `CARD_STYLES` 四档都在); 页头那组尺寸开关在同一提交的 `pages/Screener.tsx` | R522 |
| **因子页、回测页上 fork 加的东西**（因子 AI 解读 / AI 填表、研究工作流等） | 用户：两页「完全恢复成作者的样子」，作者的一切保留 | 无 | `git show 22333335^` | R174 |

---

## 三、收起：功能完整，只是不在显眼处

| 功能 | 在哪 | 出处 |
|---|---|---|
| 看板 / 连板梯队 / 概念分析 / 行业分析 | 侧栏「闲置功能」分组，默认折叠 | R57 / R64 |
| 板块 RPS 轮动 | 行业分析、概念分析两页页头的「涨幅RPS轮动分析」 | R504（从复盘页放回作者原来的位置） |
| AI 对话 | 左侧菜单 Minds →「对话」一栏；任何页面按 Ctrl+K 直达 | R502（原来是悬浮球 + 右侧抽屉） |
| 任何被隐藏的菜单项 | 设置 → 菜单，点眼睛图标 | 作者原有 |

---

## 往后怎么登记

撤下或隐藏一个**功能**（不是改一行文案），同一个提交里在这里加一行：

- 后端还留着 → 写进「一」，同时在 `test_hidden_features_registry.py` 的 `STILL_THERE` 里加一个锚点（接口路由或字段名），让「还在」一直是真的；
- 代码删了 → 写进「二」，带上提交号；
- 数据文件留在磁盘上 → 它必须还登记在数据体检（`services/data_doctor.py` 的 `STORES`）里，`note` 写明「功能已撤」，否则体检会把它当孤儿。
