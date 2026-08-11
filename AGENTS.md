# AI 开发入口

修改、调试或审查本仓库前，必须完整阅读并遵循根目录的 [`CONTRIBUTING.md`](CONTRIBUTING.md)。其中定义了项目架构、数据契约、数据源插件化、缓存与性能要求、测试矩阵以及 PR 复审和合并标准。

同时遵守以下规则：

- 先理解调用链和现有测试，再进行修改。
- 保持实现简单、改动范围最小，不处理无关问题。
- 不覆盖工作区已有修改，不虚构测试或审查结果。
- 以实际验证结果作为完成标准。

---

## 当前项目快照

| 项 | 值 |
|---|---|
| 镜像仓库 | `ghcr.io/always1ov/tickflow-stock-panel` |
| Tag 策略 | **只产 `:latest`**（不含 `:sha` / `:v*`） |
| 部署方式 | `docker-compose.yml` 拉取预构建 `:latest`，不本地 build |
| CI 工作流 | `.github/workflows/docker.yml`（push main 自动刷 latest，PR 仅构建不推，workflow_dispatch 手动兜底） |
| 多架构 | `linux/amd64` + `linux/arm64` |
| 环境变量 | 模板 `.env.example`，真实值在 `.env`（`.gitignore` 已排除） |
| 数据持久化 | `./data:/app/data`（`data/` 由 `.gitignore` 排除） |
| 上游 Dockerfile | 不改动（已支持多阶段 / CN 镜像 / Codex CLI 嵌入） |

## 本仓库的额外硬规则（本项目 AI 必读）

1. **永远不要修改 Dockerfile** —— 改动前必须与用户确认。
2. **永远不要在 compose / workflow / 配置文件中硬编码凭据** —— 一律走 `.env`。
3. **永远不要把 `.env` 或真实 key / token / PAT / 密码 提交进 git**。
4. **新增 tag / 镜像发布动作前先和用户确认** —— 当前策略是「只产 `:latest`」。
5. **PR 阶段不要 push 镜像** —— workflow 已有 `if push != PR` 判断，保持即可。
6. **本文件（`AGENTS.md`）是唯一可信的项目状态源** —— 新接手 AI 先通读「## 当前项目快照」「## 变更日志」再动手。

## 变更日志

每次对仓库的代码 / 工作流 / 部署配置 / CI 行为的改动，**追加一条记录**到本节末尾，**不要覆盖旧条目**。模板：

```markdown
### YYYY-MM-DD — <一句话标题>

**改动文件：**
- <文件路径> — <动作（新增 / 修改 / 删除）> — <一句话说明>

**关键决策：**
- <决策点 1>
- <决策点 2>

**已知注意事项 / 遗留：**
- <有则填>
```

### 2026-08-11 — 接入 CI/CD 与预构建镜像部署（AI 协作首版）

**改动文件：**
- 新增 `.github/workflows/docker.yml` —— 替换上游原 `docker.yml`，新策略「只产 `:latest`」、多架构
- 新增 `docker-compose.yml` —— 替换上游原 compose，改用预构建镜像，不本地 build，`pull_policy: always`
- 新增 `.env.example` —— 环境变量模板
- 新增 `.gitignore` —— 排除 `.env` / `data/`
- 修改 `AGENTS.md`（本文件）—— 在上游原内容后追加「当前项目快照 / 额外硬规则 / 变更日志」三节

**关键决策：**
- **只产 `:latest`**：用户明确要求「只拉取 latest」，registry 保持干净
- **多架构** `linux/amd64` + `linux/arm64`：覆盖 NAS / Mac M1 / x86 服务器
- **PR 仅构建不推**：防恶意 PR 污染 registry
- **凭据脱敏**：原 docker-compose.yml 硬编码 AI API key → 改为 `.env` 注入 + `.gitignore` 排除 `.env`
- **数据持久化**：仅挂载 `./data`，其他容器路径不外露
- **不使用 Codex CLI 模式**：compose 未挂载 Codex home，未设 `CODEX_DOCKER_HOST`
- **未挂载 `tiers.yaml`**：Dockerfile 已 `COPY tiers.yaml /app/tiers.yaml` 烤进镜像，`TIERS_YAML=/app/tiers.yaml` 写死
- **保留上游原 `AGENTS.md` 头部 11 行**：不覆盖上游「必读 `CONTRIBUTING.md`」的约定，仅在其后追加三节

**用户偏好（继承）：**
- Docker 部署只用预构建镜像，不本地构建
- 默认推送目标选 ghcr.io（免额外 secrets）
- 多架构覆盖（amd64 + arm64）
- PR 阶段只构建验证，不推送镜像

**已知注意事项 / 遗留：**
- ghcr.io 包默认私有，首次部署需在 GitHub 把包设为 Public（或本地 `docker login ghcr.io`）
- 用户曾在前轮 compose 草稿中明文暴露过 AI API key，已建议作废并重新签发
- **GitHub PAT 安全管理**：本轮用户向 AI 临时提供了一个 PAT 用于一次性写文件，AI 已声明**不持久化**该 PAT；后续如需自动化写回本文件，建议改用 GitHub App / `gh-actions` 短期 token 方案

### 2026-08-11 — 排除 AGENTS.md 出 Docker 构建上下文

**改动文件：**
- 修改 `.dockerignore` —— 在「文档 / 截图」节追加 `AGENTS.md`，分节注释更新为「文档 / 截图 / AI 协作元数据」

**关键决策：**
- AGENTS.md 是 AI 协作用的元数据文件（变更日志 / 接手说明），不属于运行时工件
- 不放入 `.gitignore`（仍需保留在 git 里供后续 AI 读取）
- 单独放入 `.dockerignore`（不进入 Docker 构建上下文）
- 用户原话："记录回写那个文档别一起构建，这是给ai看的，算是个多余的文件"

**已知注意事项 / 遗留：**
- 提交 `d8ed2b5` 触发的 build 因 `hatchling` 校验 `readme = "../README.md"` 越界而失败 —— 修复方案已提出（同时改 `backend/pyproject.toml` 的 `readme` 字段和 `Dockerfile` 的 `COPY README.md` 目标），**等待用户确认后推送**

### 2026-08-11 — 修复 hatchling readme 路径越界导致构建失败

**改动文件：**
- `Dockerfile` —— `COPY README.md /README.md` 改为 `COPY README.md ./README.md`（让 README 落在 `/app/` 即项目根，与 pyproject.toml 同目录）
- `backend/pyproject.toml` —— `readme = "../README.md"` 改为 `readme = "README.md"`（hatchling 要求 readme 路径必须在项目目录内，不能用 `..` 跳出）

**关键决策：**
- 两个文件必须**同时**改：只改 pyproject 不改 Dockerfile → uv sync 时找不到 readme 文件；只改 Dockerfile 不改 pyproject → hatchling 校验仍然报错
- README 物理位置由 `/README.md`（项目外）改回 `/app/README.md`（项目内），回到 hatchling 期望的标准布局
- 用户决策授权："你决定" → 自主推进

**提交：**
- `76fa3a2` fix(docker): place README in project root so hatchling readme path resolves inside project dir
- `2d7f6d8` fix(backend): point pyproject readme to in-project README.md (hatchling requires project-relative path)

**验证状态：**
- 待触发新一轮 Actions build（任一 push 即触发）观察是否通过 `uv sync`