/**
 * AI 大盘复盘页 —— 盘后决策台 (R791 改版)。
 *
 * 信息架构从「AI 报告阅读器」改为「事实 → 证据 → 结论 → 档案」四段纵轴:
 *   A 事实仪表  FactsBar      (core + breadth, 只放规则口径读数)
 *   B 证据带    EvidenceTabs  (主线/连板/资金/情绪, 默认主线)
 *   C 复盘正文  ReportReader  (目录 + 面包屑 + 分节进度, 整页滚动)
 *   D 复盘档案  ArchiveStrip  (横向时间轴 + 双篇对照)
 * 状态带 ReviewStatusBar 回答「哪一天 / 定稿没 / 几点跑 / 推去哪」。
 *
 * 数据全部复用已有切片端点(共享 5s 缓存单飞), 页面只做组合与版式,
 * 不在这里二次计算情绪分/涨跌结构 (AGENTS 第 12 条, 同一读数单一产地)。
 *
 * 归属: 扩展域消费页 (官方), 经 custom/review/extension.tsx 注册路由与导航;
 * 对核心能力均为只读 import (api/QK/组件/状态库), 不承载核心域语义。
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { AnimatePresence, motion } from 'framer-motion'
import {
  Check, ChevronDown, ChevronRight, ChevronUp, Clock, Database, RefreshCw, Wand2, X,
} from 'lucide-react'

import {
  api, type AiReviewReportMeta, type OverviewBreadth,
  type OverviewCore, type OverviewHeat,
} from '@/lib/api'
import { QK } from '@/lib/queryKeys'
import { cn } from '@/lib/cn'
import { StockPreviewDialog } from '@/components/StockPreviewDialog'
import { PageHeader } from '@/components/PageHeader'
import { toast } from '@/components/Toast'
import { usePreferences } from '@/lib/useSharedQueries'
import { useReviewState } from '@/lib/useReviewStore'
import {
  startReviewGeneration, resetReview, isReviewGenerating,
} from '@/lib/reviewStore'
import { Button, TYPE } from '@/components/ui'
import { Switch } from '@/components/ui/Switch'
import { ReviewStatusBar } from './ReviewStatusBar'
import { FactsBar } from './FactsBar'
import { EvidenceTabs } from './EvidenceTabs'
import { ReportReader } from './ReportReader'
import { ArchiveStrip } from './ArchiveStrip'

export function ReviewPage() {
  const qc = useQueryClient()
  // 复盘日期:当前固定取最新交易日(历史通过档案带访问, 不做日期选择器)
  const asOf: string | undefined = undefined
  const [focus, setFocus] = useState('')
  // 生成状态走全局 store:切走页面流不中断, 回来可恢复
  const { phase, content, error, meta } = useReviewState()
  // 正在查看的历史报告 id —— 全文按需拉, 不在档案列表里带正文
  const [viewingId, setViewingId] = useState<string | null>(null)
  const [previewSymbol, setPreviewSymbol] = useState<string | null>(null)

  // ===== A/B 区数据: 四个切片并行, 与看板同一套缓存 =====
  const coreQ = useQuery<OverviewCore>({
    queryKey: QK.overviewCore(asOf),
    queryFn: () => api.overviewCore(asOf),
    staleTime: 5_000,
    placeholderData: (prev) => prev,
  })
  const breadthQ = useQuery<OverviewBreadth>({
    queryKey: QK.overviewBreadth(asOf),
    queryFn: () => api.overviewBreadth(asOf),
    staleTime: 5_000,
    placeholderData: (prev) => prev,
  })
  const conceptQ = useQuery<OverviewHeat>({
    queryKey: QK.overviewHeat('concept', asOf),
    queryFn: () => api.overviewHeat('concept', asOf),
    staleTime: 30_000,
    placeholderData: (prev) => prev,
  })
  const industryQ = useQuery<OverviewHeat>({
    queryKey: QK.overviewHeat('industry', asOf),
    queryFn: () => api.overviewHeat('industry', asOf),
    staleTime: 30_000,
    placeholderData: (prev) => prev,
  })

  // D 区档案: 只要摘要(不含正文)
  const archiveQ = useQuery<{ reports: AiReviewReportMeta[] }>({
    queryKey: QK.reviewReportsMeta,
    queryFn: () => api.reviewReportsListMeta(),
  })

  // C 区详情: 点开哪篇拉哪篇
  const detailQ = useQuery({
    queryKey: QK.reviewReportDetail(viewingId ?? ''),
    queryFn: () => api.reviewReportDetail(viewingId!),
    enabled: !!viewingId,
    staleTime: 60_000,
  })
  const viewing = viewingId ? detailQ.data?.report ?? null : null

  const deleteMut = useMutation({
    mutationFn: (id: string) => api.reviewReportDelete(id),
    onSuccess: (_data, id) => {
      qc.invalidateQueries({ queryKey: QK.reviewReports })
      setViewingId(prev => (prev === id ? null : prev))
      toast('已删除', 'success')
    },
    onError: () => { /* request() 已 toast */ },
  })

  // ===== 定时复盘 =====
  const [showSchedule, setShowSchedule] = useState(false)
  const prefs = usePreferences()
  const reviewSched = prefs.data?.review_schedule ?? { enabled: false, hour: 15, minute: 10 }
  const feishuConfigured = !!(prefs.data?.feishu_webhook_url)
  const wecomConfigured = !!(prefs.data?.wecom_webhook_url)
  const dingtalkConfigured = !!(prefs.data?.dingtalk_webhook_url)
  const customConfigured = !!(prefs.data?.custom_webhook_url)
  const emailConfigured = !!(
    prefs.data?.email_smtp_config?.host
    && prefs.data.email_smtp_config.from_address
    && prefs.data.email_smtp_config.to_addresses.length
    && (!prefs.data.email_smtp_config.username || prefs.data.email_smtp_password_set)
  )
  // 推送渠道是独立的顶层偏好(多选), 与定时 / 实时行情无关, 常驻可单独设置
  // []=不推送; 可多选飞书、企微、第三方 Webhook 和邮件。
  const reviewPushChannels = prefs.data?.review_push_channels ?? []
  // 推送触发方式: auto=归档即推; manual=仅归档不自动外发。默认 manual。
  const reviewPushMode = prefs.data?.review_push_mode ?? 'manual'
  // 弹窗内的本地草稿: 开关和时间都在本地改, 点「保存」才真正提交(避免开关一拨就关弹窗)
  const [draft, setDraft] = useState(reviewSched)
  const openSchedule = useCallback(() => {
    setDraft(reviewSched)  // 每次打开同步最新服务端值
    setShowSchedule(true)
  }, [reviewSched])
  const reviewMut = useMutation({
    mutationFn: ({ enabled, hour, minute }: { enabled: boolean; hour: number; minute: number }) =>
      api.updateReviewSchedule(enabled, hour, minute),
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: QK.preferences })
      setShowSchedule(false)
      toast(vars.enabled ? '已开启定时复盘' : '已关闭定时复盘', 'success')
    },
    onError: () => { /* request() 已 toast */ },
  })
  // 推送渠道(多选): 独立常驻, 即时生效(勾选渠道即开关, 改了立刻提交)
  const pushMut = useMutation({
    mutationFn: (channels: string[]) => api.updateReviewPush(channels),
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: QK.preferences })
      toast(vars.length === 0 ? '已关闭复盘推送' : '已更新复盘推送渠道', 'success')
    },
    onError: () => { /* request() 已 toast */ },
  })
  const togglePushChannel = useCallback((ch: string) => {
    const next = reviewPushChannels.includes(ch)
      ? reviewPushChannels.filter(c => c !== ch)
      : [...reviewPushChannels, ch]
    pushMut.mutate(next)
  }, [reviewPushChannels, pushMut])
  // 推送触发方式(独立常驻): auto/manual 即时生效, 与渠道切换一致
  const pushModeMut = useMutation({
    mutationFn: (mode: 'auto' | 'manual') => api.updateReviewPush(reviewPushChannels, mode),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: QK.preferences })
      toast('已更新推送触发方式', 'success')
    },
    onError: () => { /* request() 已 toast */ },
  })

  // ===== 自定义复盘提示词 =====
  // 折叠区展开时才拉取(自定义值 + 默认全文); 草稿 null=未编辑, 跟随服务端值
  const [showPromptEditor, setShowPromptEditor] = useState(false)
  const promptQuery = useQuery({
    queryKey: ['market-recap-prompt'],
    queryFn: api.getMarketRecapPrompt,
    enabled: showPromptEditor,
    staleTime: 30_000,
  })
  const [promptDraft, setPromptDraft] = useState<string | null>(null)
  useEffect(() => { setPromptDraft(null) }, [promptQuery.data])
  const promptCustomized = !!promptQuery.data?.customized
  const promptText = promptDraft ?? promptQuery.data?.custom ?? ''
  const promptMut = useMutation({
    mutationFn: (prompt: string) => api.updateMarketRecapPrompt(prompt),
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: QK.preferences })
      qc.invalidateQueries({ queryKey: ['market-recap-prompt'] })
      setPromptDraft(null)
      toast(vars.trim() ? '已保存复盘提示词' : '已恢复默认提示词', 'success')
    },
    onError: () => { /* request() 已 toast */ },
  })

  // 新一轮生成开始时清掉「查看历史」—— 让 C 区显示流内容。
  // 只在「非 streaming → streaming」的那一刻清, 生成途中仍可翻历史(面包屑带「生成中 · 切回」)。
  const prevPhase = useRef(phase)
  useEffect(() => {
    if (prevPhase.current !== 'streaming' && phase === 'streaming') setViewingId(null)
    prevPhase.current = phase
  }, [phase])

  // 自动归档(生成完成后台静默保存)—— 通过回调注入 store,避免 store 直接依赖 qc
  const onGenerationDone = useCallback(async (fullContent: string, doneMeta: { as_of?: string; summary?: string; emotion_score?: number; emotion_label?: string } | null) => {
    const reportAsOf = doneMeta?.as_of ?? coreQ.data?.as_of ?? asOf ?? new Date().toISOString().slice(0, 10)
    try {
      await api.reviewReportSave({
        as_of: reportAsOf,
        focus,
        content: fullContent,
        summary: doneMeta?.summary,
        emotion_score: doneMeta?.emotion_score ?? null,
        emotion_label: doneMeta?.emotion_label ?? '',
      })
      qc.invalidateQueries({ queryKey: QK.reviewReports })
    } catch { /* 静默 */ }
  }, [focus, asOf, coreQ.data, qc])

  // 主流程:生成复盘(委托给全局 store,流在后台独立运行)
  const generate = useCallback(() => {
    if (isReviewGenerating()) return
    setViewingId(null)
    resetReview()
    startReviewGeneration(asOf, focus, (full, doneMeta) => {
      onGenerationDone(full, doneMeta).catch(() => { /* 静默 */ })
    })
  }, [asOf, focus, onGenerationDone])

  // 复制全文到剪贴板(viewing 优先,与主区域显示一致)
  const copyContent = useCallback(async () => {
    const text = viewing?.content ?? content
    if (!text) return
    try {
      await navigator.clipboard.writeText(text)
      toast('已复制到剪贴板', 'success')
    } catch {
      toast('复制失败,请手动选择文本', 'error')
    }
  }, [content, viewing])

  // 下载为 .md 文件(viewing 优先)
  const downloadContent = useCallback(() => {
    const text = viewing?.content ?? content
    if (!text) return
    const reportDate = viewing?.as_of ?? meta?.as_of ?? asOf ?? new Date().toISOString().slice(0, 10)
    const blob = new Blob([text], { type: 'text/markdown;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `复盘_${reportDate}.md`
    a.click()
    URL.revokeObjectURL(url)
  }, [content, viewing, meta, asOf])

  const isGenerating = phase === 'loading' || phase === 'streaming'
  const core = coreQ.data
  const displayDate = viewing?.as_of ?? meta?.as_of ?? core?.as_of ?? asOf ?? '最新'
  // 龙虎榜跟随复盘目标日 (历史复盘联动当期榜单); 非 ISO 日期(如"最新")取最近一期
  const dtDate = /^\d{4}-\d{2}-\d{2}$/.test(displayDate ?? '') ? displayDate : undefined
  // 主区域显示的内容:viewing(查看历史)优先于 store 的生成 content
  const displayContent = viewing?.content ?? content
  const archiveReports = archiveQ.data?.reports ?? []
  // 「情绪较上次」: 档案里第一份早于当前交易日的报告
  const prevMeta = core?.as_of
    ? archiveReports.find(r => r.as_of < core.as_of!) ?? null
    : null
  const intraday = !!core?.quote_status?.is_trading_hours
  const refreshing = coreQ.isFetching || breadthQ.isFetching || conceptQ.isFetching || industryQ.isFetching

  return (
    <>
      <PageHeader
        // [R543] 页头原叫「AI 复盘」+ 闪光图标, 菜单里叫「复盘」—— 同一页两个名字(AGENTS.md 第 12 条), 随菜单
        title="复盘"
        subtitle={`${displayDate}${core?.emotion ? ` · 情绪 ${core.emotion.label}` : ''}`}
      />
      {/* [R791] 整改这一页之前读了 .scratch/review-page-rework/issues/01-ladder-ai-and-friends.md
          (用户交代的提醒, 已在 R543 逐项问过: AI 打板复盘 / 板块跷跷板 / 三种复盘模式 / RPS 轮动入口
          四样均不接回)。本版只重排版式, 不换壳接回其中任何一个。 */}
      <div className="min-h-full px-3 pb-4 pt-3 lg:px-4">
        <div className="w-full space-y-3">
          {coreQ.isLoading && !core ? (
            <div className="flex h-40 items-center justify-center">
              <div className="flex items-center gap-2 text-sm text-muted">
                <RefreshCw className="h-4 w-4 animate-spin" /> 加载市场数据…
              </div>
            </div>
          ) : coreQ.isSuccess && !core?.as_of ? (
            <div className="flex flex-col items-center justify-center gap-4 rounded-card border border-border bg-surface/80 px-6 py-16">
              <div className="grid h-14 w-14 place-items-center rounded-dialog border border-accent/30 bg-accent-soft">
                <Database className="h-6 w-6 text-accent" strokeWidth={1.8} />
              </div>
              <div className="text-center">
                <div className="text-sm font-medium text-foreground">暂无市场数据</div>
                <p className="mt-1 text-xs text-muted">复盘需要日 K 与指数,请先前往「数据」页同步</p>
              </div>
              <Link
                to="/data"
                className="inline-flex items-center gap-1.5 rounded-btn bg-accent px-4 py-2 text-xs font-medium text-on-accent shadow-sm transition-ui hover:bg-accent/90 hover:shadow"
              >
                <Database className="h-3.5 w-3.5" />前往数据页同步
                <ChevronRight className="h-3.5 w-3.5" />
              </Link>
            </div>
          ) : (
            <>
              {/* 状态带: 哪一天 / 定稿没 / 几点自动跑 / 推去哪 / 主按钮 */}
              <ReviewStatusBar
                asOf={core?.as_of ?? displayDate}
                intraday={intraday}
                lastArchivedAt={archiveReports[0]?.created_at}
                schedule={reviewSched}
                pushChannels={reviewPushChannels}
                generating={isGenerating}
                refreshing={refreshing}
                onRefresh={() => { coreQ.refetch(); breadthQ.refetch(); conceptQ.refetch(); industryQ.refetch() }}
                onOpenSchedule={openSchedule}
                onGenerate={generate}
              />

              {/* A 区: 事实仪表 (生成前页面也有用) */}
              <FactsBar
                core={core}
                breadth={breadthQ.data}
                prevMeta={prevMeta}
                loading={breadthQ.isLoading}
                error={coreQ.isError || breadthQ.isError}
                onRetry={() => { coreQ.refetch(); breadthQ.refetch() }}
              />

              {/* B 区: 证据带 */}
              <EvidenceTabs
                breadth={breadthQ.data}
                concept={conceptQ.data}
                industry={industryQ.data}
                heatLoading={conceptQ.isLoading || industryQ.isLoading}
                dtDate={dtDate}
                onOpenStock={setPreviewSymbol}
              />

              {/* 关注点输入: 只影响本次生成, 不落库 */}
              <div className="flex items-center gap-2 rounded-card border border-border bg-surface/80 px-3.5 py-2 transition-colors focus-within:border-accent/40">
                <Wand2 className="h-3.5 w-3.5 shrink-0 text-accent" />
                <input
                  value={focus}
                  onChange={(e) => setFocus(e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Enter' && !isGenerating) generate() }}
                  placeholder="可选:补充复盘关注点,如「半导体板块持续性如何」「量能是否持续」"
                  className="flex-1 bg-transparent text-sm text-foreground outline-none placeholder:text-muted/60"
                />
                {focus && (
                  <button onClick={() => setFocus('')} className="text-xs text-secondary transition-colors hover:text-foreground">清除</button>
                )}
              </div>

              {/* C 区: 正文 */}
              <ReportReader
                phase={phase}
                content={displayContent}
                error={error}
                generating={isGenerating}
                viewing={viewing}
                detailLoading={!!viewingId && detailQ.isLoading}
                onCopy={copyContent}
                onDownload={downloadContent}
                onRegenerate={generate}
                onBackToLatest={() => setViewingId(null)}
              />

              {/* D 区: 档案带 */}
              <ArchiveStrip
                reports={archiveReports}
                loading={archiveQ.isLoading}
                selectedId={viewingId}
                generating={isGenerating}
                onView={setViewingId}
                onBackToGenerating={() => setViewingId(null)}
                onDelete={(id) => deleteMut.mutate(id)}
              />
            </>
          )}
        </div>
      </div>

      {/* ===== 定时复盘设置弹窗 ===== */}
      <AnimatePresence>
        {showSchedule && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
            onClick={() => setShowSchedule(false)}
          >
            <motion.div
              initial={{ scale: 0.96, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.96, opacity: 0 }}
              className="w-full max-w-md rounded-card border border-border bg-surface p-5 shadow-2xl"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="mb-4 flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Clock className="h-4 w-4 text-accent" />
                  <h3 className={TYPE.section}>定时复盘</h3>
                </div>
                <Button
                  icon
                  variant="ghost"
                  size="xs"
                  onClick={() => setShowSchedule(false)}
                >
                  <X className="h-4 w-4" />
                </Button>
              </div>

              <p className="mb-4 text-xs leading-relaxed text-muted">
                开启后,每个交易日到点自动生成大盘复盘报告并归档,静默执行。
                下次打开本页即可在档案带看到新报告;也可推送到下方渠道。
              </p>

              {/* 开关(只改本地草稿, 不提交) */}
              <label className="flex items-center justify-between rounded-btn bg-elevated/40 px-3 py-2.5">
                <span className="text-xs text-foreground">启用定时复盘</span>
                {/* [R548] 走共用 Switch(原来手写一份, 关着时轨道用 bg-border、滑块偏 4px, 与设置区的开关长得不一样) */}
                <Switch checked={draft.enabled} onChange={next => setDraft(d => ({ ...d, enabled: next }))} />
              </label>

              {/* 时间设置(仅开启时可编辑, 本地草稿) */}
              {draft.enabled && (
                <div className="mt-3 flex items-center gap-2 rounded-btn bg-elevated/40 px-3 py-2.5">
                  <span className="text-xs text-muted">每日</span>
                  <input
                    type="number" min={0} max={23} value={draft.hour}
                    onChange={e => setDraft(d => ({ ...d, hour: Math.max(0, Math.min(23, Number(e.target.value))) }))}
                    className="w-12 rounded-btn border border-border bg-base px-1.5 py-1 text-center font-mono text-xs text-foreground focus:border-accent/50 focus:outline-none"
                  />
                  <span className="text-xs text-muted">:</span>
                  <input
                    type="number" min={0} max={59} value={draft.minute}
                    onChange={e => setDraft(d => ({ ...d, minute: Math.max(0, Math.min(59, Number(e.target.value))) }))}
                    className="w-12 rounded-btn border border-border bg-base px-1.5 py-1 text-center font-mono text-xs text-foreground focus:border-accent/50 focus:outline-none"
                  />
                  <span className="text-micro text-muted/70">不早于 15:00 · 工作日执行</span>
                </div>
              )}

              {/* 推送渠道(多选, 独立常驻, 与定时无关, 即时生效) */}
              <div className="mt-3 rounded-btn bg-elevated/40 px-3 py-2.5">
                <div className="flex items-center justify-between">
                  <span className="text-xs text-foreground">生成后推送完整报告</span>
                  <span className="text-micro text-muted/70">{reviewPushChannels.length === 0 ? '未开启' : `${reviewPushChannels.length} 个渠道`}</span>
                </div>
                <div className="mt-2 space-y-1.5">
                  {/* 飞书(可用, 多选) */}
                  <button
                    type="button"
                    disabled={pushMut.isPending}
                    onClick={() => togglePushChannel('feishu')}
                    className={cn(
                      'flex w-full items-center gap-2 rounded-btn border px-2.5 py-1.5 text-left transition-colors disabled:opacity-50',
                      reviewPushChannels.includes('feishu')
                        ? 'border-accent/40 bg-accent/10'
                        : 'border-border/60 bg-base/40 hover:bg-base/60',
                    )}
                  >
                    <span className={cn('flex h-3 w-3 shrink-0 items-center justify-center rounded-btn border', reviewPushChannels.includes('feishu') ? 'border-accent bg-accent text-on-accent' : 'border-border')}>
                      {reviewPushChannels.includes('feishu') && <Check className="h-2.5 w-2.5" />}
                    </span>
                    <span className="text-xs text-foreground">飞书</span>
                    <span className="text-micro text-muted">群推送 Webhook</span>
                    <span className={cn('ml-auto text-micro', feishuConfigured ? 'text-bear' : 'text-warning')}>
                      {feishuConfigured ? '已配置' : '未配置'}
                    </span>
                  </button>
                  {/* 企业微信(可用, 多选) */}
                  <button
                    type="button"
                    disabled={pushMut.isPending}
                    onClick={() => togglePushChannel('wecom')}
                    className={cn(
                      'flex w-full items-center gap-2 rounded-btn border px-2.5 py-1.5 text-left transition-colors disabled:opacity-50',
                      reviewPushChannels.includes('wecom')
                        ? 'border-accent/40 bg-accent/10'
                        : 'border-border/60 bg-base/40 hover:bg-base/60',
                    )}
                  >
                    <span className={cn('flex h-3 w-3 shrink-0 items-center justify-center rounded-btn border', reviewPushChannels.includes('wecom') ? 'border-accent bg-accent text-on-accent' : 'border-border')}>
                      {reviewPushChannels.includes('wecom') && <Check className="h-2.5 w-2.5" />}
                    </span>
                    <span className="text-xs text-foreground">企业微信</span>
                    <span className="text-micro text-muted">群推送 Webhook</span>
                    <span className={cn('ml-auto text-micro', wecomConfigured ? 'text-bear' : 'text-warning')}>
                      {wecomConfigured ? '已配置' : '未配置'}
                    </span>
                  </button>
                  {/* 钉钉(可用, 多选) */}
                  <button
                    type="button"
                    disabled={pushMut.isPending}
                    onClick={() => togglePushChannel('dingtalk')}
                    className={cn(
                      'flex w-full items-center gap-2 rounded-btn border px-2.5 py-1.5 text-left transition-colors disabled:opacity-50',
                      reviewPushChannels.includes('dingtalk')
                        ? 'border-accent/40 bg-accent/10'
                        : 'border-border/60 bg-base/40 hover:bg-base/60',
                    )}
                  >
                    <span className={cn('flex h-3 w-3 shrink-0 items-center justify-center rounded-btn border', reviewPushChannels.includes('dingtalk') ? 'border-accent bg-accent text-on-accent' : 'border-border')}>
                      {reviewPushChannels.includes('dingtalk') && <Check className="h-2.5 w-2.5" />}
                    </span>
                    <span className="text-xs text-foreground">钉钉</span>
                    <span className="text-micro text-muted">群机器人 · 关键词</span>
                    <span className={cn('ml-auto text-micro', dingtalkConfigured ? 'text-bear' : 'text-warning')}>
                      {dingtalkConfigured ? '已配置' : '未配置'}
                    </span>
                  </button>
                  <button
                    type="button"
                    disabled={pushMut.isPending}
                    onClick={() => togglePushChannel('custom')}
                    className={cn(
                      'flex w-full items-center gap-2 rounded-btn border px-2.5 py-1.5 text-left transition-colors disabled:opacity-50',
                      reviewPushChannels.includes('custom')
                        ? 'border-accent/40 bg-accent/10'
                        : 'border-border/60 bg-base/40 hover:bg-base/60',
                    )}
                  >
                    <span className={cn('flex h-3 w-3 shrink-0 items-center justify-center rounded-btn border', reviewPushChannels.includes('custom') ? 'border-accent bg-accent text-on-accent' : 'border-border')}>
                      {reviewPushChannels.includes('custom') && <Check className="h-2.5 w-2.5" />}
                    </span>
                    <span className="text-xs text-foreground">第三方系统</span>
                    <span className="text-micro text-muted">JSON Webhook</span>
                    <span className={cn('ml-auto text-micro', customConfigured ? 'text-bear' : 'text-warning')}>
                      {customConfigured ? '已配置' : '未配置'}
                    </span>
                  </button>
                  <button
                    type="button"
                    disabled={pushMut.isPending}
                    onClick={() => togglePushChannel('email')}
                    className={cn(
                      'flex w-full items-center gap-2 rounded-btn border px-2.5 py-1.5 text-left transition-colors disabled:opacity-50',
                      reviewPushChannels.includes('email')
                        ? 'border-accent/40 bg-accent/10'
                        : 'border-border/60 bg-base/40 hover:bg-base/60',
                    )}
                  >
                    <span className={cn('flex h-3 w-3 shrink-0 items-center justify-center rounded-btn border', reviewPushChannels.includes('email') ? 'border-accent bg-accent text-on-accent' : 'border-border')}>
                      {reviewPushChannels.includes('email') && <Check className="h-2.5 w-2.5" />}
                    </span>
                    <span className="text-xs text-foreground">邮件</span>
                    <span className="text-micro text-muted">SMTP</span>
                    <span className={cn('ml-auto text-micro', emailConfigured ? 'text-bear' : 'text-warning')}>
                      {emailConfigured ? '已配置' : '未配置'}
                    </span>
                  </button>
                </div>

                {/* 推送触发方式: auto=归档即推 / manual=仅归档不自动外发 */}
                <div className="mt-2 flex items-center justify-between">
                  <span className="text-xs text-foreground">推送触发方式</span>
                  <div className="flex items-center gap-0.5 rounded-btn bg-base p-0.5">
                    <button
                      type="button"
                      disabled={pushModeMut.isPending}
                      onClick={() => pushModeMut.mutate('auto')}
                      className={cn(
                        'rounded-btn px-2 py-0.5 text-micro transition-colors disabled:opacity-50',
                        reviewPushMode === 'auto' ? 'bg-foreground font-medium text-surface' : 'text-secondary hover:text-secondary',
                      )}
                    >
                      自动
                    </button>
                    <button
                      type="button"
                      disabled={pushModeMut.isPending}
                      onClick={() => pushModeMut.mutate('manual')}
                      className={cn(
                        'rounded-btn px-2 py-0.5 text-micro transition-colors disabled:opacity-50',
                        reviewPushMode === 'manual' ? 'bg-foreground font-medium text-surface' : 'text-secondary hover:text-secondary',
                      )}
                    >
                      手动确认
                    </button>
                  </div>
                </div>

                <p className="mt-1.5 text-micro leading-relaxed text-muted/70">
                  {reviewPushMode === 'auto'
                    ? '定时与手动生成的复盘归档后都会自动推送完整报告。'
                    : '复盘仅归档保存，不自动外发。'}
                  复用「设置 → 通知」的渠道配置。
                  {(
                    (reviewPushChannels.includes('feishu') && !feishuConfigured)
                    || (reviewPushChannels.includes('wecom') && !wecomConfigured)
                    || (reviewPushChannels.includes('dingtalk') && !dingtalkConfigured)
                    || (reviewPushChannels.includes('custom') && !customConfigured)
                    || (reviewPushChannels.includes('email') && !emailConfigured)
                  ) && (
                    <Link to="/settings?tab=notifications&highlight=webhooks" className="ml-1 text-accent hover:underline" onClick={() => setShowSchedule(false)}>
                      前往配置 →
                    </Link>
                  )}
                </p>
              </div>

              {/* 自定义复盘提示词(折叠区, 展开/保存/恢复默认/填入默认模板) */}
              <div className="mt-3 rounded-btn bg-elevated/40 px-3 py-2.5">
                <button
                  type="button"
                  onClick={() => setShowPromptEditor(v => !v)}
                  className="flex w-full items-center justify-between"
                >
                  <span className="flex items-center gap-1.5 text-xs text-foreground">
                    <Wand2 className="h-3.5 w-3.5 text-accent" />
                    自定义复盘提示词
                  </span>
                  <span className="flex items-center gap-1.5">
                    <span className={cn('text-micro', promptCustomized ? 'text-accent' : 'text-muted/70')}>
                      {promptCustomized ? '已自定义' : '默认模板'}
                    </span>
                    {showPromptEditor
                      ? <ChevronUp className="h-3.5 w-3.5 text-muted" />
                      : <ChevronDown className="h-3.5 w-3.5 text-muted" />}
                  </span>
                </button>

                {showPromptEditor && (
                  <div className="mt-2.5">
                    <textarea
                      value={promptText}
                      onChange={e => setPromptDraft(e.target.value)}
                      spellCheck={false}
                      placeholder="留空使用内置默认提示词;也可点下方「填入默认模板」后在其基础上修改"
                      className="h-44 w-full resize-y rounded-btn border border-border bg-base p-2.5 font-mono text-micro leading-relaxed text-foreground outline-none placeholder:text-muted/60 focus:border-accent/50"
                    />
                    <div className="mt-1.5 flex items-center justify-between">
                      <span className="text-micro text-muted/70">
                        {promptText.length.toLocaleString()} / 32,000 字符
                        {promptCustomized && ' · 自定义后不再跟随版本默认模板更新'}
                      </span>
                      <div className="flex items-center gap-1.5">
                        <Button
                          type="button"
                          size="xs"
                          disabled={promptQuery.isLoading || !promptQuery.data}
                          onClick={() => setPromptDraft(promptQuery.data?.default ?? '')}
                          className="text-micro"
                        >
                          填入默认模板
                        </Button>
                        <Button
                          type="button"
                          size="xs"
                          disabled={promptMut.isPending || !promptCustomized}
                          onClick={() => promptMut.mutate('')}
                          className="text-micro"
                        >
                          恢复默认
                        </Button>
                        <Button
                          type="button"
                          size="xs"
                          variant="primary"
                          disabled={promptMut.isPending || promptQuery.isLoading}
                          onClick={() => promptMut.mutate(promptText)}
                          className="text-micro"
                        >
                          {promptMut.isPending ? '保存中…' : '保存'}
                        </Button>
                      </div>
                    </div>
                  </div>
                )}
              </div>

              {!draft.enabled && (
                <p className="mt-3 text-micro text-muted/70">
                  当前: 已关闭。开启后将按设定时间自动复盘。
                </p>
              )}

              {/* 操作区: 取消 + 保存(统一提交开关+时间) */}
              <div className="mt-5 flex justify-end gap-2">
                <Button
                  onClick={() => setShowSchedule(false)}
                >
                  取消
                </Button>
                <Button
                  variant="primary"
                  onClick={() => reviewMut.mutate({ enabled: draft.enabled, hour: draft.hour, minute: draft.minute })}
                  disabled={reviewMut.isPending}
                >
                  {reviewMut.isPending ? '保存中…' : '保存'}
                </Button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* 个股日 K 详情 (龙虎榜 / 连板梯队 / 风向标点击打开) */}
      <StockPreviewDialog
        symbol={previewSymbol}
        onClose={() => setPreviewSymbol(null)}
      />
    </>
  )
}

