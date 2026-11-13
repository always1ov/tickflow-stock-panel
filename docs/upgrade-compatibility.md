# 项目升级兼容规范（TSP · tickflow-stock-panel）

> **必读前置文档（MUST READ BEFORE ANY CHANGE）**
> 任何接手本项目的开发人员与 AI 工具，在修改代码、提交、升级或审查前，必须完整阅读本文件并遵循全部硬约束。本文件与 [`AGENTS.md`](../AGENTS.md)、[`CONTRIBUTING.md`](../CONTRIBUTING.md)、[`docs/secondary-development.md`](secondary-development.md) 共同构成项目核心文档体系；冲突时按 §0 的优先级裁决。

| 字段 | 值 |
|---|---|
| 文档版本 | v1.2 |
| 强制级别 | 必读（MUST） |
| 生效日期 | 2026-11-13 |
| 最近修订 | 2026-11-13（纳入 `docs/` 核心文档体系，补充必读声明与元数据） |
| 适用仓库 | `always1ov/tickflow-stock-panel`（fork）← `shy3130/tick-stock-panel`（上游） |
| 上游基线 | 以 `VERSION` 为准（当前 0.3.36），每次升级后同步更新 |
| 权威上游文档 | [`AGENTS.md`](../AGENTS.md)、[`CONTRIBUTING.md`](../CONTRIBUTING.md)、[`secondary-development.md`](secondary-development.md) |
| 变更记录 | 见 §12 修订记录 |
| 维护人 | always1ov |

**状态**：规范已定稿。本文档只定义规则与流程，**不包含任何代码改动**；待落地的工具在附录 D 标注「未实现」。

---

## 0. 定位与冲突处理优先级

本规范解决三个并存目标：

1. 上游官方版本的功能与特性**完整保留、不回退**；
2. fork 已有魔改功能在升级后**行为不变**；
3. 升级前后**性能不退化**，且全过程可复现、可验证、可回滚。

冲突时的裁决顺序（自上而下，高优先级压过低优先级）：

| 优先级 | 约束 | 来源 |
|---|---|---|
| 1 | 用户三条红线（评分选股、个股图表配置、价位指标阈值） | `AGENTS.md` 第 3/13 条 + 用户原话 |
| 2 | 上游官方功能不得丢失、不得回退 | 本规范 §1 I-1 |
| 3 | 重建阶段 UI 外观沿用作者版本；后续 UI 调整须用户明确立项，且不得破坏合并能力 | 用户 2026-11-13 决策（含修正） |
| 4 | fork 魔改功能行为不变 | 本规范 §7 Feature Manifest |
| 5 | 性能门禁 | 本规范 §5 |
| 6 | 实现便利性、代码美观 | 最低 |

文档分级：**必须 / 禁止** 为硬约束，违反即阻断；**建议** 为软约束，可不执行但需在升级记录中说明理由。

### 0.1 能力落点优先级

同一需求有多种实现方式时，按下列顺序选择，**前面的能用就不许用后面的**：

1. **Z1 配置/数据**：能用现有配置、策略文件、扩展数据完成；
2. **Z2 官方扩展点**：前端插槽/路由/导航注册、后端 `app.extensions` 注册器、`custom/`；
3. **Z4 独占模块 + Z3 单点接线**：新能力写成 Z4 文件，只在上游入口加一行注册；
4. **Z0 内最小接线（Z3）**：仅当确实没有官方扩展点；
5. **禁止**：改 Z0 非接线部分、改 Z5。

> 判定顺序不能反：先想「能不能注册」，再想「怎么接线」。直接改上游文件是最贵的选择。

---

## 1. 不可违反的不变量（Invariants）

| 编号 | 不变量 | 机器判据 |
|---|---|---|
| I-1 | 上游功能不可回退：不得删除上游文件、不得整文件替换上游实现、不得丢弃上游测试 | `git diff --diff-filter=D` 对上游文件为空；上游测试文件全部存在 |
| I-2 | UI 外观分阶段管理：重建期沿用上游原样、不移植 fork 设计系统；后续允许用户主导调整，但必须单独立项、登记并隔离，不得渗入 Z0 核心文件 | 重建期：UI 归属路径 diff 为空；调整期：独立提交 + R 行 + 还原点 |
| I-3 | 红线区域只读（Z5） | §3 自证命令输出为空 |
| I-4 | 一次升级只处理一个上游 Tag；一次提交只表达一个目的 | 提交信息 + 变更范围检查 |
| I-5 | 每个变化可单独回退 | 每条 R 行含回退命令；每批独立提交 |
| I-6 | 每个 fork 功能都有验证方式 | Feature Manifest 无「无验证」项 |
| I-7 | 性能必须同机、同数据、同参数、前后对比 | §5 基准记录齐全 |
| I-8 | 程序与用户数据分离：升级不得改写 `data/`、用户配置、扩展包 | `git status` 与升级 diff 不含 `data/` |
| I-9 | 未运行的验证必须标注「未运行」，不得虚构结论 | 升级报告字段完整 |
| I-10 | 一个概念一个名字 | `backend/tests/test_terminology.py`（fork 守卫，随重建批次恢复） |
| I-11 | 上游单向只读：永远不向上游提交 PR、issue、评论、建议、补丁或任何形式的贡献 | 无 upstream 推送记录；`upstream` 的 push URL 置为不可用 |
| I-12 | 升级窗口：重启、数据迁移、性能采集只在非交易时段执行（A 股 09:15–15:00 之外）；盘中只允许只读预检 | 升级记录含开始/结束时间与交易时段判定 |
| I-13 | 数据迁移向前兼容：新数据格式必须能被上一版代码读取至少一个大版本，否则必须提供备份与恢复步骤 | 迁移脚本 + 旧版读取测试 + 恢复演练记录 |

> I-2 的当前口径（2026-11-13 修正）：**重建阶段先不搬 fork 的界面外观，UI 暂用作者的**；重建完成后的界面外观用户可能自行调整，因此不得把「上游 UI 不可改」写成永久约束。届时的 UI 调整按 Z4 模块 + 最小接线处理，或作为独立的 UI 变更批次登记，绝不混进上游升级提交。

---

## 2. 分层隔离规则

### 2.1 六区模型

| 区 | 名称 | 定义 | 允许改动 | 与上游二开分级对照 |
|---|---|---|---|---|
| **Z0** | 上游原样区 | 上游仓库跟踪的全部文件，默认归属 | 默认禁止；只允许 §2.3 的最小接线块 | 上游 L3（受限） |
| **Z1** | 数据配置区 | `data/`、用户策略、扩展包、偏好设置、安装包数据 | 允许，但升级不触碰 | 上游 L1 |
| **Z2** | 官方扩展区 | 前端插槽/路由/导航注册、后端 `app.extensions` 注册器、`frontend/src/custom/**`、`backend/app/custom/**`、插件目录 | 允许，按官方契约 | 上游 L2 |
| **Z3** | 最小接线区 | Z0 文件中被 `[FORK]` 标记包裹的极小块 | 允许，受 §2.3 预算约束 | 上游 L3 |
| **Z4** | fork 独占区 | 上游不存在的 fork 新文件/新目录 | 允许，自由演进 | — |
| **Z5** | 冻结红线区 | 评分选股、个股图表配置、价位指标阈值 | 绝对禁止，需用户书面确认 | 用户红线 |

