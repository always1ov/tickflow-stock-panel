/**
 * 系统设置面板 — 全局行为开关。
 *
 * 独立于实时监控, 放置影响整体应用行为的开关项。
 */
import { useState, useCallback, useEffect, useRef } from 'react'
import { useMutation } from '@tanstack/react-query'
import { toast } from '@/components/Toast'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Settings2, RefreshCw, Bell, Volume2, Stethoscope, Loader2, Wrench, Minus, Plus, ShieldCheck, RotateCcw, ChevronDown, Layers, Upload, MemoryStick } from 'lucide-react'
import { usePreferences, useVersion } from '@/lib/useSharedQueries'
import { api, type DataDoctorReport } from '@/lib/api'
import type { UpgradeGuardCategory } from '@/lib/api'
import { QK } from '@/lib/queryKeys'
import { refreshAlertToastConfig } from '@/components/AlertToast'
import { mergeSoundOptions, previewSound, CUSTOM_SOUND_PREFIX } from '@/lib/notificationSound'
import { setUiPref } from '@/lib/uiPrefs'
import { setKlineBatchLimits,
  DAILY_BATCH_SYMBOLS_MIN,
  DAILY_BATCH_SYMBOLS_MAX,
  MINUTE_BATCH_SYMBOLS_MIN,
  MINUTE_BATCH_SYMBOLS_MAX,
} from '@/lib/klineBatchLimits'
import {
  listZhVoices, previewVoice, activateVoice,
} from '@/lib/voiceBroadcast'
import { loadStockExternalTemplate, saveStockExternalTemplate } from '@/lib/stock-external-link'
import { buttonClass } from '@/components/ui'
import { ExtensionSlot } from '@/extensions/ExtensionSlot'
import { ZOOM_MIN, ZOOM_MAX, ZOOM_STEP, getPageZoom, setPageZoom } from '@/lib/pageZoom'
import { SettingsCard, SettingRow } from './SettingsCard'
import { Switch } from '@/components/ui/Switch'

// [R589 同步上游 v0.3.27] 回测 worker RSS 内存上限 (GiB) 界面范围
// 与后端 BacktestWorkerRssLimitIn 校验一致
const BACKTEST_RSS_LIMIT_GIB_MIN = 0
const BACKTEST_RSS_LIMIT_GIB_MAX = 64


