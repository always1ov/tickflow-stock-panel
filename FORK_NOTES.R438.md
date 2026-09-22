# R438 — 现状块删掉「这一格历来」

| # | 改动 | 涉及文件 | 冲突风险 | 单独回退 |
|---|------|---------|:---:|---------|
| R438 | 用户看着现状块第一格「这一格历来(近 120 天) 5 段 · +1.6% 走完后 5 天 · 3/4 段走完后收涨」: 「这没用了, 删掉」。删掉 `StatusSection` 的 `HistoryCell` 及只给它用的 `Num`、`comboHistory` / `chgCls` 引用; 六态成了第一格, 去掉它前面的分隔竖线。`comboHistory` 本身不动(旧复盘页「现在」行还在用, 随旧部分统一删除时一起处理, ReviewSection 注释里记上「这一格历来不用再问去哪」)。守卫 `test_R438_现状里没有这一格历来`; 原来钉「这一格历来走 comboHistory」那条断言随之撤掉。变异 2/2 杀死(这一格历来回来 / 六态前又画竖线) | `frontend/src/components/stock-preview/StatusSection.tsx`、`frontend/src/components/stock-preview/ReviewSection.tsx`、`backend/tests/test_status_section.py` | 低(只在 fork 自己的新块里) | 回退本提交即恢复这一格 |
