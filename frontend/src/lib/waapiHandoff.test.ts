import { describe, expect, it, vi } from 'vitest'
import { installWaapiHandoff } from './waapiHandoff'

function fakeProto() {
  const log: string[] = []
  const proto = {
    playState: 'running' as AnimationPlayState,
    commitStyles() { log.push('commit') },
    cancel() { log.push('cancel') },
  }
  return { proto: proto as unknown as Animation & { playState: AnimationPlayState }, log }
}

describe('[R550] WAAPI 交接不留空帧', () => {
  it('撤掉已跑完的动画前先把终值写进行内样式', () => {
    const { proto, log } = fakeProto()
    installWaapiHandoff(proto)
    const a = Object.create(proto) as Animation
    Object.defineProperty(a, 'playState', { value: 'finished' })
    a.cancel()
    expect(log).toEqual(['commit', 'cancel'])
  })

  it('中途打断(还在跑)不写终值', () => {
    const { proto, log } = fakeProto()
    installWaapiHandoff(proto)
    const a = Object.create(proto) as Animation
    Object.defineProperty(a, 'playState', { value: 'running' })
    a.cancel()
    expect(log).toEqual(['cancel'])
  })

  it('目标脱离渲染树时 commitStyles 抛错也照样撤掉', () => {
    const { proto, log } = fakeProto()
    proto.commitStyles = vi.fn(() => { throw new Error('not rendered') })
    installWaapiHandoff(proto)
    const a = Object.create(proto) as Animation
    Object.defineProperty(a, 'playState', { value: 'finished' })
    expect(() => a.cancel()).not.toThrow()
    expect(log).toEqual(['cancel'])
  })

  it('装两次不叠两层', () => {
    const { proto, log } = fakeProto()
    installWaapiHandoff(proto)
    installWaapiHandoff(proto)
    const a = Object.create(proto) as Animation
    Object.defineProperty(a, 'playState', { value: 'finished' })
    a.cancel()
    expect(log).toEqual(['commit', 'cancel'])
  })

  it('没有 WAAPI 的环境(jsdom)直接跳过', () => {
    expect(() => installWaapiHandoff(undefined)).not.toThrow()
  })
})