**默认判定**：无法确定归属的文件，一律按 Z0 处理。

**落点优先级**（详见 §0.1）：Z1 → Z2 → Z4+Z3 → Z3 → 禁止。**能通过注册接入的，不得进 Z3。**

### 2.2 路径归属矩阵（初始值，落地时写入 `.upgrade/ownership.yaml`）

| 路径 | 区 | 规则 |
|---|---|---|
| `backend/app/**`（除下列例外） | Z0 | 只读；接线必须走 Z2 或 Z3 |
| `backend/app/main.py`、`strategy/engine.py`、`backtest/engine.py` | Z0 + Z3 | 只允许注册/注入型接线块 |
| `backend/app/strategy/scoring.py`、`strategy/builtin/**`、`factors/**`、`api/screener.py`、`api/strategy.py`、`api/signals.py` | **Z5** | 只读 |
| `backend/app/services/opportunity_score.py`、`score_ledger.py`、`livermore_service.py`、`action_timing.py`、`market_mode.py`、`position_exit.py`、`api/today.py` | **Z5** | 只读 |
| `backend/app/indicators/**`（`levels.py`、`keltner*.py`、`pipeline.py` 等） | **Z5** | 现有口径/参数/序列只读；上游**纯新增**指标函数可接受，改动既有口径按 C4 裁决 |
| `backend/app/custom/**`、`app/extensions/**` | Z2 | 按注册器契约扩展 |
| fork 独有后端模块（如 `services/fib2_grain_service.py`、`indicators/quant_macd.py`） | Z4 | 新文件，命名带领域前缀 |
| `frontend/src/components/ui/**`、`components/stock-analysis/**`、`components/ECharts*`、`tailwind.config.ts`、`index.html`、字体/主题资源 | Z0（UI） | 重建期外观只读；后续 UI 调整须用户立项并单独立项登记 |
| `frontend/src/components/stock-analysis/**` | 双维度 | 布局/样式/交互外观 → Z0（UI）；图表配置/序列/阈值/显示规则 → **Z5**，按红线二处理 |
| `frontend/src/pages/**`（上游页面） | Z0 | 禁止删除、禁止整文件替换 |
| `frontend/src/router.tsx`、`components/Layout.tsx`、`lib/api.ts`、`lib/queryKeys.ts` | Z0 + Z3 | 只允许挂载/注册/键声明；fork 端点实现必须放 Z4（见 §2.5），不得在 `api.ts` 内堆业务代码 |
| `frontend/src/fork/**`（fork 前端模块：页面、组件、API 客户端、查询键） | Z4 | 新目录；只通过 Z2 注册或 Z3 单点接线接入 |
| `frontend/src/custom/<ns>/**` | Z2 | `extension.tsx` 只做注册；内容放同目录 `Page.tsx` |
| fork 独有前端页面与组件（新目录） | Z4 | 通过 Z2 路由注册接入，不改 Z0 页面 |
| `data/**`、`backend/data/**`、用户扩展包 | Z1 | 升级不读写、不迁移（除非显式迁移任务） |
| 守卫测试（`backend/tests/test_*guard/terminology/design*` 等） | Z4 | 只允许加强，不允许放宽基线 |

### 2.3 最小接线块（Z3）规范

只有「注册、挂载、注入、字段映射」这四类操作允许写进 Z0 文件，且必须满足：

```ts
// [FORK] R### <一句话目的> begin
// 只允许：注册路由 / 挂载组件 / 注入参数 / 映射字段
// [FORK] end
```

```python
# [FORK] R### <一句话目的> begin
# 只允许：include_router / 注册扩展 / 注入上下文参数
# [FORK] end
```

硬约束：

1. 每块 **≤ 30 行**；每个 Z0 文件 **≤ 3 块**；超出即说明该能力应上移为 Z2 扩展点或下沉为 Z4 模块。
2. 块内禁止：业务计算、数据读取、缓存实现、复制上游函数体。
3. 每块必须有唯一 `R###`，并在 `FORK_NOTES.md` 有对应 R 行。
4. 块内不得嵌套第二个块；不得包裹大段上游代码。
5. 上游删除/重命名接线点所在代码时，**必须重新寻找官方扩展点**，不得把整段上游逻辑搬进块内。
6. Z3 只做接线，**不得承载业务实现**：fork 的 API 客户端、查询键、页面组件、服务类必须放 Z4，Z3 只做 import + 注册/挂载。
7. 每个块必须成对出现；提交前校验 begin/end 数量一致、R 编号唯一（见 §7 G0）。
8. 块内新增的 import 若超过 3 个，说明该能力应整体下沉到 Z4。

### 2.4 明确禁止的做法（均由历史事故反推）

| 禁止 | 原因 | 替代做法 |
|---|---|---|
| 删除上游文件，用 fork 同名文件替代 | 一次显式冲突变长期隐式分叉 | 保留上游文件，用 Z3 块挂载 Z4 模块 |
| 把上游整页复制到 `custom/` 后独立维护 | 永久失去合并能力 | 优先用插槽/路由注册；确需改核心时按 L3 最小改动 |
| 在上游组件内重写整段 UI | 合并时会被上游整段覆盖（净值图读数事故） | UI 一律取上游；功能逻辑放 Z4 |
| 重建期改 UI 设计系统/tailwind/主题/字体 | 会污染与上游的 UI 对齐 | 重建期不做；后续调整按 I-2 单独立项 |
| 改 builtin 策略、`scoring.py`、指标参数 | 违反 I-3 | 不做 |
| 为「通过」而改测试、改基线、改采样口径 | 自欺，破坏可验证性 | 修实现，或走「有意变更基线」流程 |
| 用 `git merge upstream/main` 普通合并 | 上游强推重写过历史，会搅乱 fork 提交 | §4 合成提交 + 三方合并 |
| 分批推送 / 只推部分升级内容 | 历史纪律（2026-11-12） | 全部验证后一次性推送 |
| 升级提交混入格式化、依赖升级或无关修复 | 让回滚粒度失真、diff 不可审 | 一个提交只表达一个目的；格式与依赖单独提交 |
| 在升级分支上顺手修 fork bug 或加功能 | 升级回归无法归因 | 先记录，升级完成后再单独立项 |

### 2.5 高频冲突文件的正确落点

以下文件是历次合并的主要冲突源。**默认目标都是零改动**；做不到时按表中降级方案处理，并在 R 行注明原因与「上游将来提供扩展点后的迁移计划」。

| 上游热点 | 错误做法（历史） | 正确做法 |
|---|---|---|
| `frontend/src/lib/api.ts` | 把 fork 的全部端点封装写进该文件（曾 +1420 行） | 端点实现放 Z4 `frontend/src/fork/api/*.ts`，复用 `api.ts` 的请求基座与类型；`api.ts` 最多加 1 行 re-export，最好零改动 |
| `frontend/src/lib/queryKeys.ts` | fork 键分散写在文件尾部 | Z4 `fork/queryKeys.ts` 导出对象，`queryKeys.ts` 只加一行展开 |
| `frontend/src/router.tsx` | 手写 fork 路由表 | 用 Z2 路由注册（`FrontendExtension.routes`），**零改动** |
| `frontend/src/components/Layout.tsx` | 修改 nav 数组 | 用 `layout.navigation.extra` 插槽或导航注册，**零改动** |
| `backend/app/main.py` | 直接 `include_router` + 定时器 + 启动钩子 | 用 `app.extensions` 的 `setup(registrar)` + `include_router`，**零改动**；确需生命周期钩子才允许 Z3，且 ≤ 10 行 |
| `backend/app/strategy/engine.py` | 注入 `watchlist_only` 业务逻辑 | 优先注册表/参数注入；必须改时 Z3 ≤ 10 行，逻辑留在 Z4 |
| `frontend/src/pages/*` | 删除上游页、用 fork 页替代 | 保留上游页；局部差异用插槽；整页新功能走 Z2 路由注册 |

