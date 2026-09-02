#!/usr/bin/env node
// [fork R155] 从 Radix Colors(Slate 骨架 / Indigo 强调 / Red·Green·Amber 语义)生成
// index.css 的语义 token(OKLCH 三元组), 并打印核对表。
//
// 用法: node scripts/gen-radix-theme.cjs   → 把打印出的两段贴进 src/index.css。
//
// 规则(为什么不是"直接抄 Radix 的 12 档"):
//  - 骨架色(base/surface/elevated/border/fg-primary)直接取 Radix 档位的色值。
//  - 需要**对比度保证**的文字与强调色, 取 Radix 该档的色相与彩度, 明度按目标
//    对比度反解 —— R138/R141 已经用真实界面验证过这些目标值(亮 muted 6.9:1、
//    暗 accent 4.7:1 等), 换色板不能把可读性换掉。
//  - 强调色: Indigo 色相(267°), 彩度压到 0.13(Radix indigo9 是 0.19) —— 用户
//    要的是"低饱和靛蓝"。
//  - 涨跌: 红涨绿跌是 A 股语义, 用 Radix Red / Green; 状态色 Amber 做 warning,
//    danger 与红涨同色(两者语境不重叠: 破坏性按钮/错误提示 vs 价格格子)。
const c = require('@radix-ui/colors')

const hex2rgb = h => [1, 3, 5].map(i => parseInt(h.slice(i, i + 2), 16) / 255)
const lin = v => (v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4)
const gam = v => (v <= 0.0031308 ? 12.92 * v : 1.055 * v ** (1 / 2.4) - 0.055)
function rgb2oklch([r, g, b]) {
  const [R, G, B] = [lin(r), lin(g), lin(b)]
  const l = Math.cbrt(0.4122214708 * R + 0.5363325363 * G + 0.0514459929 * B)
  const m = Math.cbrt(0.2119034982 * R + 0.6806995451 * G + 0.1073969566 * B)
  const s = Math.cbrt(0.0883024619 * R + 0.2817188376 * G + 0.6299787005 * B)
  const L = 0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s
  const a = 1.9779984951 * l - 2.428592205 * m + 0.4505937099 * s
  const bb = 0.0259040371 * l + 0.7827717662 * m - 0.808675766 * s
  const C = Math.hypot(a, bb)
  let H = (Math.atan2(bb, a) * 180) / Math.PI
  if (H < 0) H += 360
  return [L, C, H]
}
// → 线性 sRGB(未做 gamma 编码)。算亮度时**直接**用这些值, 不要再 lin() 一次(R138 踩过的坑)
function oklch2linear([L, C, H]) {
  const a = C * Math.cos((H * Math.PI) / 180), b = C * Math.sin((H * Math.PI) / 180)
  const l_ = L + 0.3963377774 * a + 0.2158037573 * b
  const m_ = L - 0.1055613458 * a - 0.0638541728 * b
  const s_ = L - 0.0894841775 * a - 1.291485548 * b
  const l = l_ ** 3, m = m_ ** 3, s = s_ ** 3
  return [
    +4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
    -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
    -0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s,
  ]
}
const inGamut = lch => oklch2linear(lch).every(v => v >= -1e-6 && v <= 1 + 1e-6)
const Y = lch => { const [r, g, b] = oklch2linear(lch).map(v => Math.min(1, Math.max(0, v))); return 0.2126 * r + 0.7152 * g + 0.0722 * b }
const contrast = (a, b) => { const ya = Y(a), yb = Y(b); const [hi, lo] = ya > yb ? [ya, yb] : [yb, ya]; return (hi + 0.05) / (lo + 0.05) }
const toHex = lch => '#' + oklch2linear(lch).map(v => Math.round(gam(Math.min(1, Math.max(0, v))) * 255).toString(16).padStart(2, '0')).join('')
const L3 = lch => lch.map((v, i) => (i === 2 ? v.toFixed(2) : v.toFixed(4))).join(' ')
const of = h => rgb2oklch(hex2rgb(h))

// 明度按目标对比度反解: 从 startL 出发沿 dir(-1 变暗 / +1 变亮)走到对比度 ≥ target 为止。
// 出色域时先压彩度(只为色域, 每次 -2%), 色相不动。
function solve(target, C, H, bg, startL, dir) {
  let L = startL, Cc = C
  for (let i = 0; i < 2000; i++) {
    let lch = [L, Cc, H]
    while (!inGamut(lch) && Cc > 0.005) { Cc *= 0.98; lch = [L, Cc, H] }
    if (contrast(lch, bg) >= target) return lch
    L += dir * 0.0005
    if (L < 0 || L > 1) break
  }
  return [L, Cc, H]
}
// 已经达标的 Radix 档位原样用; 不达标才沿 dir 反解
function ensure(target, lch, bg, dir) {
  return contrast(lch, bg) >= target ? lch : solve(target, lch[1], lch[2], bg, lch[0], dir)
}

const INDIGO_H = of(c.indigo.indigo9)[2]
const INDIGO_C = 0.13   // 低饱和: Radix indigo9 的彩度是 0.191

const out = []
const line = (name, lch, note) => out.push(`  --${name}: ${L3(lch)};${note ? ` /* ${toHex(lch)} ${note} */` : ` /* ${toHex(lch)} */`}`)

