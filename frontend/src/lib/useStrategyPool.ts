import { useState, useCallback, useEffect } from 'react'
import { storage } from '@/lib/storage'

// 旧版按周期隔离的双池 ('strategy-pool' 日线 + 'strategy-pool-1m' 分钟) 已合并为
// 统一池 ('strategy-pool'): 策略自带周期声明, 执行时按各自 timeframes 路由,
// 池不再按周期隔离。此处做一次性迁移: 日线在前、分钟在后、按 ID 去重,
// 完成后移除旧分钟 key 保证幂等 (StrictMode 双调用 / HMR 重放均安全)。
function loadUnifiedPool(): string[] {
  const minute = storage.strategyPoolMinute.get([])
  const daily = storage.strategyPool.get([])
  if (minute.length === 0) {
    storage.strategyPoolMinute.remove()
    return daily
  }
  const merged = [...daily]
  for (const id of minute) {
    if (!merged.includes(id)) merged.push(id)
  }
  storage.strategyPool.set(merged)
  storage.strategyPoolMinute.remove()
  return merged
}

/**
 * 策略池 — 日线与分钟策略共用的统一池。
 * 卡片列表可按周期筛选显示, 但池本身只有一份;
 * addToPool 不再区分周期 (构建器/叠加策略创建的日线策略与分钟策略同池)。
 */
export function useStrategyPool() {
  const [pool, setPool] = useState<string[]>(loadUnifiedPool)

  useEffect(() => {
    storage.strategyPool.set(pool)
  }, [pool])

  const addToPool = useCallback((id: string) => {
    setPool(prev => (prev.includes(id) ? prev : [...prev, id]))
  }, [])

  const removeFromPool = useCallback((id: string) => {
    setPool(prev => prev.filter(x => x !== id))
  }, [])

  const reorderPool = useCallback((newOrder: string[]) => {
    setPool(newOrder)
  }, [])

  // 清除池中不存在于 validIds 的失效策略(如本地开发残留的自定义策略)。
  // 调用方传入"全周期合并的策略列表" ID, 池内日线/分钟策略一并校验。
  // 仅当确实有失效项时才更新,避免无谓重渲染。
  //
  // [R95] 被移除的 ID 先留底到 strategyPoolPruneBackup: prune 的判据是
  // "后端当前列表里没有", 但"没有"未必是永久的 —— 数据目录还没迁移、策略文件
  // 暂时加载失败, 都会让好好的策略从列表上暂时消失。没有留底的话, 一次误清
  // 就是永久丢失(localStorage 写掉了, 用户只看见"策略全没了")。
  const prune = useCallback((validIds: Iterable<string>) => {
    const validSet = validIds instanceof Set ? validIds : new Set(validIds)
    setPool(prev => {
      if (prev.length === 0) return prev
      const next = prev.filter(id => validSet.has(id))
      if (next.length === prev.length) return prev
      const removed = prev.filter(id => !validSet.has(id))
      const old = storage.strategyPoolPruneBackup.get(null)
      const merged = [...new Set([...(old?.removed ?? []), ...removed])]
      storage.strategyPoolPruneBackup.set({ at: new Date().toISOString(), removed: merged })
      return next
    })
  }, [])

  // [R95] 一键恢复上次自动清理移除的 ID(去重并回池尾)。策略仍不存在时卡片
  // 不会显示(visiblePool 过滤), 但 ID 保住了 —— 等数据迁回来它们自动重新出现。
  const restorePruned = useCallback(() => {
    const backup = storage.strategyPoolPruneBackup.get(null)
    if (!backup || backup.removed.length === 0) return 0
    setPool(prev => {
      const next = [...prev]
      for (const id of backup.removed) {
        if (!next.includes(id)) next.push(id)
      }
      return next
    })
    storage.strategyPoolPruneBackup.remove()
    return backup.removed.length
  }, [])

  const dismissPruneBackup = useCallback(() => {
    storage.strategyPoolPruneBackup.remove()
  }, [])

  const isInPool = useCallback((id: string) => pool.includes(id), [pool])

  return { pool, addToPool, removeFromPool, reorderPool, prune, isInPool, restorePruned, dismissPruneBackup }
}
