#!/usr/bin/env node
// [fork R153] 构建后给 dist/assets 里的文本类产物生成同名 .br / .gz。
//
// 为什么在构建期压而不是请求期压: 这些文件带内容 hash, 一年不变, 每次请求再压
// 一遍纯属浪费 CPU; 后端 HashedAssets 按 Accept-Encoding 直接发对应文件。
// 只用 Node 自带的 zlib(brotli 已内置), 不引入任何新依赖 —— Docker 构建阶段
// `pnpm build` 顺带跑完, 不需要改 Dockerfile。
//
// 跳过本身已是压缩格式的文件(woff2/png/…), 以及压缩后反而不小的。
import { promises as fs } from 'node:fs'
import path from 'node:path'
import zlib from 'node:zlib'
import { promisify } from 'node:util'

const gzip = promisify(zlib.gzip)
const brotli = promisify(zlib.brotliCompress)

const root = path.resolve(process.argv[2] ?? 'dist/assets')
const COMPRESSIBLE = new Set(['.js', '.mjs', '.css', '.svg', '.json', '.txt', '.map', '.html'])
const MIN_BYTES = 1024

async function* walk(dir) {
  for (const ent of await fs.readdir(dir, { withFileTypes: true })) {
    const p = path.join(dir, ent.name)
    if (ent.isDirectory()) yield* walk(p)
    else yield p
  }
}

let files = 0, rawTotal = 0, gzTotal = 0, brTotal = 0
for await (const file of walk(root)) {
  const ext = path.extname(file)
  if (!COMPRESSIBLE.has(ext)) continue
  const raw = await fs.readFile(file)
  if (raw.length < MIN_BYTES) continue
  const [gz, br] = await Promise.all([
    gzip(raw, { level: 9 }),
    brotli(raw, {
      params: {
        [zlib.constants.BROTLI_PARAM_QUALITY]: 11,
        [zlib.constants.BROTLI_PARAM_SIZE_HINT]: raw.length,
      },
    }),
  ])
  if (gz.length < raw.length) { await fs.writeFile(`${file}.gz`, gz); gzTotal += gz.length } else { gzTotal += raw.length }
  if (br.length < raw.length) { await fs.writeFile(`${file}.br`, br); brTotal += br.length } else { brTotal += raw.length }
  files += 1
  rawTotal += raw.length
}

const mb = (n) => (n / 1024 / 1024).toFixed(2) + ' MB'
console.log(`[compress-dist] ${files} files: raw ${mb(rawTotal)} → gzip ${mb(gzTotal)} / brotli ${mb(brTotal)}`)
