# R446 — 斐波那契一型 / 二型改叫 Ⅰ型 / Ⅱ型

| # | 改动 | 涉及文件 | 冲突风险 | 单独回退 |
|---|------|---------|:---:|---------|
| R446 | 用户: 「斐波那契一型二型换成罗马数字」。界面上读得到的四处全改: 关键价位开关「斐波那契一型 / 二型」→「斐波那契Ⅰ型 / Ⅱ型」(前端 LEVEL_GROUPS 与后端 `levels.py` 的 LEVEL_TYPES 两处组名)、曲线末端标签「二型均线」→「Ⅱ型均线」(含未来段那条)、发给 AI 的粗细回测提示里「斐波那契二型的回踩位」。用的是罗马数字字符 Ⅰ(U+2160) / Ⅱ(U+2161)。注释与 docstring 里的一型 / 二型不动(守卫只扫渲染文本; 注释里复述旧说法是允许的)。名词表: 「近 120 日单波段」那一行正名改成「斐波那契Ⅰ型」, 别名正则改成只放过罗马数字 `斐波那契(?![ⅠⅡ]型)` —— 旧名与光秃秃的「斐波那契」都被它抓; 另登「斐波那契Ⅱ型」「Ⅱ型均线」两行; `test_R404_正则别名这一路真的在查` 的两个探针正则跟着换; 一个 vitest 的 describe 标题同步改名(守卫也扫它)。变异 5/5 杀死(开关名改回一型 / 二型、曲线标签改回、后端组名改回、写成阿拉伯数字) | `frontend/src/components/stock-analysis/AnalysisKChart.tsx`、`frontend/src/lib/futureZone.test.ts`、`backend/app/indicators/levels.py`、`backend/app/services/fib2_grain_service.py`、`backend/tests/test_terminology.py` | 中(`levels.py` 的 LEVEL_TYPES 与上游同源; 上游若改这两个组名, 合并时以 Ⅰ / Ⅱ 为准) | 回退本提交即改回一型 / 二型 |
