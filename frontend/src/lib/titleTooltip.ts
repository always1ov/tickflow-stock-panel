/**
 * [R553] 全站悬停提示 —— 把浏览器原生的 `title` 提示换成自己画的一层, 调用方一处不改。
 *
 * 用户: 「整改所有悬浮」。全站 126 个文件里有 741 处 `title=`, 走的都是浏览器原生提示,
 * 毛病与 R49 给「结论」列自己画悬停卡时列的一样:
 *   · 要停一秒多才弹, 扫一排按钮时等不及;
 *   · 系统渲染: 深色主题里弹出一块浅灰底, 字号、圆角、阴影都不是本系统的;
 *   · 多行说明(\n)挤成一坨, 没有行距。
 * 逐处改成 React 组件要动 126 个文件, 而且以后新写的 `title=` 照样漏回原生 —— 所以做成
 * 事件委托的一层: 鼠标进到带 `title` 的元素, 先把 `title` 暂存到 `data-tt-title`(原生提示
 * 就不会弹), 由这一层画; 离开时原样放回。读屏软件读的仍是 `title`(不悬停时它一直在)。
 *
 * 动效(emil-design-eng / review-animations STANDARDS · Tooltips):
 *   · 首次停留 400ms 才弹(防误触), 弹出后 300ms 内移到下一个带提示的元素 → 立即出现、不做动画;
 *   · 入场 opacity + scale(0.97) → 1, 125ms 有力 ease-out, transform-origin 朝向触发元素;
 *   · 离开即消失, 不做退场(提示是系统应答, 该利落);
 *   · 只在能悬停的精确指针上接管(`(hover: hover) and (pointer: fine)`), 触屏不碰;
 *   · 减少动态效果: index.css 全局兜底把 transform 移出过渡, 只剩透明度渐变。
 * 键盘: Tab 聚焦(:focus-visible)到带 `title` 的元素时也立即显示 —— 原生提示做不到这一点。
 */

const DELAY_MS = 400
const SKIP_WINDOW_MS = 300
const GAP = 6
const EDGE = 8
const MAX_W = 320
const STASH = 'data-tt-title'

const BOX_CLS = [
  'pointer-events-none fixed left-0 top-0 z-[10000] max-w-[320px] whitespace-pre-line break-words',
  'rounded-btn border border-border bg-surface px-2.5 py-1.5 text-xs leading-relaxed text-foreground shadow-lg',
  'opacity-0 [transform:scale(0.97)]',
  '[transition:opacity_125ms_var(--ease-out-strong),transform_125ms_var(--ease-out-strong)]',
  'data-[open]:opacity-100 data-[open]:[transform:none] data-[instant]:[transition:none]',
].join(' ')

type Win = Window & typeof globalThis

