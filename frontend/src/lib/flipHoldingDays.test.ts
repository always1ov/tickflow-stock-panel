import assert from 'node:assert/strict'
import { test } from 'vitest'
import { getFlipHoldingDays } from './flipHoldingDays'

test('买入当天是第 1 个交易日', () => {
  const days = getFlipHoldingDays(
    [{ symbol: 'A', date: '2026-09-11', act: 'buy' }],
    [{ date: '2026-09-11' }], '2026-09-11',
  )
  assert.equal(days.get('A'), 1)
})

test('周五买入到下周一只算 2 个交易日', () => {
  assert.equal(getFlipHoldingDays(
    [{ symbol: 'A', date: '2026-09-11', act: 'buy' }],
    [{ date: '2026-09-11' }, { date: '2026-09-14' }], '2026-09-14',
  ).get('A'), 2)
})

test('日历中的长休市间隔不补成自然日', () => {
  assert.equal(getFlipHoldingDays(
    [{ symbol: 'A', date: '2026-09-30', act: 'buy' }],
    [{ date: '2026-09-30' }, { date: '2026-10-08' }], '2026-10-08',
  ).get('A'), 2)
})

test('同一轮的再次买入不重置首次买入日', () => {
  assert.equal(getFlipHoldingDays(
    [{ symbol: 'A', date: '2026-09-14', act: 'buy' },
      { symbol: 'A', date: '2026-09-15', act: 'buy' }],
    [{ date: '2026-09-14' }, { date: '2026-09-15' }, { date: '2026-09-16' }],
    '2026-09-16',
  ).get('A'), 3)
})

test('清仓后买回重新从第 1 天开始', () => {
  assert.equal(getFlipHoldingDays(
    [{ symbol: 'A', date: '2026-09-14', act: 'buy' },
      { symbol: 'A', date: '2026-09-15', act: 'sell' },
      { symbol: 'A', date: '2026-09-16', act: 'buy' }],
    [{ date: '2026-09-14' }, { date: '2026-09-15' }, { date: '2026-09-16' }],
    '2026-09-16',
  ).get('A'), 1)
})

test('不同标的各自计数，已清仓标的不再输出', () => {
  const days = getFlipHoldingDays(
    [{ symbol: 'A', date: '2026-09-14', act: 'buy' },
      { symbol: 'B', date: '2026-09-15', act: 'buy' },
      { symbol: 'C', date: '2026-09-14', act: 'buy' },
      { symbol: 'C', date: '2026-09-15', act: 'sell' }],
    [{ date: '2026-09-14' }, { date: '2026-09-15' }, { date: '2026-09-16' }],
    '2026-09-16',
  )
  assert.equal(days.get('A'), 3)
  assert.equal(days.get('B'), 2)
  assert.equal(days.has('C'), false)
})

test('封板顺延按实际成交日计数，不按信号日', () => {
  const order = { symbol: 'A', date: '2026-09-16', act: 'buy' as const,
    signal_date: '2026-09-14', delayed: true }
  assert.equal(getFlipHoldingDays([order],
    [{ date: '2026-09-14' }, { date: '2026-09-15' }, { date: '2026-09-16' }],
    '2026-09-16',
  ).get('A'), 1)
})

test('按模拟盘最后一天截止，未来的流水和日期不混进来', () => {
  assert.equal(getFlipHoldingDays(
    [{ symbol: 'A', date: '2026-09-14', act: 'buy' },
      { symbol: 'A', date: '2026-09-16', act: 'sell' }],
    [{ date: '2026-09-14' }, { date: '2026-09-15' }, { date: '2026-09-16' }],
    '2026-09-15',
  ).get('A'), 2)
})

test('缺少本轮买入记录或日历时不给虚假的 0 天或 1 天', () => {
  assert.equal(getFlipHoldingDays([], [{ date: '2026-09-16' }], '2026-09-16').size, 0)
  const orders = [{ symbol: 'A', date: '2026-09-14', act: 'buy' as const }]
  assert.equal(getFlipHoldingDays(orders, [], '2026-09-16').size, 0)
  assert.equal(getFlipHoldingDays(orders, [{ date: '2026-09-16' }], '2026-09-16').size, 0)
  assert.equal(getFlipHoldingDays(orders, [{ date: '2026-09-14' }], '2026-09-16').size, 0)
  assert.equal(getFlipHoldingDays(orders, [{ date: '2026-09-14' }], null).size, 0)
})

test('只读缓存：支持乱序输入，重复日期不会重复计数', () => {
  const orders = Object.freeze([
    Object.freeze({ symbol: 'A', date: '2026-09-16', act: 'buy' as const }),
    Object.freeze({ symbol: 'A', date: '2026-09-14', act: 'buy' as const }),
    Object.freeze({ symbol: 'A', date: '2026-09-15', act: 'sell' as const }),
  ])
  const nav = Object.freeze([
    Object.freeze({ date: '2026-09-17' }), Object.freeze({ date: '2026-09-14' }),
    Object.freeze({ date: '2026-09-16' }), Object.freeze({ date: '2026-09-15' }),
    Object.freeze({ date: '2026-09-17' }),
  ])
  const before = JSON.stringify({ orders, nav })
  assert.equal(getFlipHoldingDays(orders, nav, '2026-09-17').get('A'), 2)
  assert.equal(JSON.stringify({ orders, nav }), before)
})
