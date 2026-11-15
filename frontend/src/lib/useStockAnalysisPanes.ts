import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { QK } from '@/lib/queryKeys'

/**
 * [R649] 关键价位 / 日K 两个入口共用的分析副图取数。
 *
 * 数据口径只此一处:
 *   · 量化MACD 要约 1000 根历史预热 EMA —— 不能从主图那份日K 现算, 是一支独立请求;
 *   · 查询键相同, 两个入口不会各发一次; `enabled` 只让日K 在没开副图时不白拉。
 */

export function useStockQuantMacd(symbol: string, enabled = true) {
  return useQuery({
    queryKey: QK.stockQuantMacd(symbol),
    queryFn: () => api.stockQuantMacd(symbol),
    enabled: !!symbol && enabled,
    staleTime: 15_000,
  })
}
