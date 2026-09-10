/**
 * 系统设置面板 — 全局行为开关。
 *
 * 独立于实时监控, 放置影响整体应用行为的开关项。
 */
import { useState, useCallback, useEffect } from 'react'
import { toast } from '@/components/Toast'
import { useQueryClient } from '@tanstack/react-query'
import { Settings2, Trash2, RefreshCw, Bell, Volume2, Info, ExternalLink, Stethoscope, Loader2, Wrench } from 'lucide-react'
import { usePreferences, useVersion } from '@/lib/useSharedQueries'
import { api, type DataDoctorReport } from '@/lib/api'
import { QK } from '@/lib/queryKeys'
import { PageHeader } from '@/components/PageHeader'
import { refreshAlertToastConfig } from '@/components/AlertToast'
import { SOUND_OPTIONS, previewSound } from '@/lib/notificationSound'
import {
  listZhVoices, previewVoice, activateVoice, getCurrentVoiceURI,
} from '@/lib/voiceBroadcast'
import { loadStockExternalTemplate, saveStockExternalTemplate } from '@/lib/stock-external-link'

export function SettingsSystemPanel() {
  const qc = useQueryClient()
  const { data: prefs } = usePreferences()
  const { data: versionData } = useVersion()
  const [saving, setSaving] = useState(false)

  const screenerAutoRun = prefs?.screener_auto_run ?? true
  const [extTpl, setExtTpl] = useState(() => loadStockExternalTemplate())
  const [clearing, setClearing] = useState(false)
  const [toastEnabled, setToastEnabled] = useState(() => {
    try { return localStorage.getItem('alert_toast_enabled') !== '0' } catch { return true }
  })
  const [toastMax, setToastMax] = useState(() => {
    try {
      const v = parseInt(localStorage.getItem('alert_toast_max') || '', 10)
      return v >= 1 && v <= 5 ? v : 3
    } catch { return 3 }
  })
  const [soundEnabled, setSoundEnabled] = useState(() => {
    try { return localStorage.getItem('alert_sound_enabled') !== '0' } catch { return true }
  })
  const [soundType, setSoundType] = useState(() => {
    try { return localStorage.getItem('alert_sound') || 'ding' } catch { return 'ding' }
  })
  const [voiceEnabled, setVoiceEnabled] = useState(() => {
    try { return localStorage.getItem('voice_broadcast_enabled') === '1' } catch { return false }
  })
  const [voices, setVoices] = useState(listZhVoices())
  // 用户手选值 (空=走默认偏好 Google 中国大陆)
  const [voiceConfigured, setVoiceConfigured] = useState(() => {
    try { return localStorage.getItem('voice_broadcast_voice') || '' } catch { return '' }
  })
  // 下拉回显值: 用户手选优先, 否则显示当前解析到的语音
  const [voiceURI, setVoiceURI] = useState(() => {
    try { return localStorage.getItem('voice_broadcast_voice') || getCurrentVoiceURI() } catch { return getCurrentVoiceURI() }
  })
  const [voiceRate, setVoiceRate] = useState(() => {
    try {
      const v = parseFloat(localStorage.getItem('voice_broadcast_rate') || '')
      return v >= 0.5 && v <= 2 ? v : 1
    } catch { return 1 }
  })

  // 语音包异步加载 (Google 云语音为 Chrome 联网注入, 比本地晚到), 监听刷新
  useEffect(() => {
    const h = () => {
      setVoices(listZhVoices())
      // 用户未手选时, 跟随默认偏好 (Google CN 到货后自动同步回显)
      if (!voiceConfigured) setVoiceURI(getCurrentVoiceURI())
    }
    if ('speechSynthesis' in window) {
      window.speechSynthesis.addEventListener('voiceschanged', h)
      // 部分浏览器首次需主动触发一次
      h()
    }
    return () => {
      if ('speechSynthesis' in window) window.speechSynthesis.removeEventListener('voiceschanged', h)
    }
  }, [voiceConfigured])

  const save = useCallback(async (cfg: Record<string, unknown>) => {
    setSaving(true)
    try {
      await api.updateRealtimeMonitorConfig(cfg)
      qc.invalidateQueries({ queryKey: QK.preferences })
    } finally {
      setSaving(false)
    }
  }, [qc])

  // 刷新前端缓存: 清除 react-query 缓存 + 强制重载 (绕过浏览器缓存)
  // 不动 localStorage (用户列配置/策略池等偏好保留), 也不影响后端的本地股票数据
  const handleClearCache = useCallback(() => {
    setClearing(true)
    qc.clear()
    // 加时间戳参数强制浏览器重新下载所有静态资源
    setTimeout(() => {
      window.location.href = window.location.pathname + '?_t=' + Date.now()
    }, 300)
  }, [qc])

  return (
    <>
      <PageHeader
        title="系统设置"
        subtitle="全局行为开关"
      />

      <section className="rounded-card border border-border bg-surface p-5">
        <div className="flex items-center gap-2 mb-4">
          <Settings2 className="h-4 w-4 text-accent" />
          <h3 className="text-sm font-medium text-foreground">策略页</h3>
        </div>

        <ToggleRow
          label="进入策略页自动运行策略"
          desc="开启后进入策略页自动跑所有策略获取命中数; 关闭则需手动点击"
          checked={screenerAutoRun}
          disabled={saving}
          onChange={(v) => save({ screener_auto_run: v })}
        />
      </section>

      <section className="rounded-card border border-border bg-surface p-5 mt-6">
        <div className="flex items-center gap-2 mb-4">
          <Bell className="h-4 w-4 text-accent" />
          <h3 className="text-sm font-medium text-foreground">通知弹窗</h3>
        </div>

        <ToggleRow
          label="开启监控通知弹窗"
          desc="收到监控告警时在右下角弹出通知卡片"
          checked={toastEnabled}
          disabled={saving}
          onChange={(v) => {
            localStorage.setItem('alert_toast_enabled', v ? '1' : '0')
            setToastEnabled(v)
            refreshAlertToastConfig()
          }}
        />

        <div className="flex items-center justify-between gap-4 py-2">
          <div className="min-w-0">
            <div className="text-sm text-foreground">最大弹窗个数</div>
            <div className="text-[11px] text-muted truncate">同时显示的通知数量 (1-5), 超出丢弃最旧的</div>
          </div>
          <select
            value={toastMax}
            disabled={!toastEnabled}
            onChange={(e) => {
              const v = Number(e.target.value)
              localStorage.setItem('alert_toast_max', String(v))
              setToastMax(v)
              refreshAlertToastConfig()
            }}
            className="w-16 h-8 px-1.5 rounded-btn border border-border bg-base text-xs text-foreground disabled:opacity-50"
          >
            {[1, 2, 3, 4, 5].map(n => <option key={n} value={n}>{n}</option>)}
          </select>
        </div>

        <ToggleRow
          label="通知声效"
          desc="收到监控告警时播放提示音"
          checked={soundEnabled}
          disabled={!toastEnabled}
          onChange={(v) => {
            localStorage.setItem('alert_sound_enabled', v ? '1' : '0')
            setSoundEnabled(v)
            if (v) previewSound(soundType)
          }}
        />

        <div className="flex items-center justify-between gap-4 py-2">
          <div className="min-w-0 flex items-center gap-1.5">
            <Volume2 className="h-3.5 w-3.5 text-muted" />
            <div>
              <div className="text-sm text-foreground">声效选择</div>
              <div className="text-[11px] text-muted truncate">选择提示音风格</div>
            </div>
          </div>
          <div className="flex items-center gap-1.5">
            <select
              value={soundType}
              disabled={!toastEnabled || !soundEnabled}
              onChange={(e) => {
                const v = e.target.value
                localStorage.setItem('alert_sound', v)
                setSoundType(v)
                if (v !== 'none') previewSound(v)
              }}
              className="w-20 h-8 px-1.5 rounded-btn border border-border bg-base text-xs text-foreground disabled:opacity-50"
            >
              {SOUND_OPTIONS.map(s => <option key={s.key} value={s.key}>{s.label}</option>)}
            </select>
            <button
              onClick={() => previewSound(soundType)}
              disabled={!toastEnabled || !soundEnabled || soundType === 'none'}
              className="px-2 h-8 rounded-btn border border-border bg-base text-xs text-secondary hover:text-foreground hover:border-accent/30 disabled:opacity-50 transition-colors cursor-pointer"
            >
              试听
            </button>
          </div>
        </div>
      </section>

      <section className="rounded-card border border-border bg-surface p-5 mt-6">
        <div className="flex items-center gap-2 mb-4">
          <Volume2 className="h-4 w-4 text-accent" />
          <h3 className="text-sm font-medium text-foreground">语音播报</h3>
        </div>

        <ToggleRow
          label="监控告警语音播报"
          desc="收到告警时用中文语音播报内容 (需浏览器支持, 默认关闭)"
          checked={voiceEnabled}
          disabled={!toastEnabled}
          onChange={(v) => {
            localStorage.setItem('voice_broadcast_enabled', v ? '1' : '0')
            setVoiceEnabled(v)
            if (v) { activateVoice(); previewVoice() }   // 开启即激活 + 试听一句
          }}
        />

        <div className="flex items-center justify-between gap-4 py-2">
          <div className="min-w-0 flex items-center gap-1.5">
            <Volume2 className="h-3.5 w-3.5 text-muted" />
            <div>
              <div className="text-sm text-foreground">语音音色</div>
              <div className="text-[11px] text-muted truncate">
                {voices.length === 0
                  ? '未检测到中文语音, 将用系统默认'
                  : '默认优先 Google 中国大陆 (音质最佳)'}
              </div>
            </div>
          </div>
          <div className="flex items-center gap-1.5">
            <select
              value={voiceURI}
              disabled={!toastEnabled || !voiceEnabled}
              onChange={(e) => {
                const v = e.target.value
                if (v) {
                  // 手选某一语音包
                  localStorage.setItem('voice_broadcast_voice', v)
                  setVoiceConfigured(v)
                  setVoiceURI(v)
                } else {
                  // 选"默认偏好": 清空手选, 走 Google 中国大陆偏好
                  localStorage.removeItem('voice_broadcast_voice')
                  setVoiceConfigured('')
                  setVoiceURI(getCurrentVoiceURI())
                }
              }}
              className="w-32 h-8 px-1.5 rounded-btn border border-border bg-base text-xs text-foreground disabled:opacity-50"
            >
              <option value={getCurrentVoiceURI()}>默认偏好</option>
              {voices
                .filter(v => v.voiceURI !== getCurrentVoiceURI())
                .map(v => <option key={v.voiceURI} value={v.voiceURI}>{v.name}</option>)
              }
            </select>
            <button
              onClick={() => previewVoice()}
              disabled={!toastEnabled || !voiceEnabled}
              className="px-2 h-8 rounded-btn border border-border bg-base text-xs text-secondary hover:text-foreground hover:border-accent/30 disabled:opacity-50 transition-colors cursor-pointer"
            >
              试听
            </button>
          </div>
        </div>

        <div className="flex items-center justify-between gap-4 py-2">
          <div className="min-w-0">
            <div className="text-sm text-foreground">语速</div>
            <div className="text-[11px] text-muted truncate">0.5 慢 — 2.0 快</div>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <input
              type="range" min={0.5} max={2} step={0.1} value={voiceRate}
              disabled={!toastEnabled || !voiceEnabled}
              onChange={(e) => {
                const v = parseFloat(e.target.value)
                localStorage.setItem('voice_broadcast_rate', String(v))
                setVoiceRate(v)
              }}
              className="w-32 disabled:opacity-50"
            />
            <span className="text-xs text-muted w-8 text-right">{voiceRate.toFixed(1)}</span>
          </div>
        </div>
      </section>

      <section className="rounded-card border border-border bg-surface p-5 mt-6">
        <div className="flex items-center gap-2 mb-4">
          <ExternalLink className="h-4 w-4 text-accent" />
          <h3 className="text-sm font-medium text-foreground">个股详情外链</h3>
        </div>

        <div className="flex items-center justify-between gap-4 py-2">
          <div className="min-w-0">
            <div className="text-sm text-foreground">详情页 URL 模板</div>
            <div className="text-[11px] text-muted truncate">{"支持 {code} {market} {symbol} · 留空关闭外链"}</div>
          </div>
          <input
            value={extTpl}
            onChange={(e) => {
              setExtTpl(e.target.value)
              saveStockExternalTemplate(e.target.value)
            }}
            placeholder="https://..."
            spellCheck={false}
            className="w-[26rem] max-w-[60%] h-8 px-2.5 rounded-btn border border-border bg-base text-xs font-mono text-foreground focus:border-accent/50 focus:outline-none"
          />
        </div>
      </section>

      <section className="rounded-card border border-border bg-surface p-5 mt-6">
        <div className="flex items-center gap-2 mb-4">
          <Trash2 className="h-4 w-4 text-accent" />
          <h3 className="text-sm font-medium text-foreground">缓存</h3>
        </div>

        <div className="flex items-center justify-between gap-4 py-2">
          <div className="min-w-0">
            <div className="text-sm text-foreground">刷新前端缓存</div>
            <div className="text-[11px] text-muted truncate">
              清除页面缓存并强制重新加载 (不影响个人配置和本地股票数据)
            </div>
          </div>
          <button
            onClick={handleClearCache}
            disabled={clearing}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-btn text-xs
                       bg-elevated text-secondary hover:text-foreground transition-colors
                       disabled:opacity-50 shrink-0"
          >
            {clearing ? (
              <RefreshCw className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <RefreshCw className="h-3.5 w-3.5" />
            )}
            {clearing ? '清理中…' : '清理并刷新'}
          </button>
        </div>
      </section>

      <DataDoctorSection />

      <section className="rounded-card border border-border bg-surface p-5 mt-6">
        <div className="flex items-center gap-2 mb-4">
          <Info className="h-4 w-4 text-accent" />
          <h3 className="text-sm font-medium text-foreground">关于</h3>
        </div>

        <div className="flex items-center justify-between gap-4 py-2">
          <div className="min-w-0">
            <div className="text-sm text-foreground">版本</div>
            <div className="text-[11px] text-muted truncate">当前安装的应用版本</div>
          </div>
          <span className="font-mono text-xs text-secondary shrink-0">
            {versionData?.version ?? '—'}
          </span>
        </div>

      </section>
    </>
  )
}


