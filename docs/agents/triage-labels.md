# Triage Labels

技能层用五个标准 triage 角色说话。这张表把角色映射到本仓库实际使用的标签字符串。

本仓库的 issue tracker 是**本地 markdown**（见 `issue-tracker.md`），没有 GitHub 标签系统 ——
所以"打标签"在这里的落地方式是：把右列字符串写进 issue 文件顶部的 `Status:` 行。

| Label in mattpocock/skills | Label in our tracker | Meaning                        |
| -------------------------- | -------------------- | ------------------------------ |
| `needs-triage`             | `needs-triage`       | 还没评估，不知道要不要做       |
| `needs-info`               | `needs-info`         | 缺信息，等补充后才能继续       |
| `ready-for-agent`          | `ready-for-agent`    | 已说清楚，可以让 agent 直接做  |
| `ready-for-human`          | `ready-for-human`    | 需要人来做（部署、密钥、判断） |
| `wontfix`                  | `wontfix`            | 不做                           |

技能提到某个角色时（例如「打上 AFK-ready 的 triage 标签」），用本表右列的字符串。

右列可以随时改成你实际用的说法。
