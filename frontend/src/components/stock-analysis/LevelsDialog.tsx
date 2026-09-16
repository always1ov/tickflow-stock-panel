/**
 * [R28 → fork R363] 关键价位弹窗 —— **一处实现, 两处共用**: 日 K + 压力支撑 +
 * 六态趋势条。
 *
 * R28 立它的理由是「关键价位不再挤占列表高度, 改成点标的后弹窗查看」。它原来是
 * `pages/StockAnalysis.tsx` 里的一个私有组件 —— 模拟盘要用它(用户: 「点击这两列
 * 都要能像个股分析页面那样弹出弹窗」), **不在那边抄一份**: 这个弹窗里有放大态、
 * Esc 关闭、退场动画、现价标签、`bare` 那一层去框, 抄一份必然漂, 而漂的表现是
 * 「两个页面点同一只票弹出来的东西不一样」, 两边都不报错。
 *
 * 常驻挂载、由 `symbol` 是否为 null 驱动 —— 这样关闭时退场动画能播完。
 */
import { useEffect, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { LineChart, Maximize2, Minimize2, X } from 'lucide-react'
import { StockLevelsPanel, StockLevelsPriceTag } from '@/components/stock-analysis/StockLevelsPanel'
import { cn } from '@/lib/cn'
import { useDialogBackdrop } from '@/lib/useDialogBackdrop'
import { useIsDesktop } from '@/lib/useMediaQuery'

export function LevelsDialog({ symbol, name, onClose }: { symbol: string | null; name: string; onClose: () => void }) {
  const [maximized, setMaximized] = useState(false)
  // [fork R366] 窄屏判定走**共用的那一个** `useIsDesktop`(Layout 的抽屉也用它),
  // 不在这儿另立一个断点 —— 两套断点会在某个宽度上互相打架, 而且不报错。
  const narrow = !useIsDesktop()
  const backdrop = useDialogBackdrop(onClose)

  // Esc 关闭 —— 弹窗高频开关, 键盘退出比找关闭按钮快
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  // 关掉时重置放大态, 下次开回到常规尺寸
  useEffect(() => { if (!symbol) setMaximized(false) }, [symbol])

  return (
    <AnimatePresence>
      {symbol && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.15 }}
            className="absolute inset-0 bg-black/60 backdrop-blur-sm"
            {...backdrop}
          />
          <motion.div
            initial={{ opacity: 0, scale: 0.95, y: 12 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.97, y: 8 }}
            transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
            className={cn(
              'relative rounded-card border border-border bg-base shadow-2xl overflow-hidden flex flex-col transition-ui duration-expand ease-smooth',
              // [fork R366] 手机上 92vw 会在两侧各留一条 4% 的黑边, 而屏幕本来就窄
              // —— 窄屏改成铺满并去掉圆角外的留白, 宽屏照旧。
              maximized ? 'w-screen h-screen max-w-none max-h-none' : 'w-full max-w-[1100px] max-h-[95vh] sm:w-[92vw]',
            )}
          >
            {/* 顶栏: 与个股日 K 弹窗同款 —— 代码 + 名称在左, 行情摘要与操作在右 */}
            <div className="flex shrink-0 items-center justify-between gap-3 px-4 py-3 sm:px-5">
              <div className="flex min-w-0 items-center gap-2">
                <LineChart className="h-4 w-4 shrink-0 text-sky-400" />
                <span className="shrink-0 font-mono text-sm font-medium text-foreground">{symbol}</span>
                {name && <span className="truncate text-xs text-muted">{name}</span>}
              </div>
              <div className="flex shrink-0 items-center gap-2">
                <StockLevelsPriceTag symbol={symbol} />
                <button
                  onClick={() => setMaximized(v => !v)}
                  title={maximized ? '缩小' : '放大'}
                  className="rounded-md p-1 text-muted transition-colors hover:bg-elevated hover:text-foreground"
                >
                  {maximized ? <Minimize2 className="h-4 w-4" /> : <Maximize2 className="h-4 w-4" />}
                </button>
                <button
                  onClick={onClose}
                  title="关闭(Esc)"
                  className="rounded-md p-1 text-muted transition-colors hover:bg-elevated hover:text-foreground"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
            </div>
            <div className="flex-1 overflow-auto px-4 pb-4 sm:px-5">
              {/* bare: 去掉内层卡片外框与标题条 —— 弹窗里再套一层框正是"辣眼睛"的来源 */}
              {/* [fork R366] 手机竖屏上 520px 的图几乎占满一屏, 下面的价位表要滚很久
                  才看得到。窄屏收到 320, 宽屏照旧。 */}
              <StockLevelsPanel symbol={symbol} bare
                                height={maximized ? 720 : (narrow ? 320 : 520)} />
            </div>
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  )
}
