/**
 * [R58] 数据源 key 逐个列出 + 逐个验活。
 *
 * 多 key 是填在同一个字段里的(逗号/换行分隔), 界面上原来只看得到一个脱敏串 ——
 * 池化跑着十几个 key, 其中哪个过期了完全看不出来, 只表现为"有些股票总是刷不
 * 出来"。这里拆开列出来, 并能逐个真打一次接口判定死活。
 *
 * 明文显示是刻意的: 本地单机应用, key 是用户自己的, 遮起来反而让人没法核对
 * 是哪一个失效 —— 要复制、要跟服务商后台比对, 都得看得见全文。
 */
import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  AlertCircle, CheckCircle2, Eye, EyeOff, Loader2, Plus, Save, Stethoscope, Trash2,
} from 'lucide-react'
import { api, type TickflowKeyRow } from '@/lib/api'
import { QK } from '@/lib/queryKeys'
import { toast } from '@/components/Toast'
import { buttonClass, TYPE } from '@/components/ui'
import { cn } from '@/lib/cn'

const INPUT = 'h-8 w-full rounded-input border border-border bg-surface px-2 font-mono text-xs text-foreground outline-none transition-colors focus:border-accent'

export function TickflowKeys() {
  const qc = useQueryClient()
  const q = useQuery({ queryKey: QK.tickflowKeys, queryFn: () => api.tickflowKeys() })
  const [rows, setRows] = useState<string[] | null>(null)
  const [health, setHealth] = useState<Record<number, TickflowKeyRow>>({})
  // 明文默认关着 —— 用户要的是"能看到", 不是"必须一直亮着给旁人看"
  const [reveal, setReveal] = useState(false)

  useEffect(() => {
    if (q.data && rows === null) setRows(q.data.keys.map(k => k.key))
  }, [q.data, rows])

  const list = rows ?? []

  const save = useMutation({
    mutationFn: (keys: string[]) => api.saveTickflowKeys(keys),
    onSuccess: res => {
      setHealth({})       // key 变了, 上一轮的死活结论作废
      qc.invalidateQueries({ queryKey: QK.tickflowKeys })
      qc.invalidateQueries({ queryKey: QK.settings })
      toast(`已保存 ${res.total} 个 key · 档位 ${res.tier_label}`, 'success')
    },
    onError: e => toast(String((e as Error).message || e), 'error'),
  })

  const probe = useMutation({
    mutationFn: () => api.probeTickflowKeys(),
    onSuccess: res => {
      setHealth(Object.fromEntries(res.keys.map(k => [k.index, k])))
      const dead = res.total - res.alive
      toast(dead === 0 ? `${res.total} 个 key 全部可用` : `${res.alive} 个可用, ${dead} 个失效`,
        dead === 0 ? 'success' : 'error')
    },
    onError: e => toast(String((e as Error).message || e), 'error'),
  })

  return (
    <section className="rounded-card border border-border bg-surface">
      <header className="flex flex-wrap items-center gap-x-2 gap-y-1 border-b border-border px-3 py-2">
        <h2 className={cn('shrink-0', TYPE.card)}>数据源 Key</h2>
        <span className="text-micro text-muted">
          第 1 个是主 key(档位探测、付费端点、历史日 K 都走它); 其余用于实时行情池化, 每个免费 key 各 5 只额度
        </span>
        <div className="ml-auto flex flex-wrap items-center gap-1.5">
          <button type="button" onClick={() => setReveal(v => !v)}
            title={reveal ? '隐藏明文' : '显示明文'}
            className="inline-flex h-7 shrink-0 items-center gap-1 whitespace-nowrap rounded-btn border border-border px-2 text-xs text-secondary transition-colors hover:border-accent/40 hover:text-accent">
            {reveal ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
            {reveal ? '隐藏' : '明文'}
          </button>
          <button type="button" disabled={probe.isPending || list.length === 0}
            onClick={() => probe.mutate()}
            title="逐个真打一次接口判定死活。串行跑, 并发会把活的 key 也打成限流"
            className="inline-flex h-7 shrink-0 items-center gap-1 whitespace-nowrap rounded-btn border border-border px-2 text-xs text-secondary transition-colors hover:border-accent/40 hover:text-accent disabled:opacity-50">
            {probe.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Stethoscope className="h-3.5 w-3.5" />}
            验活
          </button>
          <button type="button" onClick={() => setRows([...list, ''])}
            className="inline-flex h-7 shrink-0 items-center gap-1 whitespace-nowrap rounded-btn border border-border px-2 text-xs text-secondary transition-colors hover:border-accent/40 hover:text-accent">
            <Plus className="h-3.5 w-3.5" />加一个
          </button>
          <button type="button" disabled={save.isPending || rows === null}
            onClick={() => save.mutate(list.filter(k => k.trim()))}
            className={buttonClass({ variant: 'primary' }, 'shrink-0 gap-1 whitespace-nowrap')}>
            {save.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Save className="h-3.5 w-3.5" />}
            保存
          </button>
        </div>
      </header>

      {q.isLoading && (
        <div className="flex items-center justify-center gap-2 py-8 text-xs text-muted">
          <Loader2 className="h-4 w-4 animate-spin" />加载中…
        </div>
      )}

      {rows !== null && list.length === 0 && (
        <div className="px-3 py-8 text-center text-xs text-muted">还没有 key —— 点「加一个」填第一个。</div>
      )}

      {list.map((k, i) => {
        const h = health[i]
        return (
          <div key={i} className="flex items-center gap-2 border-t border-border/60 px-3 py-2">
            <span className="inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-elevated font-mono text-micro text-secondary"
              title={i === 0 ? '主 key' : '池化 key'}>
              {i + 1}
            </span>
            <input
              className={INPUT}
              type={reveal ? 'text' : 'password'}
              autoComplete="off"
              spellCheck={false}
              placeholder="粘贴 API Key"
              value={k}
              onChange={e => setRows(list.map((v, j) => (j === i ? e.target.value : v)))}
            />
            {/* 验活结论。没验过就什么都不显示 —— 显示一个灰点会被当成"已验且没问题" */}
            {h && (h.alive
              ? (
                <span className="inline-flex shrink-0 items-center gap-1 whitespace-nowrap rounded border border-bear/40 bg-bear/10 px-1.5 py-0.5 text-micro text-bear">
                  <CheckCircle2 className="h-3 w-3" />可用
                </span>
              )
              : (
                <span title={h.error || '接口调用失败'}
                  className="inline-flex shrink-0 cursor-help items-center gap-1 whitespace-nowrap rounded border border-danger/40 bg-danger/10 px-1.5 py-0.5 text-micro text-danger">
                  <AlertCircle className="h-3 w-3" />失效
                </span>
              ))}
            <button type="button" onClick={() => setRows(list.filter((_, j) => j !== i))}
              title="删掉这个 key" className="shrink-0 p-1 text-muted transition-colors hover:text-danger">
              <Trash2 className="h-3.5 w-3.5" />
            </button>
          </div>
        )
      })}

      {Object.keys(health).length > 0 && (
        <div className="border-t border-border/60 px-3 py-2 text-micro leading-4 text-muted">
          失效的那几个悬停可以看接口返回的原因。删掉之后记得点「保存」——
          验活只是查, 不会自己动你的配置。
        </div>
      )}
    </section>
  )
}
