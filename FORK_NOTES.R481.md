# R481 — 逐日复盘脚注删掉指向已撤页面的半句

| # | 改动 | 涉及文件 | 冲突风险 | 单独回退 |
|---|---|---|---|---|
| R481 | 用户:「删掉这半句」—— 逐日复盘脚注里「要摊开每一档说了什么、之后走成什么样, 切到上方的『通道档位』那一页」。那一页 R444 随页签撤了, 旧顶栏 R479 也删了, 这半句指向一个找不到的地方。脚注只留「『通道档位』列悬停看完整卡片。」。StockReviewDialog.tsx 里的那一份同步删(旧复盘页已不在界面上, 但 R444 守卫要求新旧两份脚注逐字一样)。守卫 test_R481_脚注不再指向已经没了的通道档位那一页。(注: R480 号留给同时在做、尚未提交的斐波那契Ⅱ型 934.95 改动) | frontend/src/components/stock-preview/ReviewSection.tsx; frontend/src/components/stock-analysis/StockReviewDialog.tsx; backend/tests/test_review_section.py | 低 | 可以: git revert 本提交 |