Z4 查询键的正确接法（`queryKeys.ts` 只加一行）：

```ts
// frontend/src/fork/queryKeys.ts（Z4）
export const forkKeys = {
  today: ['fork', 'today'] as const,
  focusList: ['fork', 'focus-list'] as const,
}
```

```ts
// frontend/src/lib/queryKeys.ts（Z0，Z3 块内只允许这一行）
// [FORK] R### fork 查询键接入 begin
...forkKeys,
// [FORK] end
```

---

## 3. 红线与守卫

### 3.1 红线清单（Z5）

1. **评分选股系统**：权重（trend .45 / volume .30 / position .25）、因子权重、六态分值、五条曲线、门槛、数据结构的任何改动。
2. **个股页面图表组件配置**：日 K、分时、多日分时、个股分析 K 图的配置、序列、渲染参数。
3. **价位指标参数与阈值**：生命线、止盈线、出场三阶段 ATR、Keltner 通道、布林口径。

完整路径清单以 §2.2 的 Z5 行为准，并与 [`AGENTS.md`](../AGENTS.md) 的红线条款保持一致；落地时写入 `.upgrade/ownership.yaml`。

### 3.2 守卫测试（每次提交必跑）

| 守卫 | 钉住内容 | 当前状态（`claude/rebuild` 纯上游） |
|---|---|---|
| `test_screener_builtin_params.py` | builtin 参数透传一致 | **已存在**（唯一现存的守卫） |
| `test_scoring_frozen.py` | 评分权重/曲线/门槛基线 | 不存在，随评分系统移植恢复 |
| `test_no_pink.py` / `test_no_purple.py` | 禁粉 / 禁紫 | 不存在，随 UI 守卫恢复 |
| `test_design_spec.py` / `test_ui_hierarchy.py` | 设计规格与层级 | 不存在，随 UI 守卫恢复 |
| `test_hidden_features_registry.py` | 隐藏功能登记簿 | 不存在，随功能登记恢复 |
| `test_terminology.py` | 名词表 | 不存在，随文案/名词表恢复 |
| `test_keltner*.py`、`test_boll26_chart.py`、`test_chart_levels_section.py`、`test_theme_palette.py` | 通道/口径/价位区段/指标色 | 不存在，随指标层移植恢复 |

> 规则：**每次发生「合并吞代码」事故，必须新增或加强一条守卫测试**，把事故变成断言。守卫只允许加强，放宽基线属于「有意变更」，需用户确认并单独提交。

### 3.3 提交前自证（输出必须为空）

```bash
git diff --stat HEAD -- \
  backend/app/strategy/ backend/app/factors/ backend/app/indicators/ \
  backend/app/api/screener.py backend/app/api/strategy.py backend/app/api/signals.py \
  backend/app/services/opportunity_score.py backend/app/services/score_ledger.py \
  backend/app/services/livermore_service.py backend/app/services/action_timing.py \
  backend/app/services/market_mode.py backend/app/services/position_exit.py \
  backend/app/api/today.py backend/app/backtest/ \
  "frontend/src/components/ECharts*" frontend/src/components/stock-analysis/ \
  frontend/src/lib/kline.ts frontend/src/pages/StockAnalysis.tsx
```

---

## 4. 版本升级标准流程（S0–S7）

### 4.0 前置条件

- 工作区干净（`git status --short` 为空）；有未提交改动时先提交到临时分支。
- 已 `git fetch upstream --tags`。
- 已记录本次升级的起点 commit 与当前基线（§4.1）。
- 用户已确认「本次要升到哪个 Tag」。

### 4.1 S0 冻结与基线采集

```bash
git rev-parse HEAD
git describe --tags --always
cat VERSION
cd backend && uv sync --extra dev --frozen && uv run pytest tests -q | tail -5
cd ../frontend && pnpm install --frozen-lockfile && pnpm vitest run --reporter=summary | tail -20
```

产出：`.upgrade/baseline/tests-<tag>.json`（通过数、跳过数、耗时、Python/Node/pnpm 版本）与 `.upgrade/baseline/perf-<tag>.json`（§5）。

**判据**：基线不全，不得开始升级。基线必须与上一次升级使用**相同命令、相同数据快照、相同机器**，否则不可比。

### 4.2 S1 只读预检

**先明确一个前提**：上游强推改写过历史，fork 与上游**没有共同祖先**。因此：

- `scripts/upgrade_check.py` 依赖 `merge-base`，在本仓库会报「当前分支与目标版本没有共同基线」——**它不能作为本仓库的主预检**；
- 本仓库必须用「合成树 + 显式 merge-base」做三方预演，不依赖真实祖先。

```bash
ANCHOR=$(git rev-parse <上次合成提交>)
TREE=$(git rev-parse upstream/v0.3.xx^{tree})
SYNTH=$(git commit-tree "$TREE" -p "$ANCHOR" -m "[预演] upstream v0.3.xx")

set +e
git merge-tree --write-tree --merge-base="$ANCHOR" HEAD "$SYNTH" > /tmp/merge-preview.txt
CODE=$?
set -e
echo "exit=$CODE"; grep -n "^CONFLICT" /tmp/merge-preview.txt || true
```

退出码：`0` 无文本冲突；`1` 有冲突（输出含 `CONFLICT` 行）；其他为状态异常，先修复再继续。

语义重叠（Git 看不到的部分）：

```bash
comm -12 \
  <(git diff --name-only "$ANCHOR" HEAD | sort) \
  <(git diff --name-only "$ANCHOR" "$SYNTH" | sort)
```

**判据**：
- 有文本冲突 → 必须先产出逐文件裁决表（§6.5）才能进入合并；
- 无语义重叠文件也要按 §6 做契约与红线检查；
- 未提交内容不进入预演，先提交到临时分支。

同时生成「上游特性对账表」（模板见附录 E）：逐个上游发布说明的功能项 → 对应代码/测试 → 预计落点（Z0/Z2/Z3/Z4）→ 是否触碰 Z5。

### 4.3 S2 建集成分支与合成提交

```bash
git switch -c sync/v0.3.xx-YYYYMMDD claude/rebuild   # 或目标开发分支
git read-tree -u --reset upstream/v0.3.xx            # 索引与工作区精确对齐上游树
git commit -m "[合成] 上游 v0.3.xx 的树，接在上次同步点之后"
```

要求：合成提交的**树必须与上游目标 Tag 逐字节一致**：

```bash
test "$(git rev-parse HEAD^{tree})" = "$(git rev-parse upstream/v0.3.xx^{tree})" && echo TREE_OK
```

