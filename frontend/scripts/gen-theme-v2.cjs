#!/usr/bin/env node
/**
 * [fork R317] 「分层清晰 · 语义唯一」主题色板生成器 —— 产出 index.css 的
 * :root 与 html.dark 两段骨架/语义 token, 并打印对比度核对表。
 *
 * 用法: node scripts/gen-theme-v2.cjs          只打印核对表
 *       node scripts/gen-theme-v2.cjs --emit   额外输出可直接粘贴的 CSS
 *
 * ── 这次重做的四条设计原则 ─────────────────────────────────────────────
 *
 * 1. **色相即语义, 跨模式不变**。
 *    红涨 / 绿跌 / 琥珀警示的**色相**在亮暗两套里取同一个值(22° / 158° / 72°),
 *    只有明度随背景反解。改之前亮色红涨是 25.17°、暗色是 28.54° —— 同一个
 *    「涨」在两种模式下是两种红, 这是歧义的根源之一。
 *
 * 2. **文字三级必须真正分得开**。
 *    改之前亮色的 fg-secondary(0.4450) 与 fg-muted(0.4675) 只差 ΔL 0.0225 ——
 *    二级文字和三级文字在屏幕上几乎同色, 「层级」形同虚设。现在拉到
 *    ΔL ≥ 0.09, 三级各自有明确的对比度预算。
 *
 * 3. **次级面在两种模式下都要看得见**。
 *    `bg-elevated` 全站用了 435 次(hover 行 / 次级面板)。亮色下它只比页面底
 *    深 ΔL 0.024 —— 而暗色下这个差是 0.105。同一处在暗色里明确、在亮色里
 *    几乎不可见。现在亮色抬到 ΔL ≥ 0.043。
 *
 * 4. **涨跌在灰度下也要能分**。
 *    红绿对红绿色盲会同时塌向黄褐。把两色的**明度差**拉大到 ΔL ≥ 0.07,
 *    即使在灰度截图里也能分辨, 而不是只靠色相。
 */
const fs = require('fs')
const path = require('path')

// ── 色彩数学 (sRGB <-> OKLab/OKLCH), 与 gen-radix-theme.cjs 同一套 ──────
const lin = (u) => (u <= 0.04045 ? u / 12.92 : ((u + 0.055) / 1.055) ** 2.4)
const unlin = (u) => (u <= 0.0031308 ? 12.92 * u : 1.055 * u ** (1 / 2.4) - 0.055)
const clamp01 = (v) => Math.min(1, Math.max(0, v))

function oklch2rgb([L, C, H]) {
  const a = C * Math.cos((H * Math.PI) / 180)
  const b = C * Math.sin((H * Math.PI) / 180)
  const l_ = L + 0.3963377774 * a + 0.2158037573 * b
  const m_ = L - 0.1055613458 * a - 0.0638541728 * b
  const s_ = L - 0.0894841775 * a - 1.291485548 * b
  const l = l_ ** 3, m = m_ ** 3, s = s_ ** 3
  const r = +4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s
  const g = -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s
  const bb = -0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s
  return [r, g, bb]
}
const inGamut = ([r, g, b]) => [r, g, b].every((v) => v >= -1e-4 && v <= 1 + 1e-4)

/** OKLCH -> sRGB。超出色域时逐步降彩度收回(保色相与明度)。 */
function toRgb([L, C, H]) {
  let c = C
  for (let i = 0; i < 200; i++) {
    const rgb = oklch2rgb([L, c, H])
    if (inGamut(rgb)) return rgb.map(clamp01)
    c -= C / 200
  }
  return oklch2rgb([L, 0, H]).map(clamp01)
}
const hex = ([L, C, H]) =>
  '#' + toRgb([L, C, H]).map((v) => Math.round(unlin(v) * 255).toString(16).padStart(2, '0')).join('')

/** 相对亮度 (WCAG) —— 直接用线性 sRGB, 不要再 lin() 一次 */
function lum([L, C, H]) {
  const [r, g, b] = oklch2rgb([L, C, H])
  return 0.2126 * clamp01(r) + 0.7152 * clamp01(g) + 0.0722 * clamp01(b)
}
function contrast(fg, bg) {
  const a = lum(fg), b = lum(bg)
  const [hi, lo] = a > b ? [a, b] : [b, a]
  return (hi + 0.05) / (lo + 0.05)
}
/**
 * 有效对比度: 前景带 alpha 叠在背景上。
 * 合成发生在**伽马编码后的 sRGB** 空间(CSS 的实际行为), 算亮度时才转回线性。
 */
