/**
 * [R138] 亮色模式强调色的生成脚本 —— 调色板是**算出来的, 不是手调的**。
 *
 * 起因: 全站一千多处用的是 text-amber-300 / text-sky-300 / text-emerald-400
 * 这类为深色背景挑的浅色。放到白底上, amber-300 只有 **1.44:1** —— 用户的
 * 原话是"太白了好多东西都看不见"。
 *
 * 做法: 保持每个颜色的**色相**不变(色相才是语义: 红=涨、绿=跌、琥珀=提醒),
 * 只把明度压到刚好达到目标对比度; 低明度处高彩度会掉出 sRGB 色域, 再逐步降
 * 彩度收回来。档位之间保留递增的目标(300→4.5:1 / 400→5.4 / 500→6.4 / 600→7.4),
 * 否则三档会挤成同一个颜色, 色阶就没了。
 *
 * 暗色一侧原样输出 Tailwind 值 —— 用户抱怨的是亮色, 暗色一个像素都不该动。
 *
 * 重新生成:
 *     node scripts/gen-light-palette.cjs
 * 输出三段(亮色变量 / 暗色变量 / tailwind.config 片段), 分别贴进
 * src/index.css 的 :root 与 html.dark, 以及 tailwind.config.ts 的 colors。
 * 加 VERBOSE=1 会在 stderr 打出每个颜色改前改后的白底对比度。
 */
const c = require('tailwindcss/colors');

// ---- 色彩转换 (sRGB <-> OKLab/OKLCH) ----
const h2r = h => { h = h.replace('#',''); return [0,2,4].map(i => parseInt(h.slice(i,i+2),16)/255) }
const lin = u => u <= 0.04045 ? u/12.92 : Math.pow((u+0.055)/1.055, 2.4)
const unlin = u => u <= 0.0031308 ? 12.92*u : 1.055*Math.pow(u,1/2.4)-0.055

function rgb2oklch([r,g,b]) {
  r=lin(r); g=lin(g); b=lin(b)
  const l=Math.cbrt(0.4122214708*r+0.5363325363*g+0.0514459929*b)
  const m=Math.cbrt(0.2119034982*r+0.6806995451*g+0.1073969566*b)
  const s=Math.cbrt(0.0883024619*r+0.2817188376*g+0.6299787005*b)
  const L=0.2104542553*l+0.7936177850*m-0.0040720468*s
  const A=1.9779984951*l-2.4285922050*m+0.4505937099*s
  const B=0.0259040371*l+0.7827717662*m-0.8086757660*s
  return [L, Math.hypot(A,B), (Math.atan2(B,A)*180/Math.PI+360)%360]
}
function oklch2rgb([L,C,H]) {
  const a=C*Math.cos(H*Math.PI/180), b=C*Math.sin(H*Math.PI/180)
  const l=(L+0.3963377774*a+0.2158037573*b)**3
  const m=(L-0.1055613458*a-0.0638541728*b)**3
  const s=(L-0.0894841775*a-1.2914855480*b)**3
  return [
    +4.0767416621*l -3.3077115913*m +0.2309699292*s,
    -1.2684380046*l +2.6097574011*m -0.3413193965*s,
    -0.0041960863*l -0.7034186147*m +1.7076147010*s,
  ]
}
const inGamut = rgb => rgb.every(v => v >= -0.001 && v <= 1.001)
// 相对亮度 (WCAG)。oklch2rgb 返回的**已经是线性光** sRGB —— 这里再套一次 lin()
// 就是把传输函数做了两遍, 算出来的对比度会偏高, 解出的颜色就不够暗。踩过一次。
const lum = ([L,C,H]) => {
  const [r,g,b] = oklch2rgb([L,C,H]).map(v => Math.min(1, Math.max(0, v)))
  return 0.2126*r + 0.7152*g + 0.0722*b
}
const contrastOnWhite = lch => 1.05 / (lum(lch) + 0.05)

/** 保持色相, 压暗到刚好达到目标对比度; 出色域就降彩度 */
function darkenTo(L0, C0, H, target) {
  let lo = 0.15, hi = L0, best = L0
  for (let i = 0; i < 40; i++) {
    const mid = (lo + hi) / 2
    if (contrastOnWhite([mid, C0, H]) >= target) { best = mid; lo = mid } else { hi = mid }
  }
  // 低明度处高彩度容易出 sRGB 色域 —— 逐步降彩度直到落回来
  let C = C0
  while (C > 0.02 && !inGamut(oklch2rgb([best, C, H]))) C -= 0.005
  return [best, C]
}

// 实际用到的 (家族, 档位); 只重映射 300~600 —— 50/100/200 是本来就该淡的浅底,
// 700+ 已经够暗, 动它们只会把亮色模式弄糟
const USED = `amber-300 amber-400 amber-500 amber-600 blue-300 blue-400 blue-500
cyan-300 cyan-400 cyan-500 cyan-600 emerald-300 emerald-400 emerald-500
fuchsia-300 fuchsia-400 fuchsia-500 green-400 green-500 indigo-400 lime-400
orange-300 orange-400 orange-500 purple-300 purple-400 purple-500
red-300 red-400 red-500 rose-300 rose-400 rose-500 sky-300 sky-400 sky-500
teal-300 teal-400 teal-500 violet-300 violet-400 violet-500
yellow-400 yellow-500 yellow-600`.split(/\s+/)

// 目标对比度按档位递增 —— 全压到同一个值会让 300/400/500 挤成一个颜色, 色阶就没了
const TARGET = { 300: 4.5, 400: 5.4, 500: 6.4, 600: 7.4 }

const light = [], dark = [], tw = {}
for (const key of USED) {
  const [fam, sh] = key.split('-')
  const hex = c[fam][sh]
  const [L, C, H] = rgb2oklch(h2r(hex))
  const [L2, C2] = darkenTo(L, C, H, TARGET[sh])
  const f = n => n.toFixed(4).replace(/0+$/,'').replace(/\.$/,'')
  light.push(`  --t-${key}: ${f(L2)} ${f(C2)} ${f(H)};`)
  dark.push(`  --t-${key}: ${f(L)} ${f(C)} ${f(H)};`)
  ;(tw[fam] = tw[fam] || {})[sh] = `oklch(var(--t-${key}) / <alpha-value>)`
  if (process.env.VERBOSE)
    console.error(`${key.padEnd(14)} L ${f(L)} -> ${f(L2)}   白底对比 ${contrastOnWhite([L,C,H]).toFixed(2)} -> ${contrastOnWhite([L2,C2,H]).toFixed(2)}`)
}
console.log('/*LIGHT*/\n' + light.join('\n'))
console.log('/*DARK*/\n' + dark.join('\n'))
console.log('/*TW*/\n' + JSON.stringify(tw, null, 2))
