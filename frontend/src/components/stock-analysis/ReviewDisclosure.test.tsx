// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { ReviewDisclosure } from './ReviewDisclosure'

let host: HTMLDivElement
let root: Root

beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true })
  host = document.createElement('div')
  document.body.appendChild(host)
  root = createRoot(host)
})
afterEach(async () => {
  await act(async () => root.unmount())
  host.remove()
})

/**
 * [R760] 窄列那个「?」现在是共用件的一个形态, 不再是 `EvidencePanel` 里另写的一套。
 * 这条守的是行为本身(不靠源码字符串): 收起时不把内容挂进 DOM, 点开才挂上,
 * 开合状态回传给调用方持久化。
 */
it('[R760] 窄列问号: 收起时不渲染内容, 点开才挂上', async () => {
  const onOpenChange = vi.fn()
  await act(async () => root.render(
    <ReviewDisclosure icon label="依据" title="依据 · 3 项读数" onOpenChange={onOpenChange}>
      <div>逐项读数</div>
    </ReviewDisclosure>,
  ))
  const btn = host.querySelector('button')
  expect(btn).not.toBeNull()
  expect(btn?.textContent).toBe('?')
  expect(btn?.getAttribute('aria-expanded')).toBe('false')
  expect(btn?.getAttribute('title')).toBe('依据 · 3 项读数')
  expect(host.textContent).not.toContain('逐项读数')

  await act(async () => btn?.click())
  expect(btn?.getAttribute('aria-expanded')).toBe('true')
  expect(host.textContent).toContain('逐项读数')
  expect(onOpenChange).toHaveBeenLastCalledWith(true)

  await act(async () => btn?.click())
  expect(btn?.getAttribute('aria-expanded')).toBe('false')
  expect(host.textContent).not.toContain('逐项读数')
  expect(onOpenChange).toHaveBeenLastCalledWith(false)
})

it('[R760] 两种外观共用同一份开合逻辑', async () => {
  const onOpenChange = vi.fn()
  await act(async () => root.render(
    <ReviewDisclosure label="依据 · 3 项读数" onOpenChange={onOpenChange}>
      <div>逐项读数</div>
    </ReviewDisclosure>,
  ))
  expect(host.textContent).not.toContain('逐项读数')
  const btn = host.querySelector('button')
  expect(btn?.getAttribute('aria-expanded')).toBe('false')
  await act(async () => btn?.click())
  expect(host.textContent).toContain('逐项读数')
  expect(btn?.getAttribute('aria-expanded')).toBe('true')
  expect(onOpenChange).toHaveBeenLastCalledWith(true)
})
