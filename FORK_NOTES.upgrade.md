# 上游同步升级台账（v0.3.2 → v0.3.37）

| R | 版本 | 日期 | 合成锚点 | 冲突 | 红线冲突 | 裁决要点 | 门禁 | 回滚 |
|---|---|---|---|---|---|---|---|---|
| R566 | v0.3.4 | 2026-11-13 | sync/upstream-v0.3.3-tree | 8（C0 7 / C1 1） | 0 | 安装包跟随上游改名为 `packaging/tsp.iss`/`tsp.spec`，内容保留「牛来」品牌与 `TickFlowStockPanel.exe`；`api.ts` 合并上游 `pipelineAdjFactorRun` 与本地 `pipelineJob(quiet)`；`Data.tsx`、`desktop.py` 取上游写法；`package.json` 版本 0.3.4 | 前端 build 4.41s、vitest 208 通过；后端 5070 通过 / 3 失败 → 修 `data_doctor` 的 `package.json` 登记后剩 2 项 UI 字号守卫，按用户裁决「升级期豁免」；ruff 3556 无新增 | `git reset --hard fork-pre-v0.3.4` |
| R567 | v0.3.5 | 2026-11-13 | sync/upstream-v0.3.4-tree | 3（均为版本号） | 0 | `backend/pyproject.toml`、`frontend/package.json`、`pnpm-lock.yaml` 整体取上游；前端 build 脚本回落上游（去掉本地 compress-dist 串联），依赖跟随上游 | 前端 build 4.52s、vitest 216 通过；后端 5082 通过 / 2 项豁免守卫 | `git reset --hard fork-pre-v0.3.5` |
| R568 | v0.3.6 | 2026-11-13 | sync/upstream-v0.3.6-tree | 68（C0 42 / C1 26） | 3（涨跌停递延 2 + 内置策略数 1） | ①采用上游「策略与信号全面去内置化」，补回 v0.3.5 静默缺失的 25 个上游文件，并新增行为对照门禁；②`backtest/engine.py` 直接取上游（收盘封死跌停递延修复，fork 无自有改动）；`strategy.py` 恢复「移动止盈回撤 > 激活涨幅」显式报错（不再静默 min 钳制）；③`api/paper.py` 保留 fork 的 R562 自动跟单，补入上游 arena 批量创建与 compare 增量字段；④`custom/assistant/*` 与 `services/ai_provider.py` 保留 fork 多档兜底/多模态，仅补 Gemini thought_signature 回传；⑤`custom/config.py` 补 `full_minute` 数据集；⑥信号页取上游新版，R542 分栏因「内置信号」清单消失而退场，保留「无宽度上限/卡片不套卡/条件一行流/启用色走令牌」四条；⑦批次登记页改为扩展页 `/lots`，同步改 `hidden-features.md` 与守卫锚点；⑧`Analysis.tsx` 去掉上游新增的紫色径向渐变面板 | 前端 build 6.13s、vitest 257 通过；后端 5272 通过 / 13 项失败=已裁决豁免的 UI 字号守卫（`test_ui_hierarchy` 9 + `test_design_spec` 4），`test_scoring_frozen` 通过；`test_openapi_contract` 已登记 `POST /api/paper/arena/batch_create` | `git reset --hard fork-pre-v0.3.6` |

## 待办登记

- `test_design_spec`（写死字号 42→49）、`test_ui_hierarchy`（`Data.tsx` 的 `text-[10px]`）：用户裁决升级期豁免，升级完成后统一恢复。
- v0.3.6 起豁免范围扩大：`test_ui_hierarchy` 9 个迁移文件（`SignalPicker`、`Screener`、`StrategySettingsDialog`、`Data`、`StrategyBacktest`、`analysis-shared`、`ext-data/ExtDataPullPanel`、`signals/extension`、`signals/CustomSignalDialog`）与 `test_design_spec` 4 条计数守卫；上游新页面直接写死字号，合并时整页取上游所致。
- **v0.3.6 产品影响待裁决**：上游「策略全面去内置化」后 `backend/app/strategy/builtin/` 只剩 fork 自有的 `factor_rank_research`、`keltner_reversion`；作者 25 个内置策略只存在于 `backend/tests/fixtures/strategies/`（测试用）。全新安装或升级后策略列表会变空，需决定是否加 fork 一次性种子。
- 上游 v0.3.4 起产品名与安装包改叫 TSP；本仓保留「牛来」品牌，因此这三个打包文件每次同步都需要重放品牌字段。
