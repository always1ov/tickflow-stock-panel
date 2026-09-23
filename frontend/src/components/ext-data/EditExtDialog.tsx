import { useRef, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import { X, Loader2, Upload } from 'lucide-react'
import { api, type ExtDataConfig, type ExtDataField } from '@/lib/api'
import { QK } from '@/lib/queryKeys'
import { useDialogBackdrop } from '@/lib/useDialogBackdrop'
import { TYPE, buttonClass } from '@/components/ui'

export function EditExtDialog({ config, onClose }: { config: ExtDataConfig; onClose: () => void }) {
  const qc = useQueryClient()
  const backdrop = useDialogBackdrop(onClose)
  const [label, setLabel] = useState(config.label)
  const [description, setDescription] = useState(config.description ?? '')
  const [fields, setFields] = useState<ExtDataField[]>([...config.fields])
  const [error, setError] = useState('')
  const detectFileRef = useRef<HTMLInputElement>(null)
  const [detecting, setDetecting] = useState(false)
  const [symbolMapping, setSymbolMapping] = useState<{ candidates: string[]; file: File } | null>(null)

  const update = useMutation({
    mutationFn: () =>
      api.extDataUpdate(config.id, {
        label: label.trim(),
        fields: fields.filter((f) => f.name.trim()),
        description: description.trim() || '',
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: QK.extData })
      onClose()
    },
    onError: (err) => setError(String(err)),
  })

  const addField = () =>
    setFields([...fields, { name: '', dtype: 'string', label: '' }])

  const removeField = (i: number) =>
    setFields(fields.filter((_, idx) => idx !== i))

  const updateField = (i: number, key: keyof ExtDataField, val: string) =>
    setFields(fields.map((f, idx) => (idx === i ? { ...f, [key]: val } : f)))

  const valid = label.trim() && fields.some((f) => f.name.trim())

  const applyDetectedFields = (detected: { name: string; dtype: string; label: string }[]) => {
    const rest = detected.filter(f => f.name !== 'symbol')
    setFields([
      { name: 'symbol', dtype: 'string', label: '标的代码' },
      ...rest,
    ])
  }

  const handleDetectFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    e.target.value = ''
    setDetecting(true); setError(''); setSymbolMapping(null)
    api.extDataDetectFields(file)
      .then((res) => {
        const hasSym = res.symbol_candidates.length > 0
        const hasCode = res.code_candidates.length > 0
        if (hasSym || hasCode) {
          applyDetectedFields(res.fields)
        } else {
          const candidates = res.fields.map(f => f.name)
          setSymbolMapping({ candidates, file })
        }
      })
      .catch((err) => setError(String(err)))
      .finally(() => setDetecting(false))
  }

  const handleSymbolMap = (_col: string) => {
    if (!symbolMapping) return
    setDetecting(true); setError('')
    const rest = fields.filter(f => f.name !== 'symbol')
    setFields([{ name: 'symbol', dtype: 'string', label: '标的代码' }, ...rest])
    setSymbolMapping(null)
    setDetecting(false)
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" {...backdrop} />
      <motion.div
        initial={{ opacity: 0, scale: 0.95, y: 12 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.97, y: 8 }}
        transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
        className="relative rounded-card border border-border bg-surface shadow-2xl mx-4 w-full max-w-2xl max-h-[85vh] flex flex-col overflow-hidden"
      >
        <div className="flex items-center justify-between px-5 py-3 border-b border-border">
          <h3 className={TYPE.section}>编辑扩展数据</h3>
          <button onClick={onClose} className={buttonClass({ variant: 'ghost', icon: true })}>
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4">
          <div className="grid grid-cols-[1fr_1fr] gap-3">
            <div>
              <label className="text-micro text-muted mb-1 block">标识符</label>
              <div className="h-8 px-3 rounded-btn bg-elevated/50 border border-border text-xs text-muted font-mono flex items-center">
                {config.id}
              </div>
            </div>
            <div>
              <label className="text-micro text-muted mb-1 block">数据类型</label>
              <div className={`h-8 px-3 rounded-btn border text-xs flex items-center ${
                config.mode === 'snapshot'
                  ? 'bg-blue-500/10 border-blue-500/30 text-blue-400'
                  : 'bg-amber-500/10 border-amber-500/30 text-amber-400'
              }`}>
                {config.mode === 'snapshot' ? '快照型' : '时序型'}
              </div>
            </div>
          </div>

          <div>
            <label className="text-micro text-muted mb-1 block">显示名称</label>
            <input
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              className="w-full h-8 px-3 rounded-btn bg-base border border-border text-xs text-foreground placeholder:text-muted/40 focus:outline-none focus:border-accent/50"
            />
          </div>

          <div>
            <label className="text-micro text-muted mb-1 block">描述</label>
            <input
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="可选，简要说明数据的用途"
              className="w-full h-8 px-3 rounded-btn bg-base border border-border text-xs text-foreground placeholder:text-muted/40 focus:outline-none focus:border-accent/50"
            />
          </div>

          <div>
            <div className="flex items-center justify-between mb-1.5">
              <div className={TYPE.card}>字段定义</div>
              <div className="flex items-center gap-2">
                <input
                  ref={detectFileRef}
                  type="file"
                  accept=".csv,.xlsx,.xls"
                  className="hidden"
                  onChange={handleDetectFile}
                />
                <button
                  onClick={() => detectFileRef.current?.click()}
                  disabled={detecting}
                  className={buttonClass({ size: 'xs' }, 'gap-1')}
                >
                  {detecting ? <Loader2 className="h-3 w-3 animate-spin" /> : <Upload className="h-3 w-3" />}
                  从文件导入
                </button>
                <button onClick={addField} className={buttonClass({ size: 'xs' })}>+ 添加字段</button>
              </div>
            </div>
            {symbolMapping && (
              <div className="mb-2 rounded-card border border-warning/30 bg-warning/[0.06] px-3 py-2 space-y-1.5">
                <div className="text-xs text-warning">未找到 symbol 列，请选择哪一列作为标的代码：</div>
                <div className="flex flex-wrap gap-1.5">
                  {symbolMapping.candidates.map(col => (
                    <button
                      key={col}
                      onClick={() => handleSymbolMap(col)}
                      className={buttonClass({ size: 'xs' }, 'font-mono')}
                    >
                      {col}
                    </button>
                  ))}
                  <button
                    onClick={() => setSymbolMapping(null)}
                    className={buttonClass({ size: 'xs', variant: 'ghost' })}
                  >
                    取消
                  </button>
                </div>
              </div>
            )}
            <div className="space-y-2">
              {fields.map((f, i) => {
                const isBuiltin = f.name === 'symbol' || f.name === 'name'
                return (
                  <div key={i} className="flex items-center gap-2">
                    <input
                      value={f.label}
                      onChange={(e) => updateField(i, 'label', e.target.value)}
                      placeholder="显示名"
                      disabled={isBuiltin}
                      className={`w-20 h-7 px-2 rounded-btn border text-xs text-foreground placeholder:text-muted/40 focus:outline-none focus:border-accent/50 ${
                        isBuiltin
                          ? 'bg-elevated/50 border-border text-muted cursor-not-allowed'
                          : 'bg-base border-border'
                      }`}
                    />
                    <input
                      value={f.name}
                      onChange={(e) => updateField(i, 'name', e.target.value)}
                      placeholder="字段名 (英文)"
                      disabled={isBuiltin}
                      className={`flex-1 h-7 px-2 rounded-btn border text-xs font-mono placeholder:text-muted/40 focus:outline-none focus:border-accent/50 ${
                        isBuiltin
                          ? 'bg-elevated/50 border-border text-muted cursor-not-allowed'
                          : 'bg-base border-border'
                      }`}
                    />
                    <select
                      value={f.dtype}
                      onChange={(e) => updateField(i, 'dtype', e.target.value)}
                      disabled={isBuiltin}
                      className={`h-7 px-2 rounded-btn border border-border text-xs text-foreground ${
                        isBuiltin ? 'bg-elevated/50 text-muted cursor-not-allowed' : 'bg-base'
                      }`}
                    >
                      <option value="string">文本</option>
                      <option value="int">整数</option>
                      <option value="float">小数</option>
                      <option value="bool">布尔</option>
                    </select>
                    {!isBuiltin && fields.length > 3 && (
                      <button onClick={() => removeField(i)} className="p-1 text-muted hover:text-danger">
                        <X className="h-3 w-3" />
                      </button>
                    )}
                    {isBuiltin && <div className="w-[18px]" />}
                  </div>
                )
              })}
            </div>
          </div>

          {error && (
            <div className="text-xs text-danger bg-danger/5 rounded-btn px-3 py-1.5">{error}</div>
          )}
        </div>

        <div className="flex items-center justify-end gap-2 px-5 py-3 border-t border-border">
          <button onClick={onClose} className={buttonClass()}>
            取消
          </button>
          <button
            onClick={() => update.mutate()}
            disabled={!valid || update.isPending}
            className={buttonClass({ variant: 'primary' })}
          >
            {update.isPending ? '保存中…' : '保存'}
          </button>
        </div>
      </motion.div>
    </div>
  )
}