> 不要用 `git checkout upstream/main -- .`：它不会删除上游删掉的文件，合成树会悄悄多出文件。

### 4.4 S3 三方合并与冲突裁决

```bash
git merge <上次同步锚点>
```

- 禁止 `git merge upstream/main`。
- 逐文件按 §6.4 决策树裁决；每条冲突在升级记录中登记一行。
- 合并不允许出现「文件级 ours/theirs 一键选择」而不看内容。

**判据**：冲突全部登记且有裁决依据；`git diff --diff-filter=D --name-only <锚点> HEAD` 中无上游文件被删除。

**冲突预算（超限即停，先重构再升级）**：

| 条件 | 动作 |
|---|---|
| 单个 Tag 的 C1 + C2 冲突文件 > 20 个 | 暂停；先按 §2.5 收敛 fork 接线 |
| 单个 Z0 文件需重放 Z3 块 > 3 个 | 暂停；把块合并为 Z2 扩展点或 Z4 模块 |
| 连续两个 Tag 冲突数上升 | 触发 fork 架构复盘 |
| 一次跨版本 > 3 个 Tag | 必须拆成顺序批次，禁止跳跃合并 |

### 4.5 S4 门禁验证

依次执行 §7 的 G0–G4（含 G2.5），全部通过才允许提交。

### 4.6 S5 性能对比

执行 §5，产出前后对比报告；任一项超阈值即阻断。

### 4.7 S6 台账、锚点与基线更新

1. `FORK_NOTES.md` 新增 R 行（固定四栏）。
2. 更新顶部「当前上游基线」锚点。
3. 更新 `.upgrade/baseline/tests-<tag>.json`、`perf-<tag>.json`。
4. 更新 Feature Manifest 的验证结果。
5. `scripts/sync_versions.py` 对齐 `VERSION` / `backend/pyproject.toml` / `frontend/package.json`。

### 4.8 S7 提交、推送与回滚点

- **一个 Tag 一个升级提交**（版本号/台账可拆独立提交）；禁止把多个 Tag 攒成一次合并。
- 升级提交不得包含格式化、依赖升级、fork 功能修改（§2.4）。
- 提交信息模板：

```text
chore(upstream): 合并上游 v0.3.xx

上游: <tag> / <commit>
冲突: C0 x / C1 x / C2 x / C4 x
门禁: G0-G4 全过（报告: .upgrade/reports/<id>/）
性能: PB-02 x→y (+z%)；PB-07 x→y (+z%)
回滚: git revert <sha>
```

- 推送前置条件（缺一不推）：工作区干净、全部批次 G0–G4 通过、回归演练完成、报告已归档。
- 全部批次验证完成后**一次性推送**（2026-11-12 纪律），推送目标只能是 `origin`（fork），**永远不推 `upstream`**（I-11）。
- 推送前打本地 tag `fork-v<版本>-<日期>`；推送后记录回滚命令：

```bash
git revert <升级提交>
# 或整体回退（仅回滚时使用，禁止用于常规推送）
git reset --hard <升级前 HEAD> && git push --force-with-lease origin <分支>
```

**判据**：`git log --oneline` 可逐 Tag 回退；回滚命令已写入升级记录；远程 `upstream` 无任何推送记录。

### 4.9 非 Git 运行态升级（零中断轨道）

适用于 Docker / 桌面安装包。前置：**I-12 升级窗口**（非交易时段）、`data/` 已备份、旁路实例端口与数据目录已隔离。

1. 备份用户数据与配置：

```bash
tar -czf ~/tsp-backup-$(date +%Y%m%d-%H%M).tgz data/
```

2. 启动旁路实例，就绪探测（60 次 × 2 秒）：

```bash
for i in $(seq 1 60); do
  curl -fsS http://127.0.0.1:3018/api/health >/dev/null && echo READY && break
  sleep 2
done
```

3. 就绪后切换流量，旧实例保留 ≥ 10 分钟作为回滚位。
4. 程序文件变更由上游 `upgrade_guard` 生成快照与对比报告（`data/upgrade_guard/`），按「可恢复 / 需手工合并 / 已一致 / 新增可恢复」四类处理；守卫**不自动合并**程序文件。
5. 数据迁移遵守 **expand/contract**（I-13）：
   - 新增字段先写双份，旧字段保留至少一个大版本；
   - 只读校验 + dry-run 通过后才写；
   - 迁移前复制数据目录，迁移脚本幂等，附独立回滚脚本；
   - 旧版代码必须仍能读取新数据；做不到就不能在本次升级中做破坏性迁移。
6. 回滚判定（任一命中立即切回）：5xx 比例 > 1%、健康检查连续 2 次失败、关键接口 P95 > 基线的 2 倍、SSE 断连数明显上升、出现数据写入错误。
7. 回滚后验证：旧实例健康检查通过、数据可读、关键页面可用；回滚结果写入升级记录。

---

## 5. 性能基准对比验证标准

### 5.1 基准指标

| 编号 | 指标 | 采集方式 | 口径 |
|---|---|---|---|
| PB-01 | 后端冷启动就绪 | 启动进程到 `GET /api/health` 首次 200 | 空载、无预热缓存 |
| PB-02 | 热点 API P95 | 固定脚本循环 30 次取 P95 | 自选、选股、个股详情、今日 |
| PB-03 | 全量筛选耗时 | 固定股票池、固定参数 | 冷缓存 + 热缓存各一组 |
| PB-04 | 单策略回测耗时 | 固定标的/区间/参数 | 串行、无并发 |
| PB-05 | 矩阵/优化耗时（启用时） | 固定网格 | 与 PB-04 同环境 |
| PB-06 | 后端常驻内存 | 空载运行 5 分钟后 RSS | 无请求 |
| PB-07 | 前端构建时长 | `pnpm build` 墙钟 | 清空 `dist` |
| PB-08 | 前端产物体积 | `dist` 总体积与首屏 JS（gzip） | 同构建配置 |
| PB-09 | 后端测试总时长 | `pytest --durations=0` | 辅助指标，不作门禁 |
| PB-10 | 实时空转成本 | 无订阅/无规则时的 CPU 与请求数 | 应为 0 |
| PB-11 | 列表页请求数 | 打开自选/选股/今日，统计 XHR/fetch 数量 | 不得增加（N+1 检测） |
| PB-12 | 资源泄漏 | 升级前后各跑 30 分钟，采样线程数、FD、DB 连接 | 无持续增长 |

### 5.2 采样规则

- 同一台机器、同一 Python/Node/pnpm 版本、同一数据快照、同一参数。
- 记录**机器指纹**：CPU 型号、内存、macOS 版本、电源模式；固定电源模式，关闭后台重任务。
- **数据快照必须固定**：记录文件数、总大小与 sha256 清单；前后必须使用同一份快照，不得用升级后已变化的数据。
- 后端 API 优先用**进程内 ASGI 调用**（`httpx.ASGITransport`）测，避免网络与代理噪声；需要验证真实链路时才用 `curl`，并单独标注。
- 冷/热分离；首次运行丢弃（JIT、页缓存）。
- 每项 3 次取中位数；同版本重复测量的 MAD 若大于规则阈值，按 §5.3 的噪声地板处理。
- 串行执行；避开交易时段的实时轮询与后台任务，避免互相干扰。
- 机器负载、后台进程、采集起止时间写入报告。

