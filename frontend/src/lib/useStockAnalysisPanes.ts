import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { QK } from '@/lib/queryKeys'

/**
 * [R649] 关键价位 / 日K 两个入口共用的两张副图取数。
 *
 * 数据口径只此一处:
 *   · 量化MACD 要约 1000 根历史预热 EMA, 趋势量化要从上市第一根算起 —— 都不能从主图那份
 *     日K 现算, 各是一支独立请求;
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

export function useStockTrendQuant(symbol: string, enabled = true) {
  return useQuery({
    queryKey: QK.stockTrendQuant(symbol),
    queryFn: () => api.stockTrendQuant(symbol),
    enabled: !!symbol && enabled,
    staleTime: 15_000,
  })
}
