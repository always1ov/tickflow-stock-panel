# R373 — 菜单分组标签「盘面参考」→「闲置功能」

本条是 `FORK_NOTES.md` 的独立补充记录，沿用 R371/R372 的方式 —— 编辑器只能整文件替换，原总台账约 0.8 MB 不动。

| # | 改动 | 涉及文件 | 冲突风险 | 单独回退 |
|---|------|---------|:---:|---------|
| R373 | 菜单那个展示型分组的标签从「盘面参考」改成「闲置功能」；同步重写 hint(原 "看盘面用" 与新名字语义对不上)。**只动渲染文本**: 内部 id(`group:browse`)、常量名(`BROWSE_GROUP`)、变量名(`browseOpen` / `browsePaths` / `browseItems`)、localStorage key(`tf-nav-browse-open`)都保持不变 —— 那是用户的存储键, 改了会让所有已存的 `nav_order` 找不到这条。`backend/app/strategy/builtin/*.py` 没动；`opportunity_score.py` 等冻结文件没动；后端接口无变更 | `frontend/src/lib/navGroups.ts`、`frontend/src/components/Layout.tsx`、`frontend/src/pages/settings/MenuSettings.tsx`、`frontend/src/pages/settings/ExtPages.tsx`、`backend/tests/test_terminology.py`、本记录 | 低(纯渲染文本; 已存的菜单配置与折叠状态都不受影响) | 回退本次独立提交 |

## 改动一览

| 位置 | 原 | 新 |
|------|----|----|
| `navGroups.ts` `label` | `盘面参考` | `闲置功能` |
| `navGroups.ts` `hint` | `展示型: 看盘面用, 不产出候选也不影响仓位` | `闲置中, 不产出候选也不影响仓位` |
| `ExtPages.tsx` `<h2>` | 把一个外部网页变成「盘面参考」里的一页 | 把一个外部网页变成「闲置功能」里的一页 |
| `Layout.tsx` 4 处注释 | 「盘面参考」 | 「闲置功能」(R373 行内标注由 R67/「盘面参考」改来) |
| `MenuSettings.tsx` 1 处注释 | 「盘面参考」 | 「闲置功能」 |
| `navGroups.ts` 注释 | 「盘面参考」 | 「闲置功能」 |
| `backend/tests/test_terminology.py` `TERMS` | — | 新增 `("菜单里那个展示型分组的标签", "闲置功能", ("盘面参考",))` |

## 为什么这样切

- 用户原话「菜单的盘面参考改名成闲置功能」—— 范围明确是**菜单标签**, 不是分组本身。
- id / key / 变量名 是用户的存储键(`nav_order` 里写着 `group:browse`, 折叠状态写在 `tf-nav-browse-open`), 改了等于全量重置菜单位置, 而且没有任何收益。
- `hint` 顺手重写: 原措辞「看盘面用」与新标签「闲置功能」语义相反, 放在一起会让人困惑 —— 这是命名变了的自然延伸, 算同一次改名, 不另起 R 行。
- 注释里的旧名按 R279 的设计哲学可以保留作历史标注, 但这次直接换成新名字 —— 注释是给读代码的人看的, 当前概念已经改名, 让注释与现实同步; 历史锚点放在本文件与 R67 的原始台账里。

## 验证

- `backend/tests/test_terminology.py`: 新加 `TERMS` 行会扫前后端所有渲染文本, 旧名「盘面参考」现在唯一可能出现的合法位置只剩 docstring(守卫本就排除 docstring)。新增项成功守卫住后续改动。
- 守卫自检: 加完 TERMS 行跑一次, 预期只 `navGroups.ts` 注释里的旧名会失败 —— 已同步改成「闲置功能」。
- 前端 build: tsc + vite 不动结构, 仅文案与 hint, 预期无影响。