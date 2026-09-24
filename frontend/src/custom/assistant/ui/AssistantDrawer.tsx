/**
 * AI 助手面板 — 嵌在 Minds 页「对话」一栏里(经 `minds.chat` 插槽), 占满那一栏。
 *
 * [R502 · fork] 原来是从页面最右缘滑入的非模态抽屉(默认 720px, 左缘拖拽调宽)。
 * 用户: 「系统里面悬浮的那个 ai 助手改造复刻成 minds 的功能, 也做成一个菜单选项在左侧」,
 * 定的是「悬浮按钮去掉, 对话成为 Minds 的第四栏, 原样搬过去」。所以:
 *   · 去掉 portal / 滑入动画 / 拖拽调宽 / 关闭按钮 —— 它现在是页面的一栏, 不是浮层;
 *   · 会话、消息、发送、历史(本地最近 20 个)一个字没动, 仍走 ../store;
 *   · 文件名不改, 方便同步上游时对齐作者的改动。
 * 原来钳制抽屉宽度的 clampWidth(R397)随抽屉一起没了 —— 一栏的宽度由页面版式决定。
 */
import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { AnimatePresence, motion } from 'framer-motion'
import {
  ArrowDown,
  History,
  Plus,
  SendHorizontal,
  Settings2,
  Sparkles,
  Square,
  Trash2,
} from 'lucide-react'
import { cn } from '@/lib/cn'
import {
  fetchAssistantStatus,
  fetchAssistantSuggests,
  type AssistantStatus,
  type QuickSuggest,
} from '../client'
import {
  deleteSession,
  newSession,
  retryLast,
  selectSession,
  sendMessage,
  stopSending,
  useAssistantStore,
} from '../store'
import { AssistantMessageView } from './messages'
import { buttonClass } from '@/components/ui'

const EASE_SMOOTH: [number, number, number, number] = [0.16, 1, 0.3, 1]

type PanelMessages = ReturnType<typeof useAssistantStore>['sessions'][number]['messages']

export function AssistantPanel() {
  const { sending, sessions, activeId } = useAssistantStore()
  const active = sessions.find(s => s.id === activeId) ?? null
  const messages: PanelMessages = active?.messages ?? []
  const [status, setStatus] = useState<AssistantStatus | null>(null)
  const [suggests, setSuggests] = useState<QuickSuggest[]>([])

  useEffect(() => {
    let cancelled = false
    fetchAssistantStatus().then(s => { if (!cancelled) setStatus(s) }).catch(() => {})
    fetchAssistantSuggests().then(list => { if (!cancelled) setSuggests(list) }).catch(() => {})
    return () => { cancelled = true }
  }, [])

  return (
    <section
      className="flex h-full min-h-0 min-w-0 flex-col overflow-hidden rounded-card border border-border bg-surface"
      aria-label="AI 助手"
    >
      <PanelHeader status={status} sessions={sessions} activeId={activeId} sending={sending} />
      <MessageList messages={messages} sending={sending} status={status} suggests={suggests} />
      <InputArea sending={sending} blocked={status ? !status.supports_tools : false} />
    </section>
  )
}

function PanelHeader({
  status,
  sessions,
  activeId,
  sending,
}: {
  status: AssistantStatus | null
  sessions: ReturnType<typeof useAssistantStore>['sessions']
  activeId: string
  sending: boolean
}) {
  const [menuOpen, setMenuOpen] = useState(false)

  return (
    <div className="relative flex h-14 shrink-0 items-center gap-2 border-b border-border px-4">
      <Sparkles className="h-4 w-4 shrink-0 text-accent" />
      <span className="text-sm font-semibold text-foreground">AI 助手</span>
      {status?.model && (
        <span
          className="max-w-36 truncate rounded-btn bg-elevated px-1.5 py-0.5 font-mono text-micro text-muted"
          title={`供应商: ${status.provider}`}
        >
          {status.model}
        </span>
      )}
      <div className="ml-auto flex items-center gap-0.5">
        <div className="relative">
          <IconButton title="历史会话" onClick={() => setMenuOpen(v => !v)} disabled={sending}>
            <History className="h-4 w-4" />
          </IconButton>
          {menuOpen && <SessionMenu sessions={sessions} activeId={activeId} onDone={() => setMenuOpen(false)} />}
        </div>
        <IconButton title="新对话" onClick={() => { newSession(); setMenuOpen(false) }} disabled={sending}>
          <Plus className="h-4 w-4" />
        </IconButton>
      </div>
    </div>
  )
}

