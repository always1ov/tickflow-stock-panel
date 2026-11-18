import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Archive, ArchiveRestore, ArrowRight, FlaskConical, PenLine, Search, Sparkles, Trash2,
} from 'lucide-react'
import { Modal } from '@/components/Modal'
import { toast } from '@/components/Toast'
import { api, type FactorLibraryItem } from '@/lib/api'
import { QK } from '@/lib/queryKeys'
import { refreshResourceQueries } from '@/lib/importCenter'
import { GenerateFactorStrategyDialog } from './GenerateFactorStrategyDialog'
import {
  Badge, Button, DialogClose, DIALOG_BODY, DIALOG_FOOTER, DIALOG_HEADER, DIALOG_TITLE,
  SEG, SEG_ITEM, SEG_OFF, SEG_ON, THEAD, TH_ROW, dialogPanel, fieldInput, fieldSelect,
  type BadgeTone,
} from '@/components/ui'
import { cn } from '@/lib/cn'

const INPUT_CLS = cn(fieldInput, 'text-xs')

const KIND_META: Record<FactorLibraryItem['kind'], { label: string; tone: BadgeTone }> = {
  base: { label: '基础', tone: 'neutral' },
  virtual: { label: '虚拟', tone: 'accent-soft' },
  composite: { label: '复合', tone: 'bull' },
  custom: { label: '自定义', tone: 'warning' },
}

/** 生命周期状态 (仅自定义/复合因子有): 表格状态列、筛选与详情弹窗共用。
 *
 * [R578 同步上游 v0.3.16] 上游给因子库加了生命周期筛选; 本 fork 保持手机不横滑的
 * 表格形态(R537), 只把状态并进「类型」列与筛选条。
 */
const STATUS_META: Record<string, { label: string; tone: BadgeTone }> = {
  active: { label: '激活', tone: 'bull' },
  watch: { label: '观察', tone: 'warning' },
  draft: { label: '草稿', tone: 'neutral' },
  retired: { label: '退役', tone: 'danger' },
}
const BUILTIN_STATUS = { label: '内置', tone: 'neutral' as const }
const statusOf = (item: FactorLibraryItem) =>
  (item.status && STATUS_META[item.status]) || BUILTIN_STATUS

