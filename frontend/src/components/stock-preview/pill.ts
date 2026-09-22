/**
 * [R429] 个股弹窗重做后的按钮形状: 独立方框、等高。[R430] 从头部挪出来, 「图表与价位」
 * 那一块的视图切换与分时天数也用这一套 —— 同一个弹窗里按钮只许长一个样子。
 *
 * 横向内边距和字色**不放进公共串**, 由各处自己给 —— 同一个元素上同时写 `px-3 px-0`
 * 或 `text-foreground text-muted`, 谁生效看样式表里的先后而不是写的先后:
 * 星星方框就这样被 `px-3` 挤成了 6px 宽。
 */
export const BOX = 'inline-flex h-8 items-center justify-center rounded-btn border text-xs '
  + 'transition-colors duration-hover disabled:opacity-40'
export const PILL = `${BOX} px-3`
export const SQUARE = `${BOX} w-8 border-border bg-surface hover:bg-elevated`
export const PILL_IDLE = 'border-border bg-surface text-foreground hover:bg-elevated'
export const PILL_ON = 'border-foreground bg-foreground text-surface font-medium'
