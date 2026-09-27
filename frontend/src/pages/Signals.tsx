import { useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Lock, Plus, Settings2, SlidersHorizontal, Trash2, Zap } from 'lucide-react'
import { api, type CustomSignal } from '@/lib/api'
import { QK } from '@/lib/queryKeys'
import { BUILTIN_SIGNAL_DEFINITIONS, type SignalKind } from '@/lib/signals'
import { CustomSignalDialog } from '@/components/signals/CustomSignalDialog'
import { Skeleton } from '@/components/data/Skeleton'
import { PageHeader } from '@/components/PageHeader'
import { AnchorWrap } from '@/lib/useCardFlash'
import { TYPE, buttonClass } from '@/components/ui'
import { PageTabs, usePageTab, type PageTabDef } from '@/components/PageTabs'
import { cn } from '@/lib/cn'

type SignalSection = 'builtin' | 'custom'

const KIND_LABEL: Record<SignalKind, string> = { entry: '入场', exit: '出场', both: '出入通用' }
const KIND_CLASS: Record<SignalKind, string> = {
  entry: 'bg-accent/10 text-accent',
  exit: 'bg-warning/10 text-warning',
  both: 'bg-muted/10 text-muted',
}

/** 信号库独立页: 内置只读信号 + 自定义条件信号 (csg_*), 策略/回测/监控统一取用。 */
// [R542] 分栏挪进页头(与因子 / 回测 / 异动监控同一份 PageTabs), 当前栏记在 `?tab=`;
// 原来在正文里、是组件状态, 一刷新就回到「自定义信号」。
const SECTIONS: Record<SignalSection, PageTabDef> = {
  custom: { title: '自定义信号', icon: SlidersHorizontal },
  builtin: { title: '内置信号', icon: Lock },
}

export function Signals() {
  const [searchParams] = useSearchParams()
  const highlight = searchParams.get('highlight') ?? ''
  const [activeSection, setActiveSection] = usePageTab(SECTIONS, 'custom')
  const list = useQuery({ queryKey: QK.customSignals, queryFn: api.customSignalsList })
  const [showForm, setShowForm] = useState(false)
  const [editing, setEditing] = useState<CustomSignal | null>(null)

  const openNew = () => {
    setEditing(null)
    setActiveSection('custom')
    setShowForm(true)
  }

  return (
    <div className="flex flex-col h-full">
      <PageHeader
        title="信号库"
        subtitle={<span className="hidden md:inline">内置预计算信号与自定义条件信号, 供策略 / 回测 / 监控统一使用</span>}
        className="flex-wrap gap-x-4 gap-y-2"
        right={(
          <div className="flex min-w-0 flex-wrap items-center gap-2">
            <PageTabs
              tabs={SECTIONS}
              active={activeSection}
              onChange={setActiveSection}
              counts={{ custom: list.data?.signals.length ?? null, builtin: BUILTIN_SIGNAL_DEFINITIONS.length }}
              label="信号分栏"
            />
            <button onClick={openNew} className={buttonClass({}, 'shrink-0 gap-1.5')}>
              <Plus className="h-3.5 w-3.5" />
              新建信号
            </button>
          </div>
        )}
      />
      {/* [R542] 内容区不设宽度上限(原 max-w-6xl), 与设置页「铺满」一致 */}
      <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4 lg:px-5">
        <SignalsBody
          highlight={highlight}
          activeSection={activeSection}
          setActiveSection={setActiveSection}
          showForm={showForm}
          setShowForm={setShowForm}
          editing={editing}
          setEditing={setEditing}
        />
      </div>
    </div>
  )
}

