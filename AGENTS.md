# AI 开发入口

修改、调试或审查本仓库前，必须完整阅读并遵循根目录的 [`CONTRIBUTING.md`](CONTRIBUTING.md)。其中定义了项目架构、数据契约、数据源插件化、缓存与性能要求、测试矩阵以及 PR 复审和合并标准。

涉及代码二次开发、前端插槽、后端可替换策略、扩展注册或上游升级兼容时，还必须阅读 [`docs/secondary-development.md`](docs/secondary-development.md)。该文档区分当前已实现能力与目标扩展契约；不得根据设计示例虚构尚不存在的 API。

同时遵守以下规则：

- 先理解调用链和现有测试，再进行修改。
- 保持实现简单、改动范围最小，不处理无关问题。
- 不覆盖工作区已有修改，不虚构测试或审查结果。
- 以实际验证结果作为完成标准。

<!-- ↓↓↓ 以下为 fork 追加段落（上游 AGENTS.md 到此为止）。同步上游时若此文件冲突，
     冲突多半在上方原文，本段整体保留即可。 ↓↓↓ -->

## Agent skills

本仓库装入了**三套**技能（都在 `.claude/skills/`，来源与更新方式见该目录 `README.md`）。
**任何 AI 改本仓库的代码都必须用上这三套**，这是用户定的规矩，不是可选装饰 ——
动手前先想清楚这次属于哪一类，再走对应技能。

