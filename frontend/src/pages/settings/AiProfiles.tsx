/**
 * [R56] 多 AI 档位 —— 按优先级排好, 用不了自动顺位往下。
 *
 * 在这之前只有单个 provider / 单个 key / 单个模型: 一家用完额度整个 AI 功能
 * 就停摆, 没有任何自动切换。这里把它做成一个**有序列表**, 上下移动就是调优先级。
 *
 * 两条规则写在界面上, 因为它们决定了用户该怎么排这个表:
 *   · 只有"这一档服务不了"(额度/限流/鉴权/宕机/没这个模型)才顺位往下 ——
 *     请求本身错了换谁都一样失败, 挨个试等于把每个 key 都白烧一次。
 *   · 流式输出只在吐出第一个字之前能换档。已经流给你的收不回来, 中途换档会
 *     把两家的输出接在一起, 那比直接报错更糟。
 *
 * key 是脱敏下发的, 前端手里没有明文 —— 所以留空 = 沿用原来那条, 不是清空。
 */
import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowDown, ArrowUp, KeyRound, Loader2, Plus, Save, Trash2 } from 'lucide-react'
import { api, type AiProfile } from '@/lib/api'
import { QK } from '@/lib/queryKeys'
import { toast } from '@/components/Toast'
import { buttonClass } from '@/components/ui'
import { SettingsCard } from './SettingsCard'

const INPUT = 'h-8 w-full rounded-input border border-border bg-surface px-2 text-xs text-foreground outline-none transition-colors focus:border-accent'
const LABEL = 'mb-1 block text-micro font-medium text-secondary'

// 一律按 OpenAI 兼容接口走 —— 地址、密钥、模型三样自己填就够了。
// 不再列"常用配置"预设: 那种清单只在你正好用清单里那几家时省事, 否则先得
// 从里面挑一个再把三个字段全改掉, 比直接填还多两步; 而且它会过期
// (模型名换代、中转站换域名), 过期的预设比没有预设更误事。
const OPENAI_COMPATIBLE = 'openai_compat'

function blank(): AiProfile {
  return {
    id: `p${Date.now().toString(36)}`,
    label: '', provider: OPENAI_COMPATIBLE, base_url: '', api_key: '',
    model: '', reasoning_effort: '', enabled: true,
  }
}

