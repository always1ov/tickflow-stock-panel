import { Fragment, useState, useMemo, useEffect, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Star, ArrowUp, ArrowDown, RefreshCw, Download, FlaskConical } from 'lucide-react'
import { api, type ChannelEvent, type ChannelPhase, type EffectivePosition, type ExitLine, type FocusTier, type KeltnerBands, type TrendInfo, type Urgency } from '@/lib/api'
// [R276] 分组下拉直接复用「加入自选」那个菜单 —— 定位/键盘/点外面关闭/配色全都现成
import { QK } from '@/lib/queryKeys'
import { cn } from '@/lib/cn'
import { toast } from '@/components/Toast'
import { trendBadgeCls } from '@/components/stock-analysis/TrendStateBar'
import type { PreviewView } from '@/components/StockPreviewDialog'
// [R167] 导出与两个单元格从本文件拆出 —— 拆前 933 行, 顶部堆着两张配色表和一整份
// HTML 导出模板, 主组件被压在后面。
import { storage } from '@/lib/storage'
import { buildBoardHtml } from '@/lib/decisionBoardHtmlExport'
import { DEFAULT_EXPORT_KEYS } from '@/lib/decisionBoardExportColumns'
import { ExportColumnsDialog } from '@/components/stock-analysis/decision-board/ExportColumnsDialog'
import { TrendBacktestAllDialog } from '@/components/stock-analysis/TrendBacktestAllDialog'
import { TrendPositionCell, NUM, TD_BASE } from '@/components/stock-analysis/decision-board/cells'
import { LotsLink } from '@/components/stock-analysis/decision-board/LotsLink'
import { Hint } from '@/components/Hint'   // [R323] 表头说明点得开
import { refreshEvery } from '@/lib/refreshRhythm'   // [R333] 刷新节奏一处定义
import { BoardSkeletonRows } from '@/components/stock-analysis/decision-board/BoardSkeletonRows'   // [R324] 首次加载骨架行
import { TH_ROW, THEAD, buttonClass } from '@/components/ui'   // [R451] 全站层级与样式
// [R169] 合并视图(手填 ⊕ 上游批次登记), 字段说明见 api.ts 的 EffectivePosition
type Position = EffectivePosition
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
// 合并后的「持仓」列排 `pnl`(亏最多的先看)。[R435] 「AI 信号」列与它的 `signal` 键一起撤了。
// [R310] `play` 退役 —— **理由与 R254 当初那一串逐字相同: 它点不到了。**
// 「怎么办」整列删掉之后它的表头没了, 留着就是死键。
type SortKey = 'urgency' | 'name' | 'changePct' | 'trend' | 'pnl'
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
/**
 * [R323] 表头说明 —— **一份字两个出口**: 排序按钮上的 `title`(桌面悬停, 老习惯)
 * 与旁边那个「?」(点一下 / 触屏摊开)。原来这些字内联在各个 `title=` 里, 只有
 * 悬停一条路; 提成常量是为了两处**同一份**, 不誊抄。
 */
