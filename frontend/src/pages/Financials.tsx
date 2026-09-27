import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { RefreshCw, Download, Lock, Loader2, X, Search, FileText, Database, CheckCircle2, Hourglass, ChartPie } from 'lucide-react'
import { PageHeader } from '@/components/PageHeader'
import { useCapabilities, useCapabilityMatrix } from '@/lib/useSharedQueries'
import { routeCapUsable } from '@/lib/capability-labels'
import { useFinancialStatus, useFinancialSync } from '@/lib/useFinancials'
import { StockFinancialSearch } from '@/components/financials/StockFinancialSearch'
import { StockFinancialDetail } from '@/components/financials/StockFinancialDetail'
import { ReportHistoryPanel } from '@/components/financials/ReportHistoryPanel'
import { LastStockChip } from '@/components/LastStockChip'
import { useLastStock } from '@/lib/useLastStock'
import { fmtBigNum } from '@/lib/format'
import { toast } from '@/components/Toast'
import { TYPE, buttonClass } from '@/components/ui'
import { cn } from '@/lib/cn'

const TABLE_LABELS: Record<string, string> = {
  metrics: '核心指标',
  income: '利润表',
  balance_sheet: '资产负债表',
  cash_flow: '现金流量表',
  shares: '股本表',
}

const TABLE_ICON: Record<string, typeof FileText> = {
  metrics: Database,
  income: FileText,
  balance_sheet: FileText,
  cash_flow: FileText,
  shares: ChartPie,
}