function SessionMenu({
  sessions,
  activeId,
  onDone,
}: {
  sessions: ReturnType<typeof useAssistantStore>['sessions']
  activeId: string
  onDone: () => void
}) {
  return (
    <>
      <div className="fixed inset-0 z-[61]" onClick={onDone} />
      <div className="absolute right-0 top-full z-[62] mt-1 max-h-72 w-60 overflow-y-auto rounded-card border border-border bg-surface p-1 shadow-xl">
        {sessions.length === 0 && (
          <div className="px-2 py-1.5 text-xs text-muted">暂无历史会话</div>
        )}
        {sessions.map(session => (
          <div
            key={session.id}
            className={cn(
              'group flex items-center gap-1 rounded-btn px-2 py-1.5 text-xs transition-colors duration-150 ease-smooth',
              session.id === activeId ? 'bg-elevated text-foreground' : 'text-secondary hover:bg-elevated/60 hover:text-foreground',
            )}
          >
            <button
              type="button"
              className="min-w-0 flex-1 cursor-pointer truncate text-left"
              onClick={() => { selectSession(session.id); onDone() }}
              title={session.title}
            >
              {session.title || '新对话'}
            </button>
            <button
              type="button"
              className="hidden cursor-pointer text-muted transition-colors duration-150 ease-smooth hover:text-danger group-hover:block"
              onClick={() => deleteSession(session.id)}
              title="删除会话"
            >
              <Trash2 className="h-3.5 w-3.5" />
            </button>
          </div>
        ))}
      </div>
    </>
  )
}

function IconButton({
  title,
  onClick,
  disabled,
  children,
}: {
  title: string
  onClick: () => void
  disabled?: boolean
  children: React.ReactNode
}) {
  return (
    <button
      type="button"
      title={title}
      aria-label={title}
      disabled={disabled}
      onClick={onClick}
      className="flex h-8 w-8 cursor-pointer items-center justify-center rounded-btn text-secondary transition-colors duration-150 ease-smooth hover:bg-elevated hover:text-foreground disabled:cursor-not-allowed disabled:opacity-40"
    >
      {children}
    </button>
  )
}

function MessageList({
  messages,
  sending,
  status,
  suggests,
}: {
  messages: PanelMessages
  sending: boolean
  status: AssistantStatus | null
  suggests: QuickSuggest[]
}) {
  const scrollRef = useRef<HTMLDivElement>(null)
  const pinnedRef = useRef(true)
  const [showJump, setShowJump] = useState(false)

  useLayoutEffect(() => {
    const el = scrollRef.current
    if (el && pinnedRef.current) el.scrollTop = el.scrollHeight
  }, [messages])

  const onScroll = () => {
    const el = scrollRef.current
    if (!el) return
    const distance = el.scrollHeight - el.scrollTop - el.clientHeight
    pinnedRef.current = distance < 80
    setShowJump(distance >= 240)
  }

  const jumpToBottom = () => {
    const el = scrollRef.current
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' })
  }

  return (
    <div className="relative min-h-0 flex-1">
      <div ref={scrollRef} onScroll={onScroll} className="h-full space-y-4 overflow-y-auto px-5 py-4">
        {messages.length === 0 ? (
          <EmptyState status={status} suggests={suggests} />
        ) : (
          messages.map(message => (
            <AssistantMessageView key={message.id} message={message} onRetry={sending ? undefined : retryLast} />
          ))
        )}
      </div>
      <AnimatePresence>
        {showJump && (
          <motion.button
            type="button"
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 4 }}
            transition={{ duration: 0.15, ease: EASE_SMOOTH }}
            onClick={jumpToBottom}
            className="absolute bottom-3 left-1/2 flex h-7 w-7 -translate-x-1/2 cursor-pointer items-center justify-center rounded-full border border-border bg-elevated text-secondary shadow-md transition-colors duration-150 ease-smooth hover:text-foreground"
            title="回到底部"
          >
            <ArrowDown className="h-3.5 w-3.5" />
          </motion.button>
        )}
      </AnimatePresence>
    </div>
  )
}

