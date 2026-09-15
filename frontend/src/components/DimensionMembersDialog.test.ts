// [R348] 这个文件原来用 `node:test`, 而**项目里没有任何脚本会调用它** ——
// 一个没人跑的测试, 守的东西等于没守。上游这次带进了 vitest(为它自己的
// Indices.test.tsx), 顺手把这里换成同一个运行器, 并把 `pnpm test` 扩成跑全部,
// 它才真正开始工作。断言库仍用 node:assert, 不为换运行器把断言也重写一遍。
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'vitest'

const source = readFileSync(
  new URL('./DimensionMembersDialog.tsx', import.meta.url),
  'utf8',
)

test('股票名称在前，板块标签紧随名称且代码保持独立一行', () => {
  // 只锚定结构（外层包裹 + 名称/徽标同行 flex 组 + 独立代码行），不锁定具体样式类，
  // 避免纯样式微调误报；顺序断言仍是本测试的核心。
  const identity = source.match(
    /<span className="min-w-0">\s*<span className="flex[^"]*">([\s\S]*?)<\/span>\s*<span className="block font-mono[^"]*">\{row\.symbol\}<\/span>/,
  )

  assert.ok(identity, '股票名称、板块标签和代码应使用统一的两行身份布局')
  assert.ok(
    identity[1].indexOf('{row.name || row.symbol}') < identity[1].indexOf('{board &&'),
    '板块标签应渲染在股票名称之后',
  )
})