const HEAD_TIPS = {
  name: '标的名称;第二行是「该动了」判定 —— 已触发 > 逼近 > 刚转折 > 到轨 > 无事,纯规则,AI 不参与',
  changePct: '现价与当日涨跌。点这里按涨跌幅排: 涨最多在前 → 跌最惨在前 → 回默认顺序',
  // [R425] 「走势」「位置」两列并成一列, 两份表头说明并成一份。原来 trend 那份还写着
  // 「右边的『档位』列」—— 那一列 R308 就改名「位置」了, 一句过期的指路, 顺手去掉。
  trendPos: '左右两半, 各两行:\n'
    + '  左 ① 六态趋势  ② 转折后第几天(转折当天写「今天转折」)\n'
    + '  右 ① 位置名 —— 收盘价落在**短期通道**的哪一档\n'
    + '       (破上轨 / 贴上轨 / 通道内 / 贴下轨 / 破下轨)。扫表时看这一行的颜色。\n'
    + '     ② 离那条轨还有多远 —— **价格口径**, 现价还要动多少个百分点才碰到它。\n'
    + '       口径 (轨价 − 现价) / 现价, 与出场线、六态翻转距离是同一个算法。\n'
    + '       看哪条轨跟着位置名走;「通道内」时取更近的那一条(先撞上的就是它)。\n\n'
    + '短中长三档、27 格组合码、三个尺度对齐到第几步, 都在各半的悬停里。\n'
    + '整格一个按钮, 点开是复盘(逐日趋势 / 通道档位 / 组合速查)。\n\n'
    + '点这里按六态排: 多头在前 → 空头在前 → 回默认顺序。',
  pnl: '我在这只票上的账: 拿没拿 / 买入成本 / 现在浮盈多少。\n'
    + '空仓时这一格只有一个按钮 —— 点它切成持有。\n\n'
    + '点这里按浮盈排: 赚最多在前 → 亏最多在前 → 回默认顺序。',
} as const
const BOARD_COLS = [
  // [R309] 9.5% → 13%。名称原来截在 110px, 五个字以上就带省略号 ——
  // **认票这件事上省 3% 是最亏的**: 认错票之后后面六列全白读。
  // [R435] AI 信号那一列(26%)撤掉后重新分: 18/10/34/12 → 22/12/48/18。
  // 大头给「走势/位置」—— 它是这张表里唯一的判断列, 最需要地方。
  { label: '标的', w: '22%' },
  // [R212] 「现价」「涨跌」合成一列。用户: 「这两列合成为『现价/涨跌』这样为一列」。
  // 两个数天生一起读 —— 拆成两列只是让眼睛多跳一次。
  { label: '现价/涨跌', w: '12%' },
  // [R212] 「止盈线」那一列撤掉了。用户: 「止盈线这一列不要了」。
  // **信息没丢**: 出场线破了或逼近, 「结论」列会直接判成「按纪律走」/「盯着」
  // 并把线价写在徽标上 —— 那比单独一列更早进视线。排序键与判定都还在。
  // [R211] 「量化通道」(测量) + 「通道态势」(结论) + 「趋势」(六态) 三列并一列。
  // 六态与通道阶段答的是同一个问题(往哪走), 只是方法不同 —— 放一格里,
  // 它们什么时候一致、什么时候打架, 上下一对就看见了。
  // [R425] 「走势」20% + 「位置」14% 并成一列, 宽度原数相加 —— 总和仍是 100。
  // [R520] 单行之后持仓那一格要横着放「持有 + 成本框 + 出场线」, 从这里拿 4% 给它: 48/18 → 44/22。
  { label: '走势/位置', w: '44%' },
  // [R277 加, R297 删] 「进度」那一列并进「结论」了。用户: 「个股分析页面的
  // 进度列和结论列看看怎么合并和显示哪些内容」。
  // [R212] 「贵不贵」(位置) + 「怎么办」(动作) 合成一列, 竖排, 摆在 AI 之前。
  // [R307] 那一列又拆成两列: 「档位」只说位置, 「怎么办」独立。
  // [R308] 「位置」砍到只剩两个原始读数: 短期通道位置 + 三档组合码。
  //
  // [R310] **「怎么办」整列删掉。** 用户: 「那就删除了怎么办」(在我把影响列清
  // 之后)。它是五套判定的收敛层 —— 出场线/六态/通道档位/通道阶段/AI 信号,
  // 按「纪律 > 时点 > 分歧 > 形态」挑出该说的那一句, 并指出它们互相不一致。
  //
  // **删掉之后这张表只剩读数, 没有合成的结论**: 走势说方向、位置说坐标、
  // AI 说别人的意见, 没有一列回答「所以今天我该干嘛」。这是用户看过影响清单
  // 之后的决定, 不是疏漏 —— 判定层(`services/stock_playbook.py` 与它那 36 条
  // 测试)一个字没动, 接口照旧返回 `playbook`, 只是界面不再读它。
  //
  // **一处真丢的信息已经接住了**: R212 撤「止盈线」那一列时的对价写在这儿 ——
  // 「信息没丢: 出场线破了或逼近, 结论列会把线价写在徽标上」。查下来 `r.exit`
  // 在整张表上零个渲染点, 那条线只从「怎么办」的 `price` 露过面。所以它搬进
  // 「持仓」列 —— 出场线本来就是**关于我这笔仓位**的事, 归「我的账」比归
  // 「凭什么」更准。
  { label: '持仓', w: '22%' },
  // [R284 → R435] 「AI 分析」整列并进「AI 信号」列(R284), R435 连「AI 信号」列一起撤了 ——
  // 用户: 「清除了ai信号这部分, 后续我打算用斐波那契二型重做这部分」。那一列头一行的
  // 三个入口(报告胶囊 / ✨AI 四维分析 / 🔔点位提醒)按用户选的一起去掉: AI 四维分析在
  // 个股弹窗里有入口(当天分析过会问要不要看报告), 点位提醒在弹窗里双击图就能设。
  //
  // [R309] **上面这些宽度加起来必须正好 100%, 而且一列都不许留空。**
  //
  // 这不是强迫症: 只要有一列写成 `w: ''`, 它就成了**余量的垃圾桶** —— 谁拿着
  // 余量, 谁就会在没人注意的时候长大, 而且长得无声无息(AI 信号那一列正是这么
  // 从「一列」变成「半张表」的)。加起来正好 100 之后, 想给谁加宽就必须从另一列
  // 身上明写着拿 —— **宽度从此是一笔要记账的东西。**
  //
  // `table-auto` 下百分比仍然只是建议(内容顶得开它), 所以这条守的是**设计
  // 意图**; 真正的闸门是各单元格里那道 `max-w`。两者缺一不可, 守卫各钉一条。
] as const

