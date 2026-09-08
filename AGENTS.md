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
10. **镜像构建按 [`docs/docker-build-convention.md`](docs/docker-build-convention.md) 来。**
    用户原话「以后这个项目构建都要按照这个要求」。目标是**体积更小、构建更快、
    缓存更稳**；任何动到 `Dockerfile` / `.dockerignore` / `.github/workflows/docker.yml`
    的改动，都要先读那份约定再动手，并在改完后逐条对照自查。