export function SettingsSystemPanel() {
  const qc = useQueryClient()
  const { data: prefs } = usePreferences()
  const { data: versionData } = useVersion()
  const [saving, setSaving] = useState(false)

  const screenerAutoRun = prefs?.screener_auto_run ?? true
  const [extTpl, setExtTpl] = useState(() => loadStockExternalTemplate())
  const [clearing, setClearing] = useState(false)
  // ===== 界面缩放 (整套界面等比缩放, 立即生效并记忆; 见 lib/pageZoom.ts) =====
  const [pageZoom, setPageZoomState] = useState(() => getPageZoom())
  const changeZoom = useCallback((delta: number) => {
    setPageZoomState(setPageZoom(getPageZoom() + delta))
  }, [])
  const save = useCallback(async (cfg: Record<string, unknown>) => {
    setSaving(true)
    try {
      await api.updateRealtimeMonitorConfig(cfg)
      qc.invalidateQueries({ queryKey: QK.preferences })
    } finally {
      setSaving(false)
    }
  }, [qc])

  // [R589 同步上游 v0.3.27] 回测内存上限: worker 每任务启动时从后端读取,
  // 保存后下一个回测/优化任务即生效
  const saveBacktestRssLimit = useMutation({
    mutationFn: (gib: number) => api.updateBacktestWorkerRssLimit(gib),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: QK.preferences })
    },
    onError: (e: Error) => toast(e.message || '保存失败', 'error'),
  })

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

  // [R578 同步上游 v0.3.16] 批量上限: 保存成功后把新值同步进分块助手, 并刷新偏好缓存。
  // 已挂载页面的 query 不会立刻重跑, 但下一轮轮询/切换页面即用新分块。
  const saveDailyBatch = useMutation({
    mutationFn: (size: number) => api.updateDailyBatchSymbols(size),
    onSuccess: ({ daily_batch_symbols }) => {
      setKlineBatchLimits({ daily: daily_batch_symbols })
      qc.invalidateQueries({ queryKey: QK.preferences })
    },
    onError: (e: Error) => toast(e.message || '保存失败', 'error'),
  })
  const saveMinuteBatch = useMutation({
    mutationFn: (size: number) => api.updateMinuteBatchSymbols(size),
    onSuccess: ({ minute_batch_symbols }) => {
      setKlineBatchLimits({ minute: minute_batch_symbols })
      qc.invalidateQueries({ queryKey: QK.preferences })
    },
    onError: (e: Error) => toast(e.message || '保存失败', 'error'),
  })

  return (
    <div className="space-y-5">
      {/* [R533] 这里原来又印了一遍「系统设置 · 全局行为开关」大标题 —— 分栏条上已经写着「系统」, 同一页两个标题 */}
      {/* [R534] 「通知弹窗」「语音播报」两张卡搬去了「通知」栏(AlertPopupSettings, 本文件导出) */}
      {/* [R535] 原来是五张各装一行的卡(策略页 / 个股详情外链 / 缓存 / 数据体检 / 关于), 一屏看过去五个标题
          比五行内容还显眼。按「偏好」与「维护」收成两张: 常规里是改了就生效的偏好与版本号,
          维护里是点一下才干活的两件事。每一行的文字、控件、行为都没改。 */}
      <SettingsCard icon={Settings2} title="常规">
        <ToggleRow
          label="进入策略页自动运行策略"
          desc="开启后进入策略页自动跑所有策略获取命中数; 关闭则需手动点击"
          checked={screenerAutoRun}
          disabled={saving}
          onChange={(v) => save({ screener_auto_run: v })}
        />
        <SettingRow label="个股详情外链" desc={"详情页 URL 模板 · 支持 {code} {market} {symbol} · 留空关闭外链"}>
          <input
            value={extTpl}
            onChange={(e) => {
              setExtTpl(e.target.value)
              saveStockExternalTemplate(e.target.value)
            }}
            placeholder="https://..."
            spellCheck={false}
            className="w-[26rem] max-w-[55%] h-8 px-2.5 rounded-btn border border-border bg-base text-xs font-mono text-foreground focus:border-accent/50 focus:outline-none"
          />
        </SettingRow>
        <SettingRow label="版本" desc="当前安装的应用版本">
          <span className="font-mono text-xs text-secondary shrink-0">
            {versionData?.version ?? '—'}
          </span>
        </SettingRow>
        {/* [v0.3.8 同步上游] 界面缩放: 等比缩放整页, 立即生效并记忆 */}
        <SettingRow label="界面缩放" desc="整个界面等比缩放, 立即生效并记忆 (80%–150%)">
          <div className="flex shrink-0 items-center gap-2">
            {pageZoom !== 1 && (
              <button
                onClick={() => setPageZoomState(setPageZoom(1))}
                className={buttonClass({ size: 'sm', variant: 'ghost' })}
              >
                重置
              </button>
            )}
            <button
              onClick={() => changeZoom(-ZOOM_STEP)}
              disabled={pageZoom <= ZOOM_MIN}
              aria-label="缩小界面"
              className={buttonClass({ size: 'sm', variant: 'secondary' }, 'h-7 w-7 !px-0')}
            >
              <Minus className="h-3.5 w-3.5" />
            </button>
            <span className="w-11 select-none text-center font-mono text-xs text-secondary">
              {Math.round(pageZoom * 100)}%
            </span>
            <button
              onClick={() => changeZoom(ZOOM_STEP)}
              disabled={pageZoom >= ZOOM_MAX}
              aria-label="放大界面"
              className={buttonClass({ size: 'sm', variant: 'secondary' }, 'h-7 w-7 !px-0')}
            >
              <Plus className="h-3.5 w-3.5" />
            </button>
          </div>
        </SettingRow>
      </SettingsCard>

      <SettingsCard icon={Wrench} title="维护">
        <SettingRow label="刷新前端缓存" desc="清除页面缓存并强制重新加载 (不影响个人配置和本地股票数据)">
          <button
            onClick={handleClearCache}
            disabled={clearing}
            className={buttonClass({ size: 'sm', variant: 'secondary' }, 'shrink-0 gap-1.5')}
          >
            <RefreshCw className={`h-3.5 w-3.5 ${clearing ? 'animate-spin' : ''}`} />
            {clearing ? '清理中…' : '清理并刷新'}
          </button>
        </SettingRow>
        <DataDoctorSection />

        {/* [R578 同步上游 v0.3.16] 批量请求上限: 自选/选股列表的 K 线分批大小, 改完立即生效。
            [R535] 仍是常规 + 维护两张卡, 这块并入维护, 不另起卡片。 */}
        <div className="mt-3 border-t border-border/60 pt-3">
          <div className="mb-1.5 flex items-center gap-1.5 text-xs font-medium text-foreground">
            <Layers className="h-3.5 w-3.5 text-muted" />
            批量请求
          </div>
          <p className="mb-2 text-xs leading-relaxed text-muted">
            自选 / 选股列表的 K 线按这里的数量分批请求，单批越大请求越少、速度越快，
            但单次内存峰值也越高。改完立即生效，无需重启。
          </p>
          <BatchSymbolsRow
            label="日K批量上限"
            desc="每只约 12 根 K 线，成本较低"
            min={DAILY_BATCH_SYMBOLS_MIN}
            max={DAILY_BATCH_SYMBOLS_MAX}
            value={prefs?.daily_batch_symbols ?? 400}
            saving={saveDailyBatch.isPending}
            onSave={(size) => saveDailyBatch.mutate(size)}
            warnAt={2000}
            warnText="超过 2000 只时，多标签页或分时同时刷新会叠加内存峰值，可能触发浏览器卡顿或后端内存告警。"
          />
          <div className="my-1 h-px bg-border/60" />
          <BatchSymbolsRow
            label="分时批量上限"
            desc="每只约 240 根 K 线，内存约为日K的 20 倍"
            min={MINUTE_BATCH_SYMBOLS_MIN}
            max={MINUTE_BATCH_SYMBOLS_MAX}
            value={prefs?.minute_batch_symbols ?? 400}
            saving={saveMinuteBatch.isPending}
            onSave={(size) => saveMinuteBatch.mutate(size)}
            warnAt={800}
            warnText="分时数据量是日K的 20 倍：超过 800 只时单次响应可达数十 MB，建议保持默认或更低。"
          />
        </div>

        {/* [R589 同步上游 v0.3.27] 回测内存上限, 仍并入维护卡(R535) */}
        <div className="mt-3 border-t border-border/60 pt-3">
          <div className="mb-1.5 flex items-center gap-1.5 text-xs font-medium text-foreground">
            <MemoryStick className="h-3.5 w-3.5 text-muted" />
            性能与内存
          </div>
          <p className="mb-2 text-xs leading-relaxed text-muted">
            回测 / 稳健优化 / 因子挖掘在独立进程运行，内存超过上限会被中止并提示
            （避免把整机拖入卡顿）。保存后对新发起的任务生效，无需重启。
          </p>
          <BatchSymbolsRow
            label="回测内存上限"
            desc="默认 6 · 0 = 不限制"
            min={BACKTEST_RSS_LIMIT_GIB_MIN}
            max={BACKTEST_RSS_LIMIT_GIB_MAX}
            value={prefs?.backtest_worker_rss_limit_gib ?? 6}
            saving={saveBacktestRssLimit.isPending}
            onSave={(gib) => saveBacktestRssLimit.mutate(gib)}
            warnAt={16}
            warnText="上限超过物理内存时会触发系统交换（swap），回测速度反而断崖式下降；内存不足时优先缩小回测时间范围/标的数量。"
            unit="GiB"
            rangeUnit="GiB"
          />
        </div>
      </SettingsCard>
    </div>
  )
}



