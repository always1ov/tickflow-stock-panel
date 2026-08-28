/**
 * 共享 mutation hooks — 消除多页面重复的 useMutation 调用。
 */
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from './api'
import { QK } from './queryKeys'
import { toast } from '@/components/Toast'

const REPAIR_POLL_MS = 1_000
const MAX_REPAIR_CYCLES = 2

const wait = (ms: number) => new Promise<void>(resolve => window.setTimeout(resolve, ms))

/**
 * 开启实时行情时若命中停机快照门禁，后端会返回修复任务而不立刻开行情。
 * 跟踪该任务，修复成功后自动重试用户原本的开启动作；失败/重复修不掉时
 * 明确结束，不能无限创建任务。
 */
async function updateRealtimeWithRepair(enabled: boolean) {
  if (!enabled) return api.updateRealtimeQuotes(false)

  let result = await api.updateRealtimeQuotes(true)
  let repaired = false

  for (let cycle = 0; result.repair_required && result.repair_job_id; cycle += 1) {
    if (cycle >= MAX_REPAIR_CYCLES) {
      const message = '数据修复完成后仍检测到盘中快照，请到数据页查看修复结果'
      toast(message, 'error')
      throw new Error(message)
    }

    toast(`${result.repair_detail ?? '检测到不完整行情数据'}，修复成功后将自动开启实时行情`, 'success')
    const jobId = result.repair_job_id
    while (true) {
      const job = await api.pipelineJob(jobId)
      if (job.status === 'succeeded') break
      if (job.status === 'failed') {
        const message = `数据修复失败：${job.error || '请到数据页查看任务日志'}`
        toast(message, 'error')
        throw new Error(message)
      }
      await wait(REPAIR_POLL_MS)
    }

    repaired = true
    result = await api.updateRealtimeQuotes(true)
  }

  if (result.error === 'watchlist_empty') {
    const message = '自选列表为空，请先添加自选股再开启实时行情'
    toast(message, 'error')
    return result
  }
  if (repaired && result.realtime_quotes_enabled) {
    toast('数据修复完成，实时行情已自动开启', 'success')
    return { ...result, repair_completed: true }
  }
  return result
}

/** 切换实时行情 — Layout / Data 共用 */
export function useToggleRealtimeQuotes() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: updateRealtimeWithRepair,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: QK.preferences })
      qc.invalidateQueries({ queryKey: QK.quoteStatus })
    },
  })
}

/** 更新行情轮询间隔 — Layout / Data 共用 */
export function useUpdateQuoteInterval() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: number) => api.updateQuoteInterval(v),
    onSuccess: (data) => {
      qc.setQueryData(QK.quoteInterval, data)
      qc.invalidateQueries({ queryKey: QK.quoteStatus })
    },
  })
}

interface WatchlistBatchAddInput {
  symbols: string[]
  groupId?: string | null
}

/** 批量添加自选 — Screener / 截图导入共用 */
export function useWatchlistBatchAdd() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ symbols, groupId }: WatchlistBatchAddInput) =>
      api.watchlistBatchAdd(symbols, '', groupId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: QK.watchlist })
      // 前缀匹配: 实际 key 为 ['watchlist-enriched', extColumnsParam],
      // 不能用 QK.watchlistEnriched()(= undefined) 精确匹配, 否则列表不刷新。
      qc.invalidateQueries({ queryKey: ['watchlist-enriched'] })
    },
  })
}
