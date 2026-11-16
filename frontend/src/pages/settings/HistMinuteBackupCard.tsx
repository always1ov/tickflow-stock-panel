/**
 * 分时备用接口: 独立于自定义数据源的全局分钟兜底配置。
 *
 * 只在个股弹窗分时拉不到数据时自动使用, 不参与批量/定时同步;
 * 接口失效可随时删除, 删除时一并清除它写入的分钟数据。
 */
import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Loader2, PlugZap, Save, Trash2, FlaskConical } from 'lucide-react'
import { api, type HistMinuteBackupStatus } from '@/lib/api'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { fieldInput, fieldSelect } from '@/components/ui/Field'
import { toast } from '@/components/Toast'

const EMPTY_FORM = {
  url: '',
  method: 'GET',
  symbol_param: 'code',
  date_param: 'date',
  response_path: '',
  field_map: '{}',
  params: '{}',
  timeout: '30',
}

function formFromStatus(status?: HistMinuteBackupStatus) {
  const cfg = status?.config
  if (!cfg) return EMPTY_FORM
  return {
    url: cfg.url || '',
    method: cfg.method || 'GET',
    symbol_param: cfg.symbol_param || 'code',
    date_param: cfg.date_param || 'date',
    response_path: cfg.response_path || '',
    field_map: JSON.stringify(cfg.field_map || {}, null, 2),
    params: JSON.stringify(cfg.params || {}, null, 2),
    timeout: String(cfg.timeout ?? 30),
  }
}