### 5.3 门禁阈值

| 类别 | 指标 | 允许退化上限 |
|---|---|---|
| 热路径 | PB-02、PB-03（热缓存） | **≤ 5%** |
| 冷路径/批量 | PB-01、PB-03（冷缓存）、PB-04、PB-05 | **≤ 10%** |
| 内存 | PB-06 | **≤ 10%** |
| 构建 | PB-07 | **≤ 15%** |
| 产物 | PB-08 总体积 | **≤ 3%**；首屏 JS **≤ 5%**；最大单 chunk **≤ 5%** |
| 请求数 | PB-11 | **不得增加** |
| 资源 | PB-12 | 无持续增长（30 分钟内斜率 ≈ 0） |
| 实时空转 | PB-10 | **必须为 0**，不得新增空转轮询 |

判定：任一指标超阈值 → **阻断**，进入 §5.5 处置；不得以「机器抖动」为由放行。

**噪声地板**：升级前先用**同一版本**重复测 5 次，计算 MAD（中位数绝对偏差）。若 `2 × MAD` 大于规则阈值，则本项实际阈值取 `max(规则阈值, 2 × MAD)`，并在报告中写明。没有噪声地板数据的项，一律按规则阈值判定。

### 5.4 性能反作弊规则

- 不得通过延长缓存 TTL、减少样本量、关闭指标、跳过冷缓存来「通过」基准。
- 不得改变统计口径（P95 改均值、全量改抽样）。
- 声称「性能提升」同样必须给前后数据（`CONTRIBUTING.md` §6.3）。
- 新增列表请求、每卡片独立请求、实时路径随历史线性增长，均视为退化（`CONTRIBUTING.md` §6.3 硬约束）。

### 5.5 退化处置

1. 用升级批次内的提交做二分定位（每个 Tag 一个提交，天然可 bisect）。
2. 区分「上游引入」与「fork 适配引入」：
   - 上游引入且非关键路径 → 记录并接受（需用户确认）；
   - fork 适配引入 → 修适配，不改变上游实现；
   - 红线相关（可能影响评分/图表） → 立即回退该批。
3. 修复后重跑同一基准，附前后数据。

---

## 6. 冲突场景的自动检测与处理

### 6.1 检测矩阵

| 编号 | 检测 | 手段 | 命中后的动作 |
|---|---|---|---|
| D1 | 文本冲突 | `git merge-tree`（`upgrade_check.py` 已实现） | 逐文件裁决 |
| D2 | 同文件双改 | `comm -12` 双方 diff 文件名 | 语义复核 |
| D3 | 符号级重叠 | 对双方 diff 提取函数/类/导出名，取交集 | 人工复核 + 契约测试 |
| D4 | 契约重叠 | 路由路径、API 字段、queryKey、配置键、slot 名、扩展 ID、策略 ID | 阻断，按 §6.4 处理 |
| D5 | 红线触碰 | Z5 路径清单比对升级 diff | 一律阻断 |
| D6 | 行为/性能回归 | G1–G4 门禁 | 阻断 |

D1–D4 应尽量脚本化；D5 是可完全自动化的硬门禁；D6 由测试与基准承担。

**D3 的可执行口径**（Git 自带 hunk 函数上下文 + 符号正则）：

```bash
# 取双方改动的符号名（Python / TS 常用形态），再求交集
for REV in HEAD "$SYNTH"; do
  git diff -U0 "$ANCHOR" "$REV" -- '*.py' '*.ts' '*.tsx' \
    | grep -E '^[+-](export )?(async )?(def|class|function|const|interface|type) ' \
    | sed -E 's/^[+-]//; s/^export //; s/^(async )?(def|class|function|const|interface|type) +//; s/[^A-Za-z0-9_].*$//'
done | sort | uniq -d
```

输出非空 → 存在同符号双改，进入人工复核并补契约测试。

**D4 的清单来源**（必须全部覆盖，缺一不可）：

| 契约 | 来源 |
|---|---|
| HTTP 路由/字段 | 运行实例的 `/openapi.json` |
| 前端查询键 | `frontend/src/lib/queryKeys.ts` 导出名 |
| 插槽/路由/扩展 ID | `frontend/src/custom/*/extension.tsx`、`frontend/src/extensions/types.ts` |
| 后端注册 ID | `backend/app/custom/**` 中的 `register_*('id', ...)` |
| 策略 ID | `data/strategies/**` 与 `backend/app/strategy/**` |
| 配置键 | `data/` 下用户配置结构 + 后端 settings 模型 |

### 6.2 冲突分级

| 级别 | 定义 | 默认裁决 | 裁决权 |
|---|---|---|---|
| C0 | 纯文本冲突，语义正交 | 按层：Z0 取上游，Z3 重放 fork 块 | AI 可执行，记录 |
| C1 | 同文件语义重叠 | 上游内容为底，重放 fork 的 Z3 块 | AI 提议，用户确认 |
| C2 | 契约冲突（同名不同义） | 阻断；提升 `api_version` 或改 ID | 用户 |
| C3 | 行为冲突（测试红） | 阻断 | 用户 |
| C4 | 红线冲突 | 保留 fork，上游改动进「待评估清单」 | 用户 |
| C5 | 性能冲突 | 阻断 | 用户 |

### 6.3 自动处理边界

**允许自动**：整文件取上游（仅限 fork 未改的 Z0 文件）、lockfile 重生成、`upgrade_manifest` 重生成、版本号对齐、格式化、import 排序、快照类基线更新（须标注「有意变更」）。

**禁止自动**：逻辑合并、契约改名、数据迁移、红线裁决、测试基线放宽、删除 fork 功能。

**必须人工**：C1 以上全部、任何 Z5 相关、任何涉及删除用户可见功能的改动。

### 6.4 冲突决策树

```text
命中冲突
├─ 是否触碰 Z5？──是──> 保留 fork 现值；上游改动写入「待评估清单」；等用户裁决
└─ 否
   ├─ 冲突文件是否属于 UI 外观（Z0-UI）？
   │   ├─ 重建期 → 取上游；fork 若有功能差异，改为 Z4 模块挂载
   │   └─ 用户已立项 UI 调整 → 升级提交仍取上游，UI 变更在本批次之后单独重放并验证
   └─ 否
      ├─ fork 是否曾整文件替换该上游文件？──是──> 阻断，先重构为 Z3 接线 + Z4 模块，再重做本次升级
      └─ 否
         ├─ 上游删除/重命名了 fork 依赖的 API/文件？
         │   ├─ 存在官方替代 → 适配到替代点（Z3 块更新）
         │   └─ 无替代 → 阻断，提方案等用户确认
         └─ 普通重叠 → 上游内容为底，逐个重放 Z3 块，跑 G0–G4
```

### 6.5 冲突登记模板（每条一行）

| 文件 | 级别 | 类型 | 上游改动 | fork 改动 | 裁决 | 依据 | 验证 | 回退 |
|---|---|---|---|---|---|---|---|---|
| `frontend/src/fork/api/today.ts` + `frontend/src/lib/api.ts` | C1 | 客户端方法重叠 | 新增 3 个端点封装 | fork 端点实现 | 实现放 Z4；`api.ts` 只加 1 行 re-export | 无符号冲突 | `vitest` + `tsc` | `git revert <sha>` |