// ---------------- 亮色 ----------------
{
  const S = c.slate, white = of('#ffffff')
  const base = of(S.slate3), surface = white, elevated = of(S.slate4), border = of(S.slate7)
  const fgP = of(S.slate12)
  const s11 = of(S.slate11)
  const fgS = ensure(7.6, s11, surface, -1)
  const fgM = ensure(6.9, s11, surface, -1)
  const accent = solve(5.0, INDIGO_C, INDIGO_H, surface, 0.62, -1)
  const bull = ensure(4.9, of(c.red.red11), surface, -1)
  const bear = ensure(4.9, of(c.green.green11), surface, -1)
  const warning = ensure(4.6, of(c.amber.amber11), surface, -1)
  out.push('/* ===== 亮色(:root) —— Radix Slate 3/4/7/12 骨架, Indigo 267° C0.13 强调 ===== */')
  line('base', base, 'slate3 页面底'); line('surface', surface, '卡片'); line('elevated', elevated, 'slate4')
  line('border', border, 'slate7'); line('fg-primary', fgP, `slate12 ${contrast(fgP, surface).toFixed(1)}:1`)
  line('fg-secondary', fgS, `slate11 色相, ${contrast(fgS, surface).toFixed(1)}:1`)
  line('fg-muted', fgM, `slate11 色相, ${contrast(fgM, surface).toFixed(1)}:1`)
  line('accent', accent, `indigo 低饱和 ${contrast(accent, surface).toFixed(2)}:1`)
  line('accent-text', accent, '= accent(白底上一个值两用)')
  line('bull', bull, `red11 红涨 ${contrast(bull, surface).toFixed(2)}:1`)
  line('bear', bear, `green11 绿跌 ${contrast(bear, surface).toFixed(2)}:1`)
  line('warning', warning, `amber11 ${contrast(warning, surface).toFixed(2)}:1`)
  line('danger', bull, '= bull')
  out.push(`  亮 核对: base→surface ΔL ${(surface[0] - base[0]).toFixed(3)} | border/40 vs white ${(contrast([border[0]*0.4+0.6, border[1]*0.4, border[2]], surface)).toFixed(2)} | muted/50 ≈ ${contrast([(fgM[0] + 1) / 2, fgM[1] / 2, fgM[2]], surface).toFixed(2)}`)
}
// ---------------- 暗色 ----------------
{
  const D = c.slateDark
  // [R162] 底不用 slateDark1(#111113, 本身偏灰): 压到 L 0.135 的近黑并带一点靛蓝冷调 ——
  // 有力感来自深与对比, 不是彩度。卡片/悬浮/边框仍是 Radix 4/6/7 档。
  const base = [0.135, 0.012, 265], surface = of(D.slate4), elevated = of(D.slate6), border = of(D.slate7)
  const fgP = of(D.slate12), fgS = of(D.slate11)
  const fgM = solve(5.2, fgS[1], fgS[2], surface, 0.55, +1)
  const accentText = solve(4.7, INDIGO_C, INDIGO_H, surface, 0.55, +1)
  const accent = solve(4.5, INDIGO_C, INDIGO_H, of('#ffffff'), 0.62, -1)   // 实底: 白字 ≥4.5
  const bull = ensure(4.7, of(c.redDark.red10), surface, +1)
  const bear = ensure(4.7, of(c.greenDark.green10), surface, +1)
  const warning = ensure(4.7, of(c.amberDark.amber11), surface, +1)
  out.push('\n/* ===== 暗色(html.dark) —— 近黑底 + Radix Slate Dark 4/6/7/11/12 ===== */')
  line('base', base, '近黑底(靛蓝冷调), 比 slateDark1 更深'); line('surface', surface, `slateDark4 ΔL ${(surface[0] - base[0]).toFixed(3)} over base`)
  line('elevated', elevated, `slateDark6 ΔL ${(elevated[0] - surface[0]).toFixed(3)} over surface`)
  line('border', border, `slateDark7 ΔL ${(border[0] - base[0]).toFixed(3)} over base`)
  line('fg-primary', fgP, `slateDark12 ${contrast(fgP, surface).toFixed(1)}:1`)
  line('fg-secondary', fgS, `slateDark11 ${contrast(fgS, surface).toFixed(1)}:1`)
  line('fg-muted', fgM, `slateDark11 色相, ${contrast(fgM, surface).toFixed(2)}:1`)
  line('accent', accent, `indigo 实底, 白字 ${contrast(accent, of('#ffffff')).toFixed(2)}:1`)
  line('accent-text', accentText, `indigo 文字 ${contrast(accentText, surface).toFixed(2)}:1 vs surface`)
  line('bull', bull, `red10 红涨 ${contrast(bull, surface).toFixed(2)}:1`)
  line('bear', bear, `green10 绿跌 ${contrast(bear, surface).toFixed(2)}:1`)
  line('warning', warning, `amber11 ${contrast(warning, surface).toFixed(2)}:1`)
  line('danger', bull, '= bull')
  const mix = (a, b, t) => [a[0] * t + b[0] * (1 - t), a[1] * t, a[2]]
  out.push(`  暗 核对: surface/40 over base ΔL ${(mix(surface, base, 0.4)[0] - base[0]).toFixed(3)} | border/40 ΔL ${(mix(border, base, 0.4)[0] - base[0]).toFixed(3)} | muted/50 vs surface ${contrast(mix(fgM, surface, 0.5), surface).toFixed(2)}`)
}
// ---------------- 图表调色板(theme.ts, 画布不吃 CSS 变量) ----------------
out.push('\n/* theme.ts 图表用 hex: */')
out.push(`  DARK  text ${c.slateDark.slate11} textStrong ${c.slateDark.slate12} border ${c.slateDark.slate6} crosshairLabelBg ${c.slateDark.slate7} tooltipBg ${c.slateDark.slate2} infoBar ${c.slateDark.slate4}`)
out.push(`  LIGHT text ${c.slate.slate11} textStrong ${c.slate.slate12} border ${c.slate.slate7} crosshairLabelBg ${c.slate.slate9} tooltipBg #ffffff infoBar ${c.slate.slate3}`)
console.log(out.join('\n'))
