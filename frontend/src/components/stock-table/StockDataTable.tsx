/**
 * 股票列表表格骨架（自选/策略页共享）。
 *
 * 职责：表头渲染（读列配置 label/align + 可排序三态指示器）、表体遍历、sticky 表头。
 * 不内置任何业务逻辑：单元格内容（含 symbol 列交互、操作列、ext 列）由调用方通过
 * renderCell / renderExtraCol 注入。这样两个页面的特有交互得以保留，同时表头能力一致。
 */
import { cloneElement, isValidElement, useRef, type ReactElement, type ReactNode } from 'react'
import { cn } from '@/lib/cn'
import { TH_ROW } from '@/components/ui'
import { useVirtualizer, type VirtualItem } from '@tanstack/react-virtual'
import type { ColumnConfig } from '@/lib/list-columns'
import { UNSORTABLE_KEYS } from '@/lib/stock-table'
import { VIRTUAL_LIST_THRESHOLD, useParentScroll } from '@/components/virtual-list/useParentScroll'
import type { SortState } from './useTableSort'

export type { SortState }

export interface StockDataTableProps {
  columns: ColumnConfig[]
  rows: any[]
  /** 单元格渲染回调。返回 null 时回退到内置纯数据列渲染。 */
  renderCell: (r: any, col: ColumnConfig) => ReactNode
  /** 行 key（默认取 r.symbol） */
  rowKey?: (r: any) => string | number
  /** 行 className（默认含 hover） */
  rowClassName?: (r: any) => string
  /** 表头是否 sticky（自选页需要，策略页不需要） */
  headerSticky?: boolean
  /** 最小表格宽度，默认按列数计算 */
  minWidth?: number
  /** 排序：外部受控时传入（含当前 sort 与 toggle）；不传则表头不可排序 */
  sort?: SortState | null
  onSortToggle?: (colId: string) => void
  /** 实例级放行: 让 UNSORTABLE_KEYS 中的 builtin 列在本表也可排序 (如自选页分时列) */
  extraSortableKeys?: ReadonlySet<string>
  /** 追加在每行末尾的额外单元格（如自选页的操作列） */
  renderExtraCol?: (r: any) => ReactNode
  /** 追加的表头单元格（对应 renderExtraCol） */
  extraHeader?: ReactNode
  /** 自定义表头单元格内容覆盖（如日k眼睛按钮）。返回 undefined 则用 col.label */
  renderHeaderContent?: (col: ColumnConfig) => ReactNode | undefined
  /** 外层容器 className */
  className?: string
  /**
   * [R395] 窄屏把第一列钉在左边缘。
   *
   * 手机上这张表放不下 —— 实测自选页 390px 宽只露得出两列半, 其余要往右滑。
   * 滑过去之后**行的身份就没了**: 满屏数字, 不知道哪一行是哪一只票。钉住
   * 「代码/名称」那一列, 滑动时它不动, 数字与票始终对得上。
   *
   * **只在窄屏钉**(`lg:static`): 宽屏本来就放得下, 桌面一个像素不变。
   */
  pinFirstColumn?: boolean
  /**
   * 钉住的那一格要**盖住**从它下面滑过去的内容, 所以必须是不透明底色 ——
   * 而底色是哪一个, 只有调用方知道: 行可能有选中态、失效态、涨跌态。
   * 骨架自己已经垫了一层不透明的页面底色(实测行本身是透明的, 真正画出来的
   * 是 `--base`), 这里只是**往上叠**。
   * **有行高亮的表必须在这里把高亮一起给出来**, 否则第一列会和本行其余部分
   * 差一个颜色 —— 那比不钉更难看。
   */
  pinnedCellClass?: (r: any) => string
}

function alignThClass(align: ColumnConfig['align']): string {
  // 表头一律不换行: 窄列(如收起的图表列)中标签/排序箭头折行会把整行表头顶高
  // [R452] 表头是标签那一级(11px 灰、不加粗), 与全站表格同一套 —— 原来 15px 中粗,
  // 比表格内容还显眼, 层级是反的
  if (align === 'right') return 'px-3 py-2.5 font-normal text-right whitespace-nowrap'
  if (align === 'center') return 'px-3 py-2.5 font-normal text-center whitespace-nowrap'
  return 'px-3 py-2.5 font-normal whitespace-nowrap'
}

