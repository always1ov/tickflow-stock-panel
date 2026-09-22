import { clsx, type ClassValue } from 'clsx'
import { extendTailwindMerge } from 'tailwind-merge'

/**
 * [R400] `cn()` 必须认得**本项目自己的刻度**, 否则它会静默做错两件事。
 *
 * `twMerge` 只认 Tailwind 出厂的那套类名。R399 往 `tailwind.config.ts` 里加了
 * 五档字号(`text-micro`…`text-hero`)、两套间距(`s1..s6` / `g1..g4`)、三档容器宽,
 * 但**没人告诉 `twMerge` 它们是什么**。实测(未修时):
 *
 *   cn('text-micro', 'text-muted')  →  'text-muted'      ← **字号被丢了**
 *   cn('px-s1', 'px-s2')            →  'px-s1 px-s2'     ← **覆盖不掉**
 *   cn('rounded-btn', 'rounded-card') → 两个都留          ← 同上
 *
 * 第一条最毒: `text-micro` 不在 twMerge 已知的字号表里, 它就落到**文字颜色**那一组,
 * 于是和任何一个 `text-muted` / `text-accent` 撞组, 后写的把先写的顶掉 —— **字号
 * 整个消失, 不报错**。第二条是反过来: 两个 `px-` 都留着, 最终哪个生效由 CSS 里的
 * 先后决定, 也就是**调用方写的覆盖根本不叫覆盖**。
 *
 * 这两条现在还没咬到人, **只因为这批类名一处都还没用上**(R399 只接了线)。
 * 3.2 的基础件正要开始用它们 —— 先修这里, 不然后面每一处 `className` 覆盖
 * 都是一次运气。
 *
 * **只登记, 不发明**: 下面每一项都能在 `tailwind.config.ts` 里找到同名定义,
 * 这个文件不引入任何新档位。
 */
const twMerge = extendTailwindMerge({
  extend: {
    classGroups: {
      // R399 五档字号。不登记的话它们会被当成文字颜色(见上面第一条)。
      'font-size': [{ text: ['micro', 'body', 'title', 'page', 'hero'] }],
      // R399 容器宽三档
      'max-w': [{ 'max-w': ['read', 'wide'] }],
      // 语义圆角/阴影/时长/缓动 —— 这几组**早于 R399 就在用**(782 处 rounded-btn、
      // 246 处 rounded-card), 一直覆盖不掉, 一并登记。
      rounded: [{ rounded: ['btn', 'card', 'input', 'dialog'] }],
      'rounded-t': [{ 'rounded-t': ['btn', 'card', 'input', 'dialog'] }],
      'rounded-r': [{ 'rounded-r': ['btn', 'card', 'input', 'dialog'] }],
      'rounded-b': [{ 'rounded-b': ['btn', 'card', 'input', 'dialog'] }],
      'rounded-l': [{ 'rounded-l': ['btn', 'card', 'input', 'dialog'] }],
      shadow: [{ shadow: ['card', 'pop', 'dialog'] }],
      duration: [{ duration: ['press', 'hover', 'expand', 'enter'] }],
      ease: [{ ease: ['smooth', 'out-strong', 'in-out-strong', 'drawer'] }],
      transition: [{ transition: ['ui'] }],
    },
    theme: {
      // R399 两套间距刻度。`theme.spacing` 一处登记, `p-/m-/gap-/w-/h-/space-`
      // 等所有吃 spacing 的组**一起**认得 —— 逐组去写必漏。
      spacing: ['s1', 's2', 's3', 's4', 's5', 's6', 'g1', 'g2', 'g3', 'g4'],
    },
  },
})

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}
