# Agent skills (vendored)

本目录里的技能来自**两个上游**，都是 MIT 许可证，版权声明按许可要求原样保留：

| 来源 | 取了几个 | 许可证文件 |
|---|---|---|
| **[mattpocock/skills](https://github.com/mattpocock/skills)** —— "Skills For Real Engineers" | 25 | `LICENSE.mattpocock` |
| **[emilkowalski/skills](https://github.com/emilkowalski/skills)** —— Emil Kowalski 的设计工程/动效那一套 | 2 | `LICENSE.emilkowalski` |

## 来源一：mattpocock/skills

- **来源版本**: plugin `mattpocock-skills` v1.2.3，commit `6654f6b`
- **取哪些**: 作者 `.claude-plugin/plugin.json` 里声明的那 **25 个**（engineering 18 + productivity 7）
- **不取哪些**: `skills/deprecated`（作者已弃用）、`skills/in-progress`（作者标注未完成）、
  `skills/misc`（`migrate-to-shoehorn` / `scaffold-exercises` 是 TypeScript 课程专用，
  `setup-pre-commit` 是 Husky+lint-staged 那一套，与本仓库 pnpm + pytest 的实际流程不符）

## 来源二：emilkowalski/skills

- **来源版本**: commit `d23d7f8`
- **取哪些**: 只取 **2 个** —— `emil-design-eng`（设计工程主技能：动效性能、时长、缓动、
  组件手感的硬规则）与 `review-animations`（动效评审，默认挑毛病，最后给 Block/Approve）
- **为什么只取这两个**: 本仓库是**键盘鼠标驱动的密集型看盘台**，不是消费级 App。
  上游另外 10 个里，`animate-expo` 是 React Native、`write-swift` 是 Swift、
  `ask-sonner` 是 Sonner（本仓库用的是作者自带 `Toast.tsx`）、
  `apple-design` 面向手势驱动的消费级界面（弹簧/惯性/速度接管，套到本项目只会拖慢操作）、
  `prototype` **与 mattpocock 那套里的 `prototype` 同名会冲突**且定位不同（Emil 那个偏
  视觉多方案，已有那个偏验证状态模型）、`animate` 与 `emil-design-eng` 重叠、
  `animation-vocabulary` 是给人看的词表不是给 agent 执行的。
  余下 `improve-animations` / `find-animation-opportunities` / `pick-ui-library`
  有价值但属于按需一次性使用，未纳入常驻。

## 为什么是「抄进仓库」而不是装插件

两位作者都给了两条路：Claude Code 插件（托管、只读、自动更新）和把文件抄进仓库（自己拥有、可改）。
这里选后者，因为本仓库是 fork，工作方式有自己的硬约束（见 `AGENTS.md` 的 `## Fork 硬约束`），
技能文本需要能被就地改写以适配；而且抄进仓库后**任何一台机器、任何一个会话打开就有**，
不依赖各自装没装插件。

## 目录布局

两个上游都按 `skills/<category>/<name>/` 或 `skills/<name>/` 存放；这里统一**扁平**成
`.claude/skills/<name>/`，与每个 `SKILL.md` frontmatter 里的 `name` 一致。已核对：
27 个 SKILL.md 之间**没有跨目录相对引用**（无 `../` 路径），扁平化不会打断任何链接；
`review-animations/STANDARDS.md` 是同目录引用，一并抄入。也已核对**两个来源之间没有重名**
（`prototype` 是唯一会撞的，已按上面的理由不取）。

## 怎么更新

```bash
git clone --depth 1 https://github.com/mattpocock/skills.git /tmp/mp-skills
# 对照 /tmp/mp-skills/.claude-plugin/plugin.json 的 skills 列表逐个 diff
diff -ru .claude/skills/tdd /tmp/mp-skills/skills/engineering/tdd

git clone --depth 1 https://github.com/emilkowalski/skills.git /tmp/ek-skills
diff -ru .claude/skills/emil-design-eng /tmp/ek-skills/skills/emil-design-eng
```

更新前先看上游的 `CHANGELOG.md`（如有）。**本地若改过某个技能，diff 会告诉你改在哪** ——
这正是选择"抄进仓库"而非装插件的代价与好处：不会被上游悄悄覆盖，但也不会自动跟进。
更新完在 `FORK_NOTES.md` 记一行（来源 + commit）。
