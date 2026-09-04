# Issue tracker: Local Markdown

本仓库的 issue / spec 以 markdown 文件形式存放在 `.scratch/`。

**为什么不是 GitHub Issues**：本 fork 有一条硬约束 —— **永不开 PR**（见 `AGENTS.md`
`## Fork 硬约束`），协作面只有作者本人一个人，GitHub 那套 issue/PR 流程在这里没有对象。
所有工作记录的权威位置是 `FORK_NOTES.md` 的 R 系列台账；`.scratch/` 只承载"还没做完、
需要跨会话接力"的中间产物。

## Conventions

- 一个特性一个目录：`.scratch/<feature-slug>/`
- spec 放在 `.scratch/<feature-slug>/spec.md`
- 实现工单一个文件一条：`.scratch/<feature-slug>/issues/<NN>-<slug>.md`，从 `01` 起编号，
  **不要**合成一个 tickets 大文件
- 三态记录在文件顶部的 `Status:` 行（角色字符串见 `triage-labels.md`）
- 评论与对话历史追加到文件底部 `## Comments` 标题之下

## 当某个技能说「发布到 issue tracker」

在 `.scratch/<feature-slug>/` 下新建文件（目录不存在就建）。

## 当某个技能说「取出相关工单」

读引用路径对应的文件。用户通常会直接给路径或编号。

## Wayfinding operations

`/wayfinder` 用。**map** 是一个文件，每条工单一个 **child** 文件。

- **Map**: `.scratch/<effort>/map.md`（Notes / Decisions-so-far / Fog 三段正文）
- **Child ticket**: `.scratch/<effort>/issues/NN-<slug>.md`，从 `01` 起编号，正文写问题。
  `Type:` 行记类型（`research`/`prototype`/`grilling`/`task`）；`Status:` 行记
  `claimed`/`resolved`
- **Blocking**: 顶部 `Blocked by: NN, NN` 行。它列的文件全部 `resolved` 才算解锁
- **Frontier**: 扫 `.scratch/<effort>/issues/`，找 open + 未阻塞 + 未认领的，编号最小的先做
- **Claim**: 动工前先把 `Status: claimed` 写盘
- **Resolve**: 答案追加到 `## Answer` 标题下，`Status: resolved`，再把一句话结论 + 链接
  追加到 `map.md` 的 Decisions-so-far

## 收尾

一件事做完落地到代码之后，**该记的是 `FORK_NOTES.md` 的 R 行**，`.scratch/` 里的中间
产物可以留着也可以删 —— 它不是权威记录。
