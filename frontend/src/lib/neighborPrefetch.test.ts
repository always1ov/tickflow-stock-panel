// [R348] 这个文件原来用 `node:test`, 而**项目里没有任何脚本会调用它** ——
// 一个没人跑的测试, 守的东西等于没守。上游这次带进了 vitest(为它自己的
// Indices.test.tsx), 顺手把这里换成同一个运行器, 并把 `pnpm test` 扩成跑全部,
// 它才真正开始工作。断言库仍用 node:assert, 不为换运行器把断言也重写一遍。
import assert from 'node:assert/strict'
import { test } from 'vitest'
import { QueryClient, QueryObserver } from '@tanstack/react-query'
import { scheduleNeighborPrefetch } from './neighborPrefetch.ts'

const tick = () => new Promise(resolve => setTimeout(resolve, 10))
function deferred() {
  let resolve!: () => void
  const promise = new Promise<void>(done => { resolve = done })
  return { promise, resolve }
}

test('foreground requests finish before serial neighbor requests start', async () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
  const foreground = deferred()
  const neighbor = deferred()
  const calls: string[] = []
  const observer = new QueryObserver(client, {
    queryKey: ['kline-minute', 'current'],
    queryFn: async () => { await foreground.promise; return [] },
  })
  const unsubscribe = observer.subscribe(() => {})
  const stop = scheduleNeighborPrefetch(client, 'current', [
    async () => { calls.push('first'); await neighbor.promise },
    async () => { calls.push('second') },
  ])
  try {
    await tick()
    assert.deepEqual(calls, [])
    foreground.resolve()
    await tick()
    assert.deepEqual(calls, ['first'])
    neighbor.resolve()
    await tick()
    assert.deepEqual(calls, ['first', 'second'])
  } finally { stop(); unsubscribe(); client.clear() }
})

test('new foreground work pauses the queue; errors allow it to resume', async () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
  const neighbor = deferred()
  const foreground = deferred()
  const calls: string[] = []
  const stop = scheduleNeighborPrefetch(client, 'current', [
    async () => { calls.push('first'); await neighbor.promise },
    async () => { calls.push('second'); throw new Error('prefetch failed') },
    async () => { calls.push('third') },
  ])
  await tick()
  const observer = new QueryObserver(client, {
    queryKey: ['financials', 'metrics', 'current'],
    queryFn: async () => { await foreground.promise; throw new Error('unavailable') },
  })
  const unsubscribe = observer.subscribe(() => {})
  try {
    neighbor.resolve()
    await tick()
    assert.deepEqual(calls, ['first'])
    foreground.resolve()
    await tick(); await tick()
    assert.deepEqual(calls, ['first', 'second', 'third'])
  } finally { stop(); unsubscribe(); client.clear() }
})

test('switching or closing stops pending and chained work', async () => {
  const client = new QueryClient()
  const neighbor = deferred()
  const calls: string[] = []
  const stop = scheduleNeighborPrefetch(client, 'current', [
    async () => { calls.push('first'); await neighbor.promise },
    async () => { calls.push('second') },
  ])
  await tick()
  stop()
  neighbor.resolve()
  await tick()
  assert.deepEqual(calls, ['first'])
  const stopBeforeStart = scheduleNeighborPrefetch(client, 'next', [
    async () => { calls.push('obsolete') },
  ])
  stopBeforeStart()
  await tick()
  assert.deepEqual(calls, ['first'])
  client.clear()
})

test('prefetch reuses a fresh cache entry without another network request', async () => {
  const client = new QueryClient({ defaultOptions: { queries: { gcTime: Infinity } } })
  const key = ['kline', 'neighbor']
  client.setQueryData(key, { rows: [] })
  let requests = 0
  let completed = false
  const stop = scheduleNeighborPrefetch(client, 'current', [
    () => client.prefetchQuery({
      queryKey: key,
      staleTime: 30_000,
      queryFn: async () => { requests++; return { rows: [] } },
    }),
    async () => { completed = true },
  ])
  try {
    await tick(); await tick()
    assert.equal(completed, true)
    assert.equal(requests, 0)
  } finally { stop(); client.clear() }
})