export function FactorLibrary({ onInspect, onEdit }: { onInspect: (factorId: string) => void; onEdit?: (factorId: string) => void }) {
  const [query, setQuery] = useState('')
  const [kind, setKind] = useState('all')
  const [group, setGroup] = useState('all')
  const [status, setStatus] = useState('all')
  const [view, setView] = useState<'library' | 'archive'>('library')
  const [detail, setDetail] = useState<FactorLibraryItem | null>(null)

  const lib = useQuery({
    queryKey: QK.factorLibrary('all'),
    queryFn: () => api.factorLibrary(),
    // 注册表近乎静态 (只在保存/删除自定义因子时变化, 届时主动 invalidate), 切 tab 不再闪 loading
    staleTime: 60_000,
  })
  const allFactors = lib.data?.factors ?? []
  const archivedCount = allFactors.filter(item => item.archived).length
  // 因子库隐藏已归档; 档案库只看已归档 — 归档可逆, 定义与计算均不受影响
  const factors = view === 'archive' ? allFactors.filter(item => item.archived) : allFactors.filter(item => !item.archived)

  const groups = useMemo(
    () => Array.from(new Set(factors.map(item => item.group))).sort((a, b) => a.localeCompare(b, 'zh')),
    [factors],
  )

  const queryClient = useQueryClient()
  const setArchived = useMutation({
    mutationFn: ({ id, archived }: { id: string; archived: boolean }) => api.factorArchive(id, archived),
    onSuccess: (_data, variables) => {
      toast(variables.archived ? '已归档到档案库，可随时恢复' : '已恢复到因子库', 'success')
      void refreshResourceQueries(queryClient)
    },
    onError: (error: Error) => toast(`操作失败 · ${error.message}`, 'error'),
  })

  const filtered = useMemo(() => {
    const keyword = query.trim().toLowerCase()
    return factors.filter(item => {
      if (kind !== 'all' && item.kind !== kind) return false
      if (group !== 'all' && item.group !== group) return false
      if (status !== 'all') {
        if (status === 'builtin') {
          if (item.status != null) return false
        } else if (item.status !== status) {
          return false
        }
      }
      if (keyword && !`${item.id} ${item.label} ${item.formula}`.toLowerCase().includes(keyword)) return false
      return true
    })
  }, [factors, query, kind, group, status])

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden rounded-card border border-border bg-surface">
      <div className="flex flex-wrap items-center gap-2 border-b border-border px-3 py-2.5">
        <div className="relative">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3 w-3 -translate-y-1/2 text-muted" />
          <input
            type="text"
            value={query}
            onChange={event => setQuery(event.target.value)}
            placeholder="搜索因子 (id / 名称 / 公式)"
            className={cn(INPUT_CLS, 'w-56 pl-7')}
          />
        </div>
        <select value={kind} onChange={event => setKind(event.target.value)} className={cn(fieldSelect, 'w-24 text-xs')} aria-label="因子类型">
          <option value="all">全部类型</option>
          <option value="base">基础</option>
          <option value="virtual">虚拟</option>
          <option value="composite">复合</option>
          <option value="custom">自定义</option>
        </select>
        <select value={group} onChange={event => setGroup(event.target.value)} className={cn(fieldSelect, 'w-28 text-xs')} aria-label="因子分组">
          <option value="all">全部分组</option>
          {groups.map(name => <option key={name} value={name}>{name}</option>)}
        </select>
        <select value={status} onChange={event => setStatus(event.target.value)} className={cn(fieldSelect, 'w-24 text-xs')} aria-label="生命周期状态">
          <option value="all">全部状态</option>
          <option value="builtin">内置</option>
          <option value="active">激活</option>
          <option value="watch">观察</option>
          <option value="draft">草稿</option>
          <option value="retired">退役</option>
        </select>
        <span className="ml-auto text-micro text-muted">{lib.isLoading ? '加载中…' : `${filtered.length} / ${factors.length} 个因子`}</span>
        <div className={SEG} role="tablist" aria-label="因子库视图">
          {([['library', '因子库'], ['archive', `档案库 ${archivedCount}`]] as const).map(([id, label]) => (
            <button key={id} type="button" role="tab" aria-selected={view === id} onClick={() => setView(id)}
              className={cn(SEG_ITEM, view === id ? SEG_ON : SEG_OFF)}>
              {label}
            </button>
          ))}
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-auto">
        {lib.isError && (
          <div className="m-3 rounded-btn border border-danger/30 bg-danger/10 px-3 py-2 text-xs text-danger">
            {String((lib.error as Error).message)}
          </div>
        )}
        {lib.isLoading && (
          <div className="p-6 text-center text-xs text-muted">因子库加载中…</div>
        )}
        {!lib.isLoading && !lib.isError && filtered.length === 0 && (
          <div className="p-6 text-center text-xs text-muted">
            {view === 'archive'
              ? (archivedCount > 0 ? '筛选条件下无归档因子' : '档案库为空。在因子详情里点「归档」收藏不用的因子，可随时恢复。')
              : '无匹配因子'}
          </div>
        )}
        {!lib.isLoading && filtered.length > 0 && (
          <table className="w-full text-xs max-sm:block sm:min-w-[760px]">
            {/* [R537] 手机上不横滑(用户: 「手机版现在不搞左右滑动」): 一行一块 —— 名字·id·去检验 / 分组·类型·公式;
              预热、适用两列手机上不显示(详情抽屉里都有)。桌面照旧是表格, 名字与 id 并成一行, 行高减半。 */}
            <thead className={cn(THEAD, 'z-20 text-left max-sm:hidden', TH_ROW)}>
              <tr>
                <th className="px-3 py-2 font-normal">因子</th>
                <th className="px-3 py-2 font-normal">分组</th>
                <th className="px-3 py-2 font-normal">类型</th>
                <th className="px-3 py-2 font-normal">公式</th>
                <th className="px-3 py-2 font-normal" title="按需计算所需的最少历史交易日数">预热</th>
                <th className="px-3 py-2 font-normal">适用</th>
                <th className="w-24 px-3 py-2 text-right font-normal">操作</th>
              </tr>
            </thead>
            <tbody className="max-sm:block">
              {filtered.map(item => (
                <tr
                  key={item.id}
                  onClick={() => setDetail(item)}
                  className="cursor-pointer border-t border-border/70 transition-colors hover:bg-elevated/40 max-sm:flex max-sm:flex-wrap max-sm:items-center max-sm:gap-x-2 max-sm:px-2 max-sm:py-2"
                >
                  <td className="px-3 py-2 max-sm:w-[calc(100%-6rem)] max-sm:p-0">
                    <div className="flex min-w-0 items-baseline gap-2">
                      <span className="shrink-0 font-medium text-foreground">{item.label}</span>
                      <span className="truncate font-mono text-micro text-muted">{item.id}</span>
                    </div>
                  </td>
                  <td className="px-3 py-2 text-secondary max-sm:order-3 max-sm:p-0">{item.group}</td>
                  <td className="whitespace-nowrap px-3 py-2 max-sm:order-4 max-sm:p-0">
                    <Badge tone={KIND_META[item.kind].tone}>
                      {KIND_META[item.kind].label}
                    </Badge>
                    {item.pit && <span className="ml-1 text-micro text-warning" title="点时数据: 仅使用公告日不晚于当日的财务数据">点时</span>}
                    {item.archived ? (
                      <Badge className="ml-1">已归档</Badge>
                    ) : item.status != null && (
                      <Badge className="ml-1" tone={statusOf(item).tone}>
                        {statusOf(item).label}
                      </Badge>
                    )}
                  </td>
                  <td className="max-w-[22rem] px-3 py-2 max-sm:order-5 max-sm:min-w-0 max-sm:flex-1 max-sm:p-0">
                    <span className="block truncate text-secondary" title={item.formula}>{item.formula}</span>
                  </td>
                  <td className="px-3 py-2 font-mono text-secondary max-sm:hidden">{item.warmup_bars > 1 ? `${item.warmup_bars}日` : '—'}</td>
                  <td className="px-3 py-2 text-muted max-sm:hidden">
                    {item.asset_types.includes('stock') && item.asset_types.includes('etf') ? '股票/ETF' : item.asset_types.join('/')}
                  </td>
                  <td className="px-3 py-2 text-right max-sm:order-2 max-sm:ml-auto max-sm:p-0">
                    <Button
                      variant="ghost"
                      size="xs"
                      onClick={event => { event.stopPropagation(); onInspect(item.id) }}
                      className="gap-1 text-accent"
                      title="去检验该因子（切到检验页并只选它）"
                    >
                      去检验 <ArrowRight className="h-3 w-3" />
                    </Button>
                    {(item.kind === 'custom' || item.kind === 'composite') && (
                      <Button
                        variant="ghost"
                        size="xs"
                        onClick={event => { event.stopPropagation(); setArchived.mutate({ id: item.id, archived: !item.archived }) }}
                        disabled={setArchived.isPending}
                        className="ml-1 gap-1"
                        title={item.archived ? '恢复到因子库 (归档可逆, 不影响计算)' : '归档到档案库 (可恢复, 不删除因子)'}
                      >
                        {item.archived ? <><ArchiveRestore className="h-3 w-3" />恢复</> : <><Archive className="h-3 w-3" />归档</>}
                      </Button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {detail && <FactorDetailModal item={detail} onClose={() => setDetail(null)} onInspect={onInspect} onEdit={onEdit} />}
    </div>
  )
}

function FactorDetailModal({
  item,
  onClose,
  onInspect,
  onEdit,
}: {
  item: FactorLibraryItem
  onClose: () => void
  onInspect: (factorId: string) => void
  onEdit?: (factorId: string) => void
}) {
  const queryClient = useQueryClient()
  const setStatus = useMutation({
    mutationFn: (status: 'draft' | 'active' | 'watch' | 'retired') => api.factorSetStatus(item.id, status),
    onSuccess: data => {
      toast(`${item.label} 状态已更新为 ${data.status}`, 'success')
      void queryClient.invalidateQueries({ queryKey: ['factors-library'] })
      onClose()
    },
    onError: (error: Error) => toast(`状态更新失败 · ${error.message}`, 'error'),
  })
  const setArchived = useMutation({
    mutationFn: (archived: boolean) => api.factorArchive(item.id, archived),
    onSuccess: (_data, archived) => {
      toast(archived ? `${item.label} 已归档，可在档案库恢复` : `${item.label} 已恢复到因子库`, 'success')
      void refreshResourceQueries(queryClient)
      onClose()
    },
    onError: (error: Error) => toast(`操作失败 · ${error.message}`, 'error'),
  })
  const isDynamic = item.kind === 'custom' || item.kind === 'composite'
  const [groupDraft, setGroupDraft] = useState(item.group)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [blockedRefs, setBlockedRefs] = useState<string[] | null>(null)
  const [generateOpen, setGenerateOpen] = useState(false)
  const removeFactor = useMutation({
    mutationFn: (force: boolean) => api.factorDelete(item.id, force),
    onSuccess: data => {
      const refs = data.removed_references ?? []
      toast(
        refs.length > 0
          ? `${item.label} 已强制删除 · ${refs.length} 处引用需手动调整 (${refs.join('、')})`
          : `${item.label} 已删除`,
        'success',
      )
      void queryClient.invalidateQueries({ queryKey: ['factors-library'] })
      onClose()
    },
    onError: (error: Error) => {
      // 409 时 detail 为 {message, references} → request() 已 stringify 成 JSON 文本
      try {
        const parsed = JSON.parse(error.message) as { references?: string[] }
        if (Array.isArray(parsed.references) && parsed.references.length > 0) {
          setBlockedRefs(parsed.references)
          return
        }
      } catch { /* 非 JSON 报错, 走通用提示 */ }
      toast(`删除失败 · ${error.message}`, 'error')
    },
  })
  const setGroup = useMutation({
    mutationFn: () => api.factorSetGroup(item.id, groupDraft.trim()),
    onSuccess: data => {
      toast(`${item.label} 分组已改为 ${data.group}`, 'success')
      void queryClient.invalidateQueries({ queryKey: ['factors-library'] })
      onClose()
    },
    onError: (error: Error) => toast(`分组修改失败 · ${error.message}`, 'error'),
  })
  const rows: [string, string][] = [
    ['标识', item.id],
    ['名称', item.label],
    ['分组', item.group],
    ['类型', KIND_META[item.kind].label],
    ['公式', item.formula],
    ['版本', `v${item.version}`],
    ['预热', item.warmup_bars > 1 ? `${item.warmup_bars} 个交易日` : '无需滚动窗口'],
    ['点时数据', item.pit ? '是（按公告日口径，不泄露未公告数据）' : '否'],
    ['适用资产', item.asset_types.join(' / ')],
    ['跨标的可比', item.scale_free ? '是（可直接截面排序）' : '否（原值受价格尺度影响）'],
    ['依赖列', item.dependencies.length > 0 ? item.dependencies.join(', ') : '已物化列'],
    ['状态', item.stability === 'stable' ? '稳定' : item.stability],
  ]
  return (
    <Modal
      onClose={onClose}
      labelledBy="factor-detail-title"
      panelClassName={dialogPanel('md', 'flex max-h-[86vh] flex-col overflow-hidden')}
    >
      <div className={DIALOG_HEADER}>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <FlaskConical className="h-4 w-4 shrink-0 text-accent" />
            <h2 id="factor-detail-title" className={cn('truncate', DIALOG_TITLE)}>{item.label}</h2>
            <Badge className="shrink-0" tone={KIND_META[item.kind].tone}>
              {KIND_META[item.kind].label}
            </Badge>
            {item.archived ? (
              <Badge className="shrink-0">已归档</Badge>
            ) : item.status != null && (
              <Badge className="shrink-0" tone={statusOf(item).tone}>
                {statusOf(item).label}
              </Badge>
            )}
          </div>
          <div className="mt-1 font-mono text-xs text-muted">{item.id}</div>
        </div>
        <DialogClose onClose={onClose} />
      </div>
      <div className={cn(DIALOG_BODY, 'min-h-0 flex-1 overflow-y-auto')}>
        <dl className="space-y-2">
          {rows.map(([key, value]) => (
            <div key={key} className="flex items-start gap-3 text-xs">
              <dt className="w-20 shrink-0 text-muted">{key}</dt>
              <dd className="min-w-0 flex-1 break-words text-secondary">
                {key === '分组' && isDynamic ? (
                  <span className="flex items-center gap-1.5" title="自定义/复合因子可修改分组; 内置因子分组固定">
                    <input
                      type="text"
                      value={groupDraft}
                      maxLength={24}
                      onChange={event => setGroupDraft(event.target.value)}
                      className={cn(fieldInput, 'h-7 w-32 text-xs')}
                      aria-label="修改分组"
                    />
                    <Button
                      size="xs"
                      onClick={() => setGroup.mutate()}
                      disabled={setGroup.isPending || !groupDraft.trim() || groupDraft.trim() === item.group}
                    >
                      保存
                    </Button>
                  </span>
                ) : value}
              </dd>
            </div>
          ))}
        </dl>
        <div className="mt-4 rounded-btn border border-border bg-base/40 px-3 py-2 text-xs leading-relaxed text-muted">
          方向说明：因子方向不预填，以最近一次检验的 IC 符号为准（IC 为正 = 值大看多）。到「检验」页运行后可查看。
        </div>
      </div>
      <div className={cn(DIALOG_FOOTER, 'flex-wrap justify-start')}>
        {isDynamic && (
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="text-micro text-muted" title="生命周期流转">状态：</span>
            {(['active', 'watch', 'retired', 'draft'] as const).map(status => (
              <Button
                key={status}
                size="xs"
                onClick={() => setStatus.mutate(status)}
                disabled={setStatus.isPending}
              >
                {status === 'active' ? '激活' : status === 'watch' ? '观察' : status === 'retired' ? '退役' : '回草稿'}
              </Button>
            ))}
          </div>
        )}
        {isDynamic && (
          <Button
            size="xs"
            onClick={() => setArchived.mutate(!item.archived)}
            disabled={setArchived.isPending}
            className="gap-1"
            title="归档可逆: 收进档案库, 不删除定义、不影响引用它的策略与评分列"
          >
            {item.archived ? <><ArchiveRestore className="h-3 w-3" />恢复到因子库</> : <><Archive className="h-3 w-3" />归档到档案库</>}
          </Button>
        )}
        {item.kind === 'custom' && onEdit && (
          <Button
            onClick={() => { onClose(); onEdit(item.id) }}
            className="gap-1"
            title="在编辑器中打开该公式, 修改后保存为新版本"
          >
            <PenLine className="h-3 w-3" />
            编辑公式
          </Button>
        )}
        <Button
          onClick={() => setGenerateOpen(true)}
          className="gap-1"
          title="按该因子生成单因子排名策略, 保存到自定义策略后可直接回测"
        >
          <Sparkles className="h-3 w-3" />
          生成策略
        </Button>
        <Button
          variant="primary"
          onClick={() => { onClose(); onInspect(item.id) }}
          className="ml-auto shrink-0 gap-1"
        >
          检验此因子 <ArrowRight className="h-3 w-3" />
        </Button>
        {isDynamic && (
          confirmDelete ? (
            <>
              <Button
                variant="danger"
                onClick={() => removeFactor.mutate(false)}
                disabled={removeFactor.isPending}
                className="shrink-0 gap-1"
              >
                {removeFactor.isPending ? '删除中…' : '确认删除'}
              </Button>
              <Button
                onClick={() => { setConfirmDelete(false); setBlockedRefs(null) }}
                className="shrink-0"
              >
                取消
              </Button>
            </>
          ) : (
            <Button
              variant="danger"
              onClick={() => setConfirmDelete(true)}
              className="shrink-0 gap-1"
              title="删除该自定义/复合因子; 被策略或复合因子引用时需强制删除"
            >
              <Trash2 className="h-3 w-3" />
              删除
            </Button>
          )
        )}
        {blockedRefs && (
          <div className="w-full rounded-btn border border-danger/40 bg-danger/10 px-3 py-2 text-xs leading-relaxed text-danger">
            <div className="font-medium">该因子仍被以下对象引用，删除后相关策略/复合因子将无法计算：</div>
            <div className="mt-1 font-mono text-micro break-all text-danger/90">{blockedRefs.join('、')}</div>
            <div className="mt-2 flex items-center gap-2">
              <Button
                variant="danger"
                size="sm"
                onClick={() => removeFactor.mutate(true)}
                disabled={removeFactor.isPending}
              >
                {removeFactor.isPending ? '删除中…' : '仍要强制删除'}
              </Button>
              <button
                type="button"
                onClick={() => setBlockedRefs(null)}
                className="text-xs text-secondary underline-offset-2 transition-colors hover:text-foreground hover:underline"
              >
                收起
              </button>
            </div>
          </div>
        )}
      </div>
      {generateOpen && (
        <GenerateFactorStrategyDialog item={item} onClose={() => setGenerateOpen(false)} />
      )}
    </Modal>
  )
}