function contrastAlpha(fg, bg, alpha) {
  const enc = (c) => oklch2rgb(c).map((v) => unlin(clamp01(v)))
  const f = enc(fg), b = enc(bg)
  const mixed = f.map((v, i) => v * alpha + b[i] * (1 - alpha))
  const Y = (v) => 0.2126 * lin(v[0]) + 0.7152 * lin(v[1]) + 0.0722 * lin(v[2])
  const [hi, lo] = Y(mixed) > Y(b) ? [Y(mixed), Y(b)] : [Y(b), Y(mixed)]
  return (hi + 0.05) / (lo + 0.05)
}
/**
 * 反解明度: 在给定色相/彩度下, 找到恰好达到目标对比度的 L。
 *
 * **必须判方向**: 对比度对 L 的单调性取决于底色 —— 白底上 L 越大对比越低,
 * 深底上 L 越大对比越高。第一版没判方向, 亮色的语义色全被推到 0 或 1 两个
 * 极值上(算出来是纯黑/纯白)。这里先探两端定单调方向再二分。
 */
function solveL(hue, chroma, bg, target) {
  const f = (L) => contrast([L, chroma, hue], bg)
  const increasing = f(1) > f(0)
  let lo = 0, hi = 1
  for (let i = 0; i < 60; i++) {
    const mid = (lo + hi) / 2
    const below = f(mid) < target
    if (increasing === below) lo = mid
    else hi = mid
  }
  return (lo + hi) / 2
}

// ── 设计常量 ─────────────────────────────────────────────────────────────
const HUE = { bull: 22, bear: 158, warn: 70, slate: 286.3, accentLT: 267.01, accentDK: 259.81 }

const SKEL_LIGHT = {
  base: [0.956, 0.004, 286.32],
  surface: [1, 0, 0],
  elevated: [0.91, 0.006, 286.3], // 0.9321 -> 0.910 : 对 base 的 ΔL 0.024 -> 0.046
  border: [0.853, 0.0111, 280.45],
  fgPrimary: [0.2411, 0.0097, 248.23],
  fgSecondary: [0.395, 0.0136, 264.44], // 0.4450 -> 0.3950 : 二级文字压深, 与三级拉开
  fgMuted: [0.482, 0.0136, 264.44], // 0.4675 -> 0.4820 : 三级略微上提, 保住 muted/50 的下限
  accent: [0.5475, 0.13, HUE.accentLT],
  accentText: [0.5475, 0.13, HUE.accentLT],
}
const SKEL_DARK = {
  base: [0.1452, 0.0021, 286.13],
  surface: [0.2103, 0.0059, 285.89],
  elevated: [0.262, 0.0094, 285.7], // 0.2499 -> 0.2620 : 与 surface 拉开一档
  border: [0.365, 0.0075, 286.01], // 0.3305 -> 0.3650 : border/40 下仍看得见
  fgPrimary: [0.9851, 0, 0],
  fgSecondary: [0.8224, 0.0097, 286.18],
  fgMuted: [0.6493, 0.0118, 286.07],
  accent: [0.63, 0.175, HUE.accentDK], // 彩度 0.1880 -> 0.1750 : 收敛一档
  accentText: [0.63, 0.175, HUE.accentDK],
}

// 语义色: 明度由目标对比度反解, 色相固定
//
// 注意一个物理约束: 在同一个底色上, **对比度目标直接决定明度**(对比度是 L 的
// 单调函数), 所以「涨」与「警示」只要都满足 4.5:1, 明度就必然挨得很近 ——
// 白底上可用的 L 区间只有 0.545~0.575。两者靠**色相**(70° vs 22°, 差 48°)拉开,
// 不靠明度。而「涨/跌」这一对是红绿, 对红绿色盲会同时塌向黄褐, 才需要额外的
// 明度差, 所以给绿跌定更高的对比度目标(亮 7.4:1 / 暗 8.6:1)把明度顶开。
const SEM_LIGHT = {
  bull: { hue: HUE.bull, c: 0.185, target: 5.2 },
  bear: { hue: HUE.bear, c: 0.108, target: 6.7 },
  warning: { hue: HUE.warn, c: 0.125, target: 4.75 },
}
const SEM_DARK = {
  bull: { hue: HUE.bull, c: 0.2, target: 6.4 },
  bear: { hue: HUE.bear, c: 0.15, target: 5.1 },
  warning: { hue: HUE.warn, c: 0.16, target: 8.0 },
}

