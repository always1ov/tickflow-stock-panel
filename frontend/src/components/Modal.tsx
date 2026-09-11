import { useEffect, useRef, type ReactNode } from 'react'

/**
 * 共享模态对话框原语 — 统一处理可访问性:
 * - role="dialog" + aria-modal + aria-labelledby / aria-label
 * - ESC 关闭
 * - 打开时把焦点移入对话框 (initialFocusRef 或首个可聚焦元素)
 * - Tab / Shift+Tab 焦点陷阱 (焦点不会跑出对话框)
 * - 关闭时把焦点还给打开前的元素
 * - 点击遮罩关闭 (可用 closeOnBackdrop 关闭)
 *
 * 视觉: 提供居中遮罩 + 面板容器, 面板样式由 panelClassName 定制。
 */
export interface ModalProps {
  onClose: () => void
  children: ReactNode
  /** 对话框标题元素 id (用于 aria-labelledby) */
  labelledBy?: string
  /** 无可见标题时的无障碍名称 */
  ariaLabel?: string
  /** 面板 className (尺寸/背景/圆角等) */
  panelClassName?: string
  /** 遮罩 className (覆盖默认居中/背景) */
  overlayClassName?: string
  /** 打开时聚焦的元素; 不传则聚焦面板内首个可聚焦元素 */
  initialFocusRef?: React.RefObject<HTMLElement>
  /** 点击遮罩是否关闭 (默认 true) */
  closeOnBackdrop?: boolean
}

const FOCUSABLE = [
  'a[href]',
  'button:not([disabled])',
  'textarea:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(',')

export function Modal({
  onClose,
  children,
  labelledBy,
  ariaLabel,
  panelClassName = 'w-[92vw] max-w-lg bg-surface border border-border rounded-card shadow-xl',
  overlayClassName = 'fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm',
  initialFocusRef,
  closeOnBackdrop = true,
}: ModalProps) {
  const panelRef = useRef<HTMLDivElement>(null)
  // 记录鼠标按下时是否落在遮罩(而非面板)上。
  // 仅当 mousedown 和 mouseup 都在遮罩时才视为"点击遮罩关闭",
  // 避免在面板内拖选文本时鼠标移出面板边缘导致误关 (拖拽穿透)。
  const mouseDownOnBackdrop = useRef(false)
  // onClose 存 ref: 焦点陷阱/ESC effect 只在挂载时装一次。否则父级每次重渲染 (或未 memo 的
  // onClose) 都让 effect 重跑, requestAnimationFrame(focusFirst) 会在每次输入后把焦点抢回
  // 面板首个元素, 导致对话框内文本框无法输入。
  const onCloseRef = useRef(onClose)
  onCloseRef.current = onClose

  useEffect(() => {
    // 记住打开前的焦点, 关闭时还原
    const prevActive = document.activeElement as HTMLElement | null

    // 初始聚焦
    const focusFirst = () => {
      if (initialFocusRef?.current) {
        initialFocusRef.current.focus()
        return
      }
      const panel = panelRef.current
      if (!panel) return
      const first = panel.querySelector<HTMLElement>(FOCUSABLE)
      ;(first ?? panel).focus()
    }
    // 等一帧确保内容已挂载
    const raf = requestAnimationFrame(focusFirst)

    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.stopPropagation()
        onCloseRef.current()
        return
      }
      if (e.key !== 'Tab') return
      const panel = panelRef.current
      if (!panel) return
      const nodes = Array.from(panel.querySelectorAll<HTMLElement>(FOCUSABLE))
        .filter(el => el.offsetParent !== null || el === document.activeElement)
      if (nodes.length === 0) {
        e.preventDefault()
        panel.focus()
        return
      }
      const first = nodes[0]
      const last = nodes[nodes.length - 1]
      const active = document.activeElement as HTMLElement | null
      if (e.shiftKey) {
        if (active === first || !panel.contains(active)) {
          e.preventDefault()
          last.focus()
        }
      } else {
        if (active === last || !panel.contains(active)) {
          e.preventDefault()
          first.focus()
        }
      }
    }

    document.addEventListener('keydown', onKeyDown, true)
    return () => {
      cancelAnimationFrame(raf)
      document.removeEventListener('keydown', onKeyDown, true)
      // 还原焦点
      prevActive?.focus?.()
    }
    // 只在挂载时装一次: onClose 走 ref, initialFocusRef 为稳定 ref 对象, 无需进依赖。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    // [R317] 入场动效: 遮罩淡入 160ms + 面板从 scale(0.96) 放到 1(180ms)。
    //
    // 之前是硬切出现 —— 弹窗"啪"地一下盖上来, 没有任何"它是从哪来的"的交代。
    // emil-design-eng 把弹窗归到「偶发使用 → 标准动效」那一档: 用户一天只开
    // 几次, 加动效不会拖慢高频操作, 却能明确建立"这一层浮在页面之上"的空间感。
    //
    // 三条细节:
    //   1. 曲线走 --ease-out-strong(cubic-bezier(0.23,1,0.32,1)), 内置 ease-out
    //      收得太软, 入场缺少"应答"的手感。
    //   2. 起手 0.96 而不是 0 —— 现实里没有东西凭空出现。
    //   3. 两个动画类**追加**在调用方传入的 className 之后, 而不是塞进默认值里:
    //      panelClassName / overlayClassName 是整体替换语义, 写进默认值的话,
    //      凡是自己传了面板样式的调用点都会静默丢掉动效。
    //   4. 终态在 keyframes 里是 `transform: none`(不是 scale(1)) —— 见
    //      tailwind.config.ts 的说明: 非 none 的 transform 会成为 fixed 子元素
    //      的包含块, 面板里的下拉/tooltip 会错位。
    //
    // 「减少动态效果」由 index.css 的全局规则接管(animation-duration → 0.01ms),
    // 不需要在这里再判断一次。
    <div
      className={`${overlayClassName} animate-fade-in`}
      onMouseDown={(e) => {
        // 仅记录"按下时确实在遮罩上"; 在面板内按下时记 false。
        mouseDownOnBackdrop.current = e.target === e.currentTarget
      }}
      onClick={closeOnBackdrop ? (e) => {
        // 只有按下和松开都在遮罩上才关闭, 避免拖选文本误关。
        if (mouseDownOnBackdrop.current && e.target === e.currentTarget) onClose()
      } : undefined}
    >
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={labelledBy}
        aria-label={labelledBy ? undefined : ariaLabel}
        tabIndex={-1}
        className={`animate-pop-in outline-none ${panelClassName}`}
        onClick={(e) => e.stopPropagation()}
      >
        {children}
      </div>
    </div>
  )
}
