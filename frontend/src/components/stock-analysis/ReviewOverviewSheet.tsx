/**
 * [fork 增强 R289] 复盘弹窗里的「全景」抽屉。
 *
 * 用户: 「我觉得全景图很多东西我是不看的, 用一个按钮全部藏起来, 点击按钮弹窗
 * 展示查看。我只关注最核心的东西 …… 我只要关注趋势、转折、六态状态这些」。
 *
 * ## 收的是**常驻**, 不是内容
 *
 * 一个字都没删。原来「趋势状态」那一页在逐日表之前压着四块常驻区:
 *
 *   现在(整卡)     六态 + 第几天 + 历史平均 + 两句统计 + 六态灵不灵芯片
 *   状态时间轴     这半年的色带
 *   分档依据       四到七枚芯片
 *   依据           涨跌停计数 / 封板率 / 涨停出在什么状态下
 *
 * 加起来三四百像素, 而**它们回答的都不是"今天该干什么"** —— 是背景。用户每次
 * 打开复盘要看的那张逐日表, 被它们顶到屏幕外面去了(R270 收过一次「依据」,
 * 这次是把同一条道理走完)。
 *
 * ## 为什么是"盖住正文"而不是再开一个模态
 *
 * 复盘本身已经是模态。模态套模态要处理两层焦点陷阱、两层 Esc、两层遮罩,
 * 而这里要的语义很简单: **翻到背面看资料, 翻回来接着看正文**。所以做成一层
 * 盖在弹窗正文上的面板 —— 它不抢外层的关闭键, 也不会让人分不清关掉的是哪一层。
 *
 * 动效: 一次淡入 + 极轻的位移(150ms, ease-out)。这是**偶尔**才点开的东西
 * (不是每天点几十次的快捷键), 所以给一个交代"它从哪儿来"的过渡是划算的;
 * 只动 `opacity` 与 `transform`, 且 `motion-reduce` 下直接取消。
 */
import { useEffect, useState, type ReactNode } from 'react'
import { ChevronLeft, LayoutPanelTop } from 'lucide-react'
import { cn } from '@/lib/cn'

/** 打开全景的那个按钮。与页签、日期档同一套外观 —— 它是同一层级的控件 */
export function OverviewButton({ onClick, label = '全景' }: { onClick: () => void; label?: string }) {
  return (
    <button
      type="button"
      onClick={onClick}
      title="时间轴、分档依据、涨跌停计数这些背景资料 —— 收在这里, 要看时翻开"
      className="inline-flex items-center gap-1 rounded-btn border border-border/60 px-2 py-1 text-[10px] text-muted transition-colors hover:text-foreground"
    >
      <LayoutPanelTop className="h-3 w-3" />
      {label}
    </button>
  )
}

export function ReviewOverviewSheet({ open, onClose, title, children }: {
  open: boolean
  onClose: () => void
  title: string
  children: ReactNode
}) {
  // 进场那一帧: 先挂上去(不可见), 下一帧再切到可见, 好让 transition 有得跑。
  const [shown, setShown] = useState(false)
  useEffect(() => {
    if (!open) { setShown(false); return }
    const id = requestAnimationFrame(() => setShown(true))
    return () => cancelAnimationFrame(id)
  }, [open])

  // Esc 关掉的是**这一层**, 不许穿透到外面那个复盘弹窗。
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') { e.stopPropagation(); onClose() }
    }
    window.addEventListener('keydown', onKey, true)
    return () => window.removeEventListener('keydown', onKey, true)
  }, [open, onClose])

  if (!open) return null
  return (
    <div
      className={cn(
        'absolute inset-0 z-20 flex flex-col bg-surface',
        'transition-[opacity,transform] duration-150 ease-out motion-reduce:transition-none',
        shown ? 'opacity-100 translate-y-0' : 'opacity-0 -translate-y-1',
      )}
    >
      <div className="flex shrink-0 items-center gap-2 border-b border-border/60 px-4 py-2">
        <button
          type="button"
          onClick={onClose}
          className="inline-flex items-center gap-1 rounded-btn border border-border/60 px-2 py-1 text-[10px] text-muted transition-colors hover:text-foreground"
        >
          <ChevronLeft className="h-3 w-3" />
          收起
        </button>
        <span className="text-[11px] text-secondary">{title}</span>
        <span className="text-[10px] text-muted">
          这些是背景资料 —— 正文那张逐日表才是每天要看的
        </span>
      </div>
      <div className="min-h-0 flex-1 overflow-auto pb-4">{children}</div>
    </div>
  )
}
