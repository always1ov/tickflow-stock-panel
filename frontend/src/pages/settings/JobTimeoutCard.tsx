/**
 * 网络设置面板内容 — 任务停滞超时配置 + 分时批量传输压缩开关。
 * 分栏名为「网络」(Settings.tsx, [R533] 原「网络设置」), 卡片内超时区块标题保持「超时设置」。
 * [R535] 拆成两张卡: 「超时设置」(带保存) 与「数据传输压缩」(点了即生效)。
 */
import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Clock3, Gauge } from 'lucide-react'
import { api, type Preferences } from '@/lib/api'
import { QK } from '@/lib/queryKeys'
import { usePreferences } from '@/lib/useSharedQueries'
import { toast } from '@/components/Toast'
import { buttonClass } from '@/components/ui'
import { SettingsCard, SettingRow } from './SettingsCard'

type TimeoutUnit = 'second' | 'minute' | 'hour'

const TIMEOUT_UNIT_SECONDS: Record<TimeoutUnit, number> = {
  second: 1,
  minute: 60,
  hour: 3600,
}

function preferredTimeoutUnit(seconds: number): TimeoutUnit {
  if (seconds >= 3600 && seconds % 1800 === 0) return 'hour'
  if (seconds % 60 === 0) return 'minute'
  return 'second'
}

function formatTimeoutValue(seconds: number, unit: TimeoutUnit): string {
  if (!Number.isFinite(seconds)) return ''
  const value = seconds / TIMEOUT_UNIT_SECONDS[unit]
  return String(Number(value.toFixed(4)))
}