export function installTitleTooltip(win: Win = window): () => void {
  const doc = win.document
  const box = doc.createElement('div')
  box.setAttribute('role', 'tooltip')
  box.id = 'tf-title-tooltip'
  box.className = BOX_CLS
  box.hidden = true
  doc.body.appendChild(box)

  const fine = () => win.matchMedia?.('(hover: hover) and (pointer: fine)').matches ?? false

  let target: HTMLElement | null = null
  let timer = 0
  let lastHiddenAt = -Infinity
  let showing = false
  let watch: MutationObserver | null = null
  let alive = 0

  const text = (el: HTMLElement) => el.getAttribute(STASH) ?? ''

  /** 暂存 title, 挡住原生提示; React 若在悬停期间改写了 title, 取新值再挡一次 */
  const stash = (el: HTMLElement) => {
    const t = el.getAttribute('title')
    if (t == null) return
    el.setAttribute(STASH, t)
    el.removeAttribute('title')
  }

  const place = (el: HTMLElement, pointerX?: number) => {
    const r = el.getBoundingClientRect()
    const bw = Math.min(box.offsetWidth, MAX_W)
    const bh = box.offsetHeight
    const vw = win.innerWidth
    const vh = win.innerHeight
    const below = r.bottom + GAP + bh <= vh - EDGE || r.top - GAP - bh < EDGE
    // 窄元素对准元素中线; 宽元素(整行、长单元格)对准指针, 否则提示会离手很远
    const cx = r.width > 240 && pointerX != null ? pointerX : r.left + r.width / 2
    const left = Math.min(Math.max(EDGE, cx - bw / 2), vw - bw - EDGE)
    const top = below ? r.bottom + GAP : r.top - GAP - bh
    box.style.left = `${Math.round(left)}px`
    box.style.top = `${Math.round(top)}px`
    box.style.transformOrigin = `${Math.round(cx - left)}px ${below ? 'top' : 'bottom'}`
  }

  const open = (el: HTMLElement, pointerX: number | undefined, instant: boolean) => {
    const t = text(el)
    if (!t.trim()) return
    box.textContent = t
    box.hidden = false
    box.toggleAttribute('data-instant', instant)
    box.removeAttribute('data-open')
    place(el, pointerX)
    showing = true
    if (instant) box.setAttribute('data-open', '')
    else {
      void box.offsetWidth // 先落定起始态, 过渡才会跑
      box.setAttribute('data-open', '')
    }
    // 元素在悬停中被卸掉(弹窗关了、行被刷新走了)时收起, 不留一块悬空的提示
    alive = win.setInterval(() => { if (target && !target.isConnected) release() }, 250)
  }

  const hide = () => {
    win.clearTimeout(timer)
    win.clearInterval(alive)
    if (showing) lastHiddenAt = win.performance.now()
    showing = false
    box.hidden = true
    box.removeAttribute('data-open')
  }

  /** 离开: 收起提示, 把 title 原样放回 */
  const release = () => {
    hide()
    watch?.disconnect()
    watch = null
    const el = target
    target = null
    if (el && el.hasAttribute(STASH)) {
      el.setAttribute('title', el.getAttribute(STASH)!)
      el.removeAttribute(STASH)
    }
  }

  const engage = (el: HTMLElement, pointerX: number | undefined, immediate: boolean) => {
    if (el === target) return
    release()
    if (!el.getAttribute('title')?.trim()) return
    target = el
    stash(el)
    watch = new win.MutationObserver(() => {
      if (!target) return
      stash(target)
      if (showing) { box.textContent = text(target); place(target, pointerX) }
    })
    watch.observe(el, { attributes: true, attributeFilter: ['title'] })
    const skip = win.performance.now() - lastHiddenAt < SKIP_WINDOW_MS
    if (immediate || skip) open(el, pointerX, true)
    else timer = win.setTimeout(() => { if (target === el) open(el, pointerX, false) }, DELAY_MS)
  }

  const findTitled = (node: EventTarget | null): HTMLElement | null => {
    if (!(node instanceof win.Element)) return null
    const el = node.closest(`[title],[${STASH}]`)
    if (!(el instanceof win.HTMLElement) || el.tagName === 'IFRAME') return null
    return el
  }

  const onOver = (e: MouseEvent) => {
    if (!fine()) return
    const el = findTitled(e.target)
    if (!el) { if (target && !target.contains(e.target as Node)) release(); return }
    engage(el, e.clientX, false)
  }
  const onOut = (e: MouseEvent) => {
    if (!target) return
    const to = e.relatedTarget as Node | null
    if (to && target.contains(to)) return
    // 移进另一个带提示的元素由 onOver 接手(那边会先 release 这一个)
    if (!findTitled(to)) release()
  }
  // 点一下就收起(与原生一致), 直到离开再进来才重新计时
  const onDown = () => { if (showing || timer) { hide(); timer = 0 } }
  const onFocusIn = (e: FocusEvent) => {
    const el = findTitled(e.target)
    if (!el || el !== e.target) return
    let visible = false
    try { visible = el.matches(':focus-visible') } catch { /* 老浏览器 */ }
    if (visible) engage(el, undefined, true)
  }
  const onFocusOut = (e: FocusEvent) => { if (target && e.target === target) release() }
  const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape' && showing) hide() }

  doc.addEventListener('mouseover', onOver, true)
  doc.addEventListener('mouseout', onOut, true)
  doc.addEventListener('mousedown', onDown, true)
  doc.addEventListener('focusin', onFocusIn, true)
  doc.addEventListener('focusout', onFocusOut, true)
  doc.addEventListener('keydown', onKey, true)
  win.addEventListener('scroll', hide, true)
  win.addEventListener('resize', hide)
  win.addEventListener('blur', release)

  return () => {
    release()
    doc.removeEventListener('mouseover', onOver, true)
    doc.removeEventListener('mouseout', onOut, true)
    doc.removeEventListener('mousedown', onDown, true)
    doc.removeEventListener('focusin', onFocusIn, true)
    doc.removeEventListener('focusout', onFocusOut, true)
    doc.removeEventListener('keydown', onKey, true)
    win.removeEventListener('scroll', hide, true)
    win.removeEventListener('resize', hide)
    win.removeEventListener('blur', release)
    box.remove()
  }
}