export function AiProfiles() {
  const qc = useQueryClient()
  const q = useQuery({ queryKey: QK.aiProfiles, queryFn: () => api.aiProfiles() })
  const [rows, setRows] = useState<AiProfile[] | null>(null)
  // [R94] 未保存标记 —— 移动/编辑只是本地草稿, 忘了点保存的话调整的优先级不会生效;
  // 这里给一个显眼的提醒, 免得"我明明把它挪到第一了怎么还在用旧首选"。
  const [dirty, setDirty] = useState(false)

  // 服务端那份到了就填进草稿; 之后的编辑都在本地, 点保存才整表覆写
  useEffect(() => {
    if (q.data && rows === null) setRows(q.data.profiles)
  }, [q.data, rows])

  const save = useMutation({
    mutationFn: (list: AiProfile[]) => api.saveAiProfiles(list),
    onSuccess: res => {
      setRows(res.profiles)
      setDirty(false)
      qc.invalidateQueries({ queryKey: QK.aiProfiles })
      qc.invalidateQueries({ queryKey: QK.settings })
      toast('已保存 —— 从上到下依次尝试, 全系统立即按新顺序生效', 'success')
    },
    onError: e => toast(String((e as Error).message || e), 'error'),
  })

  const list = rows ?? []
  const patch = (i: number, p: Partial<AiProfile>) => {
    setRows(list.map((r, k) => (k === i ? { ...r, ...p } : r)))
    setDirty(true)
  }
  const move = (i: number, dir: -1 | 1) => {
    const j = i + dir
    if (j < 0 || j >= list.length) return
    const next = [...list]
    ;[next[i], next[j]] = [next[j], next[i]]
    setRows(next)
    setDirty(true)
  }

  return (
    // [R535] 卡头换成设置区统一的 SettingsCard; 标题后那串长说明挪到标题下一行
    <SettingsCard
      icon={KeyRound}
      title="AI 档位 · 按优先级"
      desc="OpenAI 兼容接口 · 从上往下依次尝试 —— 上面那档用不了就自动换下一档"
      right={(
        <>
          {dirty && (
            <span className="inline-flex items-center gap-1 rounded-btn border border-warning/30 bg-warning/10 px-2 py-0.5 text-micro text-warning">
              <span className="h-1.5 w-1.5 rounded-full bg-warning" />
              有未保存改动 —— 保存后才生效
            </span>
          )}
          <button type="button" onClick={() => { setRows([...list, blank()]); setDirty(true) }}
            className="inline-flex h-7 items-center gap-1 rounded-btn border border-border px-2 text-xs text-secondary transition-colors hover:border-accent/40 hover:text-accent">
            <Plus className="h-3.5 w-3.5" />加一档
          </button>
          <button type="button" disabled={save.isPending || rows === null}
            onClick={() => save.mutate(list)}
            className={buttonClass({ variant: 'primary' }, 'gap-1')}>
            {save.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Save className="h-3.5 w-3.5" />}
            保存
          </button>
        </>
      )}
      bodyClassName="p-0 pt-3"
    >
      <div className="border-y border-border bg-elevated/40 px-5 py-2 text-micro leading-4 text-secondary">
        换档只发生在<span className="text-foreground">这一档服务不了</span>的时候 ——
        额度用尽、限流、key 失效、对面宕机、或者这一档没有你填的那个模型。
        <span className="text-muted"> 请求本身有问题时不会换档: 那种错误换谁都一样失败,
        挨个试一遍只会把每个 key 都白烧一次往返, 还会把真正的报错埋起来。</span>
        <br />
        流式输出(如复盘报告)只在<span className="text-foreground">吐出第一个字之前</span>能换档 ——
        已经显示出来的内容收不回来, 中途换档会把两家的输出接在一起。
      </div>

      {q.isLoading && (
        <div className="flex items-center justify-center gap-2 py-10 text-xs text-muted">
          <Loader2 className="h-4 w-4 animate-spin" />加载中…
        </div>
      )}

      {rows !== null && list.length === 0 && (
        <div className="px-5 py-8 text-center text-xs text-muted">
          还没有档位 —— 点「加一档」填第一个。<br />
          <span className="text-muted/70">配两家以上才有兜底的意义: 一家没额度了另一家顶上。</span>
        </div>
      )}

      {list.map((r, i) => (
        <div key={r.id} className={`border-t border-border/60 px-5 py-2.5 ${r.enabled ? '' : 'opacity-50'}`}>
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <span className="inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-elevated font-mono text-micro text-secondary"
              title={i === 0 ? '优先用这一档' : `前 ${i} 档都用不了时才轮到它`}>
              {i + 1}
            </span>
            <input className={`${INPUT} h-7 w-36`} placeholder="名字(自己看)"
              value={r.label} onChange={e => patch(i, { label: e.target.value })} />
            <label className="flex shrink-0 items-center gap-1 text-micro text-secondary">
              <input type="checkbox" className="h-3 w-3 accent-accent" checked={r.enabled}
                onChange={e => patch(i, { enabled: e.target.checked })} />
              启用
            </label>
            <div className="ml-auto flex shrink-0 items-center gap-0.5">
              <button type="button" disabled={i === 0} onClick={() => move(i, -1)}
                title="往上 = 更优先" className="p-1 text-muted transition-colors hover:text-accent disabled:opacity-30">
                <ArrowUp className="h-3.5 w-3.5" />
              </button>
              <button type="button" disabled={i === list.length - 1} onClick={() => move(i, 1)}
                title="往下 = 更靠后" className="p-1 text-muted transition-colors hover:text-accent disabled:opacity-30">
                <ArrowDown className="h-3.5 w-3.5" />
              </button>
              <button type="button" onClick={() => { setRows(list.filter((_, k) => k !== i)); setDirty(true) }}
                title="删掉这一档" className="p-1 text-muted transition-colors hover:text-danger">
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            </div>
          </div>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
            <label><span className={LABEL}>接口地址</span>
              <input className={INPUT} placeholder="https://api.xxx.com/v1"
                value={r.base_url} onChange={e => patch(i, { base_url: e.target.value })} /></label>
            <label><span className={LABEL}>模型</span>
              <input className={INPUT} placeholder="服务商给的模型名, 原样填"
                value={r.model} onChange={e => patch(i, { model: e.target.value })} /></label>
            <label>
              <span className={LABEL}>
                API Key
                {r.api_key_masked && <span className="ml-1 font-mono text-muted">已存 {r.api_key_masked}</span>}
              </span>
              <input className={INPUT} type="password" autoComplete="off"
                placeholder={r.api_key_masked ? '留空 = 不改' : 'sk-…'}
                value={r.api_key ?? ''} onChange={e => patch(i, { api_key: e.target.value })} /></label>
          </div>
        </div>
      ))}
    </SettingsCard>
  )
}
