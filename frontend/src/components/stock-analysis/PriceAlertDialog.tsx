import { useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowDown, ArrowUp, Bell, Check, ExternalLink, Loader2, Trash2, X } from 'lucide-react'
import { toast } from '@/components/Toast'
import { LEVEL_GROUPS } from './AnalysisKChart'
import { api, genRuleId, type MonitorRule, type PriceLevel } from '@/lib/api'
import {
  buildPriceAlertMessage,
  inferPriceAlertDirection,
  parsePointPriceAlert,
  type PriceAlertDirection,
} from '@/lib/price-alerts'
import { QK } from '@/lib/queryKeys'
import { usePreferences } from '@/lib/useSharedQueries'
import { useDialogBackdrop } from '@/lib/useDialogBackdrop'
import { TYPE, buttonClass } from '@/components/ui'

interface Props {
  symbol: string
  name: string
  onClose: () => void
  initialTarget?: number
  initialCurrentPrice?: number | null
}

const COOLDOWNS = [
  { value: 600, label: '10 分钟' },
  { value: 1800, label: '30 分钟' },
  { value: 3600, label: '1 小时' },
  { value: 86400, label: '当日一次' },
]

function levelGroupLabel(level: PriceLevel) {
  return LEVEL_GROUPS.find(group => group.key === level.type)?.label ?? level.type
}

// 推荐点位 → 告警 message:站在"收到通知那一刻"的视角,直接告诉你此刻该考虑什么操作。
// 推送正文是「{代码} {名称} {message}」,所以把动作写进 message,通知里就会带上。
function recoAlertMessage(p: { action: string; price: number; label: string; reason: string }): string {
  return [
    `到${p.label || '目标价'} ${p.price.toFixed(2)}`,
    p.action ? `可考虑${p.action}` : '',
    p.reason,
  ].filter(Boolean).join(' · ')
}

