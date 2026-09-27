// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { installTitleTooltip } from './titleTooltip'

type Win = Window & typeof globalThis

let uninstall: () => void
let fine = true

function setup() {
  document.body.innerHTML = `
    <button id="a" title="加自选"><span id="a-in">★</span></button>
    <button id="b" title="加监控">📡</button>
    <div id="plain">无提示</div>`
  const win = window as Win
  win.matchMedia = ((q: string) => ({ matches: fine && q.includes('pointer: fine') })) as unknown as Win['matchMedia']
  uninstall = installTitleTooltip(win)
}

const $ = (id: string) => document.getElementById(id)!
const tip = () => document.getElementById('tf-title-tooltip')!
const over = (el: Element, from?: Element) =>
  el.dispatchEvent(new MouseEvent('mouseover', { bubbles: true, relatedTarget: from ?? null, clientX: 10 }))
const out = (el: Element, to: Element | null) =>
  el.dispatchEvent(new MouseEvent('mouseout', { bubbles: true, relatedTarget: to }))

describe('[R553] 全站悬停提示', () => {
  beforeEach(() => { vi.useFakeTimers(); fine = true; setup() })
  afterEach(() => { uninstall(); vi.useRealTimers() })

  it('停 400ms 才弹, 期间原生 title 被挡住', () => {
    over($('a-in'))
    expect($('a').hasAttribute('title')).toBe(false)
    expect(tip().hidden).toBe(true)
    vi.advanceTimersByTime(399)
    expect(tip().hidden).toBe(true)
    vi.advanceTimersByTime(1)
    expect(tip().hidden).toBe(false)
    expect(tip().textContent).toBe('加自选')
    expect(tip().hasAttribute('data-open')).toBe(true)
  })

  it('离开后收起, title 原样放回', () => {
    over($('a'))
    vi.advanceTimersByTime(400)
    out($('a'), $('plain'))
    expect(tip().hidden).toBe(true)
    expect($('a').getAttribute('title')).toBe('加自选')
    expect(document.querySelectorAll('[data-tt-title]').length).toBe(0)
  })

  it('在元素内部挪动不重新计时', () => {
    over($('a'))
    vi.advanceTimersByTime(300)
    out($('a'), $('a-in')); over($('a-in'), $('a'))
    vi.advanceTimersByTime(100)
    expect(tip().hidden).toBe(false)
  })

  it('弹过之后移到相邻的按钮立即出现、不做动画', () => {
    over($('a'))
    vi.advanceTimersByTime(400)
    out($('a'), $('b')); over($('b'), $('a'))
    expect(tip().hidden).toBe(false)
    expect(tip().textContent).toBe('加监控')
    expect(tip().hasAttribute('data-instant')).toBe(true)
    expect($('a').getAttribute('title')).toBe('加自选')
  })

  it('悬停期间 title 被改写(React 重渲染): 取新值, 原生照样挡住', async () => {
    over($('a'))
    vi.advanceTimersByTime(400)
    $('a').setAttribute('title', '已在自选')
    await Promise.resolve() // MutationObserver 走微任务
    expect($('a').hasAttribute('title')).toBe(false)
    expect(tip().textContent).toBe('已在自选')
    out($('a'), $('plain'))
    expect($('a').getAttribute('title')).toBe('已在自选')
  })

  it('点一下就收起', () => {
    over($('a'))
    vi.advanceTimersByTime(400)
    $('a').dispatchEvent(new MouseEvent('mousedown', { bubbles: true }))
    expect(tip().hidden).toBe(true)
  })

  it('悬停中元素被卸掉: 提示跟着收起', () => {
    over($('a'))
    vi.advanceTimersByTime(400)
    $('a').remove()
    vi.advanceTimersByTime(250)
    expect(tip().hidden).toBe(true)
  })

  it('触屏(非精确指针)不接管, title 不动', () => {
    fine = false
    over($('a'))
    vi.advanceTimersByTime(1000)
    expect($('a').getAttribute('title')).toBe('加自选')
    expect(tip().hidden).toBe(true)
  })

  it('空 title 不弹', () => {
    $('b').setAttribute('title', '  ')
    over($('b'))
    vi.advanceTimersByTime(400)
    expect(tip().hidden).toBe(true)
  })
})
