/**
 * [R449] 全站的文字层级 —— **按级别给字号, 不是全部一样大**。
 *
 * 用户: 「全局都想要像弹窗这样大的字体和样式, 看着舒服」, 追问时又说「你要按照标题
 * 级别, 别无脑全部一样, 样式是肯定要改的」。取值就是个股弹窗重做(R429~R448)那一套,
 * 折到 R399 的字号刻度上, 每两级之间至少差 2px(否则肉眼分不出是两级):
 *
 *   L1  page     页面标题 / 弹窗里的票名               21px 粗
 *   L2  section  分区标题(「现状」「复盘」那一行)     18px 粗
 *   L3  card     卡片标题(「逐日复盘」那一行)         15px 粗
 *       body     正文、说明、按钮、表格内容             13px
 *       label    表头、小标签、单位、徽标               11px 灰
 *       reading  关键读数(价格、状态这类大字)         21px 粗
 *
 * 表格与按钮另有 `table.ts` / `Button.tsx`, 字号同样落在这几档上。
 * 迁移规则与页面清单见 `docs/ui-hierarchy.md`。
 */
export const TYPE = {
  page: 'text-xl font-semibold tracking-tight text-foreground',
  section: 'text-lg font-semibold text-foreground',
  card: 'text-sm font-semibold text-foreground',
  body: 'text-xs text-foreground',
  label: 'text-micro text-muted',
  reading: 'text-xl font-semibold tabular-nums',
} as const