export function PriceAlertDialog({
  symbol,
  name,
  onClose,
  initialTarget,
  initialCurrentPrice,
}: Props) {
  const qc = useQueryClient()
  const backdrop = useDialogBackdrop(onClose)
  const { data: prefs } = usePreferences()
  const levelsQuery = useQuery({
    queryKey: QK.stockLevels(symbol),
    queryFn: () => api.stockAnalysisLevels(symbol, 250),
    staleTime: 60_000,
  })
  const rulesQuery = useQuery({ queryKey: QK.monitorRules, queryFn: api.monitorRulesList })
  const initialTargetValue = initialTarget != null && Number.isFinite(initialTarget) && initialTarget > 0
    ? Math.round(initialTarget * 100) / 100
    : null
  const initialDirection = initialTargetValue == null
    ? 'up'
    : inferPriceAlertDirection(initialTargetValue, initialCurrentPrice)
  const [tab, setTab] = useState<'create' | 'existing'>('create')
  const [direction, setDirection] = useState<PriceAlertDirection>(initialDirection)
  const [target, setTarget] = useState(initialTargetValue?.toFixed(2) ?? '')
  const [selectedLabel, setSelectedLabel] = useState('')
  const [cooldown, setCooldown] = useState(3600)
  const [message, setMessage] = useState(initialTargetValue == null
    ? ''
    : buildPriceAlertMessage(name, symbol, initialDirection, initialTargetValue))
  const [messageEdited, setMessageEdited] = useState(false)
  const [channels, setChannels] = useState<string[]>([])
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null)
  const channelsInitialized = useRef(false)

  const currentPrice = initialCurrentPrice != null && Number.isFinite(initialCurrentPrice) && initialCurrentPrice > 0
    ? initialCurrentPrice
    : levelsQuery.data?.close ?? null
  const recommended = useMemo(() => {
    if (currentPrice == null) return { above: [] as PriceLevel[], below: [] as PriceLevel[] }
    const seen = new Set<string>()
    const all = Object.values(levelsQuery.data?.levels ?? {})
      .flat()
      .filter(level => Number.isFinite(level.value) && level.value > 0)
      .sort((a, b) => Math.abs(a.value - currentPrice) - Math.abs(b.value - currentPrice))
      .filter(level => {
        const key = level.value.toFixed(2)
        if (seen.has(key)) return false
        seen.add(key)
        return true
      })
    return {
      above: all.filter(level => level.value > currentPrice).slice(0, 6),
      below: all.filter(level => level.value < currentPrice).slice(0, 6),
    }
  }, [currentPrice, levelsQuery.data?.levels])

  // 推荐点位: 上方最近压力涨至 + 下方最近支撑跌至。
  // [R435] 原来优先用 AI 信号给的 watch_points, 规则版只是兜底; AI 信号停用后只剩规则版。
  const recoPoints = useMemo(() => {
    type Reco = { direction: PriceAlertDirection; price: number; label: string; action: string; reason: string }
    if (currentPrice == null) return [] as Reco[]
    const out: Reco[] = []
    const above = recommended.above[0]
    const below = recommended.below[0]
    if (above) out.push({ direction: 'up', price: above.value, label: above.label, action: '突破关注', reason: '上方最近压力,突破需放量' })
    if (below) out.push({ direction: 'down', price: below.value, label: below.label, action: '跌破防守', reason: '下方最近支撑,跌破转弱' })
    return out
  }, [currentPrice, recommended])

  useEffect(() => {
    if (target || currentPrice == null) return
    const initial = recommended.above[0] ?? recommended.below[0]
    if (!initial) return
    setTarget(initial.value.toFixed(2))
    setDirection(initial.value > currentPrice ? 'up' : 'down')
    setSelectedLabel(initial.label)
  }, [currentPrice, recommended, target])

  useEffect(() => {
    if (channelsInitialized.current || !prefs) return
    channelsInitialized.current = true
    const configured = new Set<string>()
    if (prefs.feishu_webhook_url) configured.add('feishu')
    if (prefs.wecom_webhook_url) configured.add('wecom')
    if (prefs.dingtalk_webhook_url) configured.add('dingtalk')
    if (prefs.custom_webhook_url) configured.add('custom')
    if (prefs.email_smtp_config?.host && prefs.email_smtp_config.from_address && prefs.email_smtp_config.to_addresses.length && (!prefs.email_smtp_config.username || prefs.email_smtp_password_set)) configured.add('email')
    setChannels((prefs.webhook_default_channels ?? []).filter(channel => configured.has(channel)))
  }, [prefs])

  useEffect(() => {
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', closeOnEscape)
    return () => window.removeEventListener('keydown', closeOnEscape)
  }, [onClose])

  const pointRules = useMemo(
    () => (rulesQuery.data?.rules ?? []).filter(rule => parsePointPriceAlert(rule, symbol)),
    [rulesQuery.data?.rules, symbol],
  )

  const targetValue = Number(target)
  const targetValid = Number.isFinite(targetValue) && targetValue > 0
  useEffect(() => {
    if (initialTargetValue == null || messageEdited || !targetValid) return
    setMessage(buildPriceAlertMessage(name, symbol, direction, targetValue))
  }, [direction, initialTargetValue, messageEdited, name, symbol, targetValid, targetValue])

  const alreadyReached = targetValid && currentPrice != null && (
    direction === 'up' ? currentPrice >= targetValue : currentPrice <= targetValue
  )
  const duplicate = targetValid && pointRules.some(rule => {
    const alert = parsePointPriceAlert(rule, symbol)!
    return alert.direction === direction && Math.abs(alert.target - targetValue) < 0.005
  })

  const save = useMutation({
    mutationFn: () => api.monitorRuleSave({
      id: genRuleId(),
      name: `点位提醒 · ${name || symbol} · ${direction === 'up' ? '涨至' : '跌至'}${selectedLabel || targetValue.toFixed(2)}`,
      enabled: true,
      type: 'price',
      asset_type: 'stock',
      scope: 'symbols',
      symbols: [symbol],
      sector: null,
      strategy_id: null,
      direction: 'entry',
      conditions: [{ field: 'close', op: direction === 'up' ? '>=' : '<=', value: targetValue }],
      logic: 'and',
      cooldown_seconds: cooldown,
      severity: 'warn',
      message: message.trim(),
      webhook_channels: channels,
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: QK.monitorRules })
      toast('点位提醒已创建', 'success')
      onClose()
    },
    onError: error => toast(String((error as Error)?.message || '创建失败'), 'error'),
  })

  // 一键创建全部推荐点位(逐个建 price 规则)
  const createReco = useMutation({
    mutationFn: async () => {
      for (const p of recoPoints) {
        await api.monitorRuleSave({
          id: genRuleId(),
          name: `点位提醒 · ${name || symbol} · ${p.direction === 'up' ? '涨至' : '跌至'}${p.label || p.price.toFixed(2)}`,
          enabled: true,
          type: 'price',
          asset_type: 'stock',
          scope: 'symbols',
          symbols: [symbol],
          sector: null,
          strategy_id: null,
          direction: 'entry',
          conditions: [{ field: 'close', op: p.direction === 'up' ? '>=' : '<=', value: p.price }],
          logic: 'and',
          cooldown_seconds: cooldown,
          severity: 'warn',
          // 通知正文带上"到价可考虑的操作",收到推送即知此刻该做什么;用户填了自定义提示则以它为准
          message: message.trim() || recoAlertMessage(p),
          webhook_channels: channels,
        })
      }
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: QK.monitorRules })
      toast(`已创建 ${recoPoints.length} 个推荐点位提醒`, 'success')
      onClose()
    },
    onError: error => toast(String((error as Error)?.message || '创建失败'), 'error'),
  })

  const toggle = useMutation({
    mutationFn: (rule: MonitorRule) => {
      const { runtime_warning: _runtimeWarning, ...persisted } = rule
      return api.monitorRuleSave({ ...persisted, enabled: !rule.enabled })
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: QK.monitorRules }),
    onError: error => toast(String((error as Error)?.message || '更新失败'), 'error'),
  })

  const remove = useMutation({
    mutationFn: api.monitorRuleDelete,
    onSuccess: () => {
      setConfirmDelete(null)
      qc.invalidateQueries({ queryKey: QK.monitorRules })
      toast('点位提醒已删除', 'success')
    },
    onError: error => toast(String((error as Error)?.message || '删除失败'), 'error'),
  })

  const selectLevel = (level: PriceLevel) => {
    setTarget(level.value.toFixed(2))
    setDirection(inferPriceAlertDirection(level.value, currentPrice))
    setSelectedLabel(level.label)
  }

  const updateTarget = (value: string) => {
    setTarget(value)
    setSelectedLabel('')
    const parsed = Number(value)
    if (Number.isFinite(parsed)) {
      setDirection(inferPriceAlertDirection(parsed, currentPrice))
    }
  }

  const updateMessage = (value: string) => {
    setMessage(value)
    setMessageEdited(true)
  }

  const toggleChannel = (channel: string) => {
    setChannels(current => current.includes(channel)
      ? current.filter(item => item !== channel)
      : [...current, channel])
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/55 p-3 backdrop-blur-sm sm:p-4" {...backdrop}>
      <div role="dialog" aria-modal="true" aria-labelledby="price-alert-title" className="flex max-h-[88vh] w-full max-w-2xl flex-col overflow-hidden rounded-btn border border-border bg-surface shadow-2xl" onClick={event => event.stopPropagation()}>
        <header className="flex items-center gap-3 border-b border-border/60 px-5 py-3.5">
          <span className="grid h-8 w-8 shrink-0 place-items-center rounded-btn border border-border bg-elevated text-secondary">
            <Bell className="h-4 w-4" />
          </span>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <h2 id="price-alert-title" className={TYPE.section}>点位提醒</h2>
              <span className="truncate text-xs text-secondary">{name || symbol}</span>
              <span className="shrink-0 font-mono text-micro text-muted">{symbol}</span>
            </div>
            <div className="mt-0.5 text-micro text-muted">
              当前价 <span className="font-mono text-foreground">{currentPrice?.toFixed(2) ?? '—'}</span>
            </div>
          </div>
          <button onClick={onClose} className={buttonClass({ variant: 'ghost', icon: true })} title="关闭">
            <X className="h-4 w-4" />
          </button>
        </header>

        <div className="flex h-10 shrink-0 border-b border-border/60 px-5">
          {([
            { key: 'create', label: '新建提醒' },
            { key: 'existing', label: `已有提醒 ${pointRules.length}` },
          ] as const).map(item => (
            <button key={item.key} onClick={() => setTab(item.key)} className={`relative px-4 text-xs font-medium transition-colors ${tab === item.key ? 'text-sky-400' : 'text-muted hover:text-foreground'}`}>
              {item.label}
              {tab === item.key && <span className="absolute inset-x-2 bottom-0 h-0.5 bg-sky-400" />}
            </button>
          ))}
        </div>

        {tab === 'create' ? (
          <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4 sm:px-5">
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-[180px_1fr]">
              <div className="space-y-1.5">
                <span className="text-xs text-muted">触发方向</span>
                <div className="grid h-9 grid-cols-2 overflow-hidden rounded-btn border border-border bg-base">
                  <button onClick={() => setDirection('up')} className={`inline-flex items-center justify-center gap-1 text-xs font-medium transition-colors ${direction === 'up' ? 'bg-bull/10 text-bull' : 'text-muted hover:text-foreground'}`}>
                    <ArrowUp className="h-3.5 w-3.5" />涨至
                  </button>
                  <button onClick={() => setDirection('down')} className={`inline-flex items-center justify-center gap-1 border-l border-border text-xs font-medium transition-colors ${direction === 'down' ? 'bg-bear/10 text-bear' : 'text-muted hover:text-foreground'}`}>
                    <ArrowDown className="h-3.5 w-3.5" />跌至
                  </button>
                </div>
              </div>
              <label className="space-y-1.5">
                <span className="text-xs text-muted">目标价格</span>
                <div className="relative">
                  <input type="number" min="0" step="0.01" value={target} onChange={event => updateTarget(event.target.value)} className="h-9 w-full rounded-btn border border-border bg-base px-3 pr-14 font-mono text-sm text-foreground focus:border-sky-400/50 focus:outline-none" />
                  {targetValid && currentPrice != null && (
                    <span className={`absolute right-3 top-2.5 font-mono text-micro ${targetValue >= currentPrice ? 'text-bull' : 'text-bear'}`}>
                      {((targetValue / currentPrice - 1) * 100).toFixed(2)}%
                    </span>
                  )}
                </div>
              </label>
            </div>

            {recoPoints.length > 0 && (
              <section className="mt-4 rounded-card border border-border bg-surface p-3">
                <div className="mb-2 flex items-center justify-between">
                  <span className={TYPE.card}>
                    🎯 推荐点位配置 · 规则
                  </span>
                  <button
                    onClick={() => createReco.mutate()}
                    disabled={createReco.isPending}
                    className={buttonClass({ size: 'xs' }, 'gap-1')}
                  >
                    {createReco.isPending && <Loader2 className="h-3 w-3 animate-spin" />}
                    一键创建全部
                  </button>
                </div>
                {/* [fork 增强] 一键创建带哪些推送渠道, 就地可选(与下方「通知渠道」同一状态) */}
                <div className="mb-2 flex flex-wrap items-center gap-1.5 text-micro">
                  <span className="text-muted">推送到:</span>
                  <span className="rounded border border-border/60 bg-elevated/40 px-1.5 py-0.5 text-muted">站内 ✓</span>
                  {([
                    { key: 'feishu', label: '飞书', configured: !!prefs?.feishu_webhook_url },
                    { key: 'wecom', label: '企微', configured: !!prefs?.wecom_webhook_url },
                    { key: 'dingtalk', label: '钉钉', configured: !!prefs?.dingtalk_webhook_url },
                  ]).map(c => (
                    <button
                      key={c.key}
                      disabled={!c.configured}
                      onClick={() => toggleChannel(c.key)}
                      title={c.configured ? '「一键创建全部」建出的每个提醒都带上所选渠道' : '未配置 webhook —— 到 设置 页配置后可用'}
                      className={`rounded border px-1.5 py-0.5 transition-colors ${
                        channels.includes(c.key)
                          ? 'border-sky-400/50 bg-sky-400/15 text-sky-300 cursor-pointer'
                          : c.configured
                            ? 'border-border/60 bg-surface text-muted hover:text-foreground cursor-pointer'
                            : 'border-border/40 text-muted/40 cursor-not-allowed'
                      }`}
                    >
                      {c.label}{channels.includes(c.key) ? ' ✓' : ''}
                    </button>
                  ))}
                </div>
                <div className="space-y-1">
                  {recoPoints.map((p, i) => (
                    <button
                      key={i}
                      onClick={() => { setTarget(p.price.toFixed(2)); setDirection(p.direction); setSelectedLabel(p.label); setMessage(recoAlertMessage(p)) }}
                      title="点击填入下方表单微调(含到价操作提示,会随通知一起推送)"
                      className="flex w-full flex-col gap-0.5 rounded-btn px-2 py-1.5 text-left transition-colors hover:bg-elevated/50"
                    >
                      <div className="flex items-center gap-2">
                        {/* 操作:最突出 */}
                        <span className={`shrink-0 rounded px-1.5 py-0.5 text-xs font-semibold ${p.direction === 'up' ? 'bg-bull/15 text-bull' : 'bg-bear/15 text-bear'}`}>
                          {p.action}
                        </span>
                        <span className={`inline-flex shrink-0 items-center gap-0.5 text-micro ${p.direction === 'up' ? 'text-bull' : 'text-bear'}`}>
                          {p.direction === 'up' ? <ArrowUp className="h-3 w-3" /> : <ArrowDown className="h-3 w-3" />}
                          {p.direction === 'up' ? '涨至' : '跌至'}
                        </span>
                        <span className="shrink-0 font-mono text-xs text-foreground">{p.price.toFixed(2)}</span>
                        {p.label && <span className="shrink-0 text-micro text-secondary">{p.label}</span>}
                      </div>
                      {p.reason && <span className="text-micro leading-snug text-muted/70">{p.reason}</span>}
                    </button>
                  ))}
                </div>
                <p className="mt-1.5 text-micro text-muted/60">到价时推送会带上"可考虑的操作"(如「可考虑突破关注买入」),收到通知即知此刻该做什么。点单条可微调,「一键创建全部」直接建这几个提醒。</p>
              </section>
            )}

            <section className="mt-5">
              <div className="mb-2 flex items-center justify-between">
                <span className="text-xs font-medium text-secondary">关键价位</span>
                {levelsQuery.isLoading && <Loader2 className="h-3.5 w-3.5 animate-spin text-muted" />}
              </div>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 sm:gap-x-4">
                {([
                  { key: 'above', label: '上方', icon: ArrowUp, levels: recommended.above, color: 'text-bull' },
                  { key: 'below', label: '下方', icon: ArrowDown, levels: recommended.below, color: 'text-bear' },
                ] as const).map(group => (
                  <div key={group.key} className="min-w-0">
                    <div className={`mb-1.5 flex items-center gap-1 text-micro ${group.color}`}>
                      <group.icon className="h-3 w-3" />{group.label}
                    </div>
                    <div className="divide-y divide-border/50 border-y border-border/50">
                      {group.levels.length === 0 ? (
                        <div className="py-5 text-center text-micro text-muted">暂无价位</div>
                      ) : group.levels.map(level => {
                        const selected = Math.abs(Number(target) - level.value) < 0.005
                        return (
                          <button key={`${level.type}-${level.value}`} onClick={() => selectLevel(level)} className={`flex h-10 w-full items-center gap-2 px-1.5 text-left transition-colors hover:bg-elevated/60 ${selected ? 'bg-sky-400/[0.08]' : ''}`}>
                            <span className="min-w-0 flex-1">
                              <span className={`block truncate text-xs ${selected ? 'text-sky-300' : 'text-foreground'}`}>{level.label}</span>
                              <span className="block truncate text-micro text-muted">{levelGroupLabel(level)}</span>
                            </span>
                            <span className="shrink-0 font-mono text-xs text-secondary">{level.value.toFixed(2)}</span>
                            <span className={`grid h-4 w-4 shrink-0 place-items-center rounded-full border ${selected ? 'border-foreground bg-foreground text-surface' : 'border-border text-transparent'}`}>
                              <Check className="h-2.5 w-2.5" />
                            </span>
                          </button>
                        )
                      })}
                    </div>
                  </div>
                ))}
              </div>
            </section>

            <div className="mt-5 grid grid-cols-1 gap-4 border-t border-border/60 pt-4 sm:grid-cols-2">
              <label className="space-y-1.5">
                <span className="text-xs text-muted">重复提醒</span>
                <select value={cooldown} onChange={event => setCooldown(Number(event.target.value))} className="h-9 w-full rounded-btn border border-border bg-base px-3 text-xs text-foreground focus:outline-none">
                  {COOLDOWNS.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}
                </select>
              </label>
              <label className="space-y-1.5">
                <span className="text-xs text-muted">自定义提示</span>
                <input value={message} onChange={event => updateMessage(event.target.value)} placeholder="留空使用默认内容" className="h-9 w-full rounded-btn border border-border bg-base px-3 text-xs text-foreground placeholder:text-muted/50 focus:outline-none" />
              </label>
            </div>

            <div className="mt-4">
              <span className="text-xs text-muted">通知渠道</span>
              <div className="mt-2 flex flex-wrap gap-4">
                <label className="inline-flex items-center gap-2 text-xs text-foreground">
                  <input type="checkbox" checked disabled className="h-3.5 w-3.5 accent-sky-500" />站内
                </label>
                {([
                  { key: 'feishu', label: '飞书', configured: !!prefs?.feishu_webhook_url },
                  { key: 'wecom', label: '企业微信', configured: !!prefs?.wecom_webhook_url },
                  { key: 'dingtalk', label: '钉钉', configured: !!prefs?.dingtalk_webhook_url },
                  { key: 'custom', label: '第三方系统', configured: !!prefs?.custom_webhook_url },
                  { key: 'email', label: '邮件', configured: !!(prefs?.email_smtp_config?.host && prefs.email_smtp_config.from_address && prefs.email_smtp_config.to_addresses.length && (!prefs.email_smtp_config.username || prefs.email_smtp_password_set)) },
                ]).map(channel => (
                  <label key={channel.key} className={`inline-flex items-center gap-2 text-xs ${channel.configured ? 'text-foreground' : 'text-muted/60'}`}>
                    <input type="checkbox" checked={channels.includes(channel.key)} disabled={!channel.configured} onChange={() => toggleChannel(channel.key)} className="h-3.5 w-3.5 accent-sky-500" />
                    {channel.label}
                    {!channel.configured && <span className="text-micro">未配置</span>}
                  </label>
                ))}
              </div>
            </div>

            {(alreadyReached || duplicate) && (
              <div className="mt-4 rounded-btn border border-warning/30 bg-warning/5 px-3 py-2 text-xs text-warning">
                {duplicate ? '相同方向和价格的提醒已存在。' : '当前价格已处于触发区间,请调整目标价格或触发方向。'}
              </div>
            )}
          </div>
        ) : (
          <div className="min-h-[280px] flex-1 overflow-y-auto px-5 py-4">
            {rulesQuery.isLoading ? (
              <div className="flex justify-center py-16"><Loader2 className="h-5 w-5 animate-spin text-muted" /></div>
            ) : pointRules.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-16 text-center">
                <Bell className="h-6 w-6 text-muted/50" />
                <span className="mt-2 text-xs text-muted">暂无点位提醒</span>
                <button onClick={() => setTab('create')} className="mt-3 text-xs text-sky-400 hover:text-sky-300">新建提醒</button>
              </div>
            ) : (
              <div className="divide-y divide-border/50 border-y border-border/50">
                {pointRules.map(rule => {
                  const alert = parsePointPriceAlert(rule, symbol)!
                  const isUp = alert.direction === 'up'
                  return (
                    <div key={rule.id} className={`flex items-center gap-3 px-2 py-3 ${rule.enabled ? '' : 'opacity-55'}`}>
                      <span className={`grid h-7 w-7 shrink-0 place-items-center rounded-btn ${isUp ? 'bg-bull/10 text-bull' : 'bg-bear/10 text-bear'}`}>
                        {isUp ? <ArrowUp className="h-3.5 w-3.5" /> : <ArrowDown className="h-3.5 w-3.5" />}
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-xs text-foreground">{rule.name}</span>
                        <span className="mt-0.5 block font-mono text-micro text-muted">{isUp ? '涨至' : '跌至'} {alert.target.toFixed(2)} · {COOLDOWNS.find(item => item.value === rule.cooldown_seconds)?.label ?? `${rule.cooldown_seconds} 秒`}</span>
                      </span>
                      <button role="switch" aria-checked={rule.enabled} onClick={() => toggle.mutate(rule)} disabled={toggle.isPending} className={`relative h-5 w-9 shrink-0 rounded-full transition-colors ${rule.enabled ? 'bg-sky-500' : 'bg-elevated'}`} title={rule.enabled ? '停用' : '启用'}>
                        <span className={`absolute top-0.5 h-4 w-4 rounded-full bg-white shadow transition-transform ${rule.enabled ? 'translate-x-[18px]' : 'translate-x-0.5'}`} />
                      </button>
                      {confirmDelete === rule.id ? (
                        <button onClick={() => remove.mutate(rule.id)} disabled={remove.isPending} className="h-7 rounded-btn border border-danger/30 bg-danger/10 px-2 text-micro text-danger">确认</button>
                      ) : (
                        <button onClick={() => setConfirmDelete(rule.id)} className="rounded-btn p-1.5 text-muted hover:bg-danger/10 hover:text-danger" title="删除">
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      )}
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        )}

        <footer className="flex min-h-14 items-center justify-between gap-3 border-t border-border/60 bg-base/30 px-5 py-2.5">
          <Link to="/monitor" onClick={onClose} className="inline-flex items-center gap-1 text-xs text-muted hover:text-sky-400">
            监控中心<ExternalLink className="h-3 w-3" />
          </Link>
          <div className="flex items-center gap-2">
            <button onClick={onClose} className="h-8 rounded-btn border border-border px-3 text-xs text-secondary hover:text-foreground">取消</button>
            {tab === 'create' && (
              <button onClick={() => save.mutate()} disabled={!targetValid || alreadyReached || duplicate || save.isPending} className="inline-flex h-8 items-center gap-1.5 rounded-btn bg-sky-500 px-4 text-xs font-medium text-white transition-colors hover:bg-sky-400 disabled:cursor-not-allowed disabled:opacity-40">
                {save.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Bell className="h-3.5 w-3.5" />}
                创建提醒
              </button>
            )}
          </div>
        </footer>
      </div>
    </div>
  )
}
