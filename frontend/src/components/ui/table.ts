/**
 * [R449] 表格的样式 —— 与个股弹窗「逐日复盘」那张表同一套。
 *
 * 表头是 label 那一级(11px 灰; [R532] 起不再有浅灰底条, 坐在卡片底上), 内容是 body 那一级(13px), 行与行之间
 * 一道细线。横向内边距比弹窗原来那张略收, 是给决策台这类十几列的宽表留地方;
 * 首尾两列由调用方各补一个 `pl-4` / `pr-4` 贴齐卡片内边距。
 */
export const TABLE = 'w-full text-xs'
// [R532] 表头不再是浅灰实底条, 直接坐在卡片底上(照 Aipha AI: 表头只靠灰字与下面那道线区分)。
// 仍是**不透明**的卡片底 —— sticky 表头底下是正在划走的行, 透出来会花(R252)。
export const THEAD = 'sticky top-0 z-10 bg-surface'
export const TH_ROW = 'text-micro text-muted'
export const TH = 'whitespace-nowrap px-2 py-2 font-normal'
export const TR = 'border-b border-border/30'
export const TD = 'px-2 py-2'
