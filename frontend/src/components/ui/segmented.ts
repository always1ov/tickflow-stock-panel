/**
 * [R456] 分段切换(「股票 / ETF」「全部 / 日线 / 分钟」这一类): 外面一圈描边, 里面选中
 * 那一格黑白反相 —— 与个股弹窗「日 K / 分时 / 关键价位」同一个样子, 只是矮一档,
 * 总高 32px, 与旁边的全站按钮齐平。
 *
 *   <div className={SEG}>
 *     <button className={cn(SEG_ITEM, on ? SEG_ON : SEG_OFF)}>…</button>
 */
export const SEG = 'inline-flex shrink-0 items-center gap-0.5 rounded-btn border border-border bg-elevated/60 p-0.5'
export const SEG_ITEM = 'inline-flex h-7 items-center gap-1 rounded-btn px-2.5 text-xs transition-colors duration-hover cursor-pointer'
export const SEG_ON = 'bg-foreground font-medium text-surface'
export const SEG_OFF = 'text-secondary hover:text-foreground'