---

## 7. 兼容性校验机制：五道门禁

### G0 静态门禁

```bash
cd frontend && pnpm build          # tsc -b && vite build，看退出码
cd ../backend && uv run ruff check app tests
cd ../frontend && pnpm lint
git diff --check
```

补丁版本一致性：

```bash
python3 - <<'PY'
import json, re, pathlib
py = re.search(r'^version = "([^"]+)"', pathlib.Path('backend/pyproject.toml').read_text(), re.M).group(1)
js = json.loads(pathlib.Path('frontend/package.json').read_text())['version']
v = pathlib.Path('VERSION').read_text().strip().lstrip('v')
print('VERSION', v, 'pyproject', py, 'package.json', js)
assert len({v, py, js}) == 1
PY
```

fork 接线块完整性（begin/end 成对、R 编号不重复）：

```bash
test "$(grep -rho '\[FORK\].* begin' frontend/src backend/app | wc -l)" \
   -eq "$(grep -rho '\[FORK\] end' frontend/src backend/app | wc -l)"
grep -rho "\[FORK\] R[0-9]\+" frontend/src backend/app | sort | uniq -d   # 必须为空
```

**判据**：全部退出码 0；不得用管道吞退出码（历史事故）。

### G1 测试门禁

```bash
cd backend && uv run pytest tests -q
cd ../frontend && pnpm vitest run
```

**判据**：
- 后端 `failed = 0`，`passed ≥ 基线`（基线取自 `.upgrade/baseline/`，不写死数字）；
- 前端 `failed = 0`，`passed ≥ 基线`；
- 守卫测试全绿；尚未随移植恢复的守卫记为「未运行」，**不得计为通过**；
- 上游测试文件数量不得减少。

### G2 契约门禁

| 对象 | 检查 |
|---|---|
| HTTP API | 路由集合与字段快照对比；新增允许，删除/改义阻断 |
| 前端 queryKey | `queryKeys.ts` 键集合对比；新增允许，删除需同步全部调用方 |
| 扩展契约 | slot 名、路由 path、扩展 ID 唯一；`api_version` 未破坏 |
| 后端契约 | `BACKEND_EXTENSION_API_VERSION`、注册 ID 唯一、默认实现仍在 |
| 持久化 | 用户配置/策略/扩展包可读；未知字段忽略；更高版本拒写 |
| 数据口径 | 收盘口径/盘中口径、复权、单位未被上游改动破坏 |

**判据**：无未登记的删除或语义变化。

契约快照的可执行做法（升级前后各跑一次，报告归档）：

```bash
# HTTP 契约：从运行中的实例取 OpenAPI，排序后对比
curl -fsS http://127.0.0.1:3018/openapi.json > /tmp/openapi-after.json
python3 -c "import json;print(json.dumps(json.load(open('/tmp/openapi-after.json')),ensure_ascii=False,sort_keys=True,indent=2))" > /tmp/openapi-after.txt
diff -u /tmp/openapi-before.txt /tmp/openapi-after.txt | head -100

# 前端扩展清单
grep -rhoE "name: '[^']+'" frontend/src/custom/*/extension.tsx | sort -u > /tmp/slots-after.txt
# 后端扩展注册 ID
grep -rhoE "register_[a-z_]+\(\s*'[^']+'" backend/app/custom | sort -u > /tmp/backend-ext-after.txt
```

### G2.5 供应链与安全门禁

| 检查 | 判据 |
|---|---|
| 锁文件 | 升级前后 `uv.lock` / `pnpm-lock.yaml` 的 diff 已逐条审阅；无未知源、无 `latest` |
| 依赖安装 | `uv lock --check` 与 `pnpm install --frozen-lockfile` 通过 |
| 密钥泄漏 | `git diff <锚点> HEAD` 中无真实 key/token/密码（命中的假阳性需逐条说明） |
| 配置示例 | `.env.example` 键集合不减少；新增配置项已补样例 |
| 许可证 | 新增依赖许可证与仓库兼容，记录在升级报告 |

### G3 功能门禁（Feature Manifest）

每个 fork 功能必须有唯一 ID 与验证方式；自动优先，人工兜底。初始清单：

| ID | 功能 | 归属 | 自动验证 | 人工验证 | 回退点 |
|---|---|---|---|---|---|
| F-01 | 评分选股 v2（权重/六态/门槛） | Z5 | `test_scoring_frozen` | 抽样对照 | R 行 |
| F-02 | 六态趋势（Livermore） | Z5 | `test_livermore*` | 状态迁移图 | R 行 |
| F-03 | 把握分与打分台账 | Z5 | `test_opportunity_score*`、`test_score_ledger*` | 台账抽查 | R 行 |
| F-04 | 出手时机 | Z5 | `test_action_timing*` | 今日页核对 | R 行 |
| F-05 | 大盘红绿灯 | Z5 | `test_market_mode*` | 三态切换 | R 行 |
| F-06 | 出场线三阶段 ATR / 生命线 | Z5 | `test_position_exit*`、`test_chart_levels_section` | 图上位置 | R 行 |
| F-07 | 个股图表（生命线/出场线/六态条） | Z5 | 图表测试 | 逐股目视 | R 行 |
| F-08 | 今日页与今日决策 | Z5 | `test_today*` | 全流程 | R 行 |
| F-09 | 焦点名单 / 今日优选 / 标注 | Z5（服务） | 服务测试 | 页面核对 | R 行 |
| F-10 | 扩展页 11 个（paper/limit-ladder/review/monitor/abnormal/industry/concept/lots/financials/signals/stock-analysis） | Z2+Z4 | 各页 `Page.test.ts` | 逐页打开 | R 行 |
| F-11 | 外部页面 / UsageNotes / Minds | Z2+Z4 | 页面测试 | 逐页打开 | R 行 |
| F-12 | Keltner / Dinapoli / 量化 MACD / 庄闲线等指标 | Z5 | 指标测试 | 叠加目视 | R 行 |
| F-13 | AI 配置、理由、校验 | Z4 | 服务测试 | 调用一次 | R 行 |
| F-14 | 虚拟账户 / 纸面交易 / 翻转交易 | Z4 | 服务与页面测试 | 下单回放 | R 行 |
| F-15 | 数据源扩展包 / 自定义数据源 | Z2 | 插件测试 | 安装一次 | R 行 |
| F-16 | 升级兼容本身（本规范） | Z0/Z3 | 本规范 §7 全部 | 升级演练 | — |

> 上表的测试名为 **fork 侧目标验证项**；`claude/rebuild` 纯上游基线中大部分尚不存在，需在对应移植批次随功能一起落地，落地前该项标记为「未运行（功能未移植）」。
> 移植或升级后，Manifest 中每一项必须填「本次结果（PASS/FAIL/未运行+原因）」。**未运行不等于通过**。

**行为等价快照（golden master）**：对纯计算链路（评分、六态、出场线、打法分类），用固定输入（股票池 + 日期区间 + 参数）跑出 JSON 快照，升级前后 diff 必须为空。上游有意改口径时，必须由用户批准后更新快照，并在升级记录中单列。

**冒烟清单（前端）**：