export function JobTimeoutCard() {
  const qc = useQueryClient()
  const prefs = usePreferences()
  const [timeoutDraft, setTimeoutDraft] = useState<{ regular: string; long: string } | null>(null)
  const [regularUnitOverride, setRegularUnitOverride] = useState<TimeoutUnit | null>(null)
  const [longUnitOverride, setLongUnitOverride] = useState<TimeoutUnit | null>(null)

  const currentRegularTimeout = prefs.data?.data_source_job_timeout_s ?? 1200
  const currentLongTimeout = prefs.data?.data_source_long_job_timeout_s ?? 1800
  const regularTimeoutUnit = regularUnitOverride ?? preferredTimeoutUnit(currentRegularTimeout)
  const longTimeoutUnit = longUnitOverride ?? preferredTimeoutUnit(currentLongTimeout)
  const regularTimeoutInput = timeoutDraft?.regular
    ?? formatTimeoutValue(currentRegularTimeout, regularTimeoutUnit)
  const longTimeoutInput = timeoutDraft?.long
    ?? formatTimeoutValue(currentLongTimeout, longTimeoutUnit)
  const regularInputNumber = Number(regularTimeoutInput)
  const longInputNumber = Number(longTimeoutInput)
  const regularTimeout = Math.round(regularInputNumber * TIMEOUT_UNIT_SECONDS[regularTimeoutUnit])
  const longTimeout = Math.round(longInputNumber * TIMEOUT_UNIT_SECONDS[longTimeoutUnit])
  const timeoutValuesValid = Number.isFinite(regularInputNumber) && regularInputNumber > 0
    && Number.isFinite(longInputNumber) && longInputNumber > 0
    && regularTimeout >= 60 && longTimeout >= 60
  const timeoutValuesChanged = regularTimeout !== currentRegularTimeout
    || longTimeout !== currentLongTimeout

  const minuteBatchCompress = prefs.data?.minute_batch_compress ?? true
  const dailyBatchCompress = prefs.data?.daily_batch_compress ?? true
  // 总开关显示: 任一子开即亮, 全关才灭; 点击 = 全开/全关 (批量写两个子项)
  const compressAnyOn = minuteBatchCompress || dailyBatchCompress
  const toggleCompress = useMutation({
    mutationFn: (enabled: boolean) => api.updateMinuteBatchCompress(enabled),
    onSuccess: (saved) => {
      qc.setQueryData<Preferences>(QK.preferences, current => (
        current ? { ...current, ...saved } : current
      ))
      toast(saved.minute_batch_compress ? '分时压缩已开启' : '分时压缩已关闭', 'success')
    },
    onError: (e: Error) => toast(`保存失败: ${e.message}`, 'error'),
  })
  const toggleDailyCompress = useMutation({
    mutationFn: (enabled: boolean) => api.updateDailyBatchCompress(enabled),
    onSuccess: (saved) => {
      qc.setQueryData<Preferences>(QK.preferences, current => (
        current ? { ...current, ...saved } : current
      ))
      toast(saved.daily_batch_compress ? '日K压缩已开启' : '日K压缩已关闭', 'success')
    },
    onError: (e: Error) => toast(`保存失败: ${e.message}`, 'error'),
  })
  const toggleAllCompress = useMutation({
    mutationFn: async (enabled: boolean) => {
      const [a, b] = await Promise.all([
        api.updateMinuteBatchCompress(enabled),
        api.updateDailyBatchCompress(enabled),
      ])
      return { ...a, ...b }
    },
    onSuccess: (saved) => {
      qc.setQueryData<Preferences>(QK.preferences, current => (
        current ? { ...current, ...saved } : current
      ))
      toast(saved.minute_batch_compress ? '传输压缩已全部开启' : '传输压缩已全部关闭', 'success')
    },
    onError: (e: Error) => toast(`保存失败: ${e.message}`, 'error'),
  })

  const saveJobTimeouts = useMutation({
    mutationFn: () => api.updateDataSourceJobTimeouts(regularTimeout, longTimeout),
    onSuccess: (saved) => {
      qc.setQueryData<Preferences>(QK.preferences, current => (
        current ? { ...current, ...saved } : current
      ))
      setTimeoutDraft(null)
      toast('任务超时配置已保存', 'success')
    },
    onError: (e: Error) => toast(`保存失败: ${e.message}`, 'error'),
  })

  return (
    <>
    {/* [R535] 原来一张「超时设置」卡里还装着数据传输压缩 —— 卡头的「保存」只管超时, 压缩是点了立即生效,
        两件事挤在一张卡里, 看不出那个保存管到哪。拆成两张, 字段、行为一个没动。 */}
    <SettingsCard
      icon={Clock3}
      title="超时设置"
      desc={<>后台任务超过对应时间<b className="text-secondary">没有任何进度</b>才判定卡死并自动终止；只要任务仍在推进（如慢带宽下的冷启动全市场拉取），无论总时长多久都不会被中断。保存时自动换算为秒，修改后对新建任务生效。</>}
      right={(
        <button
          onClick={() => saveJobTimeouts.mutate()}
          disabled={!timeoutValuesValid || !timeoutValuesChanged || saveJobTimeouts.isPending}
          className={buttonClass({ variant: 'primary' }, 'shrink-0')}
        >
          {saveJobTimeouts.isPending ? '保存中...' : '保存'}
        </button>
      )}
    >
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <label className="rounded-btn border border-border/60 bg-elevated/20 px-3.5 py-3">
          <span className="block text-xs font-medium text-foreground mb-1">普通任务停滞超时</span>
          <span className="block text-micro text-muted mb-2">日 K 管道、扩展、修正与重算任务</span>
          <div className="flex items-center gap-2">
            <input
              type="number"
              min={regularTimeoutUnit === 'second' ? 60 : regularTimeoutUnit === 'minute' ? 1 : 1 / 60}
              step={regularTimeoutUnit === 'second' ? 60 : regularTimeoutUnit === 'minute' ? 1 : 0.5}
              value={regularTimeoutInput}
              onChange={e => setTimeoutDraft({ regular: e.target.value, long: longTimeoutInput })}
              className="w-full rounded-btn border border-border bg-base px-2.5 py-1.5 text-sm text-foreground font-mono outline-none focus:border-accent"
            />
            <select
              value={regularTimeoutUnit}
              onChange={e => {
                const nextUnit = e.target.value as TimeoutUnit
                setTimeoutDraft({
                  regular: formatTimeoutValue(regularTimeout, nextUnit),
                  long: longTimeoutInput,
                })
                setRegularUnitOverride(nextUnit)
              }}
              className="w-20 shrink-0 rounded-btn border border-border bg-base px-2 py-1.5 text-xs text-foreground outline-none focus:border-accent"
            >
              <option value="second">秒</option>
              <option value="minute">分钟</option>
              <option value="hour">小时</option>
            </select>
          </div>
          <span className="block text-micro text-muted/60 mt-1.5">默认 20 分钟无进度，最小 1 分钟</span>
        </label>

        <label className="rounded-btn border border-border/60 bg-elevated/20 px-3.5 py-3">
          <span className="block text-xs font-medium text-foreground mb-1">长任务停滞超时</span>
          <span className="block text-micro text-muted mb-2">分钟 K 全市场同步任务</span>
          <div className="flex items-center gap-2">
            <input
              type="number"
              min={longTimeoutUnit === 'second' ? 60 : longTimeoutUnit === 'minute' ? 1 : 1 / 60}
              step={longTimeoutUnit === 'second' ? 60 : longTimeoutUnit === 'minute' ? 1 : 0.5}
              value={longTimeoutInput}
              onChange={e => setTimeoutDraft({ regular: regularTimeoutInput, long: e.target.value })}
              className="w-full rounded-btn border border-border bg-base px-2.5 py-1.5 text-sm text-foreground font-mono outline-none focus:border-accent"
            />
            <select
              value={longTimeoutUnit}
              onChange={e => {
                const nextUnit = e.target.value as TimeoutUnit
                setTimeoutDraft({
                  regular: regularTimeoutInput,
                  long: formatTimeoutValue(longTimeout, nextUnit),
                })
                setLongUnitOverride(nextUnit)
              }}
              className="w-20 shrink-0 rounded-btn border border-border bg-base px-2 py-1.5 text-xs text-foreground outline-none focus:border-accent"
            >
              <option value="second">秒</option>
              <option value="minute">分钟</option>
              <option value="hour">小时</option>
            </select>
          </div>
          <span className="block text-micro text-muted/60 mt-1.5">默认 30 分钟无进度，最小 1 分钟</span>
        </label>
      </div>

    </SettingsCard>

    <SettingsCard
      icon={Gauge}
      title="数据传输压缩"
      desc="大数据接口（分时、日K）启用 gzip 压缩，响应可缩至约 1/8，公网访问明显更快；本机或内网可关闭以节省服务端 CPU。任一子项开启时总开关为开，点击总开关一键全开/全关，子项可单独微调，立即生效。"
      right={(
        <Switch
          on={compressAnyOn}
          disabled={toggleAllCompress.isPending}
          onClick={() => toggleAllCompress.mutate(!compressAnyOn)}
          title={compressAnyOn ? '全部关闭' : '全部开启'}
        />
      )}
    >
      <CompressToggleRow
        label="分时数据压缩"
        desc="分时批量接口（自选/策略分时图，千只标的 MB 级响应）"
        enabled={minuteBatchCompress}
        pending={toggleCompress.isPending}
        onToggle={() => toggleCompress.mutate(!minuteBatchCompress)}
      />
      <CompressToggleRow
        label="日K数据压缩"
        desc="日K批量接口（自选/策略日K列，千只标的 MB 级响应）"
        enabled={dailyBatchCompress}
        pending={toggleDailyCompress.isPending}
        onToggle={() => toggleDailyCompress.mutate(!dailyBatchCompress)}
      />
    </SettingsCard>
    </>
  )
}

function CompressToggleRow({ label, desc, enabled, pending, onToggle }: {
  label: string
  desc: string
  enabled: boolean
  pending: boolean
  onToggle: () => void
}) {
  return (
    <SettingRow label={label} desc={desc}>
      <Switch on={enabled} disabled={pending} onClick={onToggle} title={enabled ? '点击关闭' : '点击开启'} />
    </SettingRow>
  )
}

/** [R535] 两个尺寸的开关并成一个, 与设置区其它开关同尺寸; 滑块改走 transform(原来过渡的是 `left`, 每帧重排) */
function Switch({ on, disabled, onClick, title }: { on: boolean; disabled?: boolean; onClick: () => void; title?: string }) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      title={title}
      aria-pressed={on}
      className={`relative inline-flex h-5 w-9 shrink-0 items-center rounded-full transition-colors duration-expand disabled:opacity-40 ${on ? 'bg-accent' : 'bg-elevated'}`}
    >
      <span className={`inline-block h-3.5 w-3.5 rounded-full bg-white shadow-sm transition-transform duration-expand ${on ? 'translate-x-[18px]' : 'translate-x-[3px]'}`} />
    </button>
  )
}
