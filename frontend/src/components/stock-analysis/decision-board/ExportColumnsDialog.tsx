/**
 * [fork 增强] R182 导出选列面板。
 *
 * 按分组罗列全部可导出的列, 勾选即生效, 选择记在本地(下次打开还是这套)。
 *
 * 「趋势」组里那四个默认没勾的(持续/跌破转弱/站上转强/近期信号)是原**六态汇总**
 * 弹窗独有的字段 —— 那个弹窗已经并进导出, 勾上这四个、取消其余, 导出的就是它。
 * 面板里给了一个一键预设做这件事, 免得用户逐个点。
 */
import { useMemo } from 'react'
import { Check, Download, X } from 'lucide-react'
import { Modal } from '@/components/Modal'
import { cn } from '@/lib/cn'
import { TYPE, buttonClass } from '@/components/ui'
import {
  DEFAULT_EXPORT_KEYS,
  EXPORT_COLUMNS,
  type ExportColumn,
} from '@/lib/decisionBoardExportColumns'

/** 原六态汇总的那几列 —— 标的与现价是任何视图都要的, 所以一并带上 */
const TREND_PRESET = ['name', 'close', 'trend', 'dur', 'flipDown', 'flipUp', 'trendSignal']

const GROUP_ORDER: ExportColumn['group'][] = ['决策', '行情', '持仓', '通道', '趋势']

export function ExportColumnsDialog({
  keys, onChange, onExport, onClose, rowCount,
}: {
  keys: string[]
  onChange: (keys: string[]) => void
  onExport: () => void
  onClose: () => void
  rowCount: number
}) {
  const picked = useMemo(() => new Set(keys), [keys])
  const grouped = useMemo(() => {
    const m = new Map<string, ExportColumn[]>()
    for (const c of EXPORT_COLUMNS) {
      if (!m.has(c.group)) m.set(c.group, [])
      m.get(c.group)!.push(c)
    }
    return GROUP_ORDER.filter(g => m.has(g)).map(g => [g, m.get(g)!] as const)
  }, [])

  const toggle = (key: string) => {
    const next = new Set(picked)
    if (next.has(key)) next.delete(key)
    else next.add(key)
    // 一列都不留的话导出是一张空表 —— 不给它变成这样
    if (next.size === 0) return
    onChange(EXPORT_COLUMNS.filter(c => next.has(c.key)).map(c => c.key))
  }

  return (
    <Modal
      onClose={onClose}
      labelledBy="export-cols-title"
      panelClassName="flex max-h-[86vh] w-[94vw] max-w-2xl flex-col rounded-card border border-border bg-surface shadow-xl"
    >
      <div className="flex items-center gap-2 border-b border-border/60 px-4 py-3">
        <Download className="h-4 w-4 text-accent" />
        <h2 id="export-cols-title" className={TYPE.section}>导出 · 选列</h2>
        <span className="text-xs text-muted">{rowCount} 只 · 已选 {keys.length} 列</span>
        <button
          onClick={onClose}
          aria-label="关闭"
          className={buttonClass({ icon: true }, 'ml-auto')}
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      <div className="min-h-0 flex-1 space-y-3 overflow-y-auto px-4 py-3">
        <div className="flex flex-wrap gap-1.5">
          <Preset label="屏幕上那套" onClick={() => onChange(DEFAULT_EXPORT_KEYS)} />
          <Preset
            label="六态汇总"
            title="原「六态汇总」弹窗导出的那几列 —— 那个弹窗已经并进这里"
            onClick={() => onChange(EXPORT_COLUMNS.filter(c => TREND_PRESET.includes(c.key)).map(c => c.key))}
          />
          <Preset label="全选" onClick={() => onChange(EXPORT_COLUMNS.map(c => c.key))} />
        </div>

        {grouped.map(([group, cols]) => (
          <section key={group}>
            <div className={cn('mb-1.5', TYPE.label)}>{group}</div>
            <div className="flex flex-wrap gap-1.5">
              {cols.map(c => (
                <button
                  key={c.key}
                  onClick={() => toggle(c.key)}
                  className={buttonClass({ selected: picked.has(c.key) }, 'gap-1')}
                >
                  {picked.has(c.key) && <Check className="h-3 w-3" />}
                  {c.label}
                </button>
              ))}
            </div>
          </section>
        ))}

        <p className="text-xs text-muted/70">
          导出的读法与屏幕一致(比如通道列写「贴上轨」而不是 0.87)——
          对不上的话你会怀疑哪个是错的。列序按上面的固定顺序，不随勾选先后变。
        </p>
      </div>

      <div className="flex items-center gap-2 border-t border-border/60 px-4 py-2.5">
        <button
          onClick={onExport}
          disabled={rowCount === 0 || keys.length === 0}
          className={buttonClass({ variant: 'primary' }, 'gap-1.5')}
        >
          <Download className="h-3.5 w-3.5" />
          导出 {rowCount} 只 · {keys.length} 列
        </button>
        <span className="text-xs text-muted/70">自包含 HTML,可存档、打印或转发</span>
      </div>
    </Modal>
  )
}

function Preset({ label, title, onClick }: { label: string; title?: string; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      title={title}
      className={buttonClass()}
    >
      {label}
    </button>
  )
}