// ===== [R271] 数据体检 =====

/**
 * 盘上那些跟着功能一起长出来的老文件, 到底缺了什么。
 *
 * 用户: 「我不断改这个系统, 不断沿用以前的数据 …… 我加了东西或者删除了东西,
 * 但是系统没有重头开始, 会有残留的数据文件, 缺字段或者不完整」。
 *
 * 界面上要说清楚的是**三类的处置办法不一样**:
 *   用户数据  不可重算 —— 只能按默认值补齐, 少一条就是真丢了
 *   派生数据  可重算 —— 坏了删掉重跑, 补它是在给假数据续命
 *   孤儿文件  功能删了文件还在 —— 只报, 不替人删
 *
 * **一个「一键全修」都不给。** 改的是不可重算的用户数据, 每一处都该是人点头的。
 */
function DataDoctorSection() {
  const [report, setReport] = useState<DataDoctorReport | null>(null)
  const [busy, setBusy] = useState(false)
  const [healing, setHealing] = useState('')

  const run = async () => {
    setBusy(true)
    try { setReport(await api.dataDoctorScan()) }
    catch { /* 已由 request 弹出 */ }
    finally { setBusy(false) }
  }

  const heal = async (rel: string, cn: string) => {
    setHealing(rel)
    try {
      const r = (await api.dataDoctorHeal([rel])).results[0]
      if (!r?.ok) { toast(r?.error || '补齐失败', 'error'); return }
      toast(r.filled
        ? `「${cn}」补齐 ${r.filled} 条${r.backup ? `,已备份为 ${r.backup}` : ''}`
        : `「${cn}」没有需要补的`, 'success')
      setReport(await api.dataDoctorScan())
    } catch { /* 已由 request 弹出 */ }
    finally { setHealing('') }
  }

  const problems = (report?.stores ?? []).filter(
    s => s.exists && (s.readable === false || s.error
      || Object.keys(s.missing).length || Object.keys(s.incomplete).length))
  // [R272] 派生数据里体积最大的几个 —— 删掉会自动重算, 是最省事的一档清理。
  // 真机上 strategy_cache.json 有 10MB, 不把体积摆出来根本看不出该清哪个。
  const bulky = (report?.stores ?? [])
    .filter(s => s.exists && s.kind === 'derived' && s.bytes > 5 * 1024 * 1024)
    .sort((a, b) => b.bytes - a.bytes)

  return (
    <section className="rounded-card border border-border bg-surface p-5 mt-6">
      <div className="flex items-center gap-2 mb-1">
        <Stethoscope className="h-4 w-4 text-accent" />
        <h3 className="text-sm font-medium text-foreground">数据体检</h3>
        <button
          onClick={() => void run()}
          disabled={busy}
          className="ml-auto inline-flex items-center gap-1.5 px-3 py-1.5 rounded-btn text-xs
                     bg-elevated text-secondary hover:text-foreground transition-colors disabled:opacity-50"
        >
          {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
          {busy ? '体检中…' : '开始体检'}
        </button>
      </div>
      <p className="text-[11px] leading-relaxed text-muted">
        系统一直在改,盘上的老数据是早先的版本写的 —— 后加的字段老记录不会有。
        这类缺失<b className="text-secondary">不会报错</b>,只会被当成「你没设过」静默处理。
        体检只读不改;补齐前会先备份,并且<b className="text-secondary">一条记录都不删</b>。
      </p>

      {report && (
        <div className="mt-3 space-y-3">
          <div className="text-[11px] text-secondary">
            查了 {report.summary.checked} 处,盘上有 {report.summary.present} 处
            {report.summary.with_missing > 0 && <span className="text-warning">,{report.summary.with_missing} 处缺字段</span>}
            {report.summary.unreadable > 0 && <span className="text-danger">,{report.summary.unreadable} 处读不动</span>}
            {report.summary.orphans > 0 && <span className="text-muted">,{report.summary.orphans} 个孤儿文件</span>}
            {problems.length === 0 && report.summary.orphans === 0 && <span className="text-emerald-400"> —— 没查出问题</span>}
          </div>

          {problems.map(s => (
            <div key={s.rel} className="rounded-btn border border-border/60 bg-elevated/20 px-3 py-2">
              <div className="flex flex-wrap items-baseline gap-x-2">
                <span className="text-xs text-foreground">{s.cn}</span>
                <span className="font-mono text-[10px] text-muted">{s.rel}</span>
                <span className={`text-[10px] ${s.kind === 'user' ? 'text-amber-400' : 'text-muted'}`}>
                  {s.kind === 'user' ? '用户数据 · 不可重算' : '派生数据 · 可重算'}
                </span>
                {s.records != null && <span className="text-[10px] text-muted">{s.records} 条</span>}
                {s.bytes > 0 && (
                  <span className="text-[10px] text-muted">
                    {s.bytes > 1024 * 1024 ? `${(s.bytes / 1024 / 1024).toFixed(1)} MB` : `${(s.bytes / 1024).toFixed(1)} KB`}
                  </span>
                )}
                {/* 补齐只对用户数据、且只补声明过默认值的那些 */}
                {s.kind === 'user' && Object.keys(s.missing).length > 0 && (
                  <button
                    onClick={() => void heal(s.rel, s.cn)}
                    disabled={healing === s.rel}
                    title="按默认值补上缺的字段。已有的值一个都不动,改动前先备份。"
                    className="ml-auto inline-flex items-center gap-1 rounded-btn border border-accent/40 bg-accent/10 px-2 py-0.5 text-[10px] text-accent hover:bg-accent/20 disabled:opacity-50"
                  >
                    {healing === s.rel ? <Loader2 className="h-3 w-3 animate-spin" /> : <Wrench className="h-3 w-3" />}
                    补齐
                  </button>
                )}
              </div>
              {!!s.error && <p className="mt-1 text-[10px] text-danger">{s.error}</p>}
              {Object.entries(s.missing).map(([k, n]) => (
                <p key={k} className="mt-0.5 text-[10px] text-warning/90">
                  缺字段 <code className="font-mono">{k}</code> · {n} 条
                  {s.kind === 'derived' && <span className="text-muted">(派生数据 —— 该做的是删掉重算,不是补)</span>}
                </p>
              ))}
              {Object.entries(s.incomplete).map(([k, n]) => (
                <p key={k} className="mt-0.5 text-[10px] text-danger/90">
                  <code className="font-mono">{k}</code> 为空 · {n} 条 —— 补不了,得自己看这几条还要不要
                </p>
              ))}
              {!!s.note && <p className="mt-0.5 text-[10px] text-muted/70">{s.note}</p>}
            </div>
          ))}

          {bulky.length > 0 && (
            <div className="rounded-btn border border-border/60 bg-elevated/20 px-3 py-2">
              <div className="text-[11px] text-secondary">占地方的派生数据 —— 可重算,删了会自动重建</div>
              <div className="mt-1 space-y-0.5">
                {bulky.map(s => (
                  <p key={s.rel} className="text-[10px] text-muted">
                    <span className="text-secondary">{s.cn}</span>{' '}
                    <span className="font-mono">{s.rel}</span> ·{' '}
                    <b className="text-warning">{(s.bytes / 1024 / 1024).toFixed(1)} MB</b>
                    {!!s.note && <span className="ml-1 opacity-70">{s.note}</span>}
                  </p>
                ))}
              </div>
            </div>
          )}

          {report.orphans.length > 0 && (
            <div className="rounded-btn border border-border/60 bg-elevated/20 px-3 py-2">
              <div className="text-[11px] text-secondary">
                孤儿文件 —— 现在的代码不读它们,多半是删掉的功能留下的
              </div>
              <div className="mt-1 space-y-0.5">
                {report.orphans.map(o => (
                  <p key={o.rel} className="font-mono text-[10px] text-muted">
                    {o.rel}{o.is_dir ? '/' : ''} · {(o.bytes / 1024).toFixed(1)} KB
                  </p>
                ))}
              </div>
              <p className="mt-1 text-[10px] text-muted/70">
                这里<b className="text-secondary">不替你删</b> —— 判断「没人读」靠的是一张手写清单,
                清单漏一项就等于删了你的数据。确认之后自己到 data/user_data 下删。
              </p>
            </div>
          )}
        </div>
      )}
    </section>
  )
}


// ===== ToggleRow =====

function ToggleRow({
  label,
  desc,
  checked,
  disabled,
  onChange,
}: {
  label: string
  desc: string
  checked: boolean
  disabled?: boolean
  onChange: (v: boolean) => void
}) {
  return (
    <div className="flex items-center justify-between gap-4 py-2">
      <div className="min-w-0">
        <div className="text-sm text-foreground">{label}</div>
        <div className="text-[11px] text-muted truncate">{desc}</div>
      </div>
      <button
        onClick={() => onChange(!checked)}
        disabled={disabled}
        className={`relative inline-flex h-5 w-9 items-center rounded-full shrink-0 transition-colors duration-expand disabled:opacity-50 ${
          checked ? 'bg-accent' : 'bg-elevated'
        }`}
      >
        <span
          className={`inline-block h-3.5 w-3.5 rounded-full bg-white shadow-sm transition-transform duration-expand ${
            checked ? 'translate-x-[18px]' : 'translate-x-[3px]'
          }`}
        />
      </button>
    </div>
  )
}