function semBlock(spec, bg) {
  const out = {}
  for (const [k, v] of Object.entries(spec)) out[k] = [solveL(v.hue, v.c, bg, v.target), v.c, v.hue]
  out.danger = out.bull
  return out
}

// ── Tailwind 强调色调色板: 红/翠两族的色相锚定到 A 股语义色相 ────────────
// 亮色明度按 R138 的目标对比度反解(300→4.5 / 400→5.4 / 500→6.4 / 600→7.4);
// 暗色保留 Tailwind 原明度, 只换色相 —— 暗色一侧的观感不能被这次重做推翻。
const TW_ANCHOR = {
  red: { hue: HUE.bull, chroma: { 300: 0.1035, 400: 0.1661, 500: 0.2078 } },
  emerald: { hue: HUE.bear, chroma: { 300: 0.1299, 400: 0.1535, 500: 0.1491 } },
}
const TW_LEVELS = { 300: 4.5, 400: 5.4, 500: 6.4, 600: 7.4 }
// 暗色保留的原明度(取自现 index.css html.dark)
const DARK_L = {
  red: { 300: 0.8077, 400: 0.7106, 500: 0.6368 },
  emerald: { 300: 0.8452, 400: 0.7729, 500: 0.6959 },
}

// ── 输出 ─────────────────────────────────────────────────────────────────
const fmt = ([L, C, H]) =>
  `${L.toFixed(4).replace(/0+$/, '').replace(/\.$/, '')} ${C.toFixed(4).replace(/0+$/, '').replace(/\.$/, '')} ${H.toFixed(2)}`
const hexBy = (o) => Object.fromEntries(Object.entries(o).map(([k, v]) => [k, hex(v)]))

const semL = semBlock(SEM_LIGHT, SKEL_LIGHT.surface)
const semD = semBlock(SEM_DARK, SKEL_DARK.base)

const C = {
  bullLT: contrast(semL.bull, SKEL_LIGHT.surface),
  bearLT: contrast(semL.bear, SKEL_LIGHT.surface),
  warnLT: contrast(semL.warning, SKEL_LIGHT.surface),
  bullDK: contrast(semD.bull, SKEL_DARK.base),
  bearDK: contrast(semD.bear, SKEL_DARK.base),
  warnDK: contrast(semD.warning, SKEL_DARK.base),
  // 语义色之间、以及各自在「卡片面」上的对比
  bullOnSurfDK: contrast(semD.bull, SKEL_DARK.surface),
  bearOnSurfDK: contrast(semD.bear, SKEL_DARK.surface),
  warnOnSurfDK: contrast(semD.warning, SKEL_DARK.surface),
  fgPriL: contrast(SKEL_LIGHT.fgPrimary, SKEL_LIGHT.surface),
  fgSecL: contrast(SKEL_LIGHT.fgSecondary, SKEL_LIGHT.surface),
  fgMutL: contrast(SKEL_LIGHT.fgMuted, SKEL_LIGHT.surface),
  accL: contrast(SKEL_LIGHT.accent, SKEL_LIGHT.surface),
  fgPriD: contrast(SKEL_DARK.fgPrimary, SKEL_DARK.base),
  fgSecD: contrast(SKEL_DARK.fgSecondary, SKEL_DARK.base),
  fgMutD: contrast(SKEL_DARK.fgMuted, SKEL_DARK.base),
  accD: contrast(SKEL_DARK.accent, SKEL_DARK.base),
  // 二级面可见性
  elevL: Math.abs(SKEL_LIGHT.elevated[0] - SKEL_LIGHT.base[0]),
  elevD: Math.abs(SKEL_DARK.elevated[0] - SKEL_DARK.base[0]),
  // 文字三级之间的明度差
  fg12L: Math.abs(SKEL_LIGHT.fgPrimary[0] - SKEL_LIGHT.fgSecondary[0]),
  fg23L: Math.abs(SKEL_LIGHT.fgSecondary[0] - SKEL_LIGHT.fgMuted[0]),
  fg12D: Math.abs(SKEL_DARK.fgPrimary[0] - SKEL_DARK.fgSecondary[0]),
  fg23D: Math.abs(SKEL_DARK.fgSecondary[0] - SKEL_DARK.fgMuted[0]),
}