// [fork 增强] 六态排序权重:多头在前(上涨趋势 → 下跌趋势)
const TREND_RANK: Record<string, number> = { UT: 0, NR: 1, SR: 2, SREA: 3, NREA: 4, DT: 5 }

// [R276] 分组筛选的两个哨兵。用字符串而不是 null —— 见 storage.boardGroupFilter 的说明。
/** 自选决策台 —— 个股分析页的整页主体: 一行一只自选, 点标的即弹出关键价位分析,
 *  并可标记仓位/成本、纵观对比浮盈。[R28] 起不再折叠(整页就它一个, 没有要让位的东西)。 */
export function WatchlistDecisionBoard({ currentSymbol, onSelect, onPreview, locateNonce }: {
  currentSymbol: string
  /** [R157] 页头「定位」按钮每按一次 +1: 把当前个股那一行滚到视野正中并闪一下 */
  locateNonce?: number
  onSelect: (symbol: string, name: string) => void
  /** [R103] 点标的名称时打开整合版个股弹窗(最近查看+随意切换); 未传时退回仅选中。
      [R427] 第三个参数是落在哪一页: 点「走势/位置」传 'review' —— 复盘并进了这个弹窗 */
  onPreview?: (symbol: string, name: string, view?: PreviewView) => void
}) {
  const qc = useQueryClient()
  // [R157] 定位当前个股: 行引用 + 闪烁高亮 + "行还没渲染出来"时的待定位
  const rowRefs = useRef<Record<string, HTMLTableRowElement | null>>({})
  const pendingLocate = useRef<{ symbol: string; explicit: boolean } | null>(null)
  const [flash, setFlash] = useState<string | null>(null)
  const flashTimer = useRef<number | undefined>(undefined)
  // [R182] 导出选列。六态汇总弹窗已并进导出 —— 勾上趋势那几列就是它。
  const [exportOpen, setExportOpen] = useState(false)
  // [R312] 全量阈值回测的弹窗。只在点开时挂载 —— 它一挂载什么都不跑,
  // 真正开跑要在里面再点一次(阈值是会落盘的东西, 不该被一次误触带起来)。
  const [backtestAllOpen, setBacktestAllOpen] = useState(false)
  const [exportCols, setExportCols] = useState<string[]>(
    () => storage.boardExportCols.get(DEFAULT_EXPORT_KEYS) ?? DEFAULT_EXPORT_KEYS)
  const setCols = (keys: string[]) => {
    setExportCols(keys)
    storage.boardExportCols.set(keys)
  }
  // [R48 → R427] 逐日复盘原来是这里自己挂的一个弹窗。用户: 「两个弹窗融合成一个,
  // 以后点个股名称还是走势位置按钮都跳转融合后的弹窗」—— 现在它是个股弹窗的「复盘」页,
  // 由页面那一个 StockPreviewDialog 统一打开(见 onPreview 的第三个参数)。
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
  // [R530] 「只看要动的 / 只看转折 / 只看持有 / 只看哪个分组」四个筛选一起撤了(R178 / R330 / R276 / R521)。
  // 用户: 「个股分析页面只显示那些我需要看的, 不然一大堆。自选页面里面才是一大堆, 当做个收藏夹」。
  // 这一页不再是"全量自选 + 筛选", 而是三段固定的名单: 今天要动的 / 持有·无事 / 计划中·贴轨,
  // 其余的票在这一页根本不出现 —— 要看随便哪只, 页头搜索直接开弹窗。分组是仓库(自选页)的事。
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

  // [R530] 焦点名单(持有 / 计划中 / 贴轨 / 观察, 含钉住·静音之后的有效档) —— 第三段「计划中 · 贴轨」从它来。
  // 与监控中心的焦点名单栏同一个查询键, 不多发请求; 口径由后端 focus_list 定, 这里只分档。
  const focusQ = useQuery({ queryKey: QK.focus, queryFn: api.focusList, staleTime: 30_000 })
  const focusTier = useMemo(() => {
    const m = new Map<string, FocusTier>()
    for (const it of focusQ.data?.items ?? []) m.set(it.symbol, it.effective)
    return m
  }, [focusQ.data])

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
    // [R333] 六态是**日线派生**的: 收盘落盘才会翻面, 盘中不会变 —— 所以走
    // `derived` 档而不是 `live`。行情那一侧有 SSE 管着(`watchlist-enriched`
    // 在失效列表里), 但**判定层不在那个列表里**, 不自己刷就一直是打开那一刻的。
    refetchInterval: refreshEvery('derived'),
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
    // [R333] 「该动了」**随实时价动**(距离出场线还有多远、离翻转价多近), 所以
    // 走 `live` 档 —— 盘中一分钟一刷, 盘后半小时。上面那句注释说的就是这件事,
    // 但在这之前它只有 staleTime 没有 refetchInterval: 没人碰这个页面时不会重取,
    // 「陈旧的紧迫度会误导」那句话一直没被兑现。
    refetchInterval: refreshEvery('live'),
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
  // [R310] `plays` 那一份不再取用 —— 「怎么办」列删了, 前端没有读者。
  // **接口照旧返回 `playbook`**(后端判定层一个字没动), 这里只是不接。

  // [fork 增强] 持仓出场线(仅持有+填成本的票有;后端顺带把线同步为监控规则)
  const heldWithCost = Object.values(positions).some((p) => p.held && p.cost)
  const exitLinesQ = useQuery({
    queryKey: QK.watchlistExitLines,
    queryFn: () => api.watchlistExitLines(),
    enabled: heldWithCost,
    staleTime: 5 * 60_000,
  })
  const exitLines: Record<string, ExitLine> = useMemo(() => exitLinesQ.data?.lines ?? {}, [exitLinesQ.data])

  // 手动刷新:重新拉取行情/仓位(不调用 AI、不计费)。盘中本就 SSE 自动刷新,
  // 这个按钮主要给收盘后/关闭实时时,想一键看最新盘后快照用。
  const refreshing = enriched.isFetching || positionsQ.isFetching
  const refreshAll = () => {
    qc.invalidateQueries({ queryKey: QK.watchlistEnriched() })
    qc.invalidateQueries({ queryKey: QK.watchlistPositions })
  }

  const setPos = useMutation({
    mutationFn: ({ symbol, held, cost, weight }: { symbol: string; held: boolean; cost: number | null; weight?: number | null }) =>
      api.setWatchlistPosition(symbol, held, cost, weight),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: QK.watchlistPositions })
      qc.invalidateQueries({ queryKey: QK.watchlistExitLines })
    },
  })

  // 全部自选的行(带上趋势 / 通道 / 急迫度 / 仓位); 分段在下面 `sections` 里做
  const rows = useMemo(() => {
    const src = enriched.data?.rows ?? []
    return src
      .map((r: any) => {
        const symbol = String(r.symbol)
        const pos: Position | undefined = positions[symbol]
        const close = typeof r.close === 'number' ? r.close : null
        const cost = pos?.cost ?? null
        const pnl = pos?.held && cost && cost > 0 && close != null ? (close - cost) / cost : null
        const trend: TrendInfo | undefined = trends[symbol]
        const exit: ExitLine | undefined = exitLines[symbol]
        const kc: KeltnerBands | undefined = keltner[symbol]
        return {
          symbol, name: r.name ?? symbol, close, changePct: r.change_pct ?? null,
          held: !!pos?.held, cost, weight: pos?.weight ?? null, pnl, trend, exit, kc,
          urg: urgency[symbol],
          ev: events[symbol],
          ph: phases[symbol],
          // [R169] 成本来源与批次信息 —— 让"这个成本是我填的还是批次算的"一眼可辨
          costSource: pos?.cost_source ?? null,
          lotCost: pos?.lot_cost ?? null,
          costDriftPct: pos?.cost_drift_pct ?? null,
          lotCount: pos?.lot_count ?? 0,
        }
      })
    // [R276] phases/plays 补进依赖表 —— 它们在上面的 map 里被读, 原来漏了。
  }, [enriched.data, positions, trends, exitLines, keltner, urgency, events, phases])

  const sortRows = useMemo(() => (list: typeof rows) => {
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
        case 'name': return r.name
        case 'changePct': return r.changePct
        case 'pnl': return r.pnl
        case 'trend': return r.trend ? -(TREND_RANK[r.trend.state] ?? 9) : null
      }
    }
    const arr = [...list]
    arr.sort((a, b) => {
      const av = val(a), bv = val(b)
      if (av == null && bv == null) return 0
      if (av == null) return 1  // 空值(未分析/无数据)始终垫底
      if (bv == null) return -1
      const c = typeof av === 'string' ? av.localeCompare(String(bv)) : (av as number) - (bv as number)
      return sort.dir === 'asc' ? c : -c
    })
    return arr
  }, [sort])

  /**
   * [R530] 三段固定名单 —— 这一页只放今天要看的:
   *   ① 今天要动的: 急迫度前四档(已触发 / 逼近 / 刚转折 / 到轨), 持有与否都算
   *   ② 持有 · 无事: 拿着但今天没事的
   *   ③ 计划中 · 贴轨: 焦点名单里过推送门的那两档(含钉住), 还没拿、今天也没事的
   * 一只票只出现一次, 按①②③的先后归段。观察档、无事的票不在这一页出现。
   *
   * **急迫度没回来时①不放行全部。** 原来「只看要动的」在判定缺失时一律放行 —— 接口一超时,
   * 202 只全体变成"要动的"(用户手机截图就是这样)。现在缺就明说缺, 不拿全量冒充。
   */
  const urgencyReady = !!urgencyQ.data
  const sections = useMemo(() => {
    const act = urgencyReady ? rows.filter((r) => r.urg && r.urg.level !== 'idle') : []
    const inAct = new Set(act.map((r) => r.symbol))
    const held = rows.filter((r) => r.held && !inAct.has(r.symbol))
    const focus = rows.filter((r) => {
      if (r.held || inAct.has(r.symbol)) return false
      const t = focusTier.get(r.symbol)
      return t === 'plan' || t === 'band'
    })
    return [
      { key: 'act', title: '今天要动的', rows: sortRows(act) },
      { key: 'held', title: '持有 · 无事', rows: sortRows(held) },
      { key: 'focus', title: '计划中 · 贴轨', rows: sortRows(focus) },
    ] as const
  }, [rows, urgencyReady, focusTier, sortRows])
  const sortedRows = useMemo(() => sections.flatMap((sec) => sec.rows), [sections])

  // [R435] 「全自选持有数」(heldCount)原来只用来决定「AI 分析持有」那个按钮出不出现,
  // 按钮随 AI 信号撤了, 它也跟着撤。
  // [R276] 表头那个「持有 N」改成**当前这张表里**有几只持有。
  //
  // 原来它是全自选的持有数, 和左边的「N 只」(已经被筛过)不是同一批票 ——
  // 开着筛选时那一行读作「12 只 · 持有 8」, 而这 12 只里可能一只持仓都没有。
  // 加了分组筛选之后这个错位会天天撞见, 所以一并纠正: 一行里的两个数出自同一批。
  const heldInView = useMemo(() => sortedRows.filter((r) => r.held).length, [sortedRows])
  // [R276] 自选一共几只(不受任何筛选影响) —— 空表提示和导出页脚要拿它当分母
  const totalRows = enriched.data?.rows?.length ?? 0

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
    // [R530] 在自选里、却不在这一页 —— 它今天不在要看的名单里(不持有、没事、也不在计划中 / 贴轨)。
    // 不再有筛选可撤; 要看它, 页头搜索直接开弹窗。定位按钮按下去时说一声, 别静默。
    if (explicit) toast(`${sym} 今天不在这一页的名单里(不持有、没事、也不在计划中 / 贴轨)—— 用搜索打开它`, 'error')
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
      toast('当前没有要动的、也没有「档位」列有内容的标的 —— 无可导出', 'error')
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
    // [R451] 全站迁移(docs/ui-hierarchy.md): 外框是卡片, 标题是 L3, 工具条按钮用全站按钮,
    // 选中一律反相 —— 原来四个开关各亮一种颜色(琥珀 / 天蓝 / 强调色), 同一件事四种说法
    <div className="overflow-hidden rounded-card border border-border bg-surface">
      <div className="flex flex-wrap items-center gap-x-2 gap-y-2 px-4 py-3">
        {/* 决策台就是整页主体, 没有要让位的东西 —— 不再提供折叠 */}
        <span className="flex shrink-0 items-center gap-2">
          {/* [R520] 「自选决策台」那个标题撤了 —— 这张表就是整页, 页头已经写着「个股分析」,
              同一页两个名字读的人得先确认是不是一回事。只数留着。 */}
          {/* [R276] 两个数出自同一批票(当前这张表)。筛掉了多少写在后面, 免得
              「12 只」被读成"我的自选只剩 12 只了"。 */}
          {/* [R530] 「N 只」是这一页三段加起来的数; 「自选共 M」一直写着 —— 这一页本来就只放自选的一小部分 */}
          <span className="text-xs text-muted">
            {sortedRows.length} 只 · 持有 {heldInView}
            <span className="opacity-60"> · 自选共 {totalRows}</span>
          </span>
          {/* [R198] 角上的感叹号 —— 点开只讲这些词怎么读, 不讲怎么算出来的 */}
        </span>
        <button
          onClick={refreshAll}
          disabled={refreshing}
          title="刷新行情/仓位/信号快照(不调用 AI、不计费)"
          className={buttonClass({}, 'ml-auto')}
        >
          <RefreshCw className={`h-3.5 w-3.5 ${refreshing ? 'animate-spin' : ''}`} />
          <span className="sr-only">刷新</span>
        </button>
        {/* [R312] 「全量回测」。用户: 「在刷新后面加个一键回测所有个股」。

            **摆在「刷新」紧后面是有讲究的**: 这一带全是不计费的东西。单只那个
            弹窗跑完网格还会问一次 AI 当调参顾问, 批量不问 —— 166 只票就是 166
            次调用, 而规则建议本身是纯函数、可复算。要听 AI 的逐只打开, 入口还在。

            **它只回测, 不落盘。** 阈值一改这只票的六态整条历史跟着变(决策台的
            方向、打分的趋势硬门槛、按转折买卖的全部统计都从它出), 而且没有
            「撤销上一次批量」这回事。所以跑完先摆结果, 勾了才写。 */}
        <button
          onClick={() => setBacktestAllOpen(true)}
          disabled={!sortedRows.length}
          title={sortedRows.length
            ? `对当前列表所见的 ${sortedRows.length} 只各按 3%~15% 阈值网格跑一遍六态状态机。\n`
              + '纯计算,不调用 AI、不计费。\n\n'
              + '跑完先摆结果(现在多赚 → 改后多赚),勾选之后才写入 ——\n'
              + '阈值一改,这只票的六态整条历史都会跟着重算。'
            : '当前列表是空的'}
          className={buttonClass()}
        >
          <FlaskConical className="h-3.5 w-3.5" />
          <span className="sr-only">全量回测</span>
        </button>
        <button
          onClick={() => setExportOpen(true)}
          disabled={!exportRows.length}
          title={exportRows.length
            ? `导出当前列表所见的 ${exportRows.length} 只、${exportCols.length} 列为自包含 HTML(可存档/打印/转发)。\n`
              + `点开可以选导哪些列 —— 原「六态汇总」就是其中一个预设。\n`
              + `导出的读法与屏幕一致(通道列写「贴上轨」而不是 0.87)。`
            : '当前列表是空的'}
          className={buttonClass()}
        >
          <Download className="h-3.5 w-3.5" />
          <span className="sr-only">导出</span>
        </button>
        {/* [R435] 「AI 分析持有 / AI 分析全部」两个批量按钮随 AI 信号撤了 */}
      </div>


      {/* [R28] 关键价位改弹窗后, 页面里已没有 K 线图要让位 —— 表格直接吃满剩余视口高度 */}
      <div className="overflow-auto border-t border-border/60 max-h-[calc(100vh-210px)]">
          {/* [R526] 手机(< sm)不再横滑: 表退化成一行一块 —— table / tbody 变块, thead 藏起, tr 变 flex-wrap,
              四格按 名字·价 / 持仓 / 走势·位置 折成两三行(见各 td 的 max-sm:)。用户: 「手机版现在不搞左右滑动,
              能否像监控中心那样, 每一行就能显示完整」。R395 的「首列钉住 + 横滑」在这张表上就此撤掉。 */}
          <table className="w-full text-xs max-sm:block">
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
            {/* [R451] 表头是标签那一级(11px 灰, 浅灰底条), 与全站表格同一套 */}
            <thead className={cn(THEAD, 'z-20 max-sm:hidden')}>
              <tr className={cn(TH_ROW, 'text-left')}>
                {/* [R395] 窄屏曾把「标的」钉在左边缘(sticky left-0 + lg:static), 让横滑时认得出是哪只票;
                    [R526] 手机不再横滑, 钉住随之撤掉, 表头在手机上整个藏起。 */}
                <th className="whitespace-nowrap px-3 py-2 font-normal text-left"><button onClick={() => cycleSort('name')} className={thBtn} title={HEAD_TIPS.name}>标的{caret('name')}</button><Hint title={HEAD_TIPS.name} className="ml-0.5" /></th>
                <th className="whitespace-nowrap px-2 py-2 font-normal text-right">
                  <button onClick={() => cycleSort('changePct')}
                          className={`${thBtn} whitespace-nowrap`}
                          title={HEAD_TIPS.changePct}>
                    {/* [R250] 同上 —— 表头只印列名, 三处一致(标的除外, 它本来就只有一个排序目标) */}
                    现价/涨跌
                    {caret('changePct')}
                  </button>
                  <Hint title={HEAD_TIPS.changePct} className="ml-0.5" />
                </th>
                {/* [R42] Keltner 三档: 一眼看出这只票贴着哪条轨。收盘口径, 与个股分析图表同一组公式 */}
                {/* [R198] 三档合一。排序键仍是三个 —— 点表头在 短→中→长 之间轮换,
                    再点同一个翻方向。合并的是显示不是能力。 */}
                <th className="whitespace-nowrap px-2 py-2 font-normal text-left">
                  {/* [R211] 排序标记压成同一行的一个小字。原来那个彩色徽标会换行,
                      表头看着就断成两截 —— 用户: 「量化通道我不喜欢这样搞, 不美观」。
                      [R250] 表头**只印列名** —— 排序目标是内部分层, 不该印在表头上。
                      [R425] 「走势」「位置」两列并成一列, 列名照 R212「现价/涨跌」的写法。
                      排序仍只有一个目标(六态): 位置那半 R307 起就不挂排序。 */}
                  <button
                    onClick={() => cycleSort('trend')}
                    className={`${thBtn} whitespace-nowrap`}
                    title={HEAD_TIPS.trendPos}>
                    走势/位置
                    {caret('trend')}
                  </button>
                  <Hint title={HEAD_TIPS.trendPos} className="ml-0.5" />
                </th>
                {/* [R284] 账目三列并一列。表头也只剩一个, 排序目标取「浮盈」——
                    「拿没拿」由「只看持有」那个按钮回答, 成本价排序没有决策含义。 */}
                <th className="whitespace-nowrap px-2 py-2 font-normal text-left">
                  <button onClick={() => cycleSort('pnl')} className={thBtn}
                          title={HEAD_TIPS.pnl}>
                    持仓{caret('pnl')}
                  </button>
                  <Hint title={HEAD_TIPS.pnl} className="ml-0.5" />
                </th>
              </tr>
            </thead>
            <tbody className="max-sm:block">
              {/* [R324] 自选列表还没回来时先画骨架行 —— 原来这段时间印的是「自选为空」,
                  加载中的表看起来像空表, 把人指去了错误的地方。只在 isLoading(本地
                  没有缓存)时出现; 后台重取时上一份行还在, 不盖。 */}
              {enriched.isLoading ? (
                <BoardSkeletonRows cols={BOARD_COLS.length} />
              ) : totalRows === 0 ? (
                <tr className="max-sm:block"><td colSpan={BOARD_COLS.length} className="px-4 py-6 text-center text-muted max-sm:block">
                  自选为空 —— 去自选页添加标的
                </td></tr>
              ) : sections.map((sec) => (sec.rows.length === 0 && sec.key !== 'act') ? null : (
                <Fragment key={sec.key}>
                  {/* [R530] 段头: 一行小字, 与监控中心的日期分组条同一个形状 */}
                  <tr className="max-sm:block">
                    <td colSpan={BOARD_COLS.length} className="px-3 pb-1 pt-3 text-micro font-medium text-muted max-sm:block">
                      {sec.title} <span className="font-mono tabular-nums">{sec.rows.length}</span>
                    </td>
                  </tr>
                  {sec.rows.length === 0 && (
                    /* 只有「今天要动的」会空着还画出来 —— 「今天没事」本身就是信息; 判定没回来时明说, 不拿全量冒充 */
                    <tr className="max-sm:block"><td colSpan={BOARD_COLS.length} className="px-3 py-3 text-xs text-muted max-sm:block">
                      {urgencyQ.isError ? '急迫度没算出来 —— 点右上角刷新再试'
                        : !urgencyReady ? '急迫度还在算…'
                          : '今天没有要动的'}
                    </td></tr>
                  )}
                  {sec.rows.map((r) => {
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
                    className={`scroll-mt-10 border-t border-border/30 transition-colors duration-500 hover:bg-elevated/40 max-sm:flex max-sm:flex-wrap max-sm:items-center max-sm:gap-x-3 max-sm:gap-y-1 max-sm:px-3 max-sm:py-2 ${
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
                    {/* [R395] 这一格曾在窄屏钉住(sticky left-0 + 不透明底), [R526] 随横滑一起撤掉;
                        手机上它是第一行的左半(名字 · 代码), 撑满剩下的宽度, 价格在右边。 */}
                    <td className={`${TD_BASE} px-3 border-l-2 max-sm:order-1 max-sm:min-w-0 max-sm:grow max-sm:basis-40 max-sm:py-0 max-sm:pr-0 max-sm:pl-2 ${active ? 'border-l-accent' : 'border-l-transparent'}`}>
                      {/* [R520] 单行、左对齐 —— 原来名字与代码竖着居中在一个 36px 高的按钮里, 是全表行高 80px 的根源之一 */}
                      <button onClick={() => (onPreview ?? onSelect)(r.symbol, r.name)}
                              className="flex max-w-full items-center text-left cursor-pointer group">
                        <span className="flex min-w-0 items-center gap-1.5">
                          {active && <Star className="h-2.5 w-2.5 shrink-0 text-accent" />}
                          <span className="max-w-[140px] truncate font-medium text-foreground transition-colors group-hover:text-accent">{r.name}</span>
                          <span className={`${NUM} text-micro text-muted`}>{r.symbol}</span>
                        </span>
                      </button>
                    </td>
                    {/* [R212] 现价与涨跌并成一格 —— 两个数天生一起读 */}
                    <td className={`${TD_BASE} ${NUM} whitespace-nowrap px-2 text-right max-sm:order-2 max-sm:px-0 max-sm:py-0`}>
                      <span className="text-foreground">{r.close != null ? r.close.toFixed(2) : '—'}</span>
                      <span className={`ml-1.5 text-xs ${up ? 'text-bull' : down ? 'text-bear' : 'text-muted'}`}>
                        {r.changePct != null ? `${r.changePct > 0 ? '+' : ''}${(r.changePct * 100).toFixed(2)}%` : '—'}
                      </span>
                    </td>
                    {/* [R425] 「走势」「位置」两格并成一格、一个按钮(见 TrendPositionCell)。
                        [R308] 位置那半只有两个原始读数: 短期通道位置 + 离轨距离;
                        那十档判定在复盘的「通道档位」页。 */}
                    <TrendPositionCell
                      trend={r.trend} trendCls={r.trend ? trendBadgeCls(r.trend.state) : undefined}
                      geo={r.kc?.geo} runs={r.kc?.runs} ph={r.ph} kc={r.kc} close={r.close}
                      ev={r.ev} energy={r.kc?.energy} stateRun={r.kc?.state_run}
                      onOpen={() => (onPreview
                        ? onPreview(r.symbol, r.name, 'review')
                        : onSelect(r.symbol, r.name))} />
                    {/* [R284] **账目从三格收成一格。** 用户: 「删除掉浮盈和成本列」。
                        空仓(158/166 行)时这一格只有一个按钮; 持有时才长出成本输入。
                        [R169] 写回时一律用 manualCost 而不是 r.cost —— r.cost 可能是批次
                        派生出来的, 直接回写会把"批次算的"固化成"我填的"。派生值必须保持派生。 */}
                    <td className={`${TD_BASE} whitespace-nowrap px-2 max-sm:contents`}>
                      {/* [R520] 单行。**空仓不再是一颗带边框的按钮**: 120 行里 110 行印着「空仓」, 一列按钮全在说
                          「这只我没拿」—— 没事是常态, 常态不该长得像个动作。改成一个压暗的文字入口, 点它仍切成持有;
                          持有那几行才亮起来, 一列扫下去只看得见拿着的。 */}
                      {/* [R527] 成本输入框撤掉(用户: 「不需要成本这一列」)。成本改由「持仓提醒」页的批次提供; 已经手填过的
                          成本还在 positions 里, 切换持有 / 空仓时原样带着(cost: manualCost), 出场线照旧按它算。
                          持有 / 空仓用同一颗 xs 按钮的几何, 只差亮不亮 —— 用户: 「持仓和空仓应该是在同一个位置」。
                          手机上这一格与这层壳都 display:contents: 按钮排在价格后面(order-3), 批次链接 / 出场线落到最后一行(order-5)。 */}
                      <div className="flex items-center gap-1.5 max-sm:contents">
                        <button
                          onClick={() => setPos.mutate({ symbol: r.symbol, held: !r.held, cost: manualCost, weight: r.weight })}
                          title={r.held ? '点一下改成空仓' : '空仓 —— 点一下改成持有'}
                          className={r.held
                            ? buttonClass({ size: 'xs', selected: true }, 'max-sm:order-3')
                            : buttonClass({ size: 'xs', variant: 'ghost' }, 'text-muted/50 hover:text-secondary max-sm:order-3')}
                        >
                          {r.held ? '持有' : '空仓'}
                        </button>
                        <span className="sm:contents max-sm:order-5 max-sm:flex max-sm:basis-full max-sm:items-center max-sm:gap-1.5 max-sm:empty:hidden">
                        {r.held ? (
                          <LotsLink symbol={r.symbol} lotCount={r.lotCount} driftPct={r.costDriftPct} lotCost={r.lotCost} />
                        ) : (
                          // 空仓但批次还挂着 —— 多半是卖出后忘了删批次, 那两条监控规则还在跑
                          r.lotCount > 0
                            ? <LotsLink symbol={r.symbol} lotCount={r.lotCount} driftPct={null} lotCost={null} stale />
                            : null
                        )}
                        {/* [R212 → R310] **出场线的价格回到界面上。**

                            R212 撤掉「止盈线」那一列时写下的对价是: 「信息没丢 ——
                            出场线破了或逼近, 结论列会把线价写在徽标上」。R310 删掉
                            那一列之后这句话就没人兑现了: 查过 `r.exit` 在整张表上
                            **零个渲染点**, 那条线只从 `play.price` 露过面。

                            旁边那个成本输入框的提示写着「出场线按它算」—— 不接住
                            它的话, 你填的成本会算出一条**你再也看不到的线**。

                            归「持仓」而不是别处: 出场线是**关于我这笔仓位**的事
                            (它按我的成本、我的持有天数算), 属于「我的账」。
                            只在持有且真有线时才长出来 —— 166 行里就那几行。 */}
                        {r.held && r.exit && (
                          <span className={`whitespace-nowrap text-xs ${
                            r.exit.triggered ? 'text-danger' : 'text-muted'}`}
                                title={`${r.exit.stage_cn} —— ${r.exit.line_cn} ${r.exit.line.toFixed(2)}\n`
                                       + `${r.exit.triggered ? '已破' : `还差 ${r.exit.distance_pct.toFixed(1)}%`}\n\n`
                                       + r.exit.action}>
                            {r.exit.line_cn}
                            <span className={`ml-1 ${NUM}`}>{r.exit.line.toFixed(2)}</span>
                          </span>
                        )}
                        </span>
                      </div>
                    </td>
                  </tr>
                )
              })}
                </Fragment>
              ))}
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

      {/* [R312] 回测的是**当前列表所见的那几只**, 不是整个自选 —— 「只看要动的」
          「只看持有」「只看某个分组」开着的时候, 用户看到的是哪几只就跑哪几只,
          按钮上的数字与这里传下去的数组是同一个来源。 */}
      {backtestAllOpen && (
        <TrendBacktestAllDialog
          symbols={rows.map((r) => r.symbol)}
          onClose={() => setBacktestAllOpen(false)}
        />
      )}
    </div>
  )
}