function EmptyState({ status, suggests }: { status: AssistantStatus | null; suggests: QuickSuggest[] }) {
  const navigate = useNavigate()

  if (status && !status.configured) {
    return (
      <div className="rounded-card border border-warning/30 bg-warning/5 p-4 text-sm">
        <div className="flex items-center gap-1.5 font-medium text-warning">
          <Settings2 className="h-4 w-4" />
          AI 未配置
        </div>
        <p className="mt-1.5 text-secondary">AI 助手需要先配置 AI 供应商和 API Key 才能对话。</p>
        <button
          type="button"
          onClick={() => navigate('/settings?tab=ai')}
          className={buttonClass({ variant: 'primary' }, 'mt-2')}
        >
          去设置页配置
        </button>
      </div>
    )
  }

  if (status && !status.supports_tools) {
    return (
      <div className="rounded-card border border-warning/30 bg-warning/5 p-4 text-sm">
        <div className="flex items-center gap-1.5 font-medium text-warning">
          <Settings2 className="h-4 w-4" />
          当前供应商不支持工具调用
        </div>
        <p className="mt-1.5 text-secondary">
          AI 助手依赖工具调用能力({status.provider} 不支持), 请在设置页切换为 OpenAI 兼容模型。
        </p>
        <button
          type="button"
          onClick={() => navigate('/settings?tab=ai')}
          className={buttonClass({ variant: 'primary' }, 'mt-2')}
        >
          去设置页调整
        </button>
      </div>
    )
  }

  if (!suggests.length) {
    return <p className="pt-8 text-center text-xs text-muted">问我任何关于策略、因子、回测或数据能力的问题。</p>
  }

  return (
    <div className="space-y-3 pt-6">
      <p className="text-center text-xs text-muted">试试这些:</p>
      <div className="grid grid-cols-1 gap-2">
        {suggests.map(suggest => (
          <button
            key={suggest.id}
            type="button"
            onClick={() => sendMessage(suggest.prompt)}
            className="cursor-pointer rounded-card border border-border bg-base/60 px-3 py-2.5 text-left text-xs text-secondary transition-colors duration-150 ease-smooth hover:border-accent/40 hover:bg-elevated hover:text-foreground"
          >
            {suggest.label}
          </button>
        ))}
      </div>
    </div>
  )
}

function InputArea({ sending, blocked }: { sending: boolean; blocked: boolean }) {
  const [text, setText] = useState('')
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  // [R502] 进到这一栏(含 Ctrl+K 跳过来)就能直接打字 —— 只在有鼠标的设备上:
  // 手机上一聚焦就弹键盘, 把半屏消息顶没了。依赖 location.key: 已经在这一栏时
  // 再按 Ctrl+K 会替换一次历史记录, key 变了就再聚焦一次。
  const { key: locationKey } = useLocation()
  useEffect(() => {
    if (window.matchMedia?.('(pointer: fine)').matches) textareaRef.current?.focus()
  }, [locationKey])

  const canSend = !sending && !blocked && text.trim().length > 0

  const submit = () => {
    if (!canSend) return
    sendMessage(text)
    setText('')
    if (textareaRef.current) textareaRef.current.style.height = 'auto'
  }

  const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault()
      submit()
    }
  }

  const autoGrow = () => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 144)}px`
  }

  return (
    <div className="shrink-0 border-t border-border bg-surface px-4 pb-3 pt-2.5">
      <div className="flex items-end gap-2 rounded-card border border-border bg-base transition-colors duration-150 ease-smooth focus-within:border-accent/70">
        <textarea
          ref={textareaRef}
          value={text}
          rows={1}
          disabled={blocked}
          placeholder={blocked ? '请先在设置页配置 AI' : '提问, Enter 发送 / Shift+Enter 换行'}
          onChange={e => { setText(e.target.value); autoGrow() }}
          onKeyDown={onKeyDown}
          // [R502] 焦点由外框 focus-within 标出; 自动聚焦时全局焦点环再画一圈就成了框中框
          className="focus-ring-custom max-h-36 min-h-[38px] flex-1 resize-none bg-transparent px-3 py-2 text-sm text-foreground outline-none placeholder:text-muted disabled:cursor-not-allowed"
        />
        {sending ? (
          <button
            type="button"
            onClick={stopSending}
            title="停止生成"
            aria-label="停止生成"
            className="mr-1.5 mb-1.5 flex h-8 w-8 cursor-pointer items-center justify-center rounded-btn bg-elevated text-secondary transition-colors duration-150 ease-smooth hover:text-foreground"
          >
            <Square className="h-3.5 w-3.5 fill-current" />
          </button>
        ) : (
          <button
            type="button"
            onClick={submit}
            disabled={!canSend}
            title="发送"
            aria-label="发送"
            className={buttonClass({ variant: 'primary', icon: true }, 'mr-1.5 mb-1.5')}
          >
            <SendHorizontal className="h-4 w-4" />
          </button>
        )}
      </div>
      <div className="mt-1.5 px-1 text-micro text-muted">
        {/* 手机上没有键盘快捷键可言, 那半句只在宽屏出 */}
        <span className="hidden sm:inline">⌘K / Ctrl+K 从任何页面跳到这里 · </span>回答基于本地数据, 不构成投资建议
      </div>
    </div>
  )
}