// ===== [R534] 通知弹窗 + 语音播报 —— 搬到「通知」栏 =====
//
// 用户: 「通知设置合到一栏」。两张卡原样搬出, 只读写浏览器本地偏好(alert_toast_* / alert_sound* /
// voice_broadcast_*), 与后端无关。唯一的改动: 弹窗开关原来挂着 `disabled={saving}` —— 那是「策略页」那个开关
// 落库时的忙碌态, 跟弹窗无关, 搬出来就没有了。
export function AlertPopupSettings() {
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
  const qc = useQueryClient()
  // 下拉值: 用户手选的 voiceURI (空=默认偏好)。回显只用这一份, 不再动态解析默认
  // 语音当 value —— 否则手选 X 后「默认偏好」的 value 也变成 X, 选中项被吞掉。
  const [voiceConfigured, setVoiceConfigured] = useState(() => {
    try { return localStorage.getItem('voice_broadcast_voice') || '' } catch { return '' }
  })
  const [voiceRate, setVoiceRate] = useState(() => {
    try {
      const v = parseFloat(localStorage.getItem('voice_broadcast_rate') || '')
      return v >= 0.5 && v <= 2 ? v : 1
    } catch { return 1 }
  })

  // ===== 自定义语音包 (上传提示音, 存后端 data/sound_packs, 跨设备可用) =====
  const { data: packData } = useQuery({
    queryKey: QK.soundPacks,
    queryFn: api.listSoundPacks,
    staleTime: 60_000,
  })
  const soundPacks = packData?.packs ?? []
  const soundOptions = mergeSoundOptions(soundPacks.map(p => p.name))
  const soundFileRef = useRef<HTMLInputElement>(null)

  const uploadSoundPack = useMutation({
    mutationFn: (file: File) => api.uploadSoundPack(file),
    onSuccess: (r) => {
      toast(`已上传 ${r.pack.name}`, 'success')
      qc.invalidateQueries({ queryKey: QK.soundPacks })
    },
    onError: (e: Error) => toast(e.message || '上传失败', 'error'),
  })
  const deleteSoundPack = useMutation({
    mutationFn: (name: string) => api.deleteSoundPack(name),
    onSuccess: (_r, name) => {
      toast(`已删除 ${name}`, 'success')
      // 删掉的恰是当前选中音 → 回退默认, 避免悬空引用
      if (soundType === CUSTOM_SOUND_PREFIX + name) {
        setUiPref('alert_sound', 'ding')
        setSoundType('ding')
      }
      qc.invalidateQueries({ queryKey: QK.soundPacks })
    },
    onError: (e: Error) => toast(e.message || '删除失败', 'error'),
  })
  const onSoundFilePicked = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0]
    if (f) uploadSoundPack.mutate(f)
    e.target.value = ''  // 同名重选也能触发 onChange
  }, [uploadSoundPack])

  // 语音包异步加载 (Google 云语音为 Chrome 联网注入, 比本地晚到), 监听刷新
  useEffect(() => {
    const h = () => {
      setVoices(listZhVoices())
    }
    if ('speechSynthesis' in window) {
      window.speechSynthesis.addEventListener('voiceschanged', h)
      // 部分浏览器首次需主动触发一次
      h()
    }
    return () => {
      if ('speechSynthesis' in window) window.speechSynthesis.removeEventListener('voiceschanged', h)
    }
  }, [])


  return (
    <div className="space-y-5">
      <SettingsCard icon={Bell} title="通知弹窗">

        <ToggleRow
          label="开启监控通知弹窗"
          desc="收到监控告警时在右下角弹出通知卡片"
          checked={toastEnabled}
          onChange={(v) => {
            setUiPref('alert_toast_enabled', v ? '1' : '0')
            setToastEnabled(v)
            refreshAlertToastConfig()
          }}
        />

        <div className="flex items-center justify-between gap-4 py-2">
          <div className="min-w-0">
            <div className="text-sm text-foreground">最大弹窗个数</div>
            <div className="text-xs text-muted truncate">同时显示的通知数量 (1-5), 超出丢弃最旧的</div>
          </div>
          <select
            value={toastMax}
            disabled={!toastEnabled}
            onChange={(e) => {
              const v = Number(e.target.value)
              setUiPref('alert_toast_max', String(v))
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
            setUiPref('alert_sound_enabled', v ? '1' : '0')
            setSoundEnabled(v)
            if (v) previewSound(soundType)
          }}
        />

        <div className="flex items-center justify-between gap-4 py-2">
          <div className="min-w-0 flex items-center gap-1.5">
            <Volume2 className="h-3.5 w-3.5 text-muted" />
            <div>
              <div className="text-sm text-foreground">声效选择</div>
              <div className="text-xs text-muted truncate">选择提示音风格</div>
            </div>
          </div>
          <div className="flex items-center gap-1.5">
            <select
              value={soundType}
              disabled={!toastEnabled || !soundEnabled}
              onChange={(e) => {
                const v = e.target.value
                setUiPref('alert_sound', v)
                setSoundType(v)
                if (v !== 'none') previewSound(v)
              }}
              className="w-44 h-8 px-1.5 rounded-btn border border-border bg-base text-xs text-foreground disabled:opacity-50"
            >
              {soundOptions.map(s => <option key={s.key} value={s.key}>{s.label}</option>)}
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

        <div className="flex items-center justify-between gap-4 py-2">
          <div className="min-w-0 flex items-center gap-1.5">
            <Upload className="h-3.5 w-3.5 text-muted" />
            <div>
              <div className="text-sm text-foreground">自定义语音包</div>
              <div className="text-xs text-muted truncate">上传自己的提示音 (mp3/wav/ogg/m4a/flac/aac, ≤4MB), 同名重传替换</div>
            </div>
          </div>
          <input
            ref={soundFileRef}
            type="file"
            accept=".mp3,.wav,.ogg,.m4a,.flac,.aac,.opus,.webm"
            className="hidden"
            onChange={onSoundFilePicked}
          />
          <button
            onClick={() => soundFileRef.current?.click()}
            disabled={uploadSoundPack.isPending}
            className={buttonClass({}, 'h-8 shrink-0 gap-1.5')}
          >
            <Upload className="h-3.5 w-3.5" />
            {uploadSoundPack.isPending ? '上传中…' : '上传'}
          </button>
        </div>
        {soundPacks.length > 0 && (
          <div className="mt-1 space-y-1">
            {soundPacks.map(p => (
              <div key={p.name} className="flex items-center justify-between gap-2 pl-5 pr-1.5 py-1 rounded-btn bg-base/60">
                <span className="text-xs text-foreground truncate">
                  {p.name}
                  <span className="text-muted ml-1.5">{p.size >= 1024 * 1024 ? `${(p.size / 1024 / 1024).toFixed(1)}MB` : `${Math.max(1, Math.round(p.size / 1024))}KB`}</span>
                </span>
                <div className="flex items-center gap-1 shrink-0">
                  <button
                    onClick={() => previewSound(CUSTOM_SOUND_PREFIX + p.name)}
                    className={buttonClass({ size: 'xs' })}
                  >
                    试听
                  </button>
                  <button
                    onClick={() => deleteSoundPack.mutate(p.name)}
                    disabled={deleteSoundPack.isPending && deleteSoundPack.variables === p.name}
                    className={buttonClass({ size: 'xs' })}
                  >
                    {deleteSoundPack.isPending && deleteSoundPack.variables === p.name ? '删除中' : '删除'}
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </SettingsCard>


      <SettingsCard icon={Volume2} title="语音播报">

        <ToggleRow
          label="监控告警语音播报"
          desc="收到告警时用中文语音播报内容 (需浏览器支持, 默认关闭)"
          checked={voiceEnabled}
          disabled={!toastEnabled}
          onChange={(v) => {
            setUiPref('voice_broadcast_enabled', v ? '1' : '0')
            setVoiceEnabled(v)
            if (v) { activateVoice(); previewVoice() }   // 开启即激活 + 试听一句
          }}
        />

        <div className="flex items-center justify-between gap-4 py-2">
          <div className="min-w-0 flex items-center gap-1.5">
            <Volume2 className="h-3.5 w-3.5 text-muted" />
            <div>
              <div className="text-sm text-foreground">语音音色</div>
              <div className="text-xs text-muted truncate">
                {voices.length === 0
                  ? '未检测到中文语音, 将用系统默认'
                  : '默认优先 Google 中国大陆 (音质最佳)'}
              </div>
            </div>
          </div>
          <div className="flex items-center gap-1.5">
            <select
              value={voiceConfigured}
              disabled={!toastEnabled || !voiceEnabled}
              onChange={(e) => {
                const v = e.target.value
                if (v) {
                  // 手选某一语音包
                  setUiPref('voice_broadcast_voice', v)
                  setVoiceConfigured(v)
                } else {
                  // 选"默认偏好"(固定空值): 清空手选, 走 Google 中国大陆偏好
                  setUiPref('voice_broadcast_voice', null)
                  setVoiceConfigured('')
                }
              }}
              className="w-32 h-8 px-1.5 rounded-btn border border-border bg-base text-xs text-foreground disabled:opacity-50"
            >
              <option value="">默认偏好</option>
              {voices.map(v => (
                <option key={v.voiceURI} value={v.voiceURI}>{v.name}</option>
              ))}
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
            <div className="text-xs text-muted truncate">0.5 慢 — 2.0 快</div>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <input
              type="range" min={0.5} max={2} step={0.1} value={voiceRate}
              disabled={!toastEnabled || !voiceEnabled}
              onChange={(e) => {
                const v = parseFloat(e.target.value)
                setUiPref('voice_broadcast_rate', String(v))
                setVoiceRate(v)
              }}
              className="w-32 disabled:opacity-50"
            />
            <span className="text-xs text-muted w-8 text-right">{voiceRate.toFixed(1)}</span>
          </div>
        </div>
      </SettingsCard>

    </div>
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
    <div className="border-t border-border/60 pt-3 mt-2">
      <SettingRow label="数据体检" desc={<>
        系统一直在改,盘上的老数据是早先的版本写的 —— 后加的字段老记录不会有。
        这类缺失<b className="text-secondary">不会报错</b>,只会被当成「你没设过」静默处理。
        体检只读不改;补齐前会先备份,并且<b className="text-secondary">一条记录都不删</b>。
      </>}>
        <button
          onClick={() => void run()}
          disabled={busy}
          className={buttonClass({ size: 'sm', variant: 'secondary' }, 'shrink-0 gap-1.5')}
        >
          {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Stethoscope className="h-3.5 w-3.5" />}
          {busy ? '体检中…' : '开始体检'}
        </button>
      </SettingRow>

      {report && (
        <div className="mt-3 space-y-3">
          <div className="text-xs text-secondary">
            查了 {report.summary.checked} 处,盘上有 {report.summary.present} 处
            {report.summary.with_missing > 0 && <span className="text-warning">,{report.summary.with_missing} 处缺字段</span>}
            {report.summary.unreadable > 0 && <span className="text-danger">,{report.summary.unreadable} 处读不动</span>}
            {report.summary.orphans > 0 && <span className="text-muted">,{report.summary.orphans} 个孤儿文件</span>}
            {problems.length === 0 && report.summary.orphans === 0 && <span className="text-bear"> —— 没查出问题</span>}
          </div>

          {problems.map(s => (
            <div key={s.rel} className="rounded-btn border border-border/60 bg-elevated/20 px-3 py-2">
              <div className="flex flex-wrap items-baseline gap-x-2">
                <span className="text-xs text-foreground">{s.cn}</span>
                <span className="font-mono text-micro text-muted">{s.rel}</span>
                <span className={`text-micro ${s.kind === 'user' ? 'text-warning' : 'text-muted'}`}>
                  {s.kind === 'user' ? '用户数据 · 不可重算' : '派生数据 · 可重算'}
                </span>
                {s.records != null && <span className="text-micro text-muted">{s.records} 条</span>}
                {s.bytes > 0 && (
                  <span className="text-micro text-muted">
                    {s.bytes > 1024 * 1024 ? `${(s.bytes / 1024 / 1024).toFixed(1)} MB` : `${(s.bytes / 1024).toFixed(1)} KB`}
                  </span>
                )}
                {/* 补齐只对用户数据、且只补声明过默认值的那些 */}
                {s.kind === 'user' && Object.keys(s.missing).length > 0 && (
                  <button
                    onClick={() => void heal(s.rel, s.cn)}
                    disabled={healing === s.rel}
                    title="按默认值补上缺的字段。已有的值一个都不动,改动前先备份。"
                    className={buttonClass({ size: 'xs' }, 'ml-auto gap-1')}
                  >
                    {healing === s.rel ? <Loader2 className="h-3 w-3 animate-spin" /> : <Wrench className="h-3 w-3" />}
                    补齐
                  </button>
                )}
              </div>
              {!!s.error && <p className="mt-1 text-micro text-danger">{s.error}</p>}
              {Object.entries(s.missing).map(([k, n]) => (
                <p key={k} className="mt-0.5 text-micro text-warning/90">
                  缺字段 <code className="font-mono">{k}</code> · {n} 条
                  {s.kind === 'derived' && <span className="text-muted">(派生数据 —— 该做的是删掉重算,不是补)</span>}
                </p>
              ))}
              {Object.entries(s.incomplete).map(([k, n]) => (
                <p key={k} className="mt-0.5 text-micro text-danger/90">
                  <code className="font-mono">{k}</code> 为空 · {n} 条 —— 补不了,得自己看这几条还要不要
                </p>
              ))}
              {!!s.note && <p className="mt-0.5 text-micro text-muted/70">{s.note}</p>}
            </div>
          ))}

          {bulky.length > 0 && (
            <div className="rounded-btn border border-border/60 bg-elevated/20 px-3 py-2">
              <div className="text-xs text-secondary">占地方的派生数据 —— 可重算,删了会自动重建</div>
              <div className="mt-1 space-y-0.5">
                {bulky.map(s => (
                  <p key={s.rel} className="text-micro text-muted">
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
              <div className="text-xs text-secondary">
                孤儿文件 —— 现在的代码不读它们,多半是删掉的功能留下的
              </div>
              <div className="mt-1 space-y-0.5">
                {report.orphans.map(o => (
                  <p key={o.rel} className="font-mono text-micro text-muted">
                    {o.rel}{o.is_dir ? '/' : ''} · {(o.bytes / 1024).toFixed(1)} KB
                  </p>
                ))}
              </div>
              <p className="mt-1 text-micro text-muted/70">
                这里<b className="text-secondary">不替你删</b> —— 判断「没人读」靠的是一张手写清单,
                清单漏一项就等于删了你的数据。确认之后自己到 data/user_data 下删。
              </p>
            </div>
          )}
        </div>
      )}
      {/* [v0.3.8 同步上游] 扩展页面插件槽 + 升级保护 (二次开发备份/对比) */}
      <ExtensionSlot name="settings.system.section" context={{}} compact />
      <UpgradeGuardCard />
    </div>
  )
}

// ===== 升级保护 (二次开发) =====
// 用户修改/新增的程序文件在每次启动时备份到 data/upgrade_guard/, 升级不丢;
// 检测到版本变化时给出对比报告: 可恢复项一键还原, 冲突项保留三方材料手工合并。

const UPGRADE_CATEGORY_LABEL: Record<UpgradeGuardCategory, string> = {
  restorable: '可恢复',
  conflict: '需手工合并',
  match: '已一致',
  added_lost: '新增文件可恢复',
}

function UpgradeGuardCard() {
  const qc = useQueryClient()
  const { data: st, isLoading } = useQuery({
    queryKey: ['upgrade-guard', 'status'],
    queryFn: api.upgradeGuardStatus,
    staleTime: 30_000,
    retry: 1,
  })
  const [busy, setBusy] = useState<'scan' | 'restore-all' | string | null>(null)
  const [listOpen, setListOpen] = useState(false)

  const refresh = () => qc.invalidateQueries({ queryKey: ['upgrade-guard', 'status'] })

  const scan = async () => {
    setBusy('scan')
    try {
      await api.upgradeGuardScan()
      await refresh()
    } catch (e: any) {
      toast(`扫描失败: ${e?.message ?? e}`, 'error')
    } finally {
      setBusy(null)
    }
  }

  const restore = async (reportId: string, relpath: string) => {
    setBusy(relpath)
    try {
      await api.upgradeGuardRestore(reportId, relpath)
      toast(`已恢复 ${relpath}`, 'success')
      await refresh()
    } catch (e: any) {
      toast(`恢复失败: ${e?.message ?? e}`, 'error')
    } finally {
      setBusy(null)
    }
  }

  const restoreAll = async (reportId: string, files: { relpath: string }[]) => {
    setBusy('restore-all')
    let ok = 0
    for (const f of files) {
      try {
        await api.upgradeGuardRestore(reportId, f.relpath)
        ok += 1
      } catch { /* 单个失败继续其余 */ }
    }
    toast(`已恢复 ${ok}/${files.length} 个文件`, ok === files.length ? 'success' : 'error')
    await refresh()
    setBusy(null)
  }

  const dismiss = async () => {
    setBusy('dismiss')
    try {
      await api.upgradeGuardDismiss()
      await refresh()
    } finally {
      setBusy(null)
    }
  }

  const report = st?.pending_report ?? null
  const reportFiles = report?.files ?? []
  const restorableFiles = reportFiles.filter(f => f.category === 'restorable' || f.category === 'added_lost')

  return (
    <section className="rounded-card border border-border bg-surface p-5 mt-6">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <ShieldCheck className="h-4 w-4 text-secondary" />
            <h3 className="text-sm font-medium text-foreground">升级保护（二次开发）</h3>
          </div>
          <div className="mt-1.5 text-micro leading-relaxed text-muted">
            {isLoading ? '加载中…' : st?.enabled
              ? <>修改/新增的程序文件每次启动自动备份到 <code className="text-secondary">{st?.backup_dir}</code>，升级不会丢失</>
              : '当前安装未携带版本清单（源码运行）— 请使用 Git 管理二次开发改动，配合 scripts/upgrade_check.py 做升级预检'}
          </div>
        </div>
        {st?.enabled && (
          <div className="flex shrink-0 items-center gap-2">
            <span className="text-micro text-muted">清单 {st?.manifest_version ?? '—'} · 当前 {st?.current_version}</span>
            <button onClick={scan} disabled={busy === 'scan' || !!st?.scanning}
              title="重新扫描程序目录, 刷新常备备份 (修改程序文件后可手动执行)"
              className="inline-flex items-center gap-1.5 rounded-card px-2.5 py-1 text-xs text-secondary transition-colors hover:bg-elevated hover:text-foreground disabled:opacity-50">
              <RefreshCw className={`h-3 w-3 ${busy === 'scan' || st?.scanning ? 'animate-spin' : ''}`} />
              {busy === 'scan' || st?.scanning ? '扫描中' : '重新扫描'}
            </button>
          </div>
        )}
      </div>

      {st?.enabled && (
        <div className="mt-3 border-t border-border/60 pt-3">
          <button onClick={() => setListOpen(v => !v)} className="flex w-full items-center gap-1.5 text-left text-xs text-secondary hover:text-foreground">
            <ChevronDown className={`h-3 w-3 transition-transform ${listOpen ? '' : '-rotate-90'}`} />
            当前检测到 <b className="text-foreground">{st?.modified?.length ?? 0}</b> 个修改文件、<b className="text-foreground">{st?.added?.length ?? 0}</b> 个新增文件
            <span className="text-micro text-muted">（上次扫描 {st?.last_scan?.replace('T', ' ').slice(0, 19) ?? '—'}）</span>
          </button>
          {listOpen && (
            <div className="mt-2 max-h-48 overflow-y-auto rounded-card border border-border/60 bg-base/40 p-2 font-mono text-micro leading-5">
              {st?.modified?.map(f => <div key={f} className="truncate text-warning">✎ {f}</div>)}
              {st?.added?.map(f => <div key={f} className="truncate text-bear">＋ {f}</div>)}
              {(st?.modified?.length ?? 0) + (st?.added?.length ?? 0) === 0 && (
                <div className="text-muted">无二次开发改动</div>
              )}
            </div>
          )}
        </div>
      )}

      {report && (
        <div className="mt-3 rounded-card border border-warning/25 bg-warning/[0.05] p-3">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0 text-xs">
              <div className="font-medium text-foreground">
                升级检测: {report.from_version} → {report.to_version}
              </div>
              <div className="mt-1 text-micro leading-relaxed text-muted">
                你的 {reportFiles.length} 个二次开发文件已归档比对 —
                可恢复 <b className="text-bear">{report.counts.restorable + report.counts.added_lost}</b> ·
                需手工合并 <b className="text-warning">{report.counts.conflict}</b> ·
                已一致 <b className="text-muted">{report.counts.match}</b>
              </div>
            </div>
            <div className="flex shrink-0 gap-2">
              {restorableFiles.length > 0 && (
                <button onClick={() => restoreAll(report.id, restorableFiles)} disabled={!!busy}
                  className="inline-flex items-center gap-1.5 rounded-card bg-accent px-2.5 py-1 text-micro text-on-accent hover:bg-accent/90 disabled:opacity-50">
                  <RotateCcw className="h-3 w-3" />
                  恢复可恢复项 ({restorableFiles.length})
                </button>
              )}
              <button onClick={dismiss} disabled={busy === 'dismiss'}
                className="rounded-card px-2.5 py-1 text-micro text-secondary hover:bg-elevated hover:text-foreground disabled:opacity-50">
                知道了
              </button>
            </div>
          </div>
          <div className="mt-2 max-h-56 overflow-y-auto rounded-btn border border-border/40 bg-base/40 p-2">
            {reportFiles.map(f => (
              <div key={f.relpath} className="flex items-center justify-between gap-2 py-0.5">
                <span className="min-w-0 truncate font-mono text-micro text-secondary" title={f.relpath}>{f.relpath}</span>
                <span className="flex shrink-0 items-center gap-1.5">
                  <span className={`text-micro ${f.category === 'conflict' ? 'text-warning' : f.category === 'match' ? 'text-muted' : 'text-bear'}`}>
                    {UPGRADE_CATEGORY_LABEL[f.category]}
                  </span>
                  {(f.category === 'restorable' || f.category === 'added_lost') && (
                    <button onClick={() => restore(report.id, f.relpath)} disabled={busy === f.relpath}
                      className="rounded-btn px-1.5 py-0.5 text-micro text-accent hover:bg-accent/10 disabled:opacity-50">
                      {busy === f.relpath ? '恢复中' : '恢复'}
                    </button>
                  )}
                </span>
              </div>
            ))}
          </div>
          {report.counts.conflict > 0 && (
            <div className="mt-2 text-micro leading-relaxed text-muted">
              冲突项不自动合并: 你的版本已归档在 <code>{report.dir}</code>, 磁盘上是新版文件, 请对照手动合并后重新扫描。
            </div>
          )}
        </div>
      )}
    </section>
  )
}


// ===== ToggleRow =====

function BatchSymbolsRow({
  label,
  desc,
  value,
  min,
  max,
  saving,
  onSave,
  warnAt,
  warnText,
  unit = '只/批',
  rangeUnit = '只',
}: {
  label: string
  desc: string
  value: number
  min: number
  max: number
  saving: boolean
  onSave: (size: number) => void
  warnAt: number
  warnText: string
  /** [R589] 值药丸的单位后缀; 默认「只/批」, 回测内存等场景传 'GiB' */
  unit?: string
  /** [R589] 范围提示「可设 min–max …」的单位后缀 */
  rangeUnit?: string
}) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(String(value))
  const [hint, setHint] = useState<string | null>(null)

  useEffect(() => {
    if (!editing) setDraft(String(value))
  }, [value, editing])

  function commit() {
    const raw = Number.parseInt(draft, 10)
    if (!Number.isFinite(raw)) {
      setHint(`请输入 ${min}–${max} 之间的整数`)
      return
    }
    if (raw < min) { setHint(`已按最小值 ${min} 保存`); onSave(min); setEditing(false); return }
    if (raw > max) { setHint(`已按上限 ${max} 保存`); onSave(max); setEditing(false); return }
    setHint(null)
    onSave(raw)
    setEditing(false)
  }

  const overWarn = (Number.parseInt(draft, 10) || 0) >= warnAt

  return (
    <div className="py-2">
      <div className="flex items-center justify-between gap-4">
        <div className="min-w-0">
          <div className="text-sm text-foreground">{label}</div>
          <div className="text-micro text-muted">{desc} · 可设 {min}–{max} {rangeUnit}</div>
        </div>
        {editing ? (
          <div className="flex shrink-0 items-center gap-1.5">
            <input
              type="number"
              value={draft}
              min={min}
              max={max}
              autoFocus
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') commit()
                if (e.key === 'Escape') { setEditing(false); setHint(null) }
              }}
              className="w-24 h-8 px-2 rounded-btn border border-border bg-base text-right font-mono text-xs
                         text-foreground tabular-nums focus:border-accent/50 focus:outline-none"
            />
            <button
              onClick={commit}
              disabled={saving}
              className="px-2.5 py-1.5 rounded-btn text-xs bg-accent/15 text-accent
                         hover:bg-accent/25 transition-colors disabled:opacity-50"
            >
              {saving ? '…' : '保存'}
            </button>
            <button
              onClick={() => { setEditing(false); setHint(null) }}
              className="px-2 py-1.5 rounded-btn text-xs bg-surface border border-border text-foreground hover:text-foreground transition-colors"
            >
              取消
            </button>
          </div>
        ) : (
          <button
            onClick={() => setEditing(true)}
            className="shrink-0 px-2.5 py-1 rounded-btn border border-border bg-surface font-mono text-xs
                       text-foreground tabular-nums hover:border-accent/50 transition-colors"
            title="点击修改"
          >
            {value} {unit}
          </button>
        )}
      </div>
      {hint && <div className="mt-1.5 text-micro text-warning">{hint}</div>}
      {overWarn && editing && (
        <div className="mt-2 rounded-btn border border-warning/20 bg-warning/10 px-3 py-1.5">
          <span className="text-micro leading-relaxed text-warning">{warnText}</span>
        </div>
      )}
    </div>
  )
}


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
        <div className="text-xs text-muted truncate">{desc}</div>
      </div>
      <Switch checked={checked} disabled={disabled} onChange={onChange} label={label} />
    </div>
  )
}
