/**
 * 全局 toast。**调用方式没变**: `toast(msg)` 报错, `toast(msg, 'success')` 报成功;
 * [R322] 多了一档 `'info'`, 给"既不是成功也不是失败, 只是告诉你一声"的场合。
 *
 * [R322] 分级 —— 全仓库 247 处调用, 原来不分轻重: 成功与失败一样大的色块、一样的
 * 4 秒、一样叠着往上长, 于是重要的被淹在「已保存」里。改的是**容器不是调用点**:
 *
 *   · 失败要人动手, 停 6 秒、亮色条、能点掉; 成功只是回执, 2 秒多一点就走;
 *   · 同一句话不叠 —— 连点三下「保存」只留一张卡, 计时重来;
 *   · 最多同时 4 张, 再来就挤掉最旧的 —— 一屏十张 toast 等于一张都没有;
 *   · 退场不再硬切: 淡出 + 下沉, 比入场更快(emil-design-eng: exit 快于 enter)。
 *
 * 动效走 CSS transition 而不是 keyframes —— toast 会被连着触发, keyframes 每次从
 * 零开始, transition 能接着走。「减少动态效果」由 index.css 的全局规则接管。
 */
import { useCallback, useEffect, useState } from 'react'
import { AlertCircle, CheckCircle2, Info, X } from 'lucide-react'
import { cn } from '@/lib/cn'

export type ToastKind = 'error' | 'success' | 'info'
type ToastItem = { id: number; msg: string; kind: ToastKind; leaving: boolean }

/** 各档停留时长 —— 失败要读、要决定做什么; 成功只是回执。 */
export const TOAST_MS: Record<ToastKind, number> = { error: 6000, success: 2200, info: 3500 }
/** 同时最多几张; 超过就挤掉最旧的。 */
export const TOAST_MAX = 4
/** 退场过渡时长, 与下面 `duration-hover`(150ms) 一致 —— 过渡走完再从队列里摘掉。 */
const EXIT_MS = 150

let _id = 0
const _listeners: Set<(items: ToastItem[]) => void> = new Set()
let _queue: ToastItem[] = []
const _timers = new Map<number, ReturnType<typeof setTimeout>>()

function _emit() { _listeners.forEach(fn => fn([..._queue])) }

function _arm(item: ToastItem) {
  const old = _timers.get(item.id)
  if (old) clearTimeout(old)
  _timers.set(item.id, setTimeout(() => dismiss(item.id), TOAST_MS[item.kind]))
}

/** 关掉一张: 先标 leaving 让它淡出, 过渡走完再摘。 */
export function dismiss(id: number) {
  const t = _timers.get(id)
  if (t) { clearTimeout(t); _timers.delete(id) }
  const item = _queue.find(x => x.id === id)
  if (!item || item.leaving) return
  item.leaving = true
  _emit()
  setTimeout(() => { _queue = _queue.filter(x => x.id !== id); _emit() }, EXIT_MS)
}

function toast(msg: string, kind: ToastKind = 'error') {
  // 同一句话已经在屏上: 不叠, 计时重来。
  const dup = _queue.find(x => x.msg === msg && x.kind === kind && !x.leaving)
  if (dup) { _arm(dup); return }
  const item: ToastItem = { id: ++_id, msg, kind, leaving: false }
  _queue = [..._queue, item]
  // 超出上限: 挤掉最旧的还在屏上的那张(正在退场的不算, 它马上就走)
  const live = _queue.filter(x => !x.leaving)
  if (live.length > TOAST_MAX) dismiss(live[0].id)
  _arm(item)
  _emit()
}

export { toast }

// ===== 配色: 左侧色条 + 图标, 与 AlertToast 同一套语言 =====
const BAR: Record<ToastKind, string> = {
  error: 'bg-danger', success: 'bg-emerald-500', info: 'bg-accent',
}
const ICON: Record<ToastKind, string> = {
  error: 'text-danger', success: 'text-emerald-400', info: 'text-accent',
}
const TEXT: Record<ToastKind, string> = {
  error: 'text-foreground font-medium', success: 'text-secondary', info: 'text-foreground/85',
}

function ToastCard({ t }: { t: ToastItem }) {
  // 入场: 先以 opacity-0 挂上, 下一帧再切到终态, 让 transition 有起点可走。
  const [mounted, setMounted] = useState(false)
  useEffect(() => {
    const raf = requestAnimationFrame(() => setMounted(true))
    return () => cancelAnimationFrame(raf)
  }, [])
  const shown = mounted && !t.leaving
  const IconCmp = t.kind === 'error' ? AlertCircle : t.kind === 'success' ? CheckCircle2 : Info
  return (
    <div
      role={t.kind === 'error' ? 'alert' : undefined}
      onClick={() => dismiss(t.id)}
      className={cn(
        'pointer-events-auto relative flex w-[300px] cursor-pointer items-start gap-2 overflow-hidden rounded-xl border border-border/60 bg-surface/95 py-2 pl-3 pr-2 text-xs shadow-lg backdrop-blur-md',
        'transition-[opacity,transform] ease-out-strong',
        shown ? 'duration-expand translate-y-0 opacity-100' : 'duration-hover translate-y-1.5 opacity-0',
      )}
    >
      <div className={cn('absolute left-0 top-0 h-full w-0.5', BAR[t.kind])} />
      <IconCmp className={cn('mt-px h-3.5 w-3.5 shrink-0', ICON[t.kind])} />
      <span className={cn('min-w-0 flex-1 whitespace-pre-line break-words leading-relaxed', TEXT[t.kind])}>{t.msg}</span>
      {t.kind === 'error' && (
        <button
          type="button"
          aria-label="关闭提示"
          onClick={(e) => { e.stopPropagation(); dismiss(t.id) }}
          className="shrink-0 rounded p-0.5 text-muted/50 transition-colors hover:bg-elevated hover:text-foreground cursor-pointer"
        >
          <X className="h-3 w-3" />
        </button>
      )}
    </div>
  )
}

// ===== Toast 容器 — 挂在 Layout 最顶层 =====
export function ToastContainer() {
  const [items, setItems] = useState<ToastItem[]>([])

  const sub = useCallback(() => {
    _listeners.add(setItems)
    return () => { _listeners.delete(setItems) }
  }, [])

  useEffect(sub, [sub])

  if (!items.length) return null

  return (
    <div
      role="status"
      aria-live="polite"
      aria-atomic="false"
      className="pointer-events-none fixed bottom-4 right-4 z-[9999] flex flex-col items-end gap-2"
    >
      {items.map(t => <ToastCard key={t.id} t={t} />)}
    </div>
  )
}