const line = (label, v, unit = ':1', min = '') =>
  `  ${label.padEnd(38)} ${v.toFixed(2).padStart(6)}${unit}${min ? '   (下限 ' + min + ')' : ''}`

console.log('\n===== 语义色对比度 =====')
console.log('亮色 (底 = 白卡片 surface)')
console.log(line('红涨 bull', C.bullLT, ':1', '4.5'))
console.log(line('绿跌 bear', C.bearLT, ':1', '4.5'))
console.log(line('琥珀警示 warning', C.warnLT, ':1', '4.5'))
console.log('暗色 (底 = 页面底 base)')
console.log(line('红涨 bull', C.bullDK, ':1', '4.5'))
console.log(line('绿跌 bear', C.bearDK, ':1', '4.5'))
console.log(line('琥珀警示 warning', C.warnDK, ':1', '4.5'))
console.log('暗色语义色落在卡片面(surface)上')
console.log(line('红涨 bull', C.bullOnSurfDK, ':1', '4.5'))
console.log(line('绿跌 bear', C.bearOnSurfDK, ':1', '4.5'))
console.log(line('琥珀警示 warning', C.warnOnSurfDK, ':1', '4.5'))

console.log('\n===== 语义色可辨性 =====')
console.log('灰度下的明度差 (红绿对色盲会塌向同一片黄褐, 靠明度兜底)')
console.log(line('亮 涨/跌 ΔL', Math.abs(semL.bull[0] - semL.bear[0]), '', '0.07'))
console.log(line('暗 涨/跌 ΔL', Math.abs(semD.bull[0] - semD.bear[0]), '', '0.07'))
console.log('两种模式下「涨」都必须是更亮的那一个 (方向不能翻转)')
console.log(line('亮 涨比跌亮 ΔL', semL.bull[0] - semL.bear[0], '', '>0'))
console.log(line('暗 涨比跌亮 ΔL', semD.bull[0] - semD.bear[0], '', '>0'))
console.log('色相差 (对比度预算相同时, 色相是唯一可分维度)')
console.log(line('涨 -> 警示 色相差', HUE.warn - HUE.bull, '°', '45'))
console.log(line('跌 -> 警示 色相差', HUE.bear - HUE.warn, '°', '45'))
console.log(line('涨 -> 跌 色相差', HUE.bear - HUE.bull, '°', '90'))
console.log('跨模式色相一致性 (同一个语义在亮暗里必须是同一色相)')
console.log(line('涨 亮/暗 色相差', Math.abs(SEM_LIGHT.bull.hue - SEM_DARK.bull.hue), '°', '0'))
console.log(line('跌 亮/暗 色相差', Math.abs(SEM_LIGHT.bear.hue - SEM_DARK.bear.hue), '°', '0'))
console.log(line('警示 亮/暗 色相差', Math.abs(SEM_LIGHT.warning.hue - SEM_DARK.warning.hue), '°', '0'))

console.log('\n===== 骨架: 文字三级对比度 =====')
console.log('亮色 (底 = surface 白)')
console.log(line('fg-primary', C.fgPriL, ':1', '12'))
console.log(line('fg-secondary', C.fgSecL, ':1', '7'))
console.log(line('fg-muted', C.fgMutL, ':1', '4.5'))
console.log(line('accent (文字)', C.accL, ':1', '4.5'))
console.log(line('muted/50 叠白底', contrastAlpha(SKEL_LIGHT.fgMuted, SKEL_LIGHT.surface, 0.5), ':1', '2'))
console.log('暗色 (底 = base)')
console.log(line('fg-primary', C.fgPriD, ':1', '12'))
console.log(line('fg-secondary', C.fgSecD, ':1', '7'))
console.log(line('fg-muted', C.fgMutD, ':1', '4.5'))
console.log(line('accent (文字)', C.accD, ':1', '4.5'))
console.log(line('muted/50 叠底', contrastAlpha(SKEL_DARK.fgMuted, SKEL_DARK.base, 0.5), ':1', '2'))

console.log('\n===== 骨架: 层级可分性 (ΔL, 经验阈值 0.04) =====')
console.log(line('亮 页面底 -> 次级面', C.elevL, '', '0.043'))
console.log(line('暗 页面底 -> 次级面', C.elevD, '', '0.043'))
console.log(line('亮 一级/二级文字 ΔL', C.fg12L, '', '0.09'))
console.log(line('亮 二级/三级文字 ΔL', C.fg23L, '', '0.09'))
console.log(line('暗 一级/二级文字 ΔL', C.fg12D, '', '0.09'))
console.log(line('暗 二级/三级文字 ΔL', C.fg23D, '', '0.09'))