export function StockDataTable({
  columns, rows, renderCell,
  rowKey = (r: any) => r.symbol,
  rowClassName = () => 'border-t border-border hover:bg-elevated/50',
  headerSticky = false,
  minWidth,
  sort,
  onSortToggle,
  extraSortableKeys,
  renderExtraCol,
  extraHeader,
  renderHeaderContent,
  className = 'rounded-card border border-border overflow-x-auto',
  pinFirstColumn = false,
  pinnedCellClass = () => 'group-hover:bg-elevated/50',
}: StockDataTableProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const visibleColumns = columns.filter(c => c.visible)
  const computedMinWidth = minWidth ?? Math.max(900, visibleColumns.length * 110)
  const virtualized = rows.length > VIRTUAL_LIST_THRESHOLD
  const { getScrollElement, scrollMargin } = useParentScroll(containerRef, virtualized)
  const rowVirtualizer = useVirtualizer({
    count: virtualized ? rows.length : 0,
    getScrollElement,
    estimateSize: () => 56,
    getItemKey: index => rowKey(rows[index]),
    overscan: 10,
    scrollMargin,
  })
  const virtualRows = virtualized ? rowVirtualizer.getVirtualItems() : []
  const totalSize = virtualized ? rowVirtualizer.getTotalSize() : 0
  const firstVirtualRow = virtualRows[0]
  const lastVirtualRow = virtualRows[virtualRows.length - 1]
  const topPadding = firstVirtualRow ? firstVirtualRow.start - scrollMargin : 0
  const bottomPadding = lastVirtualRow
    ? totalSize - (lastVirtualRow.end - scrollMargin)
    : totalSize
  const columnCount = visibleColumns.length + (renderExtraCol || extraHeader ? 1 : 0)

  const isColSortable = (col: ColumnConfig): boolean => {
    // 排序能力由调用方是否提供 onSortToggle 决定；sort 是否为 null 只影响当前指示器
    if (!onSortToggle) return false
    if (col.source.type === 'builtin' && UNSORTABLE_KEYS.has(col.source.key) && !extraSortableKeys?.has(col.source.key)) return false
    return true
  }

  const theadClass = headerSticky
    ? 'sticky top-0 z-10 bg-elevated after:absolute after:inset-x-0 after:bottom-0 after:h-px after:bg-border'
    : 'bg-elevated'

  const renderRow = (r: any, virtualRow?: VirtualItem) => (
    <tr
      key={rowKey(r)}
      ref={virtualRow ? rowVirtualizer.measureElement : undefined}
      data-index={virtualRow?.index}
      className={`transition-colors duration-hover ease-smooth group ${rowClassName(r)}`}
    >
      {visibleColumns.map((col, i) => {
        // renderCell 返回的 <td> 无 key, 这里补上避免 React key 警告
        const cell = renderCell(r, col)
        if (!isValidElement(cell)) return cell
        const el = cell as ReactElement<{ className?: string }>
        // 第一列钉住: 类名**合并**进调用方给的那一格, 而不是在外面再包一层 ——
        // 多包一层 <td> 会把列数对不上, colSpan 的占位行会错位。
        const extra = pinFirstColumn && i === 0
          ? cn(
              // **不透明底色写在骨架里, 不交给调用方** —— 它是"钉住"能成立的前提
              // (要盖住从底下滑过去的内容), 漏了就是两层字叠在一起且不报错。
              // 调用方只能用 `pinnedCellClass` 往上叠色, 叠不掉这一层的兜底。
              'sticky left-0 z-[1] bg-base lg:static lg:bg-transparent',
              pinnedCellClass(r),
            )
          : undefined
        return cloneElement(el, {
          key: col.id,
          ...(extra ? { className: cn(el.props.className, extra) } : {}),
        })
      })}
      {renderExtraCol && renderExtraCol(r)}
    </tr>
  )

  return (
    <div ref={containerRef} className={className}>
      <table className="w-full text-sm" style={{ minWidth: computedMinWidth }}>
        <thead className={theadClass}>
          {/* [R452] 整页主列表(自选、选股)内容保持 15px, 表头落到标签级 —— 见 docs/ui-hierarchy.md */}
          <tr className={cn(TH_ROW, 'text-left')}>
            {visibleColumns.map((col, i) => {
              const sortable = isColSortable(col)
              const isSorted = sort?.key === col.id
              const dir = isSorted ? sort!.dir : null
              const contentOverride = renderHeaderContent?.(col)
              return (
                <th
                  key={col.id}
                  className={cn(
                    alignThClass(col.align),
                    sortable && 'cursor-pointer select-none group',
                    // 表头那一格要同时钉住上边和左边, 否则往右滑时表头第一格会跑掉,
                    // 而表体第一格还钉着 —— 两者错位比都不钉更让人分神。
                    // 底色跟表头走(`bg-surface`), 不是行的底色。
                    pinFirstColumn && i === 0 && 'sticky left-0 z-20 bg-elevated lg:static lg:bg-transparent',
                  )}
                  onClick={sortable ? () => onSortToggle!(col.id) : undefined}
                >
                  {contentOverride !== undefined ? contentOverride : col.label}
                  {sortable && (
                    <span className="inline-block ml-1 text-micro opacity-30 group-hover:opacity-60 transition-opacity">
                      {isSorted ? (dir === 'asc' ? '↑' : '↓') : '↕'}
                    </span>
                  )}
                </th>
              )
            })}
            {extraHeader && (
              <th className="px-3 py-2.5 font-normal text-right">{extraHeader}</th>
            )}
          </tr>
        </thead>
        <tbody>
          {virtualized && topPadding > 0 && (
            <tr aria-hidden="true">
              <td colSpan={columnCount} className="p-0 border-0" style={{ height: topPadding }} />
            </tr>
          )}
          {virtualized
            ? virtualRows.map(virtualRow => renderRow(rows[virtualRow.index], virtualRow))
            : rows.map((r: any) => renderRow(r))}
          {virtualized && bottomPadding > 0 && (
            <tr aria-hidden="true">
              <td colSpan={columnCount} className="p-0 border-0" style={{ height: bottomPadding }} />
            </tr>
          )}
        </tbody>
      </table>
    </div>
  )
}