export function HistMinuteBackupCard() {
  const qc = useQueryClient()
  const status = useQuery({
    queryKey: ['hist-minute-backup'],
    queryFn: api.histMinuteBackup,
  })
  const [form, setForm] = useState(EMPTY_FORM)
  const [advanced, setAdvanced] = useState(false)
  const [confirming, setConfirming] = useState(false)

  useEffect(() => {
    if (status.data) setForm(formFromStatus(status.data))
  }, [status.data])

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ['hist-minute-backup'] })
  }

  const payload = () => {
    let fieldMap: Record<string, string>
    let params: Record<string, unknown>
    try {
      fieldMap = JSON.parse(form.field_map || '{}')
      params = JSON.parse(form.params || '{}')
    } catch {
      throw new Error('字段映射 / 额外参数不是合法 JSON')
    }
    return {
      url: form.url.trim(),
      method: form.method,
      symbol_param: form.symbol_param.trim() || 'code',
      date_param: form.date_param.trim() || 'date',
      response_path: form.response_path.trim(),
      field_map: fieldMap,
      params,
      timeout: Number(form.timeout) || 30,
    }
  }

  const save = useMutation({
    mutationFn: async () => {
      const body = payload()
      if (!body.url) throw new Error('请先填写接口地址')
      await api.saveHistMinuteBackup(body)
      return api.testHistMinuteBackup()
    },
    onSuccess: (result) => {
      invalidate()
      toast(
        result.ok
          ? `已保存, ${result.trade_date ?? ''} 试拉成功 ${result.rows} 行`
          : '已保存, 但试拉结果为空, 请检查地址或参数名',
        result.ok ? 'success' : 'error',
      )
    },
    onError: (e: Error) => toast(e.message || '保存失败', 'error'),
  })

  const remove = useMutation({
    mutationFn: api.deleteHistMinuteBackup,
    onSuccess: (result) => {
      invalidate()
      setConfirming(false)
      setForm(EMPTY_FORM)
      const purged = result.purged_minute_rows ?? 0
      toast(
        purged > 0 ? `已删除, 并清除 ${purged} 行分钟数据` : '已删除',
        'success',
      )
    },
    onError: () => toast('删除失败', 'error'),
  })

  const configured = status.data?.configured ?? false
  const busy = save.isPending || remove.isPending

  return (
    <Card className="space-y-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="space-y-1">
          <div className="flex items-center gap-2 text-body font-medium text-foreground">
            <PlugZap size={16} />
            分时备用接口
          </div>
          <p className="text-micro leading-relaxed text-muted">
            所有数据源共用的分钟兜底：只在个股弹窗分时拉不到数据时自动请求，按单只单日拉取，
            不做批量/定时获取。代码与日期自动替换进 URL 的 code / date 参数
            （也支持在地址里写 {'{symbol}'} / {'{date}'} 占位）；指数自动带交易所前缀
            （000001.SH → SH000001）。
          </p>
        </div>
        <span
          className={
            configured
              ? 'rounded-btn bg-accent/10 px-2 py-0.5 text-micro text-accent'
              : 'rounded-btn bg-elevated px-2 py-0.5 text-micro text-muted'
          }
        >
          {configured ? '已启用' : '未配置'}
        </span>
      </div>

      <div className="flex flex-col gap-2 md:flex-row">
        <input
          className={`${fieldInput} w-full`}
          placeholder="https://example.com/api/hist_minute?code=600519&date=20260101&key=..."
          value={form.url}
          onChange={(e) => setForm({ ...form, url: e.target.value })}
          spellCheck={false}
        />
        <div className="flex items-center gap-2">
          <Button
            variant="primary"
            onClick={() => save.mutate()}
            disabled={busy}
          >
            {save.isPending ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />}
            保存并测试
          </Button>
          {configured && (
            <Button
              variant="outline"
              onClick={() => setConfirming(true)}
              disabled={busy}
            >
              <Trash2 size={14} />
              删除
            </Button>
          )}
        </div>
      </div>

      {confirming && (
        <div className="flex flex-wrap items-center gap-2 rounded-btn border border-warning/30 bg-warning/10 px-3 py-2 text-micro text-warning">
          <span>确认删除该接口配置? 它写入的分钟数据也会一并清除（主源历史不受影响）。</span>
          <Button variant="outline" size="xs" onClick={() => setConfirming(false)}>
            取消
          </Button>
          <Button variant="danger" size="xs" onClick={() => remove.mutate()} disabled={busy}>
            确认删除
          </Button>
        </div>
      )}

      <button
        type="button"
        className="text-micro text-muted transition-colors hover:text-foreground"
        onClick={() => setAdvanced((v) => !v)}
      >
        {advanced ? '收起高级设置' : '高级设置（参数名 / 响应路径 / 字段映射）'}
      </button>

      {advanced && (
        <div className="grid gap-2 md:grid-cols-2">
          <label className="space-y-1 text-micro text-muted">
            <span>请求方法</span>
            <select
              className={`${fieldSelect} w-full`}
              value={form.method}
              onChange={(e) => setForm({ ...form, method: e.target.value })}
            >
              <option value="GET">GET</option>
              <option value="POST">POST</option>
            </select>
          </label>
          <label className="space-y-1 text-micro text-muted">
            <span>代码参数名</span>
            <input
              className={`${fieldInput} w-full`}
              value={form.symbol_param}
              onChange={(e) => setForm({ ...form, symbol_param: e.target.value })}
              spellCheck={false}
            />
          </label>
          <label className="space-y-1 text-micro text-muted">
            <span>日期参数名</span>
            <input
              className={`${fieldInput} w-full`}
              value={form.date_param}
              onChange={(e) => setForm({ ...form, date_param: e.target.value })}
              spellCheck={false}
            />
          </label>
          <label className="space-y-1 text-micro text-muted">
            <span>响应数据路径（可选）</span>
            <input
              className={`${fieldInput} w-full`}
              placeholder="data / data.items"
              value={form.response_path}
              onChange={(e) => setForm({ ...form, response_path: e.target.value })}
              spellCheck={false}
            />
          </label>
          <label className="space-y-1 text-micro text-muted">
            <span>超时（秒）</span>
            <input
              className={`${fieldInput} w-full`}
              value={form.timeout}
              onChange={(e) => setForm({ ...form, timeout: e.target.value })}
              inputMode="decimal"
            />
          </label>
          <label className="space-y-1 text-micro text-muted md:col-span-2">
            <span>字段映射（可选，留空自动识别 open/high/low/close/volume/time）</span>
            <textarea
              className={`${fieldInput} h-24 w-full font-mono`}
              placeholder={'{"t": "datetime", "c": "close"}'}
              value={form.field_map}
              onChange={(e) => setForm({ ...form, field_map: e.target.value })}
              spellCheck={false}
            />
          </label>
          <label className="space-y-1 text-micro text-muted md:col-span-2">
            <span>额外参数（可选，JSON）</span>
            <textarea
              className={`${fieldInput} h-16 w-full font-mono`}
              placeholder={'{"freq": "1m"}'}
              value={form.params}
              onChange={(e) => setForm({ ...form, params: e.target.value })}
              spellCheck={false}
            />
          </label>
          <p className="flex items-center gap-1 text-micro text-muted md:col-span-2">
            <FlaskConical size={12} />
            「保存并测试」会用 000001.SH 实拉最近一个交易日，不会落盘。
          </p>
        </div>
      )}
    </Card>
  )
}