| 路由 | 检查 |
|---|---|
| `/` | 仪表盘加载完成，无 console error |
| `/watchlist` | 列表、分组、个股跳转正常 |
| `/screener` | 结果非空，参数改动生效 |
| `/today` | 今日决策与评分卡可读 |
| 个股详情 | K 线、生命线/出场线、分时渲染正常 |
| `/settings` | 各标签页可切换、保存生效 |
| 扩展页 | 逐个打开，无白屏、无未捕获异常 |

判据：全部可达 + 关键元素存在 + console 无 error + 网络无 5xx。

### G4 性能门禁

按 §5 执行，附前后数据。

### 门禁纪律

- 任一门禁失败 → 不得提交、不得推送。
- 不得跳过门禁；确需临时跳过，必须在升级记录中写明项、原因、补偿验证，并由用户确认。
- 提交信息必须附证据（命令 + 结果摘要），不得写「测试通过」而无输出。

---

## 8. 「零」的可验证定义

绝对化口号不可验收，本规范把三个「零」量化为：

### 8.1 零业务中断

| 场景 | 判据 |
|---|---|
| 升级窗口 | 非交易时段（I-12）；盘中只允许只读预检，禁止重启、迁移、基准采集 |
| 源码/分支升级 | 升级期间不重启生产实例；不影响现有运行 |
| 运行态升级 | 旁路实例健康检查通过后才切流；切换窗口内查询成功率 ≥ 99.9%；回滚 ≤ 5 分钟 |
| 数据迁移 | 幂等、可回滚；迁移期间旧数据保持可读；旧版代码可读新数据（I-13） |
| 回滚演练 | 发布前至少演练一次回滚路径并记录结果 |

### 8.2 零功能异常

| 判据 | 阀值 |
|---|---|
| Feature Manifest | 100% PASS（人工项需签字） |
| 守卫测试 | 100% PASS |
| 新增 ERROR 日志 | 0 |
| 新增 4xx/5xx 端点 | 0（除有意变更并登记） |
| 上游功能 | 对账表 100% 覆盖，无遗漏项 |

### 8.3 零性能损耗

全部指标落在 §5.3 阈值内。注意：这里的「零」指**不超过测量噪声与阈值的退化**，不是绝对数值相等；报告必须给出原始数据与中位数。

### 8.4 验收签字

| 项 | 执行人 | 结果 | 证据位置 |
|---|---|---|---|
| G0 静态 | | | |
| G1 测试 | | | |
| G2 契约 | | | |
| G3 功能 | | | |
| G4 性能 | | | |
| 回滚演练 | | | |
| 红线自证 | | | |

---

## 9. 记录、复现与可追溯

### 9.1 目录约定（建议，落地后写入仓库）

```text
.upgrade/
├── ownership.yaml              # 路径 → 区（Z0–Z5）归属表
├── feature-manifest.yaml       # 功能清单与验证方式
├── baseline/
│   ├── tests-<tag>.json        # 测试基线
│   └── perf-<tag>.json         # 性能基线（含机器指纹与数据快照哈希）
└── reports/<日期>-<tag>/
    ├── precheck.txt            # 合成树预演 + 语义重叠 + 冲突预算
    ├── upstream-map.md         # 上游特性对账表（附录 E）
    ├── conflicts.md            # 冲突登记表
    ├── gates.txt               # G0–G4（含 G2.5）结果
    ├── perf-compare.md         # 前后对比与噪声地板
    ├── smoke.md                # 冒烟结果与日志摘要
    ├── waiver.md               # 例外/豁免记录（附录 F）
    └── rollback.md             # 回滚步骤与演练结果
```

`baseline/` 与 `reports/` 的结论性文件必须入库，原始日志不入库（体积）。

### 9.2 升级记录模板

```markdown
# 升级记录 v0.3.xx（YYYY-MM-DD）

- 上游目标：tag `v0.3.xx` / commit `<sha>`
- 起点：`<branch>@<sha>`
- 集成分支：`sync/v0.3.xx-YYYYMMDD`
- 合成提交：`<sha>`（树与上游一致：已校验）
- 合并提交：`<sha>`
- 环境：macOS <版本> / Python 3.12 / Node <版本> / pnpm 9.10.0
- 冲突：C0 x 个 / C1 x 个 / C2 x 个 / C4 x 个
- 门禁：G0 PASS / G1 PASS（passed x，基线 x）/ G2 PASS / G3 PASS / G4 PASS
- 性能：PB-02 x→y（+z%）；PB-07 x→y（+z%）
- 回滚：`git revert <sha>`（已验证 / 未验证）
- 未运行项及原因：...
```

R 行格式（`FORK_NOTES.md`，固定四栏，排在最新一行之前）。`FORK_NOTES.md` 在首次产生 R 行时创建于仓库根目录；文件不存在即表示当前没有 fork 改动：

```markdown
| R### | **<改了什么>** | `<涉及文件>` | <冲突风险：低/中/高> | <怎么单独回退> |
```

例外/豁免记录（附录 F）必须包含：编号、门禁项、原因、补偿验证、批准人、有效期、到期复核日期。

### 9.3 锚点维护

上游强推改写过历史，`merge-base` 会返回空（假阴性）。每次升级后必须用「树最近邻扫描」重新定位锚点：

```bash
for c in $(git rev-list upstream/main --max-count=400); do
  n=$(git diff --name-only "$c" upstream/main | wc -l)
  echo "$n $c"
done | sort -n | head -3
```

差异数最小者即本次等价锚点，写入 `FORK_NOTES.md` 顶部。

---

## 10. 角色与权限

| 动作 | AI | 用户 |
|---|---|---|
| 只读预检、基线采集、性能测量 | 允许 | — |
| Z4 内部实现与测试 | 允许 | — |
| Z3 接线块新增/修改 | 允许，须登记 R 行 | 事后审阅 |
| Z2 扩展点注册 | 允许，须符合官方契约 | 事后审阅 |
| 修改 Z0 非接线部分 | **禁止** | — |
| 触碰 Z5 | **禁止** | 唯一裁决人 |
| 修改/放宽测试基线 | **禁止** | 书面确认 |
| 删除用户可见功能 | **禁止** | 唯一裁决人 |
| 推送远端 | 仅用户明确指令后，且只能推 `origin`（fork） | 授权 |
| 向上游提交 PR / issue / 评论 / 建议 / 补丁 | **永远禁止**（I-11） | 禁止 |
| 宣布「完成」 | 必须有门禁证据 | 最终验收 |
| 例外/豁免（waiver） | 只能提出并记录，不能批准 | 唯一批准人（附录 F） |

AI 交付必须包含：改了什么、证据（命令+输出摘要）、未覆盖风险、需要用户确认的事项。禁止无证据宣布完成。

---

## 11. 附录

### A. 一页纸检查清单