function SignalsBody({ highlight, activeSection, setActiveSection, showForm, setShowForm, editing, setEditing }: {
  highlight: string
  activeSection: SignalSection
  setActiveSection: (s: SignalSection) => void
  showForm: boolean
  setShowForm: (v: boolean) => void
  editing: CustomSignal | null
  setEditing: (s: CustomSignal | null) => void
}) {
  const qc = useQueryClient()
  const list = useQuery({ queryKey: QK.customSignals, queryFn: api.customSignalsList })
  const options = useQuery({ queryKey: QK.customSignalsOptions, queryFn: api.customSignalsOptions })

  const [confirmingDeleteId, setConfirmingDeleteId] = useState<string | null>(null)
  const resetDeleteTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  const fields = options.data?.fields ?? []
  const signals = list.data?.signals ?? []

  useEffect(() => () => {
    if (resetDeleteTimer.current) clearTimeout(resetDeleteTimer.current)
  }, [])

  const clearDeleteConfirm = () => {
    if (resetDeleteTimer.current) clearTimeout(resetDeleteTimer.current)
    resetDeleteTimer.current = null
    setConfirmingDeleteId(null)
  }

  const openEdit = (sig: CustomSignal) => {
    setEditing(sig)
    clearDeleteConfirm()
    setActiveSection('custom')
    setShowForm(true)
  }
  const closeForm = () => {
    setShowForm(false)
    setEditing(null)
  }

  const del = useMutation({
    mutationFn: api.customSignalDelete,
    onSuccess: () => {
      clearDeleteConfirm()
      qc.invalidateQueries({ queryKey: QK.customSignals })
    },
  })

  const toggleEnabled = (sig: CustomSignal) => {
    api.customSignalSave({ ...sig, enabled: !sig.enabled }).then(() => qc.invalidateQueries({ queryKey: QK.customSignals }))
  }

  const handleDeleteClick = (sig: CustomSignal) => {
    if (confirmingDeleteId === sig.id) {
      clearDeleteConfirm()
      del.mutate(sig.id)
      return
    }
    setConfirmingDeleteId(sig.id)
    if (resetDeleteTimer.current) clearTimeout(resetDeleteTimer.current)
    resetDeleteTimer.current = setTimeout(() => setConfirmingDeleteId(null), 3000)
  }

  return (
    <div className="space-y-4">
      {activeSection === 'custom' && (
        <AnchorWrap highlight={highlight} anchor="signals">
        <section>
          {/* [R542] 原来外面还套一层白框(卡片套卡片), 手机上两层内边距把条件挤得折行; 去掉外框, 卡片直接排 */}
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
            {signals.map(sig => (
              <div key={sig.id} className="rounded-card border border-border bg-surface p-4">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <h3 className={cn('truncate', TYPE.card)}>{sig.name}</h3>
                      <span className={`rounded px-1.5 py-0.5 text-micro ${KIND_CLASS[sig.kind]}`}>
                        {KIND_LABEL[sig.kind]}
                      </span>
                      {!sig.enabled && <span className="rounded bg-muted/10 px-1.5 py-0.5 text-micro text-muted">已停用</span>}
                    </div>
                    <p className="mt-1 truncate font-mono text-xs text-muted">csg_{sig.id}</p>
                  </div>
                  <div className="flex shrink-0 items-center gap-1">
                    <button onClick={() => toggleEnabled(sig)} title={sig.enabled ? '停用' : '启用'} className={`cursor-pointer rounded p-1 ${sig.enabled ? 'text-bear hover:bg-bear/10' : 'text-muted hover:bg-elevated'}`}>
                      <Zap className="h-3.5 w-3.5" />
                    </button>
                    <button onClick={() => openEdit(sig)} className="cursor-pointer rounded p-1 text-muted hover:bg-accent/10 hover:text-accent" title="编辑">
                      <Settings2 className="h-3.5 w-3.5" />
                    </button>
                    {confirmingDeleteId === sig.id ? (
                      <button
                        onClick={() => handleDeleteClick(sig)}
                        disabled={del.isPending}
                        title="再次点击确认删除"
                        className="inline-flex cursor-pointer items-center gap-1 rounded-md border border-danger/30 bg-danger/15 px-1.5 py-0.5 text-micro font-medium text-danger disabled:opacity-50"
                      >
                        <Trash2 className="h-2.5 w-2.5" />确认
                      </button>
                    ) : (
                      <button
                        onClick={() => handleDeleteClick(sig)}
                        disabled={del.isPending}
                        className="cursor-pointer rounded p-1 text-muted hover:bg-danger/10 hover:text-danger disabled:opacity-50"
                        title="删除"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    )}
                  </div>
                </div>
                <div className="mt-3 space-y-1">
                  {sig.conditions.map((c, i) => (
                    <div key={i} className="flex flex-wrap items-baseline gap-x-1.5 text-xs text-secondary">
                      <span className="w-6 text-right text-muted/50">{i === 0 ? '当' : '且'}</span>
                      <span className="font-mono text-foreground/80">{fieldWithDays(c.left, c.leftDays, fields)}</span>
                      <span className="font-mono text-muted">{c.op}</span>
                      <span className="font-mono text-foreground/80">
                        {c.right.startsWith('field:')
                          ? fieldWithDays(c.right.slice(6), c.rightDays, fields)
                          : c.right}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            ))}
            {list.isLoading &&
              Array.from({ length: 2 }).map((_, i) => (
                <div key={`sk-${i}`} className="space-y-3 rounded-card border border-border bg-surface p-4">
                  <Skeleton w="w-1/2" h="h-4" />
                  <Skeleton w="w-1/3" h="h-3" />
                  <Skeleton h="h-4" />
                </div>
              ))}
            {!list.isLoading && signals.length === 0 && (
              <div className="rounded-card border border-dashed border-border px-5 py-10 text-center text-sm text-muted md:col-span-2 xl:col-span-3">
                暂无自定义信号。可用「字段 + 运算符 + 值」组合条件创建，或从检验页因子行一键生成；也可让 AI 按描述生成。
              </div>
            )}
          </div>
          <p className="mt-3 text-micro text-muted">
            自定义信号保存为 <span className="font-mono text-secondary">csg_*</span> 列，条件字段可用行情指标与全部注册因子
          </p>
        </section>
        </AnchorWrap>
      )}

      {activeSection === 'builtin' && (
        <section>
          <div className="mb-3 flex items-center gap-2 text-xs text-muted">
            <Lock className="h-3.5 w-3.5" />
            系统在 enriched 数据中预计算，策略选择器直接展示，只读。
          </div>
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
            {BUILTIN_SIGNAL_DEFINITIONS.map(sig => (
              <div key={sig.id} className="rounded-card border border-border bg-surface p-4">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <h4 className={cn('truncate', TYPE.card)}>{sig.name}</h4>
                      <span className={`rounded px-1.5 py-0.5 text-micro ${KIND_CLASS[sig.kind]}`}>
                        {KIND_LABEL[sig.kind]}
                      </span>
                    </div>
                    <p className="mt-1 truncate font-mono text-xs text-muted">{sig.id}</p>
                  </div>
                  <span className="shrink-0 rounded border border-border bg-elevated px-1.5 py-0.5 text-micro text-muted">{sig.category}</span>
                </div>
                <p className="mt-3 text-xs leading-5 text-secondary">{sig.description}</p>
              </div>
            ))}
          </div>
        </section>
      )}

      <CustomSignalDialog open={showForm} signal={editing} onClose={closeForm} />
    </div>
  )
}

function fieldLabel(key: string, fields: { key: string; label: string }[]): string {
  return fields.find(f => f.key === key)?.label ?? key
}

/** 带偏移标注的字段显示: 收盘价(前1日) / MA20(最新省略) */
function fieldWithDays(key: string, days: number | undefined, fields: { key: string; label: string }[]): string {
  const label = fieldLabel(key, fields)
  return days && days > 0 ? `${label}(前${days}日)` : label
}
