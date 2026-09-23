import { useState, useEffect, useRef, createContext, useContext } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Save, Loader2, Check, Wifi, WifiOff, Eye, EyeOff, Shield,
  Shuffle, Plug, Settings2, Trash2,
} from 'lucide-react'
import { useSettings } from '@/lib/useSharedQueries'
import { api, type SettingsState } from '@/lib/api'
import { QK } from '@/lib/queryKeys'
import { AiProfiles } from '@/pages/settings/AiProfiles'
import { useCardFlash, cardFlashCls } from '@/lib/useCardFlash'
import { buttonClass, TYPE } from '@/components/ui'
import { cn } from '@/lib/cn'

// 统一的输入框样式(与项目其他设置页一致)
const INPUT_CLS =
  'w-full h-9 px-2.5 rounded-btn bg-base border-0 ring-1 ring-border/30 text-xs font-mono text-foreground placeholder:text-muted/30 focus:outline-none focus:ring-2 focus:ring-accent/30 transition-shadow'

// 空/非法输入 → undefined (后端保持原值), 合法正整数 → int
const toPositiveInt = (v: string) => {
  const n = parseInt(v, 10)
  return Number.isInteger(n) && n > 0 ? n : undefined
}

const CODEX_PROVIDER = 'codex_cli'
const OPENAI_PROVIDER = 'openai'
const OPENAI_COMPAT_PROVIDER = 'openai_compat'
const CODEX_COMMAND = 'codex'
const DEFAULT_CODEX_MODEL = 'gpt-5.6-sol'
const DEFAULT_OPENAI_MODEL = 'gpt-5.5'
const DEFAULT_REASONING_EFFORT = 'high'
const SAVED_CODEX_OPTION_VALUE = '__saved_codex_config__'
const CODEX_REASONING_LABELS: Record<string, string> = {
  high: '高',
  xhigh: '极高',
}

type CodexModelOption = { label: string; value: string; model: string; effort: string; hint: string }

const CODEX_MODEL_OPTIONS: CodexModelOption[] = [
  { label: 'GPT-5.6 Sol · 极高（推荐）', value: 'gpt-5.6-sol:xhigh', model: 'gpt-5.6-sol', effort: 'xhigh', hint: '旗舰档，适合复杂金融分析与专业任务' },
  { label: 'GPT-5.6 Terra · 极高', value: 'gpt-5.6-terra:xhigh', model: 'gpt-5.6-terra', effort: 'xhigh', hint: '平衡智能、速度与使用成本' },
  { label: 'GPT-5.6 Luna · 极高', value: 'gpt-5.6-luna:xhigh', model: 'gpt-5.6-luna', effort: 'xhigh', hint: '适合成本敏感与高频分析任务' },
  { label: 'gpt-5.5 · 高', value: 'gpt-5.5:high', model: 'gpt-5.5', effort: 'high', hint: '使用 gpt-5.5 + high 推理档' },
  { label: 'gpt-5.5 · 极高', value: 'gpt-5.5:xhigh', model: 'gpt-5.5', effort: 'xhigh', hint: '使用 gpt-5.5 + xhigh 推理档' },
  { label: '跟随本机 Codex 默认', value: '', model: '', effort: '', hint: '使用本机 Codex CLI 配置的默认模型与推理强度' },
]

const codexModelLabel = (model?: string, effort?: string) => {
  if (!model && !effort) return '默认模型'
  const modelLabel = model || '默认模型'
  const effortLabel = effort ? CODEX_REASONING_LABELS[effort] ?? effort : ''
  return effortLabel ? `${modelLabel} · ${effortLabel}` : modelLabel
}

type AiPreset = { label: string; provider?: string; url: string; model: string; codexCommand?: string; website: string; websiteLabel: string; description: string; custom?: boolean }