```text
[ ] 工作区干净，已 fetch upstream --tags
[ ] 记录起点 commit 与基线（测试 + 性能 + 机器指纹）
[ ] 预检用合成树 + 显式 merge-base，未依赖 merge-base 自动推断
[ ] 上游特性对账表已填（附录 E）
[ ] 集成分支已建，合成提交树哈希与上游一致
[ ] 使用三方合并，未使用 upstream/main 普通 merge
[ ] 冲突逐条登记并裁决；冲突预算未超限
[ ] 无上游文件被删除（--diff-filter=D 为空）
[ ] 重建期 UI 外观路径 diff 为空（I-2）
[ ] 红线自证为空（I-3）
[ ] fork 标记 begin/end 成对、R 编号唯一
[ ] G0 静态全绿（看退出码）
[ ] G1 测试通过数 ≥ 基线，failed = 0
[ ] G2 契约无未登记破坏（含扩展 ID / queryKey 快照）
[ ] G2.5 锁文件已审、无密钥泄漏、配置示例未减少
[ ] G3 Feature Manifest 100% 有结果
[ ] G4 性能全部在阈值内（含噪声地板结论）
[ ] R 行 + 锚点 + 基线已更新
[ ] 版本号三处一致
[ ] 数据已备份、回滚命令已记录并演练（运行态升级）
[ ] 非交易时段执行（I-12）
[ ] 一次性推送（未分批，且未推 upstream）
```

### B. 常用命令（与当前仓库一致）

```bash
# 以下命令均在仓库根目录执行；前端命令进入 frontend/，后端命令进入 backend/
# Node/uv 的安装位置按自己的环境调整（本机为 ~/.local/share/node 与 ~/.local/bin）
export PATH=$HOME/.local/share/node/bin:$HOME/.local/bin:$PATH

# 后端
cd backend && uv sync --extra dev --frozen
uv run pytest tests -q
uv run ruff check app tests

# 前端
cd frontend && pnpm install --frozen-lockfile
pnpm build            # tsc -b && vite build
pnpm vitest run       # 注意：仓库没有 "test" 脚本
pnpm lint

# 预检与版本
python3 scripts/upgrade_check.py <tag>
python3 scripts/sync_versions.py
```

### C. 历史事故 → 规则映射

| 事故 | 教训 | 对应规则 |
|---|---|---|
| 合并后回测净值图十字线与读数区消失 | UI 整段被上游覆盖 | I-2、§2.4、§7 G3 人工目视 |
| 删除 11 个上游 `Page.tsx` 改用 fork 结构 | 结构分叉导致后续合并对撞 | I-1、§2.4 |
| 上游 builtin 去内置化 | 红线资产被连根拔起 | I-3、§6.4 |
| `merge-base` 返回空被当作「无更新」 | 历史被强推 | §9.3 |
| `pnpm build \| grep` 吞掉退出码 | 验证结果失真 | §7 G0 |
| 改测试让失败变通过 | 自欺，掩盖真实回归 | §6.3、§10 |
| 分批推送导致历史不一致 | 推送纪律 | §4.8、I-5 |
| 用 `merge-base` 做预检，误判「没有更新」 | 上游强推改写历史 | §4.2 合成树预检 |
| 合成提交用 `checkout -- .`，残留上游已删文件 | 合成树与上游不一致 | §4.3 `read-tree --reset` + 树哈希校验 |
| 盘中重启后端，实时行情断档 | 交易时段风险 | I-12、§4.9 |
| 迁移后回滚，旧代码读不了新数据 | 破坏性迁移 | I-13、§4.9 expand/contract |

### D. 待落地工具契约（当前**未实现**）

以下工具用于把本规范从「人工照做」升级为「一键门禁」。未落地前，按 §4/§5/§7 的手工命令等价执行。

| 工具 | 职责 | 接口契约 | 退出码 |
|---|---|---|---|
| `scripts/upgrade_precheck.py` | 强推历史下的合成树预检（取代 `upgrade_check.py` 的 merge-base 路径） | `--tag vX --anchor <sha> --report <dir>`；**不改工作区** | 0 无冲突 / 1 有冲突 / 2 状态异常 |
| `scripts/fork_marker_lint.py` | Z3 标记配对、块行数、R 编号唯一 | `--root .` | 0 通过 / 1 违规 |
| `scripts/dump_contracts.py` | 导出 OpenAPI、queryKeys、扩展 ID 快照并对比 | `--out <dir>`；`--compare <before> <after>` | 0 兼容 / 2 破坏 |
| `scripts/upgrade_perf.py` | 采集/对比性能基准（机器指纹、快照哈希、噪声地板） | `--capture --out <json>`；`--compare <before> <after>` | 0 通过 / 3 超阈值 / 4 数据不足 |
| `scripts/upgrade_gate.py` | 串行执行 G0–G4（含 G2.5） | `--profile full\|fast`；`--report <dir>` | 0 全过 / 2 门禁失败 / 4 环境不全 |
| `.upgrade/ownership.yaml` | 路径归属（Z0–Z5） | 供 gate 与 diff 检查读取 | — |
| `.upgrade/feature-manifest.yaml` | 功能清单与验证映射 | 供 gate 生成 G3 报告 | — |

落地顺序建议：`ownership.yaml` → `feature-manifest.yaml` → `fork_marker_lint.py` → `dump_contracts.py` → `upgrade_precheck.py` → `upgrade_gate.py` → `upgrade_perf.py`。每落地一个，先在纯上游基线上跑一次「全过」，证明工具本身不产生假阳性。

### E. 上游特性对账表模板

每次升级建一张，逐项填写，**不允许有空白行**：

| 上游版本 | 特性/修复 | 上游证据（commit/文件） | 我方落点 | 触碰 Z5 | 验证方式 | 结果 |
|---|---|---|---|---|---|---|
| v0.3.xx | 例：回测提速 | `<sha>` / `backend/app/backtest/*` | Z0 原样 | 否 | G1 + PB-04 | PASS |
| v0.3.xx | 例：新增图表样式 | `<sha>` / `frontend/src/components/*` | Z0；与 fork 冲突 | 是 | 人工目视 + 红线自证 | 保留 fork |

### F. 例外/豁免申请单模板

仅用户可批准；无批准编号的豁免一律视为未豁免。

```text
编号: E-YYYYMMDD-01
门禁项: G1 / G2 / G2.5 / G3 / G4
原因: <为什么必须在本批次例外>
影响范围: <文件/功能/用户可见行为>
补偿验证: <替代验证命令与结果>
有效期: <截止日期>
批准人: 用户
复核日期: <到期后必须复核>
```

---

## 12. 生效与修订

- 本规范自建立日起生效，适用于所有后续上游升级与 fork 功能移植。
- 修订必须说明：改了什么、为什么、影响哪些门禁、是否需要重跑基线。
- 与 `docs/secondary-development.md` 冲突时，以用户红线与本规范为准；与 `AGENTS.md` 冲突时，以 `AGENTS.md` 为准并立即修订本规范。

### 修订记录

| 版本 | 日期 | 内容 |
|---|---|---|
| v1.0 | 2026-11-13 | 初版：六区隔离、S0–S7、G0–G4、PB-01~10、D1–D6 |
| v1.1 | 2026-11-13 | 对抗性复审：合成树预检（修正强推历史下 merge-base 失效）、Z1→Z2→Z4→Z3 落点优先级、§2.5 高频冲突文件正确落点、冲突预算与版本间隔上限、数据迁移 expand/contract、交易时段窗口、性能机器指纹/快照哈希/噪声地板、G2.5 供应链门禁、PB-11/12、附录 E/F |
| v1.2 | 2026-11-13 | 纳入 `docs/` 核心文档体系：标注必读前置、增加元数据表、README/CONTRIBUTING/AGENTS 强制引用、修正仓库内相对链接 |
