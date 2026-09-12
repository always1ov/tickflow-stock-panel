/**
 * [fork 增强 R323] 名词说明的**全局入口**。
 *
 * 六态与通道档位的词表(`ReviewHelpView`)原来只有一个入口 —— 复盘弹窗里的
 * 「说明」页签; 要查一个词得先找一只票、打开它的复盘、再切页签。词表与哪只票
 * 无关, 该从侧栏一步就到。这里只是给它一个壳: 正文原样复用, 不誊抄第二份。
 *
 * 走 `lazy()` 挂在 Layout 上: 词表那一页连着 27 格速查表, 不该进入口 chunk。
 */
import { BookOpen, X } from 'lucide-react'
import { Modal } from '@/components/Modal'
import { ReviewHelpView } from '@/components/stock-analysis/ReviewHelpView'

export function GlossaryDialog({ onClose }: { onClose: () => void }) {
  return (
    <Modal
      onClose={onClose}
      labelledBy="glossary-title"
      panelClassName="flex max-h-[85vh] w-[92vw] max-w-4xl flex-col rounded-card border border-border bg-surface shadow-xl"
    >
      <div className="flex items-center gap-2 border-b border-border/60 px-4 py-2.5">
        <BookOpen className="h-4 w-4 shrink-0 text-accent" />
        <h2 id="glossary-title" className="text-sm font-medium text-foreground">名词说明</h2>
        <span className="hidden text-[10px] text-muted sm:inline">
          六态状态 · 通道档位 · 27 种三档组合 —— 与哪只票无关的固定词表
        </span>
        <button
          type="button"
          aria-label="关闭"
          onClick={onClose}
          className="ml-auto rounded p-1 text-muted transition-colors hover:bg-elevated hover:text-foreground cursor-pointer"
        >
          <X className="h-4 w-4" />
        </button>
      </div>
      <ReviewHelpView />
    </Modal>
  )
}

export default GlossaryDialog