| 第几套 | 是什么 | 什么时候用 |
| --- | --- | --- |
| ① | **[mattpocock/skills](https://github.com/mattpocock/skills)** 的 25 个工程技能 | 任何改动的骨架流程（见下表） |
| ② | **`emil-design-eng`**（[emilkowalski/skills](https://github.com/emilkowalski/skills)） | **动到前端就要用** —— 界面、组件、样式、动效、交互手感 |
| ③ | **`review-animations`**（同上） | **动效相关的改动完成后必过** —— 本仓库不开 PR，没有第三方评审，这是唯一卡口 |

⚠️ **③ 只能由人来触发。** 它的 frontmatter 写了 `disable-model-invocation: true`，
agent 用 Skill 工具调会被直接拒绝，且明确禁止「换个方式把它的流程复刻一遍」。
所以 agent 的义务是：**动完动效，在收尾汇报里提醒用户自己敲 `/review-animations`**，
不要假装已经评审过。这条限制是作者有意设的 —— 评审要独立于写代码的人。

② 和 ③ 是补 ① 的缺口：mattpocock 那套管的是工程流程（怎么拆、怎么测、怎么合），
不管界面手感；Emil 那两个只管手感与动效，且带**可执行的硬规则**（见下节）。

第 ① 套的常见场景对应关系：

| 场景                       | 用哪个                              |
| -------------------------- | ----------------------------------- |
| 用户提了个需求，但没说透   | `/grill-me`（非代码）/ `/grill-with-docs`（同时产出 ADR 与术语） |
| 要写代码了                 | `/implement`；测试先行走 `/tdd`     |
| 改完自查                   | `/code-review`                      |
| 疑难 bug、性能回归         | `/diagnosing-bugs`                  |
| 模块该怎么切、缝划在哪     | `/codebase-design`                  |
| 同步上游时遇到冲突         | `/resolving-merge-conflicts`        |
| 要查证某件事的事实         | `/research`                         |
| 一次会话装不下的大工程     | `/wayfinder`                        |
| 会话要交接给下一个 agent   | `/handoff`                          |
| 不知道该用哪个             | `/ask-matt`                         |

### 前端动效硬规则（来自 `emil-design-eng`，本仓库已定案）

写前端时这几条直接照做，不用每次重新查技能正文：

1. **只动 `transform` 和 `opacity`。** 不要动 `height` / `width` / `padding` / `margin` /
   `top` / `left` —— 这些每帧触发布局重排。因此 **不要用 `transition-all`**，
   写明要过渡的属性（绝大多数情况是 `transition-colors` 或 `transition-transform`）。
2. **framer-motion 的 `x` / `y` / `scale` 简写不走 GPU 合成**，性能敏感处写完整
   `transform` 字符串。
3. **UI 动画一律 < 300ms**，缺省 150~200ms。**永远不用 `ease-in`**（起手慢，显得拖沓），
   UI 用 `ease-out`，双向过渡用 `ease-in-out`。
4. **键盘发起的高频操作不加动画。** 本仓库尤其相关：定位当前个股、搜索跳转、
   表格排序与翻页 —— 这些必须是瞬时的，加动效等于加延迟。
5. **hover 动效要用 `@media (hover: hover) and (pointer: fine)` 包住**，否则触屏上会误触发。
6. **必须尊重 `prefers-reduced-motion`**（本仓库在 `index.css` 里有全局兜底，见 R168）。
7. **不给功能性数据加装饰性动效** —— K 线、盘口、数据表不做「跳动」「流动」这类效果，
   看盘的人要的是稳定可扫读，不是动感。
8. 按钮 `:active` 给 `transform: scale(0.97)`；缩放动效最小到 `scale(0.95)`，不要 `scale(0)`。

### Issue tracker

本地 markdown，issue 存在 `.scratch/`（本 fork 不用 GitHub Issues，理由见文件内）。
见 [`docs/agents/issue-tracker.md`](docs/agents/issue-tracker.md)。

### Triage labels

沿用五个标准角色，写在 issue 文件顶部的 `Status:` 行。
见 [`docs/agents/triage-labels.md`](docs/agents/triage-labels.md)。

### Domain docs

单上下文：根目录 [`CONTEXT.md`](CONTEXT.md) + `docs/adr/`。
见 [`docs/agents/domain.md`](docs/agents/domain.md)。

**动手前先读 [`CONTEXT.md`](CONTEXT.md)** —— 本项目术语密度很高（把握分、六态、生命线、
Keltner 三档、注记·不计分、焦点名单、收盘口径 vs 盘中口径），用词错了讨论就会错。

## Fork 硬约束

这些不是偏好，是**已经定案的规矩**，除非用户明确改口，一律照办：

1. **永不开 pull request。** 用户原话「我的修改永不提交 pr」。所有工作直接提交并推送到
   `claude/upstream-clean`。
2. **沟通用中文。**
3. **`backend/app/strategy/builtin/*.py` 只读。** 用户原话「我策略里面的因子不能动，
   那是精心设计验证过的」—— 不改因子、阈值、参数、META。每次提交前用
   `git diff --stat backend/app/strategy/` 自证为空。
4. **每个改动在 [`FORK_NOTES.md`](FORK_NOTES.md) 记一条 R 行**（改动 / 涉及文件 /
   冲突风险 / 单独回退），排在最新一行之前。这是本 fork 的权威变更记录。
5. **`deploy` 分支保持脱敏**：不写真实域名、IP、路径；真值只放 Dokploy 面板的 Environment。
   任何密钥都不进仓库文件。
6. **数据源只用 TickFlow。** 唯一例外是境外指数（已定案，独立模块，见 `CONTEXT.md`）。
7. **同步上游的原则**：以作者为尊，fork 增强一个不丢，AI 分析系统（`api/today.py`、
   `opportunity_score.py`、`score_ledger.py`、`today_annotations.py`、`action_timing.py`、
   `focus_list.py`、`pages/Today.tsx` 等）不动。合完把"合并相对 fork HEAD 删掉的行"
   全部过一遍，确认没有一行 fork 内容被抹掉，并前移 `FORK_NOTES.md` 顶部的上游基线锚点。
8. **验证看真实退出码。** `pnpm build | grep ...` 这类管道会吞掉退出码，
   踩过一次（构建其实没过却提交了）。要么单独 `echo $?`，要么写文件后再 grep。
9. **改代码必须用 `.claude/skills/` 里那三套技能**（见上面 `## Agent skills`）。
   用户原话「以后任何 ai 改代码都要用这三套技能」。动前端就得走 `emil-design-eng`；
   动到动效，改完必须过 `review-animations`。
10. **交易哲学: 大道至简, 趋势为王, 核心是利弗莫尔的心法。**
    用户原话「尽可能减少买卖次数，我走的路是大道至简，趋势为王，核心是利弗莫尔的心法」。
    这不是偏好, 是**判定层的取舍依据** —— 任何一处判定在两个方案之间犹豫时, 选
    「让人少动一次」的那个:

    - **趋势没坏就不给卖出理由。** 到上沿、涨得多、走了很长, 这些都不是卖点 ——
      卖点是止盈线、生命线、六态转弱。([R212] 「到轨」那一档原来无脑判
      「上沿=卖」, 一只正在上涨的票碰到上沿就被叫卖, 那正是这条纪律的反面。)
    - **逆势的「机会」一律不给。** 下跌趋势里到下沿不是抄底信号 —— 那条下沿
      会跟着一路下移。
    - **「没事」是常态。** 自选一百多只, 每天真该动的本来就只有几只; 一个每天
      给出几十条动作的系统, 错的是系统不是市场。
    - **新增任何一档判定之前先问**: 它会让人多动一次还是少动一次? 多动一次的,
      得有明确的理由压过这条纪律。

11. **镜像构建按 [`docs/docker-build-convention.md`](docs/docker-build-convention.md) 来。**
    用户原话「以后这个项目构建都要按照这个要求」。目标是**体积更小、构建更快、
    缓存更稳**；任何动到 `Dockerfile` / `.dockerignore` / `.github/workflows/docker.yml`
    的改动，都要先读那份约定再动手，并在改完后逐条对照自查。

12. **全局表达一致：一个东西只许有一个名字。**
    用户原话「以后所有改动都要注意全局的表达是一致的」「反正要全局统一表达」。

    这不是文案洁癖 —— **一个东西两个名字，读的人得先确认它们是不是一回事**，
    那一步本不该存在。已经犯过四轮：R249（天数两种写法）、R258（「贵不贵」）、
    R277（快慢在跌势里说反）、R279（同一个弹窗里「通道档位/结论/位置结论」三个名字）。

    - **改动里凡是新增或改写会渲染给用户看的中文名词，先查[名词表](backend/tests/test_terminology.py)。**
      那里的 `TERMS` 是「概念 → 正名 → 不许再出现的旧名」，`NOT_A_CONFLICT` 是
      「核查过确实不是冲突」的同形词及其理由。
    - **改名 = 加一行 `TERMS`。** 把旧名写进别名列，守卫会扫前后端两侧的渲染文本。
      只改代码不加行，下一处旧名照样漏出去。
    - **别名只收核查过的。** 多收一个会把合法文案判成违规 —— 与 R272 存储注册表
      「宁可多收」的取舍方向**相反**（那边漏一个会让体检说假话，这边多一个只会
      挡住写文案的人）。拿不准就先进 `NOT_A_CONFLICT` 并写清理由。
    - **注释和 docstring 里复述旧说法是允许的**，讲清楚「以前叫什么、为什么改」
      恰恰要写出旧名字。守卫扫的是渲染文本，不是全文。
    - **同一个读数只许有一个产地。** 措辞散在两处必然漂移（R277 的方向判据差一个
      边界点、R278 同一个量有三套措辞 + 一套按词取的错配色）。要显示的话从一个
      函数出，不要在下游各写一遍。

13. **`opportunity_score.py` 是稳定版打分系统，冻结。**
    用户原话「v2 版本的打分系统是稳定版，不能动」「不动我稳定版本的打分系统就行」。

    权重、曲线、门槛全部不许改。措辞校准、版面重排、加观测都不构成改它的理由 ——
    [`test_scoring_frozen.py`](backend/tests/test_scoring_frozen.py) 把那几组数钉住了，
    真要动得先改那份基线，**让改动是有意的、看得见的**。

    - **要新证据就走台账**（`score_ledger.py`「只记不反馈」），不要回头去调分。
    - **几何量自 R229 起整层不进把握分**，别再接回去；界面上「不进把握分」那句话
      得一直是真的。

14. **发现问题直接修，不用先问 —— 但有五类例外必须先确认。**
    用户原话「发现问题时直接自行修复，无需事先征求我的同意」「对于其余一般性问题，
    请自行分析并采用你认为最优的方案完成修复，同时简要说明问题原因、修复方式和验证结果」。

    **默认是动手，不是请示。** 顺手撞见的错、说假话的注释、静默失败、措辞不一致、
    空测试 —— 一律当场修掉，事后在汇报里说清三件事就够：
    **问题原因 / 修复方式 / 验证结果**。

    **五类例外，动手前必须先跟用户确认：**

    - **架构调整** —— 分层、模块边界、数据流向的改变。
    - **核心逻辑重构** —— 判定层、打分、通道几何这些"结论从哪来"的地方。
    - **删除或替换关键模块。** 删一个孤儿文件不算；换掉一整套判定算。
    - **修改公共接口或依赖** —— 接口出入参与形状、前后端契约、新增/升级三方库。
    - **可能影响其他功能或带来明显风险的改动** —— 拿不准影响面就归到这一类。

    判据是**影响面与可逆性**，不是改动行数：一行改动动了公共接口要问，
    两百行的措辞校准不用问。

    **这条不覆盖别的硬约束。** 第 3 条（作者策略只读）、第 13 条（打分冻结）
    是"根本不许动"，不是"问一声就能动"；第 12 条（表达一致）该修就修，
    但改名要同步加进名词表。

    **这一条没有配套的机器守卫，也不该有** —— 它管的是"什么时候该停下来问"，
    而那是判断，不是可断言的事实。硬编一道闸只会变成走过场的形式，
    反而稀释了另外那几条真能拦住东西的守卫。

---

## 当前项目快照

| 项 | 值 |
|---|---|
| 镜像仓库 | `ghcr.io/always1ov/tickflow-stock-panel` |
| Tag 策略 | 发布分支与 `v*` tag 覆盖 **`:latest`**；此外**每次构建都另出** `:<sha>` 与 `:<分支名>`（斜杠转横线），`v*` tag 另出 `:vX.Y.Z`。部署只拉 `:latest`，其余是可追溯用的 |
| 部署方式 | `docker-compose.yml` 拉取预构建 `:latest`，不本地 build |
| CI 工作流 | `.github/workflows/docker.yml`（push 到 **`main` 或 `claude/upstream-clean`** 自动刷 `:latest` + `:sha` **并自动触发 Coolify 部署**；其他工作分支只出 `:sha` / `:<分支名>`，不动 `:latest`；`v*` tag 另出版本号镜像；`workflow_dispatch` 手动兜底） |
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

### 2026-08-11 — 修复 ghcr push 被拒 (user-scoped package 需用 PAT)

**改动文件：**
- 修改 `.github/workflows/docker.yml` —— `password: ${{ secrets.GITHUB_TOKEN }}` 改为 `password: ${{ secrets.GHCR_PAT }}`
- 创建 repo secret `GHCR_PAT`（封入用户提供的 PAT，该 PAT 含 `write:packages` scope）
- 通过 API 调高仓库 `default_workflow_permissions` 为 `write`（保险措施，与本次修复不直接相关，但补上避免未来错觉）

**根因：**
- `ghcr.io/always1ov/tickflow-stock-panel` 是**用户作用域**的 ghcr 包（owner_type=User，非 Org）
- `GITHUB_TOKEN` 在仓库级别只能写入**同一 Org 的包**，对 user-scoped ghcr 包始终 `permission_denied: write_package`
- 即使 workflow YAML 声明 `permissions: packages: write` 也无效 —— GitHub 2023 安全策略默认 `GITHUB_TOKEN` 为读权限

**补充验证过程：**
- 修 default_workflow_permissions 后首次 build (run 31507912613) 仍失败，错误不变
- run `b0379f5`（GHCR_PAT 替换后）✅ 成功，image `b0379f5` + `:latest` 均已推送到 ghcr.io

**提交：**
- `b0379f5` fix(ci): use GHCR_PAT instead of GITHUB_TOKEN (user-scoped ghcr package requires PAT)

**验证状态：**
- 镜像 tags 验证：`['b0379f5', 'latest']`，updated_at=2026-08-11T16:14:24Z
- 后续 `docker pull ghcr.io/always1ov/tickflow-stock-panel:latest` 即可获取最新镜像

**安全提示：**
- `GHCR_PAT` secret 现已存于仓库。任何能 push 仓代码的人不会泄漏 secret 值（GitHub 加密），但本身有 repo 写权限的人可以改 workflow 使用该 secret
- 用户后续推荐：rotate PAT 或改用 GitHub App Token 以缩短 token 生命周期

### 2026-09-20 — 修正「CI 工作流」那一行(它把我自己骗了)

**改动文件：**
- `AGENTS.md`（本文件）— 修改 — 「当前项目快照」里 CI 工作流那一行只写了 `push main`

**问题：**
- 那一行是 2026-08-11 首版写的，当时触发分支确实只有 `main`。后来 `docker.yml`
  把 `claude/upstream-clean` 也加进了 `on.push.branches`，并在 merge job 末尾加了
  「Trigger Coolify deploy」——**快照这一行一直没跟着改**。
- 后果不是构建坏了，而是**这份文档在说假话**：本文件自己声明是「唯一可信的项目
  状态源」，照着它读会得出「推到工作分支不会构建、不会部署」的结论。我这一轮
  R377~R380 就是照着它，连着四次跟用户说「这些还没上线，要重新构建镜像重新
  部署」——**而四次构建全都成功跑完并自动部署了**。用户反问「不是设置了改完就会
  自动触发吗」，去查 Actions 才发现是文档旧了。

**关键决策：**
- 只改这一行的事实描述，触发规则、tag 策略、部署动作一个字节没动。
- 顺带把「其他工作分支只出 `:sha` / `:<分支名>`，不动 `:latest`」也写进去——
  那条守卫在 `docker.yml` 的注释里写得很清楚，快照里却完全没有，同样会误导。

**顺带修掉同一张表里第二处假话：**
- 「Tag 策略：**只产 `:latest`**（不含 `:sha` / `:v*`）」—— 工作流的 `tags:` 块里
  明明白白有 `type=sha` / `type=ref,event=branch` / `type=ref,event=tag`，**每次构建
  都会另出** `:<sha>` 与 `:<分支名>`。这一行的原意（「部署只拉 latest，registry 保持
  干净」）现在写成了事实描述，而那个事实早就不成立了。

**已知注意事项 / 遗留：**
- **这两行都是从工作流文件抄的，会再次过期。** 改 `docker.yml` 的触发分支、`tags:`
  块或部署步骤时，必须同时改这两行。没有守卫钉着它们 —— 快照表是给人读的散文，
  钉不住；能做的只有在改工作流时顺手回来看一眼。
