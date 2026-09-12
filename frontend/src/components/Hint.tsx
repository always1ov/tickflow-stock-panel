/**
 * [fork 增强 R323] 「?」—— 把只在悬停里存在的说明变成点得开的。
 *
 * 全仓库 817 处 `title=` 悬停说明: 每个数字都有解释, 但**只在鼠标停上去时存在**——
 * 手机、触屏、以及不知道该停哪儿的新用户一条都看不到。这个组件不重写文案, 只换
 * 容器: 同一份字, 桌面悬停(原生 title 照旧)、点一下 / 触屏点一下就摊开成一块
 * 浮层, 点别处、Esc、滚动都收起。
 *
 * 浮层用 `position: fixed` 按触发器的位置摆: 它常常挂在 `overflow-x: auto` 的表格
 * 表头里, absolute 会被容器裁掉。贴着视口边缘时往里挪, 下面放不下就翻到上面 ——
 * 并且 `transform-origin` 跟着翻(emil-design-eng: 浮层要从触发器长出来, 不是从
 * 中心)。180ms `pop-in`, 在「tooltip / 小浮层 125~200ms」那一档里。
 *
 * 触发器**不做**按下缩放之外的动效: 它一天会被点几十次。
 */
import { useEffect, useLayoutEffect, useRef, useState, type CSSProperties } from 'react'
import { HelpCircle } from 'lucide-react'
import { cn } from '@/lib/cn'

const GAP = 8      // 离视口边缘至少留这么多
const OFFSET = 4   // 浮层与触发器之间

export function Hint({ title, className }: {
  /** 说明文字 —— 与原来写在 `title=` 里的是同一份, `\n` 会换行 */
  title: string
  className?: string
}) {
  const [open, setOpen] = useState(false)
  const [style, setStyle] = useState<CSSProperties>()
  const [above, setAbove] = useState(false)
  const btnRef = useRef<HTMLButtonElement>(null)
  const popRef = useRef<HTMLSpanElement>(null)

  // 先挂上再量: 浮层的宽高要看文字多长。useLayoutEffect 在绘制前跑完, 不会闪。
  useLayoutEffect(() => {
    if (!open) { setStyle(undefined); return }
    const b = btnRef.current?.getBoundingClientRect()
    const p = popRef.current?.getBoundingClientRect()
    if (!b || !p) return
    const vw = window.innerWidth
    const vh = window.innerHeight
    const left = Math.min(Math.max(b.left + b.width / 2 - p.width / 2, GAP), Math.max(GAP, vw - p.width - GAP))
    const fitsBelow = b.bottom + OFFSET + p.height <= vh - GAP
    setAbove(!fitsBelow)
    setStyle({ left, top: fitsBelow ? b.bottom + OFFSET : Math.max(GAP, b.top - OFFSET - p.height) })
  }, [open])

  useEffect(() => {
    if (!open) return
    const onDoc = (e: PointerEvent) => {
      const t = e.target as Node
      if (btnRef.current?.contains(t) || popRef.current?.contains(t)) return
      setOpen(false)
    }
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false) }
    const onScroll = () => setOpen(false)
    document.addEventListener('pointerdown', onDoc)
    document.addEventListener('keydown', onKey)
    window.addEventListener('scroll', onScroll, true)
    window.addEventListener('resize', onScroll)
    return () => {
      document.removeEventListener('pointerdown', onDoc)
      document.removeEventListener('keydown', onKey)
      window.removeEventListener('scroll', onScroll, true)
      window.removeEventListener('resize', onScroll)
    }
  }, [open])

  return (
    <>
      <button
        ref={btnRef}
        type="button"
        aria-label="说明"
        aria-expanded={open}
        title={open ? undefined : title}
        onClick={(e) => { e.stopPropagation(); setOpen(o => !o) }}
        className={cn(
          'inline-flex shrink-0 items-center justify-center rounded-full p-0.5 align-middle text-muted/50 transition-colors duration-hover hover:text-foreground cursor-pointer',
          open && 'text-foreground',
          className,
        )}
      >
        <HelpCircle className="h-3 w-3" />
      </button>
      {open && (
        <span
          ref={popRef}
          role="tooltip"
          style={style ?? { left: GAP, top: GAP, visibility: 'hidden' }}
          onClick={(e) => e.stopPropagation()}
          className={cn(
            'fixed z-[70] w-max max-w-[min(22rem,calc(100vw-1rem))] cursor-auto select-text whitespace-pre-line rounded-btn border border-border bg-surface px-2.5 py-2 text-left text-[11px] font-normal leading-relaxed text-secondary shadow-lg animate-pop-in',
            above ? 'origin-bottom' : 'origin-top',
          )}
        >
          {title}
        </span>
      )}
    </>
  )
}
