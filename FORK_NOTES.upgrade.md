# 上游同步升级台账（v0.3.2 → v0.3.37）

| R | 版本 | 日期 | 合成锚点 | 冲突 | 红线冲突 | 裁决要点 | 门禁 | 回滚 |
|---|---|---|---|---|---|---|---|---|
| R566 | v0.3.4 | 2026-11-13 | sync/upstream-v0.3.3-tree | 8（C0 7 / C1 1） | 0 | 安装包跟随上游改名为 `packaging/tsp.iss`/`tsp.spec`，内容保留「牛来」品牌与 `TickFlowStockPanel.exe`；`api.ts` 合并上游 `pipelineAdjFactorRun` 与本地 `pipelineJob(quiet)`；`Data.tsx`、`desktop.py` 取上游写法；`package.json` 版本 0.3.4 | 前端 build 4.41s、vitest 208 通过；后端 5070 通过 / 3 失败 → 修 `data_doctor` 的 `package.json` 登记后剩 2 项 UI 字号守卫，按用户裁决「升级期豁免」；ruff 3556 无新增 | `git reset --hard fork-pre-v0.3.4` |
| R567 | v0.3.5 | 2026-11-13 | sync/upstream-v0.3.4-tree | 3（均为版本号） | 0 | `backend/pyproject.toml`、`frontend/package.json`、`pnpm-lock.yaml` 整体取上游；前端 build 脚本回落上游（去掉本地 compress-dist 串联），依赖跟随上游 | 前端 build 4.52s、vitest 216 通过；后端 5082 通过 / 2 项豁免守卫 | `git reset --hard fork-pre-v0.3.5` |

## 待办登记

- `test_design_spec`（写死字号 42→49）、`test_ui_hierarchy`（`Data.tsx` 的 `text-[10px]`）：用户裁决升级期豁免，升级完成后统一恢复。
- 上游 v0.3.4 起产品名与安装包改叫 TSP；本仓保留「牛来」品牌，因此这三个打包文件每次同步都需要重放品牌字段。
