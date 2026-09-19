# R375 — 同步上游 main 8 个 commit

| # | 改动 | 涉及文件 | 冲突风险 | 单独回退 |
|---|------|---------|:---:|---------|
| R375 | merge `origin/main` 同步作者 8 个基础设施 commit (AGENTS.md / Dockerfile / .dockerignore / docker.yml / pyproject.toml)。 | `AGENTS.md`、`.dockerignore`、`.github/workflows/docker.yml`、`Dockerfile`、`backend/pyproject.toml`、本记录 | 低 | merge commit `ec210a54` 直接 revert |

## 同步来源

`origin/main` 领先 `claude/upstream-clean` 8 个 commit, merge-base `ecfddb451`。8 个 commit 全部是基础设施 / CI / AGENTS 文档修复, 与 fork 增强 (R366~R374) 无重叠意图。

| sha | 标题 | 改的文件 |
|---|---|---|
| `d8ed2b5f` | docs(AGENTS): append snapshot/rules/changelog sections | `AGENTS.md` |
| `6b773535` | ci(dockerignore): exclude AGENTS.md from Docker context | `.dockerignore` |
| `48119982` | docs(AGENTS): log .dockerignore exclusion | `AGENTS.md` |
| `76fa3a2e` | fix(docker): place README in project root | `Dockerfile` |
| `2d7f6d8d` | fix(backend): pyproject readme → project-relative path | `backend/pyproject.toml` |
| `e2569027` | docs(AGENTS): log hatchling readme fix | `AGENTS.md` |
| `b0379f51` | fix(ci): GHCR_PAT instead of GITHUB_TOKEN | `.github/workflows/docker.yml` |
| `8176c60f` | docs(AGENTS): log GHCR_PAT secret | `AGENTS.md` |

## 冲突处理 (按 `/resolving-merge-conflicts` 技能)

3 个冲突文件, 2 个自动合并成功。

### `AGENTS.md` — 1 个 hunk, 手动解决

| 上半 (fork HEAD) | 下半 (origin/main) |
|---|---|
| `# AI 开发入口` + 提到 `secondary-development.md` + Agent skills + Fork 硬约束 1~14 条 | `# AI 开发入口` 简化版 + 当前项目快照 + 额外硬规则 + 变更日志 4 条 + 安全提示 |

**取舍：**
- 保留 fork 上半整段 —— Fork 硬约束 1~14 条 (`<!-- ↓↓↓ 以下为 fork 追加段落 -->` 标记以下) 是本 fork 的核心规矩, 不能丢。
- 删除 main 下半的 `# AI 开发入口` 重复段 —— fork 上半已有, 删去避免两份。
- 保留 main 下半的后续章节 —— 当前项目快照表 + 本仓库额外硬规则 (6 条 docker / CI / 安全约束) + 变更日志 (4 条作者提交记录) + 安全提示。这些是作者新章节, 与 fork 硬约束不冲突, 可共存。
- 衔接处补 `---` + `## 当前项目快照` 标题 (在 fork 上半结尾后, main 表格前)。

**已知注意：** fork 的 Fork 硬约束 #11 (镜像构建按 `docker-build-convention.md` 来) 与 main 的"额外硬规则 #1 (永远不要修改 Dockerfile —— 改动前必须与用户确认)"**并存不冲突** —— 前者是约定, 后者是流程。后续若用户觉得认知负担重可合并, 但本次不动。

### `.dockerignore` — 1 个 hunk, 取 fork 上半

| 上半 (fork HEAD) | 下半 (origin/main) |
|---|---|
| `gui-test-screenshots` / `assets` / `.claude` / `community-qr-code.jpg` / `AGENTS.md` / `FORK_NOTES.md` / `CONTEXT.md` / `CONTRIBUTING.md` / `操作说明书.md` | 仅 `AGENTS.md` |

**取舍：** fork 上半**已包含**作者想排除的 `AGENTS.md`, 多加了 fork 专属排除项。两者并集 = fork 上半, 取 fork 上半即可。无需重写。

### `backend/pyproject.toml` — 1 个 hunk, 取作者 (`origin/main`)

| 上半 (fork HEAD) | 下半 (origin/main) |
|---|---|
| (无 `readme` 字段) | `readme = "README.md"` |

**取舍：以作者为尊。** 这是反向冲突 —— fork `fe8cb2ee` 当时删 `readme` 是因为上游没有项目内 README, hatchling 报错指向仓库根外的路径。作者 `76fa3a2e` 在 `Dockerfile` 里加了 `COPY README.md ./README.md` 让项目内有 README, 现在 `pyproject.toml` 的 `readme = "README.md"` 重新有意义。两个 fix 互为补充, 保留两者。

### `Dockerfile` / `.github/workflows/docker.yml` — 自动合并成功

- `Dockerfile` 的 `COPY README.md ./README.md` 在 fork 上半本来就存在 (R213 全量落地时已加), 作者 `76fa3a2e` 加的是同一行同一位置, 自动合并无冲突。
- `docker.yml` 的 `password: ${{ secrets.GITHUB_TOKEN }}` → `password: ${{ secrets.GHCR_PAT }}` 在 fork 端没动过, 自动合并直接保留作者版本。

## 验证

| 检查 | 结果 |
|---|---|
| 三冻结区 (`backend/app/strategy/` / `opportunity_score.py` 等) `git diff` | 空 (未受影响) |
| 前端 `npm run build` (tsc + vite + compress) | 退出码 0, 6.21s |
| `docker.yml` 中 `password:` 行 | 两处均为 `GHCR_PAT` (line 64, 132) ✓ |
| `Dockerfile` 中 `COPY README.md ./README.md` | line 126 存在 ✓ |
| `pyproject.toml` 中 `readme = "README.md"` | 已加回 ✓ |
| conflict marker (`<<<<<<<` / `=======` / `>>>>>>>`) | 0 处残留 ✓ |
| 前端 UI / 数据契约 / 接口 / 依赖 | 未改 ✓ |

## 不动

- `backend/app/strategy/builtin/*` —— 第 3 条只读
- `opportunity_score.py` 及配套 —— 第 13 条冻结
- Fork 硬约束 1~14 条 / AGENTS.md 第 11~14 条 —— fork 增强, 不能丢
- `nav_order` / `tf-settings-nav-collapsed` 等用户存储 —— 本次未碰
- 已存过 `/lots` / `/paper-trading` / `/today` 等路由的重定向 —— 未碰

## 遗留

- AGENTS.md 现在存在**两套**硬约束:
  - fork 的 14 条 (`## Fork 硬约束`, 编号 1~14)
  - main 的 6 条 (`## 本仓库的额外硬规则`, 编号 1~6)
  - 两者**不冲突**, 但读起来像两个体系。后续若用户觉得认知负担重, 可以整理成一套。本次不擅自动 —— 同步原则是"以作者为尊, fork 增强一个不丢", 不是"强行统一表述"。

本记录沿用 R371/R372/R374 独立补充方式; 主 `FORK_NOTES.md` 保持原样, 不用片段覆盖历史。