const PRESETS: AiPreset[] = [
  { label: '自定义', url: '', model: '', website: '', websiteLabel: '', description: '不自动填充任何配置，完全手动填写 API 地址、模型和密钥。', custom: true },
  { label: 'OpenAI', provider: OPENAI_PROVIDER, url: 'https://api.openai.com/v1', model: DEFAULT_OPENAI_MODEL, website: 'https://platform.openai.com/', websiteLabel: 'platform.openai.com', description: 'OpenAI 官方接口，可单独配置模型支持的推理强度。' },
  { label: 'DeepSeek', url: 'https://api.deepseek.com', model: 'deepseek-v4-pro', website: 'https://www.deepseek.com/', websiteLabel: 'deepseek.com', description: 'DeepSeek 官方 OpenAI 兼容接口。' },
  { label: '通义千问', url: 'https://dashscope.aliyuncs.com/compatible-mode/v1', model: 'qwen-3.6plus', website: 'https://tongyi.aliyun.com/', websiteLabel: 'tongyi.aliyun.com', description: '阿里云 DashScope 兼容模式接口。' },
  { label: '智谱 GLM', url: 'https://open.bigmodel.cn/api/paas/v4', model: 'glm-5.2', website: 'https://open.bigmodel.cn/', websiteLabel: 'open.bigmodel.cn', description: '智谱 AI 官方 OpenAI 兼容接口。' },
  { label: 'Kimi', url: 'https://api.moonshot.cn/v1', model: 'kimi-k2.7-code', website: 'https://platform.moonshot.cn/', websiteLabel: 'platform.moonshot.cn', description: '月之暗面 Moonshot 官方 OpenAI 兼容接口，支持超长上下文。' },
  { label: 'Codex CLI', provider: CODEX_PROVIDER, url: '', model: DEFAULT_CODEX_MODEL, codexCommand: CODEX_COMMAND, website: 'https://developers.openai.com/codex/noninteractive', websiteLabel: 'codex exec', description: '调用本机 Codex CLI 的 codex exec, 适合已登录 ChatGPT/Codex 的本地环境。' },
  { label: '炸鸡中转站', url: 'https://api.zhaji.dev/v1', model: 'gpt-5.5', website: 'https://api.zhaji.dev', websiteLabel: 'api.zhaji.dev', description: 'OpenAI 兼容中转服务，适合直接使用国际模型。' },
]

const findPreset = (provider: string, baseUrl: string, codexCommand: string) => PRESETS.find(p => {
  if (p.custom || (p.provider ?? OPENAI_COMPAT_PROVIDER) !== provider) return false
  if (provider === OPENAI_PROVIDER) return true
  return provider === CODEX_PROVIDER ? p.codexCommand === codexCommand : p.url === baseUrl
}) ?? PRESETS[0]

