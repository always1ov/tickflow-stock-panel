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

本仓库已装入 **[mattpocock/skills](https://github.com/mattpocock/skills)** 的 25 个稳定技能
（`.claude/skills/`，来源与更新方式见该目录 `README.md`）。**这是本仓库改动的默认工作方式**，
不是可选装饰 —— 动手前先想清楚这次属于哪一类，再走对应技能。

常见场景对应关系：

| 场景                       | 用哪个                              |
| -------------------------- | ----------------------------------- |
| 用户提了个需求，但没说透   | `/grill-me`（非代码）/ `/grill-with-docs`（同时产出 ADR 与术语） |
| 要写代码了                 | `/implement`；测试先行走 `/tdd`     |
| 改完自查                   | `/code-review`                      |
| 疑难 bug、性能回归         | `/diagnosing-bugs`                  |
| 同步上游时遇到冲突         | `/resolving-merge-conflicts`        |
| 要查证某件事的事实         | `/research`                         |
| 一次会话装不下的大工程     | `/wayfinder`                        |
| 会话要交接给下一个 agent   | `/handoff`                          |
| 不知道该用哪个             | `/ask-matt`                         |

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

