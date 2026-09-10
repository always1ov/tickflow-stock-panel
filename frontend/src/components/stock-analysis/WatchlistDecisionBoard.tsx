import { useState, useMemo, useEffect, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Star, Wallet, Sparkles, Loader2, ArrowUp, ArrowDown, RefreshCw, FileText, Download, Bell, ChevronDown, Folder, Inbox, List } from 'lucide-react'
import { api, type ChannelEvent, type ChannelPhase, type EffectivePosition, type Playbook, type ExitLine, type KeltnerBands, type TrendInfo, type Urgency } from '@/lib/api'
// [R276] 分组下拉直接复用「加入自选」那个菜单 —— 定位/键盘/点外面关闭/配色全都现成
import { WatchlistGroupMenu } from '@/components/WatchlistAddMenu'
import { resolveWatchlistGroupColor } from '@/lib/watchlist-group-colors'
import { QK } from '@/lib/queryKeys'
import { pickStale, SIGNAL_TTL_HOURS } from '@/lib/signalFreshness'   // [R131] 增量分析判据
import { toast } from '@/components/Toast'
import { useHistoryReports, openHistoryReport, loadHistory } from '@/lib/stockAnalysisStore'
import { trendBadgeCls } from '@/components/stock-analysis/TrendStateBar'
import { StockReviewDialog, type ReviewTab } from '@/components/stock-analysis/StockReviewDialog'
// [R167] 导出与两个单元格从本文件拆出 —— 拆前 933 行, 顶部堆着两张配色表和一整份
// HTML 导出模板, 主组件被压在后面。
import { storage } from '@/lib/storage'
import { buildBoardHtml } from '@/lib/decisionBoardHtmlExport'
import { DEFAULT_EXPORT_KEYS } from '@/lib/decisionBoardExportColumns'
import { ExportColumnsDialog } from '@/components/stock-analysis/decision-board/ExportColumnsDialog'
import { ChannelStateCell, ConclusionCell, NUM, TD_BASE } from '@/components/stock-analysis/decision-board/cells'
import { LotsLink } from '@/components/stock-analysis/decision-board/LotsLink'
// [R169] 合并视图(手填 ⊕ 上游批次登记), 字段说明见 api.ts 的 EffectivePosition
type Position = EffectivePosition
type WatchPoint = { direction: 'up' | 'down'; price: number; label?: string; action?: string; reason?: string }
type Signal = { signal: string; confidence: number; reason: string; close: number | null; created_at: string; watch_points?: WatchPoint[] }
// [R254] 排序目标从 18 个砍到 10 个 —— **每列只留一个**。
//
// 用户: 「我也不想切换那么多下」「点击第三下就恢复原状」。
//
// 原来「走势」一列塞了 5 个目标(六态/间距/短中长), 那是 R211 把三列并成一列时
// 带来的; 「结论」2 个、「现价/涨跌」2 个。轮换一圈要点 6 下, 而且**一个方向
// 永远点不到**(只在目标之间乒乓, dir 恒为首次方向)。
//
// 砍掉的是: close(现价) / spread(间距) / ks·km·kl(三档位置) / verdict(贵不贵) /
// exit(止盈线, R212 那一列早撤了) / confidence(置信度, R178 换掉了)。
// 后两个本来就**没有任何表头能选中**, 是死代码。
// [R277 → R297] `spread` 进来又出去了, **两次都是同一条判据: 点不到就删。**
// R254 删它是因为它只能靠"轮换目标"够着; R277 加回来是因为那一版给了它自己的
// 表头(前提变了); R297 那一列并进「结论」, 表头没了, 前提又变回去 ——
// 这不是反复, 是同一条规矩在三种版面下各判了一次。
// [R284] `held` / `cost` / `report` 三个键删掉了 —— 它们的表头随列合并消失,
// 留着就是**点不到的死键**(R254 立的规矩, R277 已把它做成了机器核对)。
//
// 各自的去处:
//   · held   —— 「只看持有」那个按钮本来就在做这件事, 排序是重复入口
//   · cost   —— 按成本价排 166 只票没有任何决策含义
//   · report —— 「上次 AI 分析是什么时候」不是决策输入; 胶囊照旧可点开
// 合并后的「持仓」列排 `pnl`(亏最多的先看), 「AI 信号」列照旧排 `signal`。
type SortKey = 'urgency' | 'name' | 'changePct' | 'trend' | 'play'
  | 'pnl' | 'signal'
const SIGNAL_RANK: Record<string, number> = { buy: 0, sell: 1, hold: 2, watch: 3 }
/**
 * [R194] 决策台的列宽表 —— colgroup 与空表提示的 colSpan 同源。
 *
 * 不写宽度的话浏览器会把富余空间全塞给 max-content 最大的那一列(AI 信号),
 * 别的列挤在一起; 写死 px 又不随视口走。
 *
 * 分配原则: 前半段(该动~止盈线)是查对用的, 给到"完整显示不换行"就够;
 * 后半段(趋势/三档通道/结论/AI 信号)才是要盯的, 富余空间往那边给。
 * 这些列内容宽度固定(输入框、徽标、等宽数字), 所以百分比调小**不会压字** ——
 * 内容宽度是硬底线, 百分比只决定"能不能多吃富余空间"。
 *
 * **顺序必须与 thead 里的 <th> 一一对应。**
 */
const BOARD_COLS = [
  { label: '标的', w: '9.5%' },
  // [R212] 「现价」「涨跌」合成一列。用户: 「这两列合成为『现价/涨跌』这样为一列」。
  // 两个数天生一起读 —— 拆成两列只是让眼睛多跳一次。
  { label: '现价/涨跌', w: '6%' },
  // [R212] 「止盈线」那一列撤掉了。用户: 「止盈线这一列不要了」。
  // **信息没丢**: 出场线破了或逼近, 「结论」列会直接判成「按纪律走」/「盯着」
  // 并把线价写在徽标上 —— 那比单独一列更早进视线。排序键与判定都还在。
  // [R211] 「量化通道」(测量) + 「通道态势」(结论) + 「趋势」(六态) 三列并一列。
  // 六态与通道阶段答的是同一个问题(往哪走), 只是方法不同 —— 放一格里,
  // 它们什么时候一致、什么时候打架, 上下一对就看见了。
  { label: '走势', w: '9.5%' },
  // [R277 加, R297 删] 「进度」那一列并进「结论」了。用户: 「个股分析页面的
  // 进度列和结论列看看怎么合并和显示哪些内容」。
  //
  // **两列本来就是一层**: 同源(都从 `phase()`/`geo` 出), 而且点开去的是同一个
  // 地方(复盘弹窗的「通道结论」页)。进度那两个读数是结论的**刻度**, 不是第四条
  // 结论 —— 与 R211「测量与结论拆两列等于让人左右对眼把结论和它的依据接起来」
  // 同一条理由, 这次轮到它自己。并法见 cells.tsx 的 `ConclusionCell`:
  // **行数一行没加**, 两个读数各自并进已有的两行。
  //
  // [R212] 「贵不贵」(位置) + 「怎么办」(动作) 合成一列, 竖排, 摆在 AI 之前。
  // 用户: 「贵不贵在上换行怎么办在下」「结论这行放在 ai 分析前一列」。
  // 顺序是有讲究的: 上面是事实(这个价算贵还是便宜), 下面是结论(所以今天该干嘛)。
  // [R297] 18% → 21%: 吃掉「进度」5.5% 里的大半, 余下匀给 AI 信号(它吃剩下的)。
  // 内容上限跟着抬到 23rem —— R283 的教训: 那个上限低于列宽时, 光加列宽没用。
  { label: '结论', w: '21%' },
  // [R249] 账目三列从「现价」后面挪到这里。用户: 「我有点乱, 是否有好办法整理
  // 好顺序调整显示和列」。**原来它们把判断切开了** —— 扫表时要连着读
  // 「走势 → 结论」, 中间却横着三列只有持仓那几只才用得上的账目。
  // 现在一行从左到右是: 认票 → 凭什么 → 我的账 → 别人的意见。
  // [R284] **「成本」「浮盈」两列删掉**(用户: 「删除掉浮盈和成本列」), 只留「持仓」。
  //
  // 它们为 5% 的行占着 9% 的宽度: 持有 8 只 / 自选 166 只 —— 另外 158 行两格全是
  // 一个 `—`。浮盈是**派生量**(现价与成本一减就有), 模拟盘与持仓页都在算;
  // 决策台是用来"今天该动哪只"的, 赚了多少不进这个判断。
  //
  // **成本输入框保留, 挪进这一格**(只在持有时长出来): 它不是展示而是**录入**,
  // 而且是出场线(止盈/止损)的输入 —— 整个删掉等于把那条线的来源砍了一半。
  { label: '持仓', w: '5%' },
  // [R284] 「AI 分析」整列撤掉 —— 用户: 「仅保留对投资决策最具影响力和决定性的
  // 核心数据列」。**它压根不是数据列**: 一枚报告胶囊 + 两个图标按钮, 是操作入口。
  // 三件东西并进「AI 信号」那一列的头一行(与信号徽标、时间同排), 一个不少。
  { label: 'AI 信号', w: '' },       // 不给宽度, 吃掉剩下的 —— 只有它是整段文字
] as const

