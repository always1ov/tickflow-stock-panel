/**
 * [fork 增强] 决策台导出 —— 自包含 HTML(内联样式, 无脚本无外链, 可存档/打印/转发)。
 *
 * [R182] 改成**列驱动**: 导哪些列由 `decisionBoardExportColumns` 的注册表 + 用户
 * 勾选决定, 这里只负责渲染。改之前列写死在模板里, 而且**另有一套**几乎一样的
 * 模板长在六态汇总弹窗里 —— 两套必然长成两个样子, 加一列要改两处, 用户还没法
 * 决定导什么。合并之后六态汇总不必单独存在: 勾上趋势那几列就是它。
 *
 * 一条约束写在列注册表里、这里只是照做: **导出的读法要和屏幕一致**。同一个字段
 * 界面上显示"贴上轨", 导出件里就不该变成 0.87 —— 对不上时用户会怀疑哪个是错的。
 */
import {
  columnsFor,
  type ExportColumn,
  type ExportRow,
} from '@/lib/decisionBoardExportColumns'

export type { ExportRow }

const esc = (v: unknown) =>
  String(v ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c] as string))

const alignCls = (c: ExportColumn) =>
  c.align === 'right' ? ' class="num"' : c.align === 'center' ? ' class="mid"' : ''

function renderRow(r: ExportRow, cols: ExportColumn[]): string {
  const tds = cols.map(c => {
    let cell
    try {
      cell = c.cell(r)
    } catch {
      // 一列取值出错不该让整份导出失败 —— 那一格空着就是了
      cell = { text: '—' }
    }
    // 有 style 的当成标签渲染(与屏幕上那些彩色胶囊对应), 否则纯文本
    const inner = cell.style
      ? `<span class="tag" style="${cell.style}">${esc(cell.text)}</span>`
      : esc(cell.text)
    return `<td${alignCls(c)}>${inner}</td>`
  })
  return `<tr>${tds.join('')}</tr>`
}

export function buildBoardHtml(
  rows: ExportRow[],
  total: number,
  keys: string[],
): string {
  const cols = columnsFor(keys)
  const head = cols.map(c => `<th${alignCls(c)}>${esc(c.label)}</th>`).join('')
  const body = rows.map(r => renderRow(r, cols)).join('')

  return `<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>自选决策台 · ${new Date().toLocaleDateString('zh-CN')}</title>
<style>
  body { margin:0; background:#f6f7f9; color:#1f2430;
         font:13px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif; }
  .wrap { max-width:1400px; margin:0 auto; padding:28px 20px 40px; }
  h1 { font-size:19px; margin:0 0 4px; }
  .meta { font-size:12px; color:#8a919f; margin-bottom:14px; }
  .note { font-size:12px; color:#5b6472; background:#fff; border:1px solid #e3e6ec;
          border-radius:8px; padding:10px 12px; margin-bottom:14px; }
  table { width:100%; border-collapse:collapse; background:#fff;
          border:1px solid #e3e6ec; border-radius:8px; overflow:hidden; }
  th, td { padding:7px 10px; text-align:left; border-bottom:1px solid #eef0f4;
           font-size:12px; white-space:nowrap; }
  th { background:#fafbfc; color:#5b6472; font-weight:500; font-size:11px; }
  td.num, th.num { text-align:right; font-variant-numeric:tabular-nums; }
  td.mid, th.mid { text-align:center; }
  tr:last-child td { border-bottom:none; }
  .tag { display:inline-block; padding:1px 6px; border-radius:4px; font-size:11px; }
  .foot { margin-top:14px; font-size:11px; color:#8a919f; line-height:1.7; }
  @media print { body { background:#fff; } .wrap { padding:0; } }
</style>
</head>
<body>
<div class="wrap">
  <h1>自选决策台</h1>
  <div class="meta">导出 ${rows.length} 只(自选共 ${total} 只)· ${cols.length} 列 · 生成于 ${esc(new Date().toLocaleString('zh-CN'))}</div>
  <div class="note">
    「该动」是<b>纯规则</b>判定(已触发 &gt; 逼近 &gt; 刚变盘 &gt; 到轨), <b>AI 不参与</b> —— 它只解释, 不决定先看谁。<br>
    通道口径:短期 MA20±2ATR / 中期 MA60±2.5ATR / 长期 MA120±3ATR,<b>收盘价</b>判定;
    结论说的是<b>位置</b>(贵不贵), 不是会不会继续涨。<br>
    清仓与否看止盈线与生命线, 优先级在通道之上。
  </div>
  <table>
    <thead><tr>${head}</tr></thead>
    <tbody>${body}</tbody>
  </table>
  <div class="foot">
    本页为自包含 HTML(无脚本、无外链), 可直接存档、打印或转发。<br>
    数据来自 TickFlow, 仅供研究参考, 不构成投资建议。
  </div>
</div>
</body>
</html>`
}
