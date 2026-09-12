/**
 * [fork 增强 R324] 今日总览首次加载的骨架 —— 先画出版面的形状, 内容填进来不跳。
 *
 * 原来是一个居中转圈: 页面从"一个点"突然长成"四个区块", 视线得重新找位置。
 * 骨架按真实版面摆: 市场状态卡(标题行 + 五个统计格)→ 需要行动(两行)→
 * 持仓体检(三行表)→ 机会(五行表)。**只在 `isLoading`(本地没有任何缓存)时出现**;
 * 后台重取时上一份数据还在, 不该盖骨架。
 *
 * 不做 stagger: 骨架是"等着"的状态, 不该表演。`animate-pulse` 来自 Skeleton 原语。
 */
import { Skeleton } from '@/components/data/Skeleton'

function SectionHead({ w }: { w: string }) {
  return (
    <div className="flex items-center gap-2 border-b border-border/40 px-4 py-2.5">
      <Skeleton w="w-4" h="h-4" rounded="rounded-sm" />
      <Skeleton w={w} h="h-3.5" />
      <Skeleton w="w-10" h="h-2.5" />
    </div>
  )
}

function Row({ cells }: { cells: string[] }) {
  return (
    <div className="flex items-center gap-4 border-b border-border/30 px-4 py-2.5 last:border-b-0">
      {cells.map((w, i) => <Skeleton key={i} w={w} h="h-3" />)}
    </div>
  )
}

export function TodaySkeleton() {
  return (
    <div role="status" aria-label="正在加载今日总览" className="space-y-3">
      {/* 市场状态卡 */}
      <div className="overflow-hidden rounded-lg border border-border/60 bg-surface/40">
        <div className="flex items-center gap-2 border-b border-border/40 px-4 py-2.5">
          <Skeleton w="w-4" h="h-4" rounded="rounded-sm" />
          <Skeleton w="w-14" h="h-5" rounded="rounded-btn" />
          <Skeleton w="w-10" h="h-4" rounded="rounded" />
          <Skeleton w="w-24" h="h-4" rounded="rounded-btn" />
        </div>
        <div className="grid grid-cols-2 divide-x divide-y divide-border/30 sm:grid-cols-3 lg:grid-cols-5 lg:divide-y-0">
          {Array.from({ length: 5 }, (_, i) => (
            <div key={i} className="space-y-1.5 px-4 py-2.5">
              <Skeleton w="w-14" h="h-2.5" />
              <Skeleton w="w-10" h="h-4" />
              <Skeleton w="w-16" h="h-2.5" />
            </div>
          ))}
        </div>
      </div>

      {/* 需要行动 */}
      <div className="overflow-hidden rounded-lg border border-border/60 bg-surface/40">
        <SectionHead w="w-16" />
        <Row cells={['w-3', 'w-16', 'w-1/2']} />
        <Row cells={['w-3', 'w-20', 'w-1/3']} />
      </div>

      {/* 持仓体检 */}
      <div className="overflow-hidden rounded-lg border border-border/60 bg-surface/40">
        <SectionHead w="w-16" />
        {Array.from({ length: 3 }, (_, i) => (
          <Row key={i} cells={['w-24', 'w-12', 'w-10', 'w-12', 'w-16', 'w-12', 'w-12', 'w-16']} />
        ))}
      </div>

      {/* 机会 */}
      <div className="overflow-hidden rounded-lg border border-border/60 bg-surface/40">
        <SectionHead w="w-20" />
        {Array.from({ length: 5 }, (_, i) => (
          <Row key={i} cells={['w-8', 'w-24', 'w-16', 'w-1/3', 'w-14']} />
        ))}
      </div>
    </div>
  )
}