// [fork 增强] 六态排序权重:多头在前(上涨趋势 → 下跌趋势)
const TREND_RANK: Record<string, number> = { UT: 0, NR: 1, SR: 2, SREA: 3, NREA: 4, DT: 5 }

// [R276] 分组筛选的两个哨兵。用字符串而不是 null —— 见 storage.boardGroupFilter 的说明。
const G_ALL = 'all'
const G_UNGROUPED = 'ungrouped'

// AI 信号 → 展示标签/配色。买入=红(A股涨红), 卖出=绿, 持有=琥珀, 观望=灰。
const SIGNAL_META: Record<string, { label: string; cls: string }> = {
  buy: { label: '买入', cls: 'border-red-400/40 bg-red-400/10 text-red-400' },
  sell: { label: '卖出', cls: 'border-emerald-400/40 bg-emerald-400/10 text-emerald-400' },
  hold: { label: '持有', cls: 'border-amber-400/40 bg-amber-400/10 text-amber-400' },
  watch: { label: '观望', cls: 'border-border bg-base text-muted' },
}

/**
 * [R284] 「AI 分析」那一列撤掉之后, 它的三件东西(报告胶囊 / ✨生成分析 / 🔔点位提醒)
 * 收成这个小组件, 挂在「AI 信号」列的头一行。
 *
 * 用户: 「仅保留对投资决策最具影响力和决定性的核心数据列」——
 * **它压根不是数据列, 是操作入口**, 不该按第三宽的比例占着一整列。
 *
 * 抽成组件是因为它要在**两支**里各出一次: 有信号的那支挂在徽标旁边, 没信号的
 * 那支挂在「未分析」旁边 —— 后者一漏, 没跑过分析的票就再也点不到那个 ✨。
 *
 * 配色: 报告胶囊原来是**紫色**, 这次去掉了。紫色在这张表里不表达任何市场含义
 * (它只说"有报告"), 而表里每一种颜色都该有含义 —— 见 R284 的配色收敛。
 */
function AiActions({ r, onAnalyze, onPriceAlert, reports }: {
  r: { symbol: string; name: string }
  onAnalyze?: (symbol: string, name: string) => void
  onPriceAlert?: (symbol: string, name: string) => void
  reports?: { latest: { id: string; created_at: string }; count: number }
}) {
  const iconCls = 'grid h-6 w-6 place-items-center rounded-btn text-muted/50 '
    + 'transition-colors duration-hover hover:bg-elevated hover:text-sky-300'
  return (
    <span className="inline-flex items-center gap-1">
      {!!reports && (
        <button
          onClick={() => openHistoryReport(reports.latest.id)}
          title={`打开最近报告(${new Date(reports.latest.created_at).toLocaleString()})${reports.count > 1 ? ` · 共 ${reports.count} 份` : ''}`}
          className="inline-flex items-center gap-1 rounded-btn border border-border bg-elevated/60 px-1.5 py-0.5 text-[11px] text-secondary transition-colors duration-hover hover:text-foreground cursor-pointer"
        >
          <FileText className="h-2.5 w-2.5 shrink-0" />
          {fmtAgo(reports.latest.created_at)}
          {reports.count > 1 && <span className="opacity-60">·{reports.count}</span>}
        </button>
      )}
      {onAnalyze && (
        <button onClick={() => onAnalyze(r.symbol, r.name)}
                title={`对 ${r.name} 生成/更新 AI 四维分析`}
                aria-label={`对 ${r.name} 生成 AI 分析`} className={iconCls}>
          <Sparkles className="h-3 w-3" />
        </button>
      )}
      {onPriceAlert && (
        <button onClick={() => onPriceAlert(r.symbol, r.name)}
                title={`为 ${r.name} 设置价格点位提醒`}
                aria-label={`为 ${r.name} 设置点位提醒`} className={iconCls}>
          <Bell className="h-3 w-3" />
        </button>
      )}
    </span>
  )
}

function fmtAgo(iso?: string): string {
  if (!iso) return ''
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000)
  if (s < 60) return '刚刚'
  if (s < 3600) return `${Math.floor(s / 60)}分前`
  if (s < 86400) return `${Math.floor(s / 3600)}小时前`
  return `${Math.floor(s / 86400)}天前`
}

/** 自选决策台 —— 个股分析页的整页主体: 一行一只自选, 点标的即弹出关键价位分析,
 *  并可标记仓位/成本、纵观对比浮盈。[R28] 起不再折叠(整页就它一个, 没有要让位的东西)。 */