export function SettingsAIPanel({ highlight }: { highlight?: string } = {}) {
  const qc = useQueryClient()
  const settings = useSettings()
  const s = settings.data

  const [provider, setProvider] = useState(OPENAI_COMPAT_PROVIDER)
  const [baseUrl, setBaseUrl] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [model, setModel] = useState('')
  const [reasoningEffort, setReasoningEffort] = useState(DEFAULT_REASONING_EFFORT)
  const [codexModel, setCodexModel] = useState('')
  const [codexReasoningEffort, setCodexReasoningEffort] = useState('')
  const [codexCommand, setCodexCommand] = useState(CODEX_COMMAND)
  const [customUa, setCustomUa] = useState(false)
  const [userAgent, setUserAgent] = useState('')
  const [maxOutputTokens, setMaxOutputTokens] = useState('')
  const [contextWindow, setContextWindow] = useState('')
  const [showKey, setShowKey] = useState(false)
  const [saved, setSaved] = useState(false)
  const [confirmClear, setConfirmClear] = useState(false)
  const [testing, setTesting] = useState(false)
  const [testResult, setTestResult] = useState<{ ok: boolean; msg: string } | null>(null)
  const [selectedPresetLabel, setSelectedPresetLabel] = useState(PRESETS[0].label)
  const directDrafts = useRef({
    custom: { baseUrl: '', model: '' },
    openai: { baseUrl: 'https://api.openai.com/v1', model: DEFAULT_OPENAI_MODEL },
  })
  const draftsInitialized = useRef(false)

  // [fork R94] 全系统 AI 统一由「AI 档位」管理: 用户配过档位表(非合成的 legacy 单条)后,
  // 调用链只走档位(第 1 档优先, 用不了自动顺位) —— 下面这张卡里的接口/模型/Key 不再
  // 参与任何调用, 只剩全局参数(UA/输出上限/上下文窗口)仍然全局生效, 界面据此收起。
  const profilesQuery = useQuery({ queryKey: QK.aiProfiles, queryFn: api.aiProfiles })
  const profileRows = profilesQuery.data?.profiles ?? []
  const profilesManaged = profileRows.some(p => !p.synthesized)
  const enabledProfiles = profileRows.filter(p => p.enabled && !p.synthesized)
  const primaryProfile = enabledProfiles[0]

  const isCodexProvider = provider === CODEX_PROVIDER
  const isOpenAIProvider = provider === OPENAI_PROVIDER
  const savedCodexProvider = s?.ai_provider === CODEX_PROVIDER
  const configured = s?.ai_configured ?? (savedCodexProvider ? !!(s?.ai_codex_command ?? CODEX_COMMAND) : s?.has_ai_key)
  const selectedPreset = PRESETS.find(p => p.label === selectedPresetLabel) ?? PRESETS[0]
  // [R62] 标题不再随匹配到的预设变化 —— 预设已经不给选了, 还显示
  // "DeepSeek 配置"会让人以为自己在某个选项里
  const configTitle = profilesManaged
    ? '全局参数(对所有档位生效)'
    : isCodexProvider ? 'Codex CLI 配置' : 'AI 配置(OpenAI 兼容)'
  const savedCodexModel = s?.ai_codex_model ?? (savedCodexProvider ? (s?.ai_model ?? '') : '')
  const savedCodexEffort = s?.ai_codex_reasoning_effort ?? ''
  const savedCodexOptionKnown = CODEX_MODEL_OPTIONS.some(option =>
    option.model === savedCodexModel && option.effort === savedCodexEffort,
  )
  const savedCodexOption: CodexModelOption | null =
    (savedCodexModel || savedCodexEffort) && !savedCodexOptionKnown
      ? {
          label: `${codexModelLabel(savedCodexModel, savedCodexEffort)}（当前配置）`,
          value: SAVED_CODEX_OPTION_VALUE,
          model: savedCodexModel,
          effort: savedCodexEffort,
          hint: '保留项目中已保存的模型与推理档；此兼容项不可编辑',
        }
      : null
  const codexModelOptions = savedCodexOption
    ? [savedCodexOption, ...CODEX_MODEL_OPTIONS]
    : CODEX_MODEL_OPTIONS
  const selectedCodexModelOption = codexModelOptions.find(option =>
    option.model === codexModel && option.effort === codexReasoningEffort,
  ) ?? CODEX_MODEL_OPTIONS[0]
  const codexModelSelectValue = selectedCodexModelOption.value
  // 档位接管时这张卡只存全局参数, 不再要求接口/模型必填
  const canSave = profilesManaged ? true : isCodexProvider ? true : !!baseUrl.trim() && !!model.trim()

  useEffect(() => {
    if (!s) return
    // 未配置过 AI (无 api_key): 字段留空, 默认选中"自定义"预设, 不预填充后端默认值
    const unconfigured = !s.has_ai_key && !s.ai_configured
    const savedProvider = s.ai_provider ?? OPENAI_COMPAT_PROVIDER
    const savedBaseUrl = unconfigured ? '' : (s.ai_base_url ?? '')
    const savedOpenAIModel = unconfigured ? '' : (s.ai_openai_model ?? (savedProvider !== CODEX_PROVIDER ? s.ai_model : '') ?? '')
    const savedPreset = unconfigured ? PRESETS[0] : findPreset(savedProvider, savedBaseUrl, s.ai_codex_command ?? CODEX_COMMAND)
    if (!draftsInitialized.current) {
      const officialOpenAI = PRESETS.find(p => p.provider === OPENAI_PROVIDER)
      if (savedProvider === OPENAI_PROVIDER || (savedProvider === CODEX_PROVIDER && savedBaseUrl === officialOpenAI?.url)) {
        directDrafts.current.openai = { baseUrl: savedBaseUrl, model: savedOpenAIModel }
      } else if (findPreset(OPENAI_COMPAT_PROVIDER, savedBaseUrl, CODEX_COMMAND).custom) {
        directDrafts.current.custom = { baseUrl: savedBaseUrl, model: savedOpenAIModel }
      }
      draftsInitialized.current = true
    }
    setProvider(savedProvider)
    setSelectedPresetLabel(savedPreset.label)
    setBaseUrl(savedBaseUrl)
    setModel(savedOpenAIModel)
    setReasoningEffort(s.ai_reasoning_effort ?? DEFAULT_REASONING_EFFORT)
    setCodexModel(s.ai_codex_model ?? (savedProvider === CODEX_PROVIDER ? s.ai_model : '') ?? '')
    setCodexReasoningEffort(s.ai_codex_reasoning_effort ?? '')
    setCodexCommand(s.ai_codex_command ?? CODEX_COMMAND)
    const ua = s.ai_user_agent ?? ''
    setCustomUa(!!ua)
    setUserAgent(ua)
    setMaxOutputTokens(String(s?.ai_max_output_tokens ?? 8192))
    setContextWindow(String(s?.ai_context_window ?? 64000))
  }, [s])

  const payload = () => ({
    provider,
    base_url: baseUrl,
    api_key: apiKey || undefined,
    model: isCodexProvider ? codexModel : model,
    ...(isOpenAIProvider ? { reasoning_effort: reasoningEffort } : {}),
    codex_command: isCodexProvider ? CODEX_COMMAND : codexCommand,
    codex_reasoning_effort: isCodexProvider ? codexReasoningEffort : '',
    user_agent: customUa ? userAgent : '',
    max_output_tokens: toPositiveInt(maxOutputTokens),
    context_window: toPositiveInt(contextWindow),
  })

  const save = useMutation({
    mutationFn: () => api.saveAiSettings(payload()),
    onSuccess: (result) => {
      setSaved(true)
      setApiKey('')
      qc.setQueryData<SettingsState>(QK.settings, prev => prev ? {
        ...prev,
        ai_provider: result.ai_provider ?? provider,
        ai_base_url: baseUrl,
        ai_model: result.ai_model ?? (isCodexProvider ? codexModel : model),
        ai_openai_model: result.ai_openai_model ?? model,
        ai_reasoning_effort: result.ai_reasoning_effort ?? reasoningEffort,
        ai_codex_model: result.ai_codex_model ?? codexModel,
        ai_codex_command: result.ai_codex_command ?? (isCodexProvider ? CODEX_COMMAND : codexCommand),
        ai_codex_reasoning_effort: result.ai_codex_reasoning_effort ?? (isCodexProvider ? codexReasoningEffort : ''),
        ai_configured: result.ai_configured ?? (isCodexProvider ? true : (apiKey ? true : prev.ai_configured)),
        ai_max_output_tokens: result.ai_max_output_tokens ?? toPositiveInt(maxOutputTokens),
        ai_context_window: result.ai_context_window ?? toPositiveInt(contextWindow),
        ...(apiKey ? {
          has_ai_key: true,
          ai_api_key_masked: `${apiKey.slice(0, 4)}......${apiKey.slice(-4)}`,
        } : {}),
      } : prev)
      qc.invalidateQueries({ queryKey: QK.settings })
      setTimeout(() => setSaved(false), 2000)
    },
  })

  const clear = useMutation({
    mutationFn: () => api.clearAiSettings(),
    onSuccess: () => {
      setConfirmClear(false)
      setProvider(OPENAI_COMPAT_PROVIDER)
      setSelectedPresetLabel(PRESETS[0].label)
      setBaseUrl('')
      setApiKey('')
      setModel('')
      setReasoningEffort(DEFAULT_REASONING_EFFORT)
      setCodexModel('')
      setCodexReasoningEffort('')
      setCodexCommand(CODEX_COMMAND)
      directDrafts.current = {
        custom: { baseUrl: '', model: '' },
        openai: { baseUrl: 'https://api.openai.com/v1', model: DEFAULT_OPENAI_MODEL },
      }
      setMaxOutputTokens('8192')
      setContextWindow('64000')
      setTestResult(null)
      qc.setQueryData<SettingsState>(QK.settings, prev => prev ? {
        ...prev,
        ai_provider: OPENAI_COMPAT_PROVIDER,
        ai_base_url: '',
        ai_model: '',
        ai_openai_model: '',
        ai_reasoning_effort: DEFAULT_REASONING_EFFORT,
        ai_codex_model: '',
        ai_codex_command: CODEX_COMMAND,
        ai_codex_reasoning_effort: '',
        ai_max_output_tokens: 8192,
        ai_context_window: 64000,
        has_ai_key: false,
        ai_configured: false,
        ai_api_key_masked: '',
      } : prev)
      qc.invalidateQueries({ queryKey: QK.settings })
    },
  })

  const genRandomUa = () => {
    const major = 128 + Math.floor(Math.random() * 8)
    const platforms = [
      'Windows NT 10.0; Win64; x64',
      'Macintosh; Intel Mac OS X 10_15_7',
      'X11; Linux x86_64',
    ]
    const pf = platforms[Math.floor(Math.random() * platforms.length)]
    setUserAgent(`Mozilla/5.0 (${pf}) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/${major}.0.0.0 Safari/537.36`)
  }


  const handleBaseUrlChange = (value: string) => {
    setBaseUrl(value)
    if (selectedPreset.custom) directDrafts.current.custom.baseUrl = value
    if (isOpenAIProvider) directDrafts.current.openai.baseUrl = value
  }

  const handleModelChange = (value: string) => {
    setModel(value)
    if (selectedPreset.custom) directDrafts.current.custom.model = value
    if (isOpenAIProvider) directDrafts.current.openai.model = value
  }

  const handleTest = async () => {
    setTesting(true)
    setTestResult(null)
    try {
      // 档位接管时测试的是档位链本身, 不该顺手把旧单档配置写回去
      if (canSave && !profilesManaged) await api.saveAiSettings(payload())
      const r = await api.strategyAiTest()
      setTestResult({ ok: r.ok, msg: r.ok ? `连通成功 · ${r.model ?? provider}` : (r.error ?? '未知错误') })
    } catch (e: any) {
      setTestResult({ ok: false, msg: String(e?.message ?? '测试失败') })
    } finally {
      setTesting(false)
    }
  }

  // 自定义 UA 块 —— 未接管时嵌在单档配置里, 档位接管后单独作为全局参数出现
  const uaBlock = (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <Field label="自定义 User-Agent" inline>
          <Toggle checked={customUa} onChange={() => setCustomUa(v => !v)} />
        </Field>
      </div>
      {customUa && (
        <div className="flex gap-2">
          <input type="text" value={userAgent} onChange={e => setUserAgent(e.target.value)} placeholder="粘贴浏览器 User-Agent" className={`${INPUT_CLS} flex-1`} />
          <button type="button" onClick={genRandomUa} title="随机生成浏览器 User-Agent" className="h-9 px-2.5 rounded-btn border border-border/50 text-xs text-secondary hover:text-accent hover:border-accent/30 transition-ui flex items-center gap-1.5 shrink-0">
            <Shuffle className="h-3 w-3" /> 随机
          </button>
        </div>
      )}
    </div>
  )

  return (
    <HighlightContext.Provider value={highlight ?? ''}>
    <div className="space-y-5 max-w-2xl">
      {/* [R56] 多档兜底放最上 —— 这是"AI 能不能一直用得上"的那一层。
          [R94] 配过档位表后它就是全系统 AI 的唯一配置入口: 下面那张卡收起
          接口/模型/Key, 只剩全局参数。没配过档位的老用户看到的仍是单档配置
          (它会被合成为兜底链的唯一一档), 行为不变。 */}
      <AiProfiles />
      <Card icon={Plug} title="连接状态" anchor="ai-connection" right={
        (profilesManaged ? enabledProfiles.length > 0 : configured) && (
          <button onClick={handleTest} disabled={testing}
            className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-btn bg-elevated hover:bg-elevated/80 text-xs text-secondary transition-colors duration-hover ease-smooth disabled:opacity-50">
            {testing ? <Loader2 className="h-3 w-3 animate-spin" /> : <Wifi className="h-3 w-3" />}
            {testing ? '测试中' : '测试'}
          </button>
        )
      }>
        <div className="flex items-center gap-3">
          <div className={`w-9 h-9 rounded-btn flex items-center justify-center shrink-0 ${(profilesManaged ? enabledProfiles.length > 0 : configured) ? 'bg-bear/10 text-bear' : 'bg-warning/10 text-warning'}`}>
            {(profilesManaged ? enabledProfiles.length > 0 : configured) ? <Wifi className="h-4.5 w-4.5" /> : <WifiOff className="h-4.5 w-4.5" />}
          </div>
          <div className="min-w-0">
            <div className="text-sm font-medium text-foreground">
              {profilesManaged
                ? (enabledProfiles.length > 0 ? 'AI 已连接 · 档位统一管理' : 'AI 档位全部停用')
                : configured ? 'AI 已连接' : 'AI 未配置'}
            </div>
            <div className="text-xs text-muted mt-0.5 truncate">
              {profilesManaged
                ? (primaryProfile
                  ? `首选 ${primaryProfile.label || primaryProfile.model}${enabledProfiles.length > 1 ? ` · 共 ${enabledProfiles.length} 档自动兜底` : ''}`
                  : '在上方档位表里至少启用一档')
                : configured
                ? (savedCodexProvider
                  ? `${s?.ai_codex_command ?? CODEX_COMMAND} · ${codexModelLabel(s?.ai_model, s?.ai_codex_reasoning_effort)}`
                  : `${s?.ai_model} · ${s?.ai_api_key_masked}`)
                : (isCodexProvider ? '使用本机 codex exec, 此处无需填写 API Key。' : '配置 API Key 后即可使用 AI 功能。')}
            </div>
          </div>
        </div>
        {testResult && (
          <div className={`mt-3 rounded-btn border px-3 py-2 text-xs flex items-center gap-2 ${testResult.ok ? 'border-bear/20 bg-bear/[0.04] text-bear' : 'border-danger/20 bg-danger/[0.04] text-danger'}`}>
            <div className={`w-1.5 h-1.5 rounded-full shrink-0 ${testResult.ok ? 'bg-bear' : 'bg-danger'}`} />
            {testResult.msg}
          </div>
        )}
      </Card>

      {/* [R62] 「快速预设」整块去掉 —— 用户明确不要这种挑选:
          那种清单只在你正好用清单里那几家时省事, 否则先得挑一个再把三个字段
          全改掉, 比直接填还多两步; 而且它会过期(模型名换代、中转站换域名),
          过期的预设比没有预设更误事。一律按 OpenAI 兼容接口走, 地址/密钥/模型
          三样自己填。 */}
      <Card
        icon={Settings2}
        title={configTitle}
        right={profilesManaged ? undefined : (
          <span className="inline-flex items-center gap-1.5 text-micro text-muted/60" title={isCodexProvider ? 'Use local Codex CLI via codex exec' : 'Use OpenAI-compatible Chat Completions API'}>
            <span className="rounded-btn border border-border/40 bg-base/50 px-1.5 py-px font-mono">{isCodexProvider ? 'codex exec' : 'Chat Completions'}</span>
            {isCodexProvider ? 'CLI' : '接口'}
          </span>
        )}
      >
        <div className="space-y-4">
          {profilesManaged ? (
            <>
              <div className="rounded-btn border border-accent/15 bg-accent/[0.03] px-3 py-2.5 text-xs leading-relaxed text-secondary">
                接口地址、模型与 API Key 已统一由上方「AI 档位」表管理: 全系统默认用第 1 档,
                这一档服务不了时自动顺位切换。此处只保留对所有档位生效的全局参数。
              </div>
              {uaBlock}
            </>
          ) : isCodexProvider ? (
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <Field label="CLI 命令" hint="固定使用默认 codex 命令, 由后端自动解析本机 Codex Desktop/CLI, 不支持自定义可执行路径。">
                <div className={`${INPUT_CLS} flex items-center text-muted/80 select-none`} aria-label="Codex CLI command">
                  {CODEX_COMMAND}
                </div>
              </Field>
              <Field
                label="模型 / 推理档"
                hint={selectedCodexModelOption.hint}
              >
                <select
                  value={codexModelSelectValue}
                  onChange={e => {
                    const value = e.target.value
                    const option = codexModelOptions.find(item => item.value === value) ?? CODEX_MODEL_OPTIONS[0]
                    setCodexModel(option.model)
                    setCodexReasoningEffort(option.effort)
                  }}
                  className={INPUT_CLS}
                >
                  {codexModelOptions.map(option => (
                    <option key={option.value || 'codex-local-default'} value={option.value}>{option.label}</option>
                  ))}
                </select>
              </Field>
            </div>
          ) : (
            <>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <Field label="API 地址">
                  <input type="text" value={baseUrl} onChange={e => handleBaseUrlChange(e.target.value)} placeholder="https://api.zhaji.dev/v1" className={INPUT_CLS} />
                </Field>
                <Field label="模型">
                  <input type="text" value={model} onChange={e => handleModelChange(e.target.value)} placeholder="gpt-5.6-sol" className={INPUT_CLS} />
                </Field>
              </div>

              {isOpenAIProvider && (
                <div className="rounded-btn border border-accent/15 bg-accent/[0.03] p-3">
                  <div className="mb-2.5">
                    <span className="rounded-btn bg-accent/10 px-2 py-0.5 text-micro font-medium text-accent">OpenAI 专属</span>
                  </div>
                  <div className="max-w-xs">
                    <Field label="推理强度">
                      <input type="text" value={reasoningEffort} onChange={e => setReasoningEffort(e.target.value)} placeholder={DEFAULT_REASONING_EFFORT} className={INPUT_CLS} />
                    </Field>
                  </div>
                </div>
              )}

              <Field label="API Key">
                <div className="flex gap-2">
                  <div className="flex-1 relative">
                    <input type={showKey ? 'text' : 'password'} value={apiKey} onChange={e => setApiKey(e.target.value)} placeholder={configured ? `${s?.ai_api_key_masked} · 留空不修改` : 'sk-...'} className={`${INPUT_CLS} pr-9`} />
                    <button onClick={() => setShowKey(v => !v)} className="absolute right-2 top-1/2 -translate-y-1/2 text-muted/40 hover:text-muted" tabIndex={-1} aria-label={showKey ? '隐藏' : '显示'}>
                      {showKey ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
                    </button>
                  </div>
                  <button onClick={handleTest} disabled={testing || !apiKey} className="h-9 px-3 rounded-btn border border-border/50 text-xs text-secondary hover:text-accent hover:border-accent/30 disabled:opacity-40 transition-ui flex items-center gap-1.5 shrink-0">
                    {testing ? <Loader2 className="h-3 w-3 animate-spin" /> : <Wifi className="h-3 w-3" />}
                    测试
                  </button>
                </div>
              </Field>

              <div className="border-t border-border/20" />

              {uaBlock}
            </>
          )}

          <div className="border-t border-border/20 pt-4">
            <div className="grid grid-cols-2 gap-4">
              <Field label="输出上限 max_tokens" hint="所有 AI 任务的输出 token 上限, 任务请求会被钳制到此值; 默认 8192">
                <input type="number" min={1} value={maxOutputTokens} onChange={e => setMaxOutputTokens(e.target.value)} placeholder="8192" className={INPUT_CLS} />
              </Field>
              <Field label="上下文窗口 (输入上限)" hint="输入估算超出此窗口时会报错并提示调大; 默认 64000">
                <input type="number" min={1} value={contextWindow} onChange={e => setContextWindow(e.target.value)} placeholder="64000" className={INPUT_CLS} />
              </Field>
            </div>
          </div>
        </div>
      </Card>

      <div className="rounded-card border border-warning/20 bg-warning/[0.04] px-4 py-3 flex items-start gap-3">
        <Shield className="h-4 w-4 text-warning/70 mt-0.5 shrink-0" />
        <div className="text-xs text-warning/70 leading-relaxed">
          {isCodexProvider
            ? 'Codex CLI 模式会复用本机已登录的 Codex 账户, 个股、财务、复盘等分析上下文会发送给 OpenAI/Codex。保存即表示确认仅在本机或可信内网使用。'
            : 'API Key 仅保存在本机项目文件中, 不会上传到任何服务器。请妥善保管。'}
        </div>
      </div>

      <div className="flex gap-2">
        <button onClick={() => save.mutate()} disabled={save.isPending || !canSave} className={buttonClass({ variant: 'primary' }, 'flex-1 justify-center gap-2')}>
          {save.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : saved ? <Check className="h-4 w-4" /> : <Save className="h-4 w-4" />}
          {save.isPending ? '保存中...' : saved ? '已保存' : '保存配置'}
        </button>
        {configured && !profilesManaged && (
          <button onClick={() => setConfirmClear(true)} disabled={clear.isPending} className="h-10 px-4 rounded-btn bg-elevated text-secondary hover:text-danger text-sm flex items-center justify-center gap-1.5 hover:bg-elevated/80 disabled:opacity-50 transition-ui shrink-0" title="Clear AI provider configuration">
            <Trash2 className="h-4 w-4" />
            清空
          </button>
        )}
      </div>

      {confirmClear && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={() => setConfirmClear(false)} />
          <div className="relative w-[90vw] max-w-[380px] rounded-card border border-border bg-base shadow-2xl p-6">
            <h3 className={cn(TYPE.section, 'mb-2')}>清空 AI 配置</h3>
            <p className="text-xs text-secondary mb-5 leading-relaxed">
              这会清空已保存的 provider、API Key、API 地址、模型和 Codex CLI 命令。之后可以重新配置。
            </p>
            <div className="flex items-center justify-end gap-2">
              <button onClick={() => setConfirmClear(false)} className="px-3 py-1.5 rounded-btn bg-elevated text-secondary hover:bg-elevated/80 text-sm transition-colors">
                取消
              </button>
              <button onClick={() => clear.mutate()} disabled={clear.isPending} className="px-3 py-1.5 rounded-btn bg-danger/15 text-danger hover:bg-danger/25 text-sm font-medium transition-colors disabled:opacity-50">
                {clear.isPending ? '清空中...' : '确认'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
    </HighlightContext.Provider>
  )
}

// ===== 通用卡片(与 Keys 页风格统一) =====

// 卡片定位锚点: highlight=<anchor> 时滚动到视口中央并闪烁 (见 useCardFlash)
const HighlightContext = createContext('')

interface CardProps {
  icon: React.ComponentType<{ className?: string }>
  title: string
  right?: React.ReactNode
  children: React.ReactNode
  anchor?: string
}

function Card({ icon: Icon, title, right, children, anchor }: CardProps) {
  const highlight = useContext(HighlightContext)
  const { ref, flash } = useCardFlash(anchor ? highlight : undefined, anchor ?? '')
  const inner = (
    <section className="rounded-card border border-border bg-surface p-5">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2.5">
          <Icon className="h-4 w-4 text-secondary" />
          <h2 className={TYPE.card}>{title}</h2>
        </div>
        {right}
      </div>
      {children}
    </section>
  )
  if (!anchor) return inner
  return (
    <div ref={ref} id={anchor} className={cardFlashCls(flash)}>
      {inner}
    </div>
  )
}

// ===== 表单字段(统一 label + 输入框样式) =====

function Field({ label, hint, inline, children }: {
  label: string
  hint?: string
  inline?: boolean
  children: React.ReactNode
}) {
  if (inline) {
    return (
      <div className="flex items-center justify-between gap-3">
        <div>
          <div className="text-micro text-muted/50 uppercase tracking-wider">{label}</div>
          {hint && <div className="text-micro text-muted mt-0.5">{hint}</div>}
        </div>
        {children}
      </div>
    )
  }
  return (
    <div className="space-y-1.5">
      <div className="text-micro text-muted/50 uppercase tracking-wider">{label}</div>
      {children}
      {hint && <div className="text-micro text-muted">{hint}</div>}
    </div>
  )
}

// ===== 开关 =====

function Toggle({ checked, onChange }: { checked: boolean; onChange: () => void }) {
  return (
    <button
      type="button"
      onClick={onChange}
      className={`tap-target relative inline-flex h-5 w-9 items-center rounded-full shrink-0 transition-colors duration-expand ${checked ? 'bg-accent' : 'bg-elevated'}`}
      aria-pressed={checked}
    >
      <span className={`inline-block h-3.5 w-3.5 rounded-full bg-white shadow-sm transition-transform duration-expand ${checked ? 'translate-x-[18px]' : 'translate-x-[3px]'}`} />
    </button>
  )
}
