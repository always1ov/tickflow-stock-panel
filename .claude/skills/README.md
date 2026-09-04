# Agent skills (vendored)

这些技能来自 **[mattpocock/skills](https://github.com/mattpocock/skills)** —— Matt Pocock 的
"Skills For Real Engineers"，MIT 许可证（见同目录 `LICENSE`，版权声明按许可要求保留）。

- **来源版本**: plugin `mattpocock-skills` v1.2.3，commit `6654f6b`
- **取哪些**: 作者 `.claude-plugin/plugin.json` 里声明的那 **25 个**（engineering 18 + productivity 7）
- **不取哪些**: `skills/deprecated`（作者已弃用）、`skills/in-progress`（作者标注未完成）、
  `skills/misc`（`migrate-to-shoehorn` / `scaffold-exercises` 是 TypeScript 课程专用，
  `setup-pre-commit` 是 Husky+lint-staged 那一套，与本仓库 pnpm + pytest 的实际流程不符）

## 为什么是「抄进仓库」而不是装插件

作者给了两条路：Claude Code 插件（托管、只读、自动更新）和把文件抄进仓库（自己拥有、可改）。
这里选后者，因为本仓库是 fork，工作方式有自己的硬约束（见 `AGENTS.md` 的 `## Fork 硬约束`），
技能文本需要能被就地改写以适配；而且抄进仓库后**任何一台机器、任何一个会话打开就有**，
不依赖各自装没装插件。

## 目录布局

作者仓库里按 `skills/<category>/<name>/` 分类存放；这里**扁平**成 `.claude/skills/<name>/`，
与每个 `SKILL.md` frontmatter 里的 `name` 一致。已核对：这 25 个 SKILL.md 之间
**没有跨目录相对引用**（无 `../` 路径），扁平化不会打断任何链接。

## 怎么更新

```bash
git clone --depth 1 https://github.com/mattpocock/skills.git /tmp/mp-skills
# 对照 /tmp/mp-skills/.claude-plugin/plugin.json 的 skills 列表逐个 diff
diff -ru .claude/skills/tdd /tmp/mp-skills/skills/engineering/tdd
```

更新前先看 `CHANGELOG.md`。**本地若改过某个技能，diff 会告诉你改在哪** —— 这正是选择
"抄进仓库"而非装插件的代价与好处：不会被上游悄悄覆盖，但也不会自动跟进。
更新完在 `FORK_NOTES.md` 记一行（版本号 + commit）。
