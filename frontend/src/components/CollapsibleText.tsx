/**
 * [fork 增强 R266] 长文折叠 —— 收起到固定行数, 超出了才给「展开」。
 *
 * 消息面那一页把 AI 综合出来的一大段和每条笔记都**全量铺开**渲染: 一段综合动辄
 * 几十行, 一进页面就把整屏吃光, 下面的输入框和卡片全被顶到屏外; 卡片墙里一条长
 * 记录会撑出上千像素的卡片, 同一行里旁边那条只有一句话, 高度差到没法看。
 *
 * 两个要点:
 *
 * - **按内容量决定给不给按钮**, 不按字数猜。列宽会变(两列/三列/窄屏一列),
 *   同样一段话在窄列里要占两倍行数 —— 字数阈值那种做法必然在某个宽度上判错,
 *   要么该给按钮的没给(内容被截断且无从展开), 要么明明没截断却挂个没用的按钮。
 *   这里量的是真实溢出, 并且跟着尺寸变化重新量。
 * - **收起用 max-height 而不是 line-clamp**: 这一页的正文是 `whitespace-pre-wrap`
 *   (AI 凝练带换行和缩进), `-webkit-line-clamp` 要把元素变成 `-webkit-box`,
 *   和 pre-wrap 一起用在各浏览器上表现不一致。max-height 没有这个问题。
 */
import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react'
import { ChevronDown } from 'lucide-react'
import { cn } from '@/lib/cn'

/** 与正文的 `leading-relaxed` 对齐 —— 收起高度 = 行数 × 行高。 */
const LINE_HEIGHT_EM = 1.625

interface Props {
  children: ReactNode
  /** 收起时显示几行 */
  lines: number
  /** 初始是否展开(通常来自 localStorage) */
  defaultOpen?: boolean
  /** 展开状态变了通知外面 —— 有些附带内容(免责说明之类)只在展开时才显示 */
  onOpenChange?: (open: boolean) => void
  moreLabel?: string
  lessLabel?: string
  className?: string
  /** 折叠按钮那一行的额外样式 */
  toggleClassName?: string
}

export function CollapsibleText({
  children,
  lines,
  defaultOpen = false,
  onOpenChange,
  moreLabel = '展开全文',
  lessLabel = '收起',
  className,
  toggleClassName,
}: Props) {
  const ref = useRef<HTMLDivElement>(null)
  const [open, setOpen] = useState(defaultOpen)
  const [overflowing, setOverflowing] = useState(false)

  // 量真实溢出。展开着的时候 clientHeight 就是全高, 比不出溢出 ——
  // 所以拿收起高度(行数 × 行高)去比 scrollHeight, 展开与否都能判。
  const measure = useCallback(() => {
    const el = ref.current
    if (!el) return
    const lineHeightPx = parseFloat(getComputedStyle(el).fontSize) * LINE_HEIGHT_EM
    setOverflowing(el.scrollHeight > lineHeightPx * lines + 2)
  }, [lines])

  useEffect(() => {
    measure()
    const el = ref.current
    if (!el || typeof ResizeObserver === 'undefined') return
    // 列宽会变(窄屏一列 / 宽屏三列), 换了宽度同一段话的行数就变了, 得重量
    const ro = new ResizeObserver(measure)
    ro.observe(el)
    return () => ro.disconnect()
  }, [measure, children])

  const toggle = () => {
    const next = !open
    setOpen(next)
    onOpenChange?.(next)
  }

  return (
    <>
      <div
        ref={ref}
        className={cn('overflow-hidden', className)}
        style={open ? undefined : {
          maxHeight: `${lines * LINE_HEIGHT_EM}em`,
          // 截断处让**文字自己**淡出, 而不是盖一层底色渐变 —— 这一页三处底色各不相同
          // (卡片/紫色总览块/原文小框), 盖底色就得每处传一个对应的颜色, 传错就露馅。
          // 遮罩与底色无关, 一处写法处处对。没截断不上遮罩, 否则最后一行平白发灰。
          ...(overflowing ? {
            maskImage: 'linear-gradient(to bottom, black calc(100% - 1.5rem), transparent)',
            WebkitMaskImage: 'linear-gradient(to bottom, black calc(100% - 1.5rem), transparent)',
          } : {}),
        }}
      >
        {children}
      </div>
      {overflowing && (
        <button
          type="button"
          onClick={toggle}
          aria-expanded={open}
          className={cn(
            'mt-1 inline-flex items-center gap-1 text-micro text-muted/70 transition-colors hover:text-foreground cursor-pointer',
            toggleClassName,
          )}
        >
          <ChevronDown className={cn('h-3 w-3 transition-transform', open && 'rotate-180')} />
          {open ? lessLabel : moreLabel}
        </button>
      )}
    </>
  )
}