export function WatchlistDecisionBoard({ currentSymbol, onSelect, onPreview, onAnalyze, onPriceAlert, locateNonce }: {
  currentSymbol: string
  /** [R157] 页头「定位」按钮每按一次 +1: 把当前个股那一行滚到视野正中并闪一下 */
  locateNonce?: number
  onSelect: (symbol: string, name: string) => void
  /** [R103] 点标的名称时打开整合版个股弹窗(最近查看+随意切换); 未传时退回仅选中 */
  onPreview?: (symbol: string, name: string) => void
  /** [R106] 行内 AI 分析(原页头「AI 个股分析」按钮, 整合进 AI 分析列, 每个标的都有) */
  onAnalyze?: (symbol: string, name: string) => void
  /** [R106] 行内点位提醒(原页头「点位提醒」按钮, 同上) */
  onPriceAlert?: (symbol: string, name: string) => void
}) {
  const qc = useQueryClient()
  const [heldOnly, setHeldOnly] = useState(false)
  // [R157] 定位当前个股: 行引用 + 闪烁高亮 + "行还没渲染出来"时的待定位
  const rowRefs = useRef<Record<string, HTMLTableRowElement | null>>({})
  const pendingLocate = useRef<{ symbol: string; explicit: boolean } | null>(null)
  const [flash, setFlash] = useState<string | null>(null)
  const flashTimer = useRef<number | undefined>(undefined)
  // [R182] 导出选列。六态汇总弹窗已并进导出 —— 勾上趋势那几列就是它。
  const [exportOpen, setExportOpen] = useState(false)
  const [exportCols, setExportCols] = useState<string[]>(
    () => storage.boardExportCols.get(DEFAULT_EXPORT_KEYS) ?? DEFAULT_EXPORT_KEYS)
  const setCols = (keys: string[]) => {
    setExportCols(keys)
    storage.boardExportCols.set(keys)
  }
  // [R48] 逐日复盘弹窗 —— 「趋势」「结论」两列点进来的就是它。
  // [R51] tab 记住是从哪一列进来的: 两列点开看的不是同一张表(见 StockReviewDialog)
  const [review, setReview] = useState<{ symbol: string; name: string; tab: ReviewTab } | null>(null)
  // 排序:默认按置信度降序(信号最强的排前面;未分析的始终垫底)
  // [R178] 默认按「该动了」排, 不再按 AI 置信度。
  //
  // 置信度是"AI 有多确定", 不是"这只有多急" —— 一只 AI 95% 确信「观望」的票
  // 会压在一只刚跌破止损线的票上面。而且拿 AI 决定用户先看谁, 跟本项目别处
  // 立的规矩是矛盾的(台账「只记不反馈」、R175「AI 只念表」)。
  // 升序 = 最急的在最上面(order 越小越急)。
  // 默认顺序 = 「该动了」判定从急到缓。「走势」表头循环一圈之后回到它。
  const DEFAULT_SORT = { key: 'urgency' as SortKey, dir: 'asc' as const }
  const [sort, setSort] = useState<{ key: SortKey; dir: 'asc' | 'desc' }>(DEFAULT_SORT)
  // [R228] 27 种组合速查的独立弹窗状态在这里删掉了。用户: 「这两个弹窗也整合到
  // 一起, 外部入口就变成一个按钮了」。它已经是复盘弹窗的第三个页签, 而且 geo/runs
  // 改由复盘接口的 `channel` 给 —— 决策台不必再把行数据透传进弹窗。
  // 「只看要动的」—— 自选一多, 默认列 80 行本身就是噪音
  const [actionableOnly, setActionableOnly] = useState(false)
  // [R276] 「只看某个分组」。用户: 「这里还要加个选择按钮, 能下拉菜单只看哪个分组」。
  //
  // 记进 localStorage: 分组是长期的编队(军工/稳定币/…), 你昨天在看哪一队, 今天
  // 多半还想接着看 —— 每次刷新都退回「全部」等于这个功能只对当次会话有用。
  // **但记住一个筛选就必须管它过期**: 那个分组被删掉之后, 界面会永远是空的而不说
  // 为什么。下面 groupsQ 到位后的那个 useEffect 就是干这个的。
  const [groupFilter, setGroupFilterRaw] = useState<string>(
    () => storage.boardGroupFilter.get(G_ALL) || G_ALL)
  const setGroupFilter = (g: string) => {
    setGroupFilterRaw(g)
    storage.boardGroupFilter.set(g)
  }
  /**
   * [R251] 每个排序目标**第一次点击**该往哪边排。
   *
   * 原来的规矩是「除了名称一律降序」—— 那对"数值越大越好"的列没问题, 可对
   * **越小越要紧**的那几个恰好是反的: 「怎么办」(0=按纪律走)与「AI 信号」
   * (0=买入)都会把最不该先看的顶到最前面, 而表头 title 写的正好相反。
   *
   * 口径: **第一下就把最该看的顶到最前面**, 与默认排序(该动了, 升序)同一个方向感。
   */
  const FIRST_DIR: Record<SortKey, 'asc' | 'desc'> = {
    urgency: 'asc',        // order 越小越急
    play: 'asc',           // 同上 —— 按纪律走 > 今天就得动 > … > 没事
    signal: 'asc',         // 买入 > 卖出 > 持有 > 观望
    name: 'asc',           // A → Z
    trend: 'desc',         // 值取了负 —— 降序 = 多头在前
    // [R277 加, R297 删] `spread` 这个排序目标退役了 —— **理由与 R254 当初删它
    // 时逐字相同: 它点不到了。** R277 之所以把它加回来, 正是因为那一版给了它
    // 一个自己的列头; 现在那一列并进「结论」, 而「结论」已经有自己的目标
    // (`play`, 按急迫程度), 一列一个目标是 R254 立的规矩。
    //
    // **能力上损失有限**: 「走得最远」里真正要决策的那一半, `play` 排序已经
    // 顶上来了(「该想退出计划了」是 SHAPE 档), 而「该止盈了」「大顶区域」
    // 「高位回落」本来就是结论徽标上的词, 扫一眼就在。
    changePct: 'desc',     // 涨最多在前
    pnl: 'desc',           // 浮盈最高在前; 再点一下就是亏最多在前
  }

  /**
   * [R254] **每一列都是三下一圈**: 最该看的在前 → 反过来 → 回默认。
   *
   * 用户: 「我也不想切换那么多下」「点击第三下就恢复原状」。
   *
   *     走势      多头在前 ↔ 空头在前
   *     结论      最急在前 ↔ 最闲在前
   *     现价/涨跌  涨最多 ↔ 跌最惨
   *     …其余列同理
   *
   * 取代了两套并存的老写法: `toggleSort` 的"再点一下翻方向"(永远回不到默认)
   * 与 `TREND_SORTS` 的"轮换五个目标"(六下一圈, 而且一个方向点不到)。
   * 一列一个目标之后, 这两件事合成了同一条规则。
   */
  const cycleSort = (key: SortKey) =>
    setSort((s) => {
      if (s.key !== key) return { key, dir: FIRST_DIR[key] }
      if (s.dir === FIRST_DIR[key]) {
        return { key, dir: FIRST_DIR[key] === 'asc' ? 'desc' : 'asc' }
      }
      return DEFAULT_SORT          // 第三下: 回默认(该动了)
    })
  const caret = (...keys: SortKey[]) =>
    keys.includes(sort.key)
      ? (sort.dir === 'asc' ? <ArrowUp className="h-2.5 w-2.5" /> : <ArrowDown className="h-2.5 w-2.5" />)
      : null
  const thBtn = 'inline-flex items-center gap-0.5 hover:text-foreground cursor-pointer'

  const enriched = useQuery({
    queryKey: QK.watchlistEnriched(),
    queryFn: () => api.watchlistEnriched(),
    staleTime: 30_000,
  })
  const positionsQ = useQuery({
    queryKey: QK.watchlistPositions,
    queryFn: () => api.watchlistPositions(),
    staleTime: 30_000,
  })
  // 下面这几个 `?? {}` 都要包 useMemo: 否则每次渲染都是新对象,
  // 会让 rows 的 useMemo 依赖每帧都变, 记忆化等于没做。
  const positions = useMemo(() => positionsQ.data?.positions ?? {}, [positionsQ.data])

  // [R276] 分组归属与分组名录。
  //
  // **enriched 那个接口不带 group_ids** —— 它只出行情, 分组归属在自选列表里。
  // 两份都走各自已有的 QK, 与自选页/侧栏/监控共用同一份 React Query 缓存, 不多一次请求。
  const wlQ = useQuery({
    queryKey: QK.watchlist,
    queryFn: () => api.watchlistList(),
    staleTime: 60_000,
  })
  const groupsQ = useQuery({
    queryKey: QK.watchlistGroups,
    queryFn: () => api.watchlistGroups(),
    staleTime: 60_000,
  })
  const groups = useMemo(() => groupsQ.data?.groups ?? [], [groupsQ.data])
  /** symbol → 所属分组 id 列表(空数组 = 未分组) */
  const groupOf = useMemo(() => {
    const m = new Map<string, string[]>()
    for (const e of wlQ.data?.symbols ?? []) m.set(e.symbol, e.group_ids ?? [])
    return m
  }, [wlQ.data])
  // **归属还没到之前一律不筛。** 空 Map 会让每一只都看着像「未分组」—— 选了某个
  // 分组的人在加载那一瞬间会看到一张空表, 而那不是真的。宁可多显示, 见下面「只看
  // 要动的」同样的取舍。
  const groupsReady = !!wlQ.data
  const inGroup = useMemo(() => (sym: string) => {
    if (groupFilter === G_ALL || !groupsReady) return true
    const ids = groupOf.get(sym) ?? []
    return groupFilter === G_UNGROUPED ? ids.length === 0 : ids.includes(groupFilter)
  }, [groupFilter, groupOf, groupsReady])

  const signalsQ = useQuery({
    queryKey: QK.stockSignals,
    queryFn: () => api.stockSignals(),
    staleTime: 30_000,
    // [R27] 每小时自动拉一次: 定时任务批量刷完信号后, 页面开着也能自动看到新结果
    refetchInterval: 60 * 60 * 1000,
  })
  const signals = useMemo(() => signalsQ.data?.signals ?? {}, [signalsQ.data])

  // [fork 增强] 六态趋势列 —— 批量一次拉取,零 AI 成本,基于日线收盘价
  const trendSyms = useMemo(
    () => ((enriched.data?.rows ?? []) as any[]).map((r) => String(r.symbol)).sort().join(','),
    [enriched.data],
  )
  const trendsQ = useQuery({
    queryKey: QK.stockTrends(trendSyms),
    queryFn: () => api.stockTrends(trendSyms.split(',')),
    enabled: trendSyms.length > 0,
    staleTime: 5 * 60_000,
  })
  const trends: Record<string, TrendInfo> = useMemo(() => trendsQ.data?.trends ?? {}, [trendsQ.data])

  // [R42] Keltner 三档位置 —— 与趋势列同一批标的, 收盘口径。
  // 通道要 ATR 与均线, 实时叠加层只有价格 —— 拿实时价比昨天的通道会得到半新半旧的判定
  const keltnerQ = useQuery({
    queryKey: QK.stockKeltner(trendSyms),
    queryFn: () => api.stockKeltner(trendSyms.split(',')),
    enabled: trendSyms.length > 0,
    staleTime: 5 * 60_000,
  })
  const keltner: Record<string, KeltnerBands> = useMemo(
    () => keltnerQ.data?.keltner ?? {}, [keltnerQ.data])

  // [R178] 「该动了」判定 —— 决策台的默认顺序由它定, 不再由 AI 置信度定。
  // 判定全在后端(纯规则、有测试), 这边只负责按 order/distance 排。
  const urgencyQ = useQuery({
    queryKey: QK.stockUrgency(trendSyms),
    queryFn: () => api.stockUrgency(trendSyms.split(',')),
    enabled: trendSyms.length > 0,
    staleTime: 60_000,     // 比通道短: 距离随实时价动, 陈旧的紧迫度会误导
  })
  const urgency: Record<string, Urgency> = useMemo(
    () => urgencyQ.data?.urgency ?? {}, [urgencyQ.data])
  // [R195] 通道事件与「该动了」同一个端点返回 —— 那里已经同时拿着六态与三档,
  // 事件必须三样齐全(位置 × 方向 × 确认)才判得出, 所以合在那儿算
  const events: Record<string, ChannelEvent> = useMemo(
    () => urgencyQ.data?.event ?? {}, [urgencyQ.data])
  // [R200] 阶段判定同一趟返回。事件是"今天发生了什么", 阶段是"整体走到哪一段、
  // 该盯什么" —— 后者才是能照着做的那句, 之前只有复盘弹窗看得到。
  const phases: Record<string, ChannelPhase> = useMemo(
    () => urgencyQ.data?.phase ?? {}, [urgencyQ.data])
  // [R205] 「怎么办」与「该动了」同一趟返回 —— 它就是在那份判定之上再合成一层
  const plays: Record<string, Playbook> = useMemo(
    () => urgencyQ.data?.playbook ?? {}, [urgencyQ.data])

  // [fork 增强] 持仓出场线(仅持有+填成本的票有;后端顺带把线同步为监控规则)
  const heldWithCost = Object.values(positions).some((p) => p.held && p.cost)
  const exitLinesQ = useQuery({
    queryKey: QK.watchlistExitLines,
    queryFn: () => api.watchlistExitLines(),
    enabled: heldWithCost,
    staleTime: 5 * 60_000,
  })
  const exitLines: Record<string, ExitLine> = useMemo(() => exitLinesQ.data?.lines ?? {}, [exitLinesQ.data])

  // 历史报告整合: 每只自选显示最近一份 AI 分析报告(时间+份数), 点击直接打开报告弹窗。
  // 数据来自 stockAnalysisStore(个股分析页挂载时已 loadHistory, 此处再调一次是安全去重)。
  const { reports } = useHistoryReports()
  useEffect(() => { loadHistory() }, [])
  const reportsBySymbol = useMemo(() => {
    const m = new Map<string, { latest: (typeof reports)[number]; count: number }>()
    for (const r of reports) {  // reports 已按 created_at 降序 → 首见即最新
      const cur = m.get(r.symbol)
      if (cur) cur.count += 1
      else m.set(r.symbol, { latest: r, count: 1 })
    }
    return m
  }, [reports])

  // 手动刷新:重新拉取行情/仓位/信号(不调用 AI、不计费)。盘中本就 SSE 自动刷新,
  // 这个按钮主要给收盘后/关闭实时时,想一键看最新盘后快照用。
  const refreshing = enriched.isFetching || positionsQ.isFetching || signalsQ.isFetching
  const refreshAll = () => {
    qc.invalidateQueries({ queryKey: QK.watchlistEnriched() })
    qc.invalidateQueries({ queryKey: QK.watchlistPositions })
    qc.invalidateQueries({ queryKey: QK.stockSignals })
  }

  const setPos = useMutation({
    mutationFn: ({ symbol, held, cost, weight }: { symbol: string; held: boolean; cost: number | null; weight?: number | null }) =>
      api.setWatchlistPosition(symbol, held, cost, weight),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: QK.watchlistPositions })
      qc.invalidateQueries({ queryKey: QK.watchlistExitLines })
    },
  })

  // 「分析全部/持有」—— 逐只并发(限 3)调用信号接口, 每完成一只即刷新, 显示进度。
  const [progress, setProgress] = useState<{ done: number; total: number } | null>(null)
  const runBatch = async (syms: string[]) => {
    if (progress) return
    if (!syms.length) {
      // 静默 return 会让按钮看起来"点了没反应" —— 空列表必须说明原因
      toast('没有可分析的标的:行情数据未就绪或自选为空(只看持有时需先标记持有)', 'error')
      return
    }
    setProgress({ done: 0, total: syms.length })
    let done = 0
    let failed = 0
    let firstErr = ''
    let idx = 0
    const worker = async () => {
      while (idx < syms.length) {
        const s = syms[idx++]
        try {
          // 注意: 后端信号接口失败时返回 200 + {error} 而非抛 HTTP 错误,
          // 必须检查响应体 —— 否则 AI 挂掉时(如 503)整批"成功"但信号纹丝不动
          const res = await api.generateStockSignal(s)
          if (res?.error) {
            failed++
            if (!firstErr) firstErr = res.error
          }
        } catch (e: any) {
          // 单只失败不阻断, 但必须计数并保留首个错误 —— 全军覆没时(如 AI Key
          // 失效/未配置)若静默吞掉, 用户看到的就是"点了没反应"
          failed++
          if (!firstErr) firstErr = e?.message ?? String(e)
        }
        done++
        setProgress({ done, total: syms.length })
        qc.invalidateQueries({ queryKey: QK.stockSignals })
      }
    }
    await Promise.all(Array.from({ length: Math.min(3, syms.length) }, () => worker()))
    setProgress(null)
    qc.invalidateQueries({ queryKey: QK.stockSignals })
    if (failed) {
      toast(
        `AI 分析完成:成功 ${syms.length - failed} 只,失败 ${failed} 只${firstErr ? ` — ${firstErr}` : ''}`,
        failed === syms.length ? 'error' : 'success',
      )
    }
  }
  const allSyms = () => (enriched.data?.rows ?? []).map((r: any) => String(r.symbol))
  const heldSyms = () => allSyms().filter((sym: string) => positions[sym]?.held)

  // [R131] 批量分析改**增量**: 只跑"需要重算"的。判据见 lib/signalFreshness ——
  // 主要看信号有没有见过最新那根 K 线, 数据没更新就没必要再花一次调用。
  // 单只想强制重跑, 点行内那个 ✨(它不走这套过滤)。
  const staleAll = useMemo(
    () => pickStale(allSyms(), signals, enriched.data?.as_of),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [enriched.data, signals],
  )
  const staleHeld = useMemo(
    () => pickStale(heldSyms(), signals, enriched.data?.as_of),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [enriched.data, signals, positions],
  )

  /** 跑增量批量, 并在结果里如实说明跳过了多少 */
  const runIncremental = (stale: string[], total: number, what: string) => {
    if (!total) {
      toast(`没有可分析的标的:行情数据未就绪或自选为空${what === '持有' ? '(只看持有时需先标记持有)' : ''}`, 'error')
      return
    }
    if (!stale.length) {
      toast(`${what}的 ${total} 只都已是最新分析(基于当前数据基准日), 无需重算`, 'success')
      return
    }
    const skipped = total - stale.length
    if (skipped > 0) toast(`跳过 ${skipped} 只已是最新的, 开始分析 ${stale.length} 只`, 'success')
    runBatch(stale)
  }
  const runAll = () => runIncremental(staleAll, allSyms().length, '全部')
  const runHeld = () => runIncremental(staleHeld, heldSyms().length, '持有')

  // [R276] `scoped` = 过完「只看要动的」「只看持有」但**还没过分组**的那一批。
  // 分组下拉里那些数字要从它算 —— 见下面 groupCounts 的说明。
  const scoped = useMemo(() => {
    const src = enriched.data?.rows ?? []
    return src
      .map((r: any) => {
        const symbol = String(r.symbol)
        const pos: Position | undefined = positions[symbol]
        const sig: Signal | undefined = signals[symbol]
        const close = typeof r.close === 'number' ? r.close : null
        const cost = pos?.cost ?? null
        const pnl = pos?.held && cost && cost > 0 && close != null ? (close - cost) / cost : null
        const trend: TrendInfo | undefined = trends[symbol]
        const exit: ExitLine | undefined = exitLines[symbol]
        const kc: KeltnerBands | undefined = keltner[symbol]
        return {
          symbol, name: r.name ?? symbol, close, changePct: r.change_pct ?? null,
          held: !!pos?.held, cost, weight: pos?.weight ?? null, pnl, sig, trend, exit, kc,
          urg: urgency[symbol],
          ev: events[symbol],
          ph: phases[symbol],
          play: plays[symbol],
          // [R169] 成本来源与批次信息 —— 让"这个成本是我填的还是批次算的"一眼可辨
          costSource: pos?.cost_source ?? null,
          lotCost: pos?.lot_cost ?? null,
          costDriftPct: pos?.cost_drift_pct ?? null,
          lotCount: pos?.lot_count ?? 0,
        }
      })
      .filter((r) => (heldOnly ? r.held : true))
      // [R178] 「要动的」= 前四档(已触发/逼近/刚转折/到轨), 无事档不算。
      // 判定还没回来时不过滤 —— 宁可多显示, 不能让表在加载中看起来是空的。
      .filter((r) => (actionableOnly ? (r.urg ? r.urg.level !== 'idle' : true) : true))
    // [R276] phases/plays 补进依赖表 —— 它们在上面的 map 里被读, 原来漏了。
    // 实际不会串数据(四份都来自同一个 urgencyQ, 一起变), 但漏一个依赖是下一次
    // 拆查询时才会爆的雷, 现在补上不花钱。
  }, [enriched.data, positions, signals, heldOnly, actionableOnly, trends, exitLines,
      keltner, urgency, events, phases, plays])

  const rows = useMemo(() => scoped.filter((r) => inGroup(r.symbol)), [scoped, inGroup])

  /**
   * [R276] 下拉里每一项后面那个数字 = **选它之后你能看到几行**, 不是"这个组里有几只"。
   *
   * 两者在开着「只看要动的」时能差很远。显示"组里有 8 只"而点进去是 0 行, 就又变成
   * 这个项目一直在治的那种毛病: 界面说的和界面做的不是一回事, 而人只会以为它坏了。
   * 菜单标题里把口径写出来, 免得反过来被当成"这个组只剩 3 只票了"。
   *
   * 一只票同时属于两个分组时**两边各计一次** —— 与 lib/watchlistGroupStats.ts 同口径。
   */
  const groupCounts = useMemo(() => {
    const c: Record<string, number> = { ungrouped: 0 }
    for (const g of groups) c[g.id] = 0
    for (const r of scoped) {
      const ids = groupsReady ? (groupOf.get(r.symbol) ?? []) : []
      if (!ids.length) c.ungrouped += 1
      else for (const id of ids) c[id] = (c[id] ?? 0) + 1
    }
    return c
  }, [scoped, groupOf, groups, groupsReady])

  /**
   * [R276] **记住的那个分组被删掉之后, 要有人说一声。**
   *
   * 不管的话: 自选页删掉「稳定币」这一组 → 决策台下次打开永远是空表, 而底下写的是
   * 「自选为空」。那句话是假的, 而且指向完全错误的方向(去自选页添加标的)。
   * 名录到位之后核对一次, 对不上就退回「全部分组」并明说。
   */
  useEffect(() => {
    if (groupFilter === G_ALL || groupFilter === G_UNGROUPED) return
    if (!groupsQ.data) return          // 还没加载完 —— 这时候判"不存在"是冤枉它
    if (groups.some((g) => g.id === groupFilter)) return
    setGroupFilter(G_ALL)
    toast('原先筛选的那个分组已经不在了 —— 已切回「全部分组」', 'error')
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [groupsQ.data, groupFilter])

  const sortedRows = useMemo(() => {
    const val = (r: (typeof rows)[number]): string | number | null => {
      switch (sort.key) {
        // [R178] 档位为主、同档内离触发多近为辅。合成一个可比的数:
        // order*1000 + 距离(百分点), 距离缺失的排在同档最后。
        // 这样同为「逼近」时, 离线 0.3% 的会排在 1.4% 前面。
        case 'urgency': {
          if (!r.urg) return null
          const d = r.urg.distance == null ? 999 : Math.min(r.urg.distance * 100, 998)
          return r.urg.order * 1000 + d
        }
        // [R205] 「怎么办」按急迫程度排 —— order 越小越该先看
        case 'play': return r.play ? r.play.order : 9
        case 'name': return r.name
        case 'changePct': return r.changePct
        case 'pnl': return r.pnl
        case 'trend': return r.trend ? -(TREND_RANK[r.trend.state] ?? 9) : null
        case 'signal': return r.sig ? (SIGNAL_RANK[r.sig.signal] ?? 9) : null
      }
    }
    const arr = [...rows]
    arr.sort((a, b) => {
      const av = val(a), bv = val(b)
      if (av == null && bv == null) return 0
      if (av == null) return 1  // 空值(未分析/无数据)始终垫底
      if (bv == null) return -1
      const c = typeof av === 'string' ? av.localeCompare(String(bv)) : (av as number) - (bv as number)
      return sort.dir === 'asc' ? c : -c
    })
    return arr
  }, [rows, sort, reportsBySymbol])

  // 全自选的持有数 —— **只用来决定「分析持有」那个按钮出不出现**。
  // 那个按钮跑的是全部持有股(heldSyms 走 allSyms), 拿看得见的行数去关它会对不上。
  const heldCount = Object.values(positions).filter((p) => p.held).length
  // [R276] 表头那个「持有 N」改成**当前这张表里**有几只持有。
  //
  // 原来它是全自选的持有数, 和左边的「N 只」(已经被筛过)不是同一批票 ——
  // 开着筛选时那一行读作「12 只 · 持有 8」, 而这 12 只里可能一只持仓都没有。
  // 加了分组筛选之后这个错位会天天撞见, 所以一并纠正: 一行里的两个数出自同一批。
  const heldInView = useMemo(() => rows.filter((r) => r.held).length, [rows])
  // 「要动的」有几只 —— 显示在开关上, 用户不点也能一眼知道今天有没有事
  const actionCount = useMemo(
    () => Object.values(urgency).filter((u) => u.level !== 'idle').length, [urgency])
  // [R276] 自选一共几只(不受任何筛选影响) —— 空表提示和导出页脚要拿它当分母
  const totalRows = enriched.data?.rows?.length ?? 0
  const curGroup = groups.find((g) => g.id === groupFilter)
  const groupLabel = groupFilter === G_ALL ? '全部分组'
    : groupFilter === G_UNGROUPED ? '未分组' : (curGroup?.name ?? '分组')

  // ===== [R157] 定位当前个股 =====
  // 用户: 「加个定位当前个股的功能, 任何适合被选中的都要能当前页面显示, 我不想每次
  // 都找半天」。150 行的表, 搜索框选中一只票之后它在哪一行只能靠肉眼扫。
  //
  // 两条路径, 一个函数:
  //   · 自动 —— currentSymbol 一变(搜索/URL ?symbol=/上次记忆/行内点击)就把那一行
  //     滚进视野。用 `nearest`: 已经看得见的不动(行内点击时不该把表格跳一下)。
  //   · 手动 —— 页头「定位」按钮: 滚到正中 + 闪一下, 让眼睛一下落到它身上。
  // 行还没渲染出来(数据没到 / 刚切换筛选)时记成待定位, rows 一出来就补做。
  const scrollToRow = (sym: string, explicit: boolean) => {
    const el = rowRefs.current[sym]
    if (!el) return false
    el.scrollIntoView({ block: explicit ? 'center' : 'nearest', behavior: 'smooth' })
    setFlash(sym)
    if (flashTimer.current) window.clearTimeout(flashTimer.current)
    flashTimer.current = window.setTimeout(() => setFlash(null), explicit ? 1800 : 1000)
    return true
  }
  const locate = (sym: string, explicit: boolean) => {
    if (!sym) return
    if (scrollToRow(sym, explicit)) return
    // 行不在当前可见列表里 —— 分清是哪种"不在", 别静默
    const loaded = !!enriched.data
    const inWatchlist = (enriched.data?.rows ?? []).some((r: any) => String(r.symbol) === sym)
    if (!loaded) {                       // 数据还没到: 等 rows 出来再滚
      pendingLocate.current = { symbol: sym, explicit }
      return
    }
    if (!inWatchlist) {
      if (explicit) toast(`${sym} 不在自选里, 决策台没有它这一行`, 'error')
      return
    }
    // [R276] 在自选里、却没有这一行 —— 那就是被筛选挡住了。**挡路的可能不止一个**,
    // 所以逐个查、逐个撤, 而不是只撤第一个(只撤一个的话行还是不出现, 看起来就是
    // "点了定位没反应")。原来这里只认「只看持有」, 漏了「只看要动的」——
    // 加分组筛选之后这个洞会更常撞到, 一并补齐。
    const byHeld = heldOnly && !positions[sym]?.held
    const byAction = actionableOnly && urgency[sym]?.level === 'idle'
    const byGroup = !inGroup(sym)
    const blockers = [
      byHeld && '只看持有',
      byAction && '只看要动的',
      byGroup && `只看「${groupLabel}」`,
    ].filter(Boolean) as string[]
    if (!blockers.length) return
    pendingLocate.current = { symbol: sym, explicit: true }
    if (byHeld) setHeldOnly(false)
    if (byAction) setActionableOnly(false)
    if (byGroup) setGroupFilter(G_ALL)
    toast(`这只票被${blockers.join(' / ')}挡住了 —— 已撤掉并定位`, 'success')
  }
  // 行渲染出来之后补做待定位(数据首次到达 / 切换筛选 / 排序变化)
  useEffect(() => {
    const p = pendingLocate.current
    if (p && rowRefs.current[p.symbol]) {
      pendingLocate.current = null
      scrollToRow(p.symbol, p.explicit)
    }
    // [R276] 这里原本挂着一条 eslint-disable —— 它早就没有在压制任何东西了。
    // 留着一条失效的豁免和留着一条假警报是同一件事: 下次真有问题时没人看得见。
  }, [sortedRows])
  // 自动: 选中谁就让谁在视野里
  useEffect(() => {
    if (currentSymbol) locate(currentSymbol, false)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentSymbol])
  // 手动: 页头「定位」
  useEffect(() => {
    if (locateNonce && currentSymbol) locate(currentSymbol, true)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [locateNonce])
  useEffect(() => () => { if (flashTimer.current) window.clearTimeout(flashTimer.current) }, [])

  // [R46] 导出用的行: 只留「结论」列有内容的。三档都在通道中部的票没有位置
  // 信息, 导出来只是占地方。按当前排序导出 —— 你在界面上怎么排, 导出件就怎么排。
  // [R182] 导出**当前列表所见**, 不再另加筛选条件。
  //
  // 以前写死"只导有结论的", R178 又补了"或要动的" —— 那是因为列写死在模板里,
  // 只能靠行筛选控制篇幅。现在列可选了, 导多少由「只看要动的」「只看持有」这两个
  // 已有的开关决定就够了: **屏幕上看到什么就导出什么**, 不再有第三套隐藏规则。
  const exportRows = sortedRows
  const exportHtml = () => {
    if (!exportRows.length) {
      toast('当前没有要动的、也没有「结论」列有内容的标的 —— 无可导出', 'error')
      return
    }
    // [R276] 分母改成**自选总数**。原来传的是筛完之后的 rows.length, 于是页脚永远
    // 写成「导出 12 只(自选共 12 只)」—— 那句话的用处正是让人知道筛掉了多少。
    const blob = new Blob([buildBoardHtml(exportRows, totalRows, exportCols)], { type: 'text/html;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `自选决策台_${new Date().toISOString().slice(0, 10).replace(/-/g, '')}.html`
    a.click()
    URL.revokeObjectURL(url)
    toast(`已导出 ${exportRows.length} 只(自选共 ${totalRows} 只)`, 'success')
  }

  return (
    <div className="rounded-xl border border-border/60 bg-surface/40 overflow-hidden">
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1.5 px-4 py-2.5">
        {/* 决策台就是整页主体, 没有要让位的东西 —— 不再提供折叠 */}
        <span className="flex shrink-0 items-center gap-2">
          <Wallet className="h-3.5 w-3.5 text-sky-400" />
          <span className="text-xs font-medium text-foreground">自选决策台</span>
          {/* [R276] 两个数出自同一批票(当前这张表)。筛掉了多少写在后面, 免得
              「12 只」被读成"我的自选只剩 12 只了"。 */}
          <span className="text-[12px] text-muted">
            {rows.length} 只 · 持有 {heldInView}
            {rows.length < totalRows && (
              <span className="opacity-60"> · 自选共 {totalRows}</span>
            )}
          </span>
          {/* [R198] 角上的感叹号 —— 点开只讲这些词怎么读, 不讲怎么算出来的 */}
        </span>
        <button
          onClick={() => setActionableOnly((v) => !v)}
          title={'只留下有触发的那几只: 出场线已破/逼近、离趋势翻转价 2% 以内、今日刚翻转、'
            + '短期通道到轨。判定是纯规则的(与推送焦点名单同一套到轨口径), AI 不参与。\n'
            + '自选一多, 默认列出全部本身就是噪音 —— 绝大多数票今天确实不需要你看。'}
          className={`text-[12px] px-2 py-0.5 rounded-btn border transition-colors cursor-pointer ${
            actionableOnly ? 'border-amber-400/40 bg-amber-400/10 text-amber-400' : 'border-border bg-base text-muted hover:text-foreground'
          }`}
        >
          只看要动的{actionCount > 0 && <span className="opacity-70">·{actionCount}</span>}
        </button>
        <button
          onClick={() => setHeldOnly((v) => !v)}
          className={`text-[12px] px-2 py-0.5 rounded-btn border transition-colors cursor-pointer ${
            heldOnly ? 'border-accent/40 bg-accent/10 text-accent' : 'border-border bg-base text-muted hover:text-foreground'
          }`}
        >
          只看持有
        </button>
        {/* [R276] 只看某个分组。选中时按分组自己的颜色亮起 —— 与自选页的分组条同一套配色,
            扫一眼就知道现在挂着的是哪一队, 而不用去读文字。 */}
        <WatchlistGroupMenu
          includeAll
          align="left"
          menuLabel="只看哪个分组(数字=当前筛选下能看到几只)"
          counts={groupCounts}
          total={scoped.length}
          preferredGroupId={groupFilter === G_ALL ? undefined
            : groupFilter === G_UNGROUPED ? null : groupFilter}
          onSelect={(g) => setGroupFilter(g === 'all' ? G_ALL : g ?? G_UNGROUPED)}
          title={'只看某一个分组的票。分组在自选页维护 —— 一只票可以同时属于多个分组, '
            + '那它在每个分组里都会出现。\n'
            + '这个选择会记住, 下次打开还是它; 分组万一被删掉会自动退回「全部分组」并提示。'}
          ariaLabel="按分组筛选"
          triggerClassName={`inline-flex items-center gap-1 text-[12px] px-2 py-0.5 rounded-btn border transition-colors cursor-pointer ${
            groupFilter === G_ALL
              ? 'border-border bg-base text-muted hover:text-foreground'
              : curGroup
                ? `${resolveWatchlistGroupColor(curGroup.color).border} ${resolveWatchlistGroupColor(curGroup.color).background} ${resolveWatchlistGroupColor(curGroup.color).text}`
                : 'border-accent/40 bg-accent/10 text-accent'
          }`}
        >
          {groupFilter === G_ALL ? <List className="h-3 w-3" />
            : groupFilter === G_UNGROUPED ? <Inbox className="h-3 w-3" />
              : <Folder className="h-3 w-3" />}
          <span className="max-w-[7rem] truncate">{groupLabel}</span>
          <ChevronDown className="h-3 w-3 opacity-70" />
        </WatchlistGroupMenu>
        <span className="mx-0.5 h-3 w-px shrink-0 bg-border/60" aria-hidden />
        <button
          onClick={refreshAll}
          disabled={refreshing}
          title="刷新行情/仓位/信号快照(不调用 AI、不计费)"
          className="ml-auto inline-flex items-center gap-1 text-[12px] px-2 py-0.5 rounded-btn border border-border bg-base text-muted hover:text-foreground disabled:opacity-60 transition-colors cursor-pointer"
        >
          <RefreshCw className={`h-3 w-3 ${refreshing ? 'animate-spin' : ''}`} />
          刷新
        </button>
        <button
          onClick={() => setExportOpen(true)}
          disabled={!exportRows.length}
          title={exportRows.length
            ? `导出当前列表所见的 ${exportRows.length} 只为自包含 HTML(可存档/打印/转发)。\n`
              + `点开可以选导哪些列 —— 原「六态汇总」就是其中一个预设。\n`
              + `导出的读法与屏幕一致(通道列写「贴上轨」而不是 0.87)。`
            : '当前列表是空的'}
          className="inline-flex items-center gap-1 text-[12px] px-2 py-0.5 rounded-btn border border-sky-400/30 bg-sky-400/10 text-sky-300 hover:bg-sky-400/20 disabled:opacity-50 transition-colors cursor-pointer"
        >
          <Download className="h-3 w-3" />
          导出
          {exportRows.length > 0 && <span className="opacity-70">{exportRows.length}·{exportCols.length}列</span>}
        </button>
        <span className="mx-0.5 h-3 w-px shrink-0 bg-border/60" aria-hidden />
        {heldCount > 0 && (
          <button
            onClick={runHeld}
            disabled={!!progress}
            title={`只对标记为「持有」的自选生成 AI 买卖信号(省调用, 持仓优先)。`
              + `\n[R131] 只跑需要重算的 ${staleHeld.length} 只 —— 信号已看过最新一根 K 线的会跳过`
              + `\n(数据没更新时重跑, 喂给 AI 的还是同一份输入; 超过 ${SIGNAL_TTL_HOURS} 小时仍会重算)`
              + `\n想强制重跑某一只, 点它那行的 ✨`}
            className="inline-flex items-center gap-1 text-[12px] px-2 py-0.5 rounded-btn border border-amber-400/30 bg-amber-400/10 text-amber-300 hover:bg-amber-400/20 disabled:opacity-60 transition-colors cursor-pointer"
          >
            {progress ? <Loader2 className="h-3 w-3 animate-spin" /> : <Sparkles className="h-3 w-3" />}
            AI 分析持有{staleHeld.length > 0 && <span className="text-amber-300/70">·{staleHeld.length}</span>}
          </button>
        )}
        <button
          onClick={runAll}
          disabled={!!progress}
          title={`对自选逐只生成 AI 买卖信号(会调用 AI, 按只计费)。`
            + `\n[R131] 只跑需要重算的 ${staleAll.length} 只 —— 信号已看过最新一根 K 线的会跳过`
            + `\n(数据没更新时重跑, 喂给 AI 的还是同一份输入, 花钱买不到新信息; 超过 ${SIGNAL_TTL_HOURS} 小时仍会重算)`
            + `\n想强制重跑某一只, 点它那行的 ✨`}
          className="inline-flex items-center gap-1 text-[12px] px-2 py-0.5 rounded-btn border border-sky-400/30 bg-sky-400/10 text-sky-300 hover:bg-sky-400/20 disabled:opacity-60 transition-colors cursor-pointer"
        >
          {progress ? <Loader2 className="h-3 w-3 animate-spin" /> : <Sparkles className="h-3 w-3" />}
          {progress
            ? `分析中 ${progress.done}/${progress.total}`
            : <>AI 分析全部{staleAll.length > 0 && <span className="text-sky-300/70">·{staleAll.length}</span>}</>}
        </button>
      </div>

      {/* [R48] 逐日复盘: 趋势 / 三档结论 / 涨停按同一条时间轴排开
          [R228] 27 种组合速查已经并成它的第三个页签 —— 这里只剩一个弹窗 */}
      {review && (
        <StockReviewDialog symbol={review.symbol} name={review.name} tab={review.tab} onClose={() => setReview(null)} />
      )}

      {/* [R28] 关键价位改弹窗后, 页面里已没有 K 线图要让位 —— 表格直接吃满剩余视口高度 */}
      <div className="overflow-auto border-t border-border/60 max-h-[calc(100vh-210px)]">
          <table className="w-full text-xs">
            {/* [R194] 列宽表驱动(宽度与分配原则见 BOARD_COLS)。R178 加「该动」列时**只加了 <th> 没加 <col>**,
                15 对 16, 从那天起每个宽度都串了一位(R193 才发现); R184/R189 改列数
                时又要手动同步 colSpan。改成从 BOARD_COLS 渲染之后, colgroup 与
                colSpan 同源, 只剩「th 数量要跟上」这一处需要人盯。 */}
            <colgroup>
              {BOARD_COLS.map(c => (
                <col key={c.label} style={c.w ? { width: c.w } : undefined} />
              ))}
            </colgroup>
            {/* [R252] **`z-20` 与不透明背景**。用户: 「怎么背后的东西也显示出来了, 层级
                是不是不对」—— 是的。
                原来只有 `sticky top-0`, **没有 z-index**: 行里那个 `opacity-70` 的
                天数徽标(opacity < 1 会自己造一个层叠上下文)于是画到了表头上面,
                滚动时表头被行内容穿透。背景也从 95% 半透明改成实心 —— 表头底下本来
                就是要划走的行, 让它透出来没有任何好处。 */}
            <thead className="sticky top-0 z-20 bg-surface text-[12px] text-muted">
              <tr className="text-left">
                <th className="whitespace-nowrap px-3 py-2.5 font-normal text-center"><button onClick={() => cycleSort('name')} className={thBtn} title="标的名称;第二行是「该动了」判定 —— 已触发 > 逼近 > 刚转折 > 到轨 > 无事,纯规则,AI 不参与">标的{caret('name')}</button></th>
                <th className="whitespace-nowrap px-2 py-2.5 font-normal text-center">
                  <button onClick={() => cycleSort('changePct')}
                          className={`${thBtn} whitespace-nowrap`}
                          title="现价与当日涨跌。点这里按涨跌幅排: 涨最多在前 → 跌最惨在前 → 回默认顺序">
                    {/* [R250] 同上 —— 表头只印列名, 三处一致(标的除外, 它本来就只有一个排序目标) */}
                    现价/涨跌
                    {caret('changePct')}
                  </button>
                </th>
                {/* [R42] Keltner 三档: 一眼看出这只票贴着哪条轨。收盘口径, 与个股分析图表同一组公式 */}
                {/* [R198] 三档合一。排序键仍是三个 —— 点表头在 短→中→长 之间轮换,
                    再点同一个翻方向。合并的是显示不是能力。 */}
                <th className="whitespace-nowrap px-1.5 py-2.5 font-normal text-center">
                  {/* [R211] 排序标记压成同一行的一个小字。原来那个彩色徽标会换行,
                      表头看着就断成两截 —— 用户: 「量化通道我不喜欢这样搞, 不美观」。
                      现在只在名字后面缀一个 6px 的目标名 + 箭头, 永不换行。 */}
                  <button
                    onClick={() => cycleSort('trend')}
                    className={`${thBtn} whitespace-nowrap`}
title={'两行: 六态趋势 / 价格·六态·均线三个尺度转到第几步。\n'
                      + '「走到哪一步」与「还有没有劲」在右边的「结论」列里,\n'
                      + '各自贴着它修饰的那一行(R297 起)。\n\n'
                      + '点这里按六态排: 多头在前 → 空头在前 → 回默认顺序。'}>
                    {/* [R250] 表头**只有「走势」两个字** —— 与「结论」那一列同一条:
                        排序目标是内部分层, 不该印在表头上。轮换照旧, 说明在悬停里。 */}
                    走势
                    {caret('trend')}
                  </button>
                </th>
                {/* [R297] 「进度」那一列并到「结论」里去了 —— 那两个读数是结论的
                    刻度, 不是第四条结论。见下面「结论」表头的说明。 */}
                <th className="whitespace-nowrap px-2 py-2.5 font-normal text-center">
                  <button onClick={() => cycleSort('play')}
                          className={`${thBtn} whitespace-nowrap`}
title={'三行, 每行都是「一个判定 + 它的刻度」:\n'
                            + '  ① 这个价现在算高还是算低 · 已经这样几天 · 这一段走到哪一步了\n'
                            + '  ② 今天该干嘛(五套判定合成的一句话) · 这个速度还撑不撑得住\n'
                            + '  ③ 事件 · 理由 · 另有几处判定不一致\n\n'
                            + '[R297] ①② 右边那两个词原来是独立的「进度」列 —— 它们是结论的刻度,\n'
                            + '不是第四条结论, 所以各自贴回它修饰的那一行。数字全在格子的悬停里。\n\n'
                            + '点这里按「怎么办」的急迫程度排: 按纪律走 > 今天就得动 > 先别动 > '
                            + '盯着 > 留意 > 没事。\n'
                            + '最急在前 → 最闲在前 → 回默认顺序。'}>
                    {/* [R250] 表头**只有「结论」两个字**。用户: 「别搞贵不贵怎么办,
                        我就只想显示结论两个字」。
                        原来点一下会在表头缀出「贵不贵」/「怎么办」标出当前排序目标 ——
                        那是把**内部分层**摆到表头上, 而这一列对外就叫「结论」。
                        排序照旧在两者之间轮换, 说明留在悬停里。 */}
                    结论
                    {caret('play')}
                  </button>
                </th>
                {/* [R284] 账目三列并一列。表头也只剩一个, 排序目标取「浮盈」——
                    「拿没拿」由「只看持有」那个按钮回答, 成本价排序没有决策含义。 */}
                <th className="whitespace-nowrap px-2 py-2.5 font-normal text-center">
                  <button onClick={() => cycleSort('pnl')} className={thBtn}
title={'我在这只票上的账: 拿没拿 / 买入成本 / 现在浮盈多少。\n'
                            + '空仓时这一格只有一个按钮 —— 点它切成持有。\n\n'
                            + '点这里按浮盈排: 赚最多在前 → 亏最多在前 → 回默认顺序。'}>
                    持仓{caret('pnl')}
                  </button>
                </th>
                <th className="whitespace-nowrap px-4 py-2.5 font-normal text-left"><button onClick={() => cycleSort('signal')} className={thBtn}>AI 信号{caret('signal')}</button></th>
              </tr>
            </thead>
            <tbody>
              {rows.length === 0 ? (
                /* [R276] **原来这里一律写「自选为空」, 而那多半是假的。**
                   开着任一筛选把行数筛成 0 时, 这句话既说错了原因、又把人指向完全
                   错误的动作(去自选页添加标的)。现在分两种情况说, 并点名是谁挡的。 */
                <tr><td colSpan={BOARD_COLS.length} className="px-4 py-6 text-center text-muted">
                  {totalRows === 0
                    ? '自选为空 —— 去自选页添加标的'
                    : `自选有 ${totalRows} 只, 但当前筛选(${
                      [actionableOnly && '只看要动的', heldOnly && '只看持有',
                        groupFilter !== G_ALL && `只看「${groupLabel}」`]
                        .filter(Boolean).join(' + ') || '无'
                    })之后一只不剩`}
                </td></tr>
              ) : sortedRows.map((r) => {
                const active = r.symbol === currentSymbol
                // [R169] 只有手填的成本才回写。r.cost 可能是批次派生值, 回写它等于
                // 把派生固化成手填, 之后改批次就不跟着动了。
                const up = (r.changePct ?? 0) > 0
                const down = (r.changePct ?? 0) < 0
                const manualCost = r.costSource === 'manual' ? r.cost : null
                const flashing = r.symbol === flash
                return (
                  // [R157] ref 供定位滚动; scroll-mt 避开 sticky 表头; 定位到时整行闪一下
                  <tr
                    key={r.symbol}
                    ref={(el) => { rowRefs.current[r.symbol] = el }}
                    className={`scroll-mt-10 border-t border-border/30 transition-colors duration-500 hover:bg-elevated/40 ${
                      flashing ? 'bg-accent/25' : active ? 'bg-accent/[0.10]' : ''}`}
                  >
                    {/* 点标的即切换分析(免搜索) */}
                    {/* [R157b] 当前个股整行常驻高亮 + 左侧一道靛蓝边: 搜索后先弹出关键价位
                        弹窗, 闪烁那 1.8 秒多半被弹窗盖住, 关掉弹窗还得一眼认得出它在哪 */}
                    {/* [R209] 「该动了」那两行从这里撤掉了。用户: 「已经有怎么办的列了,
                        标的里面的那些就不多余了」—— **说得对, 那是同一句话印了两遍**:
                        「怎么办」列本来就是把「该动了」合成进去的一层(它是五套判定里的
                        一套), 于是同一只票的「生命线跌破 399.85 已跌破 3.6%」左右各印
                        一份。R198 当初把它挪进标的格是为了省一列, 现在收敛层顶上了,
                        它就成了纯重复。
                        判定本身一个字没动 —— 排序键、「只看要动的」筛选照旧走它。 */}
                    <td className={`${TD_BASE} px-3 text-center border-l-2 ${active ? 'border-l-accent' : 'border-l-transparent'}`}>
                      <button onClick={() => (onPreview ?? onSelect)(r.symbol, r.name)}
                              className="mx-auto flex min-h-[2.25rem] flex-col items-center justify-center gap-0.5 text-center cursor-pointer group">
                        <span className="flex items-center gap-1.5">
                          {active && <Star className="h-2.5 w-2.5 shrink-0 text-accent" />}
                          <span className="max-w-[110px] truncate font-medium text-foreground transition-colors group-hover:text-sky-300">{r.name}</span>
                          <span className={`${NUM} text-[11px] text-muted`}>{r.symbol}</span>
                        </span>
                      </button>
                    </td>
                    {/* [R212] 现价与涨跌并成一格 —— 两个数天生一起读 */}
                    <td className={`${TD_BASE} ${NUM} whitespace-nowrap px-2`}>
                      <span className="text-foreground">{r.close != null ? r.close.toFixed(2) : '—'}</span>
                      <span className={`ml-1.5 text-[12px] ${up ? 'text-red-400' : down ? 'text-emerald-400' : 'text-muted'}`}>
                        {r.changePct != null ? `${r.changePct > 0 ? '+' : ''}${(r.changePct * 100).toFixed(2)}%` : '—'}
                      </span>
                    </td>
                    {/* [R42] Keltner 三档位置 */}
                    <ChannelStateCell
                      trend={r.trend} trendCls={r.trend ? trendBadgeCls(r.trend.state) : undefined}
                      geo={r.kc?.geo} runs={r.kc?.runs} ph={r.ph} kc={r.kc} close={r.close}
                      onOpenReview={() => setReview({ symbol: r.symbol, name: r.name, tab: 'trend' })} />
                    {/* [R212 → R297] 结论 = 贵不贵(位置) + 怎么办(动作) + 事件理由,
                        三行竖排; 每行右边贴着它自己的刻度(走到哪一步 / 快慢),
                        那两个读数原来是独立的「进度」列。 */}
                    <ConclusionCell v={r.kc?.verdict} ev={r.ev} geo={r.kc?.geo} runs={r.kc?.runs}
                                    energy={r.kc?.energy} ph={r.ph} p={r.play}
                                    stateRun={r.kc?.state_run}
                                    onOpen={() => setReview({ symbol: r.symbol, name: r.name, tab: 'verdict' })} />
                    {/* [R284] **账目从三格收成一格。** 用户: 「删除掉浮盈和成本列」。
                        空仓(158/166 行)时这一格只有一个按钮; 持有时才长出成本输入。
                        [R169] 写回时一律用 manualCost 而不是 r.cost —— r.cost 可能是批次
                        派生出来的, 直接回写会把"批次算的"固化成"我填的"。派生值必须保持派生。 */}
                    <td className={`${TD_BASE} whitespace-nowrap px-2 text-center`}>
                      <div className="inline-flex flex-col items-center gap-1">
                        <button
                          onClick={() => setPos.mutate({ symbol: r.symbol, held: !r.held, cost: manualCost, weight: r.weight })}
                          className={`whitespace-nowrap text-[12px] px-1.5 py-0.5 rounded border transition-colors cursor-pointer ${
                            r.held ? 'border-accent/40 bg-accent/10 text-accent' : 'border-border bg-base text-muted hover:border-accent/30'
                          }`}
                        >
                          {r.held ? '持有' : '空仓'}
                        </button>
                        {r.held ? (
                          <span className="inline-flex items-center gap-1">
                            <input
                              type="number"
                              defaultValue={manualCost ?? ''}
                              placeholder={r.costSource === 'lots' && r.lotCost != null ? `批 ${r.lotCost.toFixed(2)}` : '成本'}
                              title={r.costSource === 'lots' && r.lotCost != null
                                ? `成本来自「持仓提醒」页的 ${r.lotCount} 笔批次(数量加权均价 ${r.lotCost.toFixed(2)})。这里留空即跟随批次; 填了数字则以填的为准。`
                                : '买入成本(手填) —— 出场线按它算'}
                              onBlur={(e) => {
                                const v = e.target.value === '' ? null : Number(e.target.value)
                                if (v !== manualCost) setPos.mutate({ symbol: r.symbol, held: true, cost: v, weight: r.weight })
                              }}
                              className={`w-14 h-6 px-1 rounded bg-base border text-[12px] ${NUM} text-right text-foreground focus:outline-none focus:border-accent/50 ${
                                r.costSource === 'lots' ? 'border-accent/35 placeholder:text-accent/70' : 'border-border'
                              }`}
                            />
                            <LotsLink symbol={r.symbol} lotCount={r.lotCount} driftPct={r.costDriftPct} lotCost={r.lotCost} />
                          </span>
                        ) : (
                          // 空仓但批次还挂着 —— 多半是卖出后忘了删批次, 那两条监控规则还在跑
                          r.lotCount > 0
                            ? <LotsLink symbol={r.symbol} lotCount={r.lotCount} driftPct={null} lotCost={null} stale />
                            : null
                        )}
                      </div>
                    </td>
                    {/* AI 信号:徽标 + 时间 + 理由整段换行(不截断)。
                        [R211] **这一列靠左**。用户: 「ai 信号这一列里面的文字都是
                        靠左对齐才好看」—— 说得对: 别的列是短标签, 居中让它们各自
                        落在自己那一格的正中; 这一列是整段会换行的文字, 居中之后
                        每一行的起点都不一样, 读起来像被撕开的。 */}
                    <td className={`${TD_BASE} px-4 !text-left`}>
                      {r.sig ? (
                        <div className="flex flex-col gap-0.5">
                          <div className="flex flex-wrap items-center gap-x-1.5 gap-y-1">
                            <span className={`text-[12px] px-1.5 py-0.5 rounded border ${SIGNAL_META[r.sig.signal]?.cls ?? 'border-border text-muted'}`}>
                              {SIGNAL_META[r.sig.signal]?.label ?? r.sig.signal}
                            </span>
                            <span className="text-[11px] text-muted/50">{fmtAgo(r.sig.created_at)}</span>
                            <AiActions r={r} onAnalyze={onAnalyze} onPriceAlert={onPriceAlert}
                                       reports={reportsBySymbol.get(r.symbol)} />
                          </div>
                          {r.sig.reason && (
                            <span className="text-[12px] text-muted/80 leading-snug whitespace-normal break-words">{r.sig.reason}</span>
                          )}
                          {/* [fork 增强] 到价预案:AI watch_points(涨至/跌至 → 对应操作),提前有准备 */}
                          {(r.sig.watch_points ?? []).length > 0 && (
                            /* [R253] **一个预案一行**, 不再"能挤就挤、挤不下才换行"。
                               用户: 「ai信号显示成这样换行」。
                               原来是 `flex-wrap` —— 同样三个预案, 列宽够时挤成一行、
                               不够时折成两三行, **每一行高度都不一样**, 一屏扫下去
                               行与行对不齐。现在固定竖排: 行是高了点, 但高度一致,
                               而且价位天然对齐(方向词都是三个字 + 等宽数字),
                               眼睛顺着一列往下扫就行。 */
                            <div className="mt-0.5 flex flex-col gap-y-0.5">
                              {(r.sig.watch_points ?? []).map((p, i) => (
                                <span
                                  key={i}
                                  className="inline-flex items-center gap-1.5 text-[12px] font-mono whitespace-nowrap"
                                  title={p.reason ? `${p.label ?? ''} — ${p.reason}` : p.label}
                                >
                                  <span className={`tabular-nums ${p.direction === 'up' ? 'text-red-400' : 'text-emerald-400'}`}>
                                    {p.direction === 'up' ? '↑涨至' : '↓跌至'} {p.price.toFixed(2)}
                                  </span>
                                  {p.action && <span className="text-foreground/80">{p.action}</span>}
                                </span>
                              ))}
                            </div>
                          )}
                        </div>
                      ) : (
                        /* [R284] **从没分析过的票也得够得着** —— AI 分析列撤掉之后
                           操作入口只剩这里; 这一支要是只印「未分析」, 那些没跑过
                           分析的票就再也点不到那个 ✨ 了。 */
                        <span className="flex items-center gap-1.5">
                          <span className="text-[12px] text-muted/50">未分析</span>
                          <AiActions r={r} onAnalyze={onAnalyze} onPriceAlert={onPriceAlert}
                                       reports={reportsBySymbol.get(r.symbol)} />
                        </span>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
      </div>

      {exportOpen && (
        <ExportColumnsDialog
          keys={exportCols}
          onChange={setCols}
          rowCount={exportRows.length}
          onClose={() => setExportOpen(false)}
          onExport={() => { exportHtml(); setExportOpen(false) }}
        />
      )}
    </div>
  )
}
