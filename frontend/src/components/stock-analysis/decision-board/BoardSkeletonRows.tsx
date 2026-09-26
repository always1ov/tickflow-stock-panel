/**
 * [fork 增强 R324] 决策台首次加载的骨架行 —— 表头已经在了, 先把行的形状画出来。
 *
 * 原来自选列表还没回来时, 那一格印的是「自选为空 —— 去自选页添加标的」:
 * **那多半是假的**(R276 早就为筛选的情形修过同一句), 加载中的表看起来像空表,
 * 新用户第一眼就被指去了错误的地方。骨架只在 `isLoading`(本地没有缓存)时
 * 出现, 后台重取不盖。
 */
import { Skeleton } from '@/components/data/Skeleton'

/** 每列一格的宽度 —— 与 BOARD_COLS 的顺序一致: 标的 / 现价涨跌 / 走势/位置 / 持仓
 *  ([R435] 末尾「AI 信号」那一格随列一起撤了) */
const CELL_W = ['w-16', 'w-12', 'w-32', 'w-10']

export function BoardSkeletonRows({ rows = 6, cols = CELL_W.length }: { rows?: number; cols?: number }) {
  return (
    <>
      {Array.from({ length: rows }, (_, r) => (
        <tr key={r} className="border-t border-border/30 max-sm:flex max-sm:items-center max-sm:gap-x-3 max-sm:px-3" aria-hidden="true">
          {Array.from({ length: cols }, (_, c) => (
            <td key={c} className="px-3 py-2.5">
              {/* [R520] 表改单行左对齐, 骨架跟着(数据到位时版面不跳) */}
              <Skeleton w={CELL_W[c] ?? 'w-12'} h="h-3" />
            </td>
          ))}
        </tr>
      ))}
    </>
  )
}