export function Financials() {
  const { data: caps } = useCapabilities()
  const { data: matrix } = useCapabilityMatrix()
  const { data: status, isLoading } = useFinancialStatus()
  // 路由感知门控: 生效源当前能否提供财务数据 (含插件/自定义源);
  // 矩阵未加载时回退 TickFlow 套餐视角 + 后端可用状态
  const hasFinancial = routeCapUsable(matrix, 'financial')
    ?? (caps?.capabilities?.['financial'] != null || status?.available === true)
  const syncMut = useFinancialSync()
  // 同步进行中 = 服务端真值(status.syncing)或本地乐观态(请求已发出待确认)。
  // 乐观窗口:点击后到 invalidate 触发的 refetch 返回之间,status.syncing 暂为 false,
  // 用 syncMut.isPending 覆盖,让按钮立即置灰、避免重复点击。
  // 后端 trigger() 返回时 syncing 已为 true,refetch 到达后 status.syncing 接管。
  const syncing = (status?.syncing ?? false) || syncMut.isPending
  // 本次同步开始时间戳(ms): 用于判断每张表的 last_sync 是否属于本次同步
  // (后端每张表完成即更新 last_sync, 前端轮询时对比时间戳得到精确进度)
  const [syncStartedAt, setSyncStartedAt] = useState<number | null>(null)
  // 单表同步时记录表名 (null = 全量同步), 用于区分卡片状态
  const [syncSingleTable, setSyncSingleTable] = useState<string | null>(null)
  // 同步自然结束(服务端 syncing 由 true→false):清空本次同步记录。
  // 这是可靠的收尾时机 —— 不依赖 mutation 的 onSettled(它现在瞬间触发,会误清)。
  useEffect(() => {
    if (!syncing && syncStartedAt !== null) {
      setSyncStartedAt(null)
      setSyncSingleTable(null)
    }
  }, [syncing, syncStartedAt])
  // 选中的个股(模糊搜索结果);null 时显示搜索引导
  const [selected, setSelected] = useState<{ symbol: string; name: string } | null>(null)
  const { last: lastStock, remember: rememberStock } = useLastStock('financials')
  const pick = (symbol: string, name: string) => {
    setSelected({ symbol, name })
    rememberStock(symbol, name)
  }

  if (!hasFinancial) {
    return (
      <>
        <PageHeader title="财务分析" subtitle="利润表 / 资负表 / 现金流 / 关键指标 / 股本 / AI分析" />
        <div className="px-8 py-10">
          {/* [R539] 原来是橙色卡里再套一个「关于数据源」小框, 两段话说的是同一件事(当前源没有 / 需付费, 换一个源),
              合成一段; 「数据源」只有一处, 一个按钮 */}
          <div className="mx-auto max-w-md rounded-card border border-border bg-surface p-8 text-center">
            <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-elevated">
              <Lock className="h-6 w-6 text-secondary" />
            </div>
            <h3 className={cn('mt-4', TYPE.section)}>财务数据不可用</h3>
            <p className="mt-2 text-xs leading-relaxed text-secondary">
              当前数据源未提供财务数据(TickFlow 的财务数据需付费档位), 可在数据源配置里换用其他已接入的来源;
              配好后此页自动显示财务数据面板。
            </p>
            <Link
              to="/settings?tab=data-sources"
              className={buttonClass({ variant: 'primary' }, 'mt-4 gap-1.5')}
            >
              前往数据源配置
            </Link>
          </div>
        </div>
      </>
    )
  }

  const handleSync = (table: string) => {
    // 防重复点击:syncing 中不再触发(后端 trigger 也有 _is_syncing 兜底)
    if (syncing) return
    // 记录开始时间: 全量同步判断所有财务表, 单表同步只判断这一张
    setSyncStartedAt(Date.now())
    setSyncSingleTable(table === 'all' ? null : table)
    syncMut.mutate(table, {
      onSuccess: (r) => {
        // 后端 trigger 立即返回 started 状态;若被防并发跳过(已有同步在进行),
        // 给用户明确反馈,并清空本次误设的记录。
        if (!r.synced?.started) {
          if (r.synced?.reason === 'already running') {
            toast('财务数据正在同步中,请稍候', 'success')
          } else if (r.synced?.reason === 'no FINANCIAL capability') {
            // 能力未就绪:通常发生在升级/刷新 Key 后调度器状态未同步 —— 提示用户检查 Key
            toast('财务数据能力未就绪,请检查 API Key 或刷新页面后重试', 'error')
          } else {
            toast(`同步未能开始${r.synced?.reason ? `:${r.synced.reason}` : ''}`, 'error')
          }
          setSyncStartedAt(null)
          setSyncSingleTable(null)
        }
      },
      onError: () => {
        // 请求失败:清空本次记录(request 已弹错误 toast)
        setSyncStartedAt(null)
        setSyncSingleTable(null)
      },
    })
  }

  const tables = status?.tables ?? {}
  const available = status?.available ?? false
  const lastSync = status?.last_sync ?? {}
  // 本次同步进度: 仅当 syncStartedAt 存在且 syncing 时, 按 last_sync 时间戳判断
  const isFullSync = syncing && syncStartedAt && !syncSingleTable  // 全量同步
  const isSingleSync = syncing && syncStartedAt && !!syncSingleTable  // 单表同步
  const TABLE_ORDER = ['metrics', 'income', 'balance_sheet', 'cash_flow', 'shares'] as const
  const tableDoneThisRound = (key: string): boolean => {
    if (!syncStartedAt || !syncing) return false
    // 单表同步: 只判断这一张表是否完成
    if (syncSingleTable && key !== syncSingleTable) return false
    const ls = lastSync[key]
    if (!ls) return false
    return new Date(ls).getTime() >= syncStartedAt
  }
  // 当前正在同步的表:
  // 全量同步 → 第一个未完成的; 单表同步 → 那张表(未完成时)
  const currentSyncingTable = syncing && syncStartedAt
    ? (syncSingleTable
        ? (tableDoneThisRound(syncSingleTable) ? null : syncSingleTable)
        : TABLE_ORDER.find(t => !tableDoneThisRound(t)) ?? null)
    : null
  const syncedCount = TABLE_ORDER.filter(t => tableDoneThisRound(t)).length
  // 卡片三态: 仅全量同步时未轮到的表显示"等待"; 单表同步时其他表保持原样
  const isWaitingTable = (key: string): boolean =>
    !!isFullSync && !tableDoneThisRound(key) && currentSyncingTable !== key

  return (
    <>
      <PageHeader
        title="财务分析"
        subtitle="利润表 / 资负表 / 现金流 / 关键指标 / 股本 / AI分析"
        right={
          <div className="flex flex-wrap items-center gap-2">
            <LastStockChip stock={lastStock} onSelect={pick} />
            {syncing && (
              <span className="text-xs text-accent/80 flex items-center gap-1.5">
                <Loader2 className="w-3 h-3 animate-spin" />
                {isFullSync
                  ? `已同步 ${syncedCount}/${TABLE_ORDER.length} 张表…`
                  : isSingleSync
                    ? `同步${TABLE_LABELS[syncSingleTable!] ?? syncSingleTable}…`
                    : '同步中…'}
              </span>
            )}
            <button
              className={buttonClass({ variant: 'primary' }, 'gap-1.5')}
              onClick={() => handleSync('all')}
              disabled={syncing}
              title={syncing ? '正在同步，请稍候…' : '同步全部财务表'}
            >
              {syncing
                ? <Loader2 className="h-3.5 w-3.5 animate-spin" />
                : <RefreshCw className="h-3.5 w-3.5" />}
              {syncing ? '同步中…' : '全部同步'}
            </button>
          </div>
        }
      />

      {/* [R60] 统一版式 */}
      <div className="px-3 pb-4 pt-3 lg:px-4">
        <div className="w-full space-y-3">
        {syncing && (
          <div className="flex items-center gap-2 rounded-card border border-accent/30 bg-accent/[0.06] px-3 py-2 text-xs text-accent">
            <Loader2 className="h-3.5 w-3.5 animate-spin shrink-0" />
            正在从财务数据源拉取数据，请稍候…
          </div>
        )}

        {/* 同步状态 —— 始终显示, 反映本地财务数据概况。
            [R539] 原来是五张 130px 高的卡(大号行数 + 标的数 + 同步时间), 每次打开都压在页面最上方;
            它是数据维护信息, 不是分析内容。收成一条: 每张表一格, 同样的四样东西(名称 / 行数 / 标的数 / 同步时间)
            加单表更新按钮, 一个都没少。 */}
        {!isLoading && available && (
          <div className="grid grid-cols-1 divide-y divide-border/60 rounded-card border border-border bg-surface sm:grid-cols-2 sm:divide-y-0 lg:grid-cols-5 lg:divide-x">
            {Object.entries(TABLE_LABELS).map(([key, label]) => {
              const info = tables[key]
              const TIcon = TABLE_ICON[key] ?? Database
              const hasData = (info?.rows ?? 0) > 0
              // 本次同步三态: 完成 / 同步中 / 等待 (仅全量同步时未轮到的表才"等待")
              const doneThisRound = tableDoneThisRound(key)
              const isThisSyncing = currentSyncingTable === key
              const isWaiting = isWaitingTable(key)
              const lsTime = lastSync[key]
              return (
                <div
                  key={key}
                  className={`flex min-w-0 items-center gap-2 px-3 py-2 max-sm:py-1.5 ${isThisSyncing ? 'bg-accent/[0.04]' : isWaiting ? 'opacity-60' : ''}`}
                >
                  {doneThisRound ? (
                    <CheckCircle2 className="h-3.5 w-3.5 shrink-0 text-bear" />
                  ) : isThisSyncing ? (
                    <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin text-accent" />
                  ) : isWaiting ? (
                    <Hourglass className="h-3.5 w-3.5 shrink-0 text-muted/60" />
                  ) : (
                    <TIcon className={`h-3.5 w-3.5 shrink-0 ${hasData ? 'text-secondary' : 'text-muted'}`} />
                  )}
                  <div className="min-w-0 flex-1 max-sm:flex max-sm:items-baseline max-sm:gap-2">
                    <div className="flex shrink-0 items-baseline gap-1.5">
                      <span className="text-xs font-medium text-foreground">{label}</span>
                      <span className="font-mono text-xs tabular-nums text-secondary">{fmtBigNum(info?.rows ?? 0)}行</span>
                    </div>
                    <div className="truncate text-micro text-muted">
                      {fmtBigNum(info?.symbols ?? 0)} 只 ·{' '}
                      {lsTime
                        ? new Date(lsTime).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
                        : '尚未同步'}
                    </div>
                  </div>
                  <button
                    className="shrink-0 text-muted transition-colors hover:text-foreground disabled:cursor-not-allowed disabled:opacity-30"
                    onClick={() => handleSync(key)}
                    disabled={syncing}
                    title={syncing ? '正在同步…' : `更新${label}`}
                  >
                    <Download className="h-3.5 w-3.5" />
                  </button>
                </div>
              )
            })}
          </div>
        )}

        {isLoading ? (
          <div className="flex items-center justify-center py-16">
            <Loader2 className="h-5 w-5 animate-spin text-muted" />
          </div>
        ) : !available ? (
          <div className="rounded-card border border-dashed border-border bg-surface px-6 py-14 text-center">
            <Database className="mx-auto h-8 w-8 text-muted" />
            <div className="mt-3 text-sm text-secondary">暂无财务数据</div>
            <div className="mt-1 text-xs text-muted">点击右上角"全部同步"从当前数据源拉取</div>
          </div>
        ) : (
          <>
            {/* 个股搜索区 */}
            <div>
              {selected ? (
                // 已选股:紧凑搜索条 + 清除按钮(便于换股)
                <div className="flex items-center gap-3">
                  <div className="flex-1 max-w-xl">
                    <StockFinancialSearch onSelect={pick} />
                  </div>
                  <button
                    onClick={() => setSelected(null)}
                    className="inline-flex items-center gap-1 px-2.5 py-1.5 text-xs text-secondary hover:text-foreground rounded-btn border border-border hover:bg-elevated transition-colors shrink-0"
                    title="清除选择"
                  >
                    <X className="h-3.5 w-3.5" />
                    清除
                  </button>
                </div>
              ) : (
                // 未选股:醒目居中引导
                <div className="flex flex-col items-center gap-3 py-12">
                  <div className="flex items-center gap-2 text-sm text-secondary">
                    <Search className="h-4 w-4 text-accent" />
                    <span>搜索个股查看详细财务数据</span>
                  </div>
                  <div className="w-full max-w-xl">
                    <StockFinancialSearch onSelect={pick} />
                  </div>
                  <div className="text-xs text-muted">支持股票代码或名称模糊匹配，如 600000 / 浦发</div>
                </div>
              )}
            </div>

            {/* 个股详情 / 空引导 */}
            <div className="pb-4">
              {/* [R539] 未选股时这里原来还有一块「未选择股票 · 在上方搜索框输入…」—— 与正上方的搜索引导说的是同一句话 */}
              {selected && <StockFinancialDetail symbol={selected.symbol} name={selected.name} />}
            </div>

            {/* AI 历史分析报告 */}
            {available && <ReportHistoryPanel />}
          </>
        )}
        </div>
      </div>
    </>
  )
}