console.log('\n===== 色值 =====')
console.log('亮 base', hex(SKEL_LIGHT.base), '| surface', hex(SKEL_LIGHT.surface),
  '| elevated', hex(SKEL_LIGHT.elevated), '| border', hex(SKEL_LIGHT.border))
console.log('亮 fg', hex(SKEL_LIGHT.fgPrimary), hex(SKEL_LIGHT.fgSecondary), hex(SKEL_LIGHT.fgMuted))
console.log('亮 语义 bull', hex(semL.bull), 'bear', hex(semL.bear), 'warning', hex(semL.warning))
console.log('暗 base', hex(SKEL_DARK.base), '| surface', hex(SKEL_DARK.surface),
  '| elevated', hex(SKEL_DARK.elevated), '| border', hex(SKEL_DARK.border))
console.log('暗 fg', hex(SKEL_DARK.fgPrimary), hex(SKEL_DARK.fgSecondary), hex(SKEL_DARK.fgMuted))
console.log('暗 语义 bull', hex(semD.bull), 'bear', hex(semD.bear), 'warning', hex(semD.warning))

if (process.argv.includes('--emit')) {
  // 变量名映射: 脚本内部用驼峰, CSS 里是短横线
  const NAME = {
    base: 'base', surface: 'surface', elevated: 'elevated', border: 'border',
    fgPrimary: 'fg-primary', fgSecondary: 'fg-secondary', fgMuted: 'fg-muted',
    accent: 'accent', accentText: 'accent-text',
    bull: 'bull', bear: 'bear', warning: 'warning', danger: 'danger',
  }
  const emit = (title, o) =>
    `  /* ${title} */\n` +
    Object.entries(o).map(([k, v]) => `  --${NAME[k] || k}: ${fmt(v)};`).join('\n')
  console.log('\n===== CSS (亮色 :root) =====')
  console.log(emit('骨架', SKEL_LIGHT))
  console.log(emit('语义', semL))
  console.log('\n===== CSS (暗色 html.dark) =====')
  console.log(emit('骨架', SKEL_DARK))
  console.log(emit('语义', semD))
}

// 锚定后的 Tailwind 红/翠族
console.log('\n===== Tailwind 红/翠族色相锚定 =====')
const twOut = { light: {}, dark: {} }
for (const [fam, spec] of Object.entries(TW_ANCHOR)) {
  const lightRow = Object.keys(spec.chroma).map((lv) => {
    const L = solveL(spec.hue, spec.chroma[lv], SKEL_LIGHT.surface, TW_LEVELS[lv])
    twOut.light[`--t-${fam}-${lv}`] = [L, spec.chroma[lv], spec.hue]
    return `${lv}:${hex([L, spec.chroma[lv], spec.hue])}(${contrast([L, spec.chroma[lv], spec.hue], SKEL_LIGHT.surface).toFixed(2)})`
  })
  const darkRow = Object.keys(DARK_L[fam]).map((lv) => {
    const L = DARK_L[fam][lv]
    twOut.dark[`--t-${fam}-${lv}`] = [L, spec.chroma[lv], spec.hue]
    return `${lv}:${hex([L, spec.chroma[lv], spec.hue])}`
  })
  console.log(`  ${fam.padEnd(8)} 色相 ${spec.hue}°`)
  console.log(`    亮 ${lightRow.join('  ')}`)
  console.log(`    暗 ${darkRow.join('  ')}`)
}

if (process.argv.includes('--emit')) {
  console.log('\n===== 红/翠族 CSS 片段 (直接替换同名变量) =====')
  console.log('  亮色 :root')
  for (const [k, v] of Object.entries(twOut.light)) console.log(`  ${k}: ${fmt(v)};`)
  console.log('  暗色 html.dark')
  for (const [k, v] of Object.entries(twOut.dark)) console.log(`  ${k}: ${fmt(v)};`)
}

const out = { SKEL_LIGHT, SKEL_DARK, semL, semD }
fs.writeFileSync(path.join(__dirname, '..', '.theme-v2.json'), JSON.stringify(out, null, 2))
console.log('\n(机器可读结果已写入 frontend/.theme-v2.json)')
