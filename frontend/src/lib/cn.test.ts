/**
 * [R400] 钉住 `cn()` **认得本项目自己的刻度**。
 *
 * 为什么这条值得单独一组: 它坏掉的样子是**静默的**。`text-micro` 落错组之后
 * 字号整个消失、`px-s2` 覆盖不掉之后最终宽度由 CSS 先后决定 —— 两种都不报错、
 * tsc 不管、eslint 不管、build 照过, 只有人眼在某一页上看出"这儿怎么不对"。
 * 而这正是 3.2 起所有基础件赖以工作的那一层。
 *
 * 钉的是**性质不是实现**: 断言全部写成"后写的盖掉先写的"与"不同组互不相干",
 * 换掉 tailwind-merge 的版本或改写配置形状都不会误报。
 */
import { describe, it, expect } from 'vitest'
import { cn } from './cn'

/** 出现在结果里的、属于同一组的类名集合(用来断言"只剩一个") */
function pick(out: string, candidates: string[]) {
  const set = new Set(out.split(' '))
  return candidates.filter(c => set.has(c))
}

describe('cn() 认得 R399 的规范刻度', () => {
  it('五档字号每一档都当字号用, 不会被文字颜色吃掉', () => {
    // **不要写成 `cn('text-micro','text-body')` 然后断言只剩后者** —— 那条
    // 在修之前也是绿的: 两个都被当成颜色时, 颜色组照样只留后写的那个。
    // 一条"对错两种实现都绿"的断言等于没有(变异测试当场证过)。
    // 真正有区分力的是**它与一个颜色并存**。
    for (const tier of ['text-micro', 'text-body', 'text-title', 'text-page', 'text-hero']) {
      const out = cn(tier, 'text-muted')
      expect(out, `${tier} 被当成了颜色`).toContain(tier)
      expect(out).toContain('text-muted')
      // 同时它仍然是字号: 后面跟**另一**档字号要能把它顶掉
      const other = tier === 'text-hero' ? 'text-micro' : 'text-hero'
      expect(pick(cn(tier, other), [tier, other])).toEqual([other])
    }
  })

  it('规范字号与 Tailwind 旧档位也互相覆盖 —— 迁移中两套会并存', () => {
    expect(pick(cn('text-xs', 'text-body'), ['text-xs', 'text-body'])).toEqual(['text-body'])
    expect(pick(cn('text-body', 'text-xs'), ['text-xs', 'text-body'])).toEqual(['text-xs'])
  })

  it('字号与文字颜色是两组, 谁也不许吃掉谁', () => {
    // 这一条是本组最要紧的: 修之前 `text-micro` 被当成颜色, 与 `text-muted`
    // 撞组, **字号被静默丢掉**。
    const out = cn('text-micro', 'text-muted')
    expect(out).toContain('text-micro')
    expect(out).toContain('text-muted')
    // 反过来写也一样(撞组的话这一侧丢的是颜色)
    const rev = cn('text-muted', 'text-micro')
    expect(rev).toContain('text-micro')
    expect(rev).toContain('text-muted')
  })

  it('两套间距刻度可以互相覆盖, 也能被 Tailwind 原生间距覆盖', () => {
    expect(pick(cn('px-s1', 'px-s2'), ['px-s1', 'px-s2'])).toEqual(['px-s2'])
    expect(pick(cn('px-g4', 'px-s3'), ['px-g4', 'px-s3'])).toEqual(['px-s3'])
    expect(pick(cn('px-4', 'px-s2'), ['px-4', 'px-s2'])).toEqual(['px-s2'])
    expect(pick(cn('px-s2', 'px-4'), ['px-4', 'px-s2'])).toEqual(['px-4'])
  })

  it('间距只登记一次, 但 p-/m-/gap-/w-/h- 全都跟着认得', () => {
    for (const p of ['p', 'pt', 'pb', 'pl', 'pr', 'm', 'mt', 'gap', 'gap-x', 'w', 'h', 'space-y']) {
      expect(pick(cn(`${p}-s1`, `${p}-s3`), [`${p}-s1`, `${p}-s3`])).toEqual([`${p}-s3`])
    }
  })

  it('横纵向间距互不相干 —— px 不该吃掉 py', () => {
    const out = cn('px-s2', 'py-g3')
    expect(out).toContain('px-s2')
    expect(out).toContain('py-g3')
  })

  it('语义圆角互相覆盖, 也能被 Tailwind 原生圆角覆盖', () => {
    expect(pick(cn('rounded-btn', 'rounded-card'), ['rounded-btn', 'rounded-card'])).toEqual(['rounded-card'])
    expect(pick(cn('rounded-lg', 'rounded-btn'), ['rounded-lg', 'rounded-btn'])).toEqual(['rounded-btn'])
    expect(pick(cn('rounded-card', 'rounded-full'), ['rounded-card', 'rounded-full'])).toEqual(['rounded-full'])
  })

  it('单边圆角与整体圆角不是一组, 也不该被整体吃掉方向', () => {
    expect(pick(cn('rounded-l-btn', 'rounded-l-card'), ['rounded-l-btn', 'rounded-l-card']))
      .toEqual(['rounded-l-card'])
  })

  it('容器宽三档互相覆盖', () => {
    expect(pick(cn('max-w-read', 'max-w-wide'), ['max-w-read', 'max-w-wide'])).toEqual(['max-w-wide'])
    expect(pick(cn('max-w-wide', 'max-w-[900px]'), ['max-w-wide', 'max-w-[900px]'])).toEqual(['max-w-[900px]'])
  })

  it('语义时长/缓动/过渡属性也认得', () => {
    expect(pick(cn('duration-hover', 'duration-enter'), ['duration-hover', 'duration-enter'])).toEqual(['duration-enter'])
    expect(pick(cn('ease-smooth', 'ease-out'), ['ease-smooth', 'ease-out'])).toEqual(['ease-out'])
    expect(pick(cn('transition-ui', 'transition-colors'), ['transition-ui', 'transition-colors'])).toEqual(['transition-colors'])
  })
})
