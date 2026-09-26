# R527 — 决策台「持仓」格: 成本输入框撤掉, 持有 / 空仓同一个位置

| # | 改动 | 涉及文件 | 冲突风险 | 单独回退 |
|---|---|---|---|---|
| R527 | 用户(看过 R526 手机图):「我觉得不需要成本这一列的, 然后持仓和空仓应该是在同一个位置」。① 持有行旁边那个「成本」输入框撤掉 —— 成本改由「持仓提醒」页的批次提供(数量加权均价); 已经手填过的成本还在 positions 里, 切换持有 / 空仓时原样带着(cost: manualCost), 出场线照旧按它算。属「隐藏」不属「撤下」: 后端 PUT /api/watchlist/positions/{symbol} 仍收 cost, 登记进 docs/hidden-features.md「一、隐藏」并加 STILL_THERE 锚点。② 持有 / 空仓用同一颗 xs 按钮的几何(h-7), 只差亮不亮: 持有是反相实底, 空仓是 ghost 灰字(R520「空仓不是按钮」的立论没变 —— 没边框、压暗, 只是与持有等高等宽, 一列扫下去两种行的那颗落在同一个 x)。③ 手机: 「持仓」格与它的壳都 display:contents, 那颗按钮排在价格后面(order-3), 持有行才有的批次链接 / 出场线落到最后一行(order-5); 没了输入框, 持有行的第一行不再换行, 与空仓行排得一样。宽屏只少了个输入框, 其余一个像素没动 | frontend/src/components/stock-analysis/WatchlistDecisionBoard.tsx; docs/hidden-features.md; backend/tests/test_hidden_features_registry.py; backend/tests/test_board_mobile_stack_r526.py; backend/tests/test_stock_analysis_r520.py | 低: 决策台是 fork 自己的 | 可以: git revert 本提交(输入框: git show 5a19c723:… 搜 type="number") |
