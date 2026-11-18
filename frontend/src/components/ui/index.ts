/**
 * [R400] 设计规范的基础件。**新写界面一律从这里取, 不要再手写 class 串。**
 *
 * 取值表分别在 `Button.tsx` / `Card.tsx` / `Field.tsx` 的文件头, 每一处都写了
 * 值是从现状哪个多数派折过来的。要加档位请改那三个文件里的表, 不要在调用处
 * 就地写死 —— `backend/tests/test_design_spec.py` 的棘轮盯着这件事。
 */
export { Button, buttonClass, OUTLINE, SELECTED, type ButtonVariant, type ButtonSize, type ButtonStyleProps } from './Button'
export { Card, CardSection, type CardPadding } from './Card'
export { Field, fieldInput, fieldSelect } from './Field'
export { SectionTitle } from './SectionTitle'
export { TYPE } from './type'
export { TABLE, THEAD, TH_ROW, TH, TR, TD } from './table'
export { SEG, SEG_ITEM, SEG_ON, SEG_OFF } from './segmented'
export { Switch, SwitchTrack } from './Switch'
// [R814] 补齐三处手写最多的缺口: 徽标 / 工具条 / 弹窗固定件 / 复选框。
export { Badge, type BadgeTone } from './Badge'
export { Toolbar, ToolbarGroup, ToolbarDivider, TOOLBAR, TOOLBAR_GROUP } from './Toolbar'
export {
  DialogClose, dialogPanel,
  DIALOG_HEADER, DIALOG_TITLE, DIALOG_BODY, DIALOG_FOOTER,
  type DialogSize,
} from './Dialog'
export { Checkbox } from './Checkbox'
// [R824] 补齐 R823 报上来的两处缺口: 弱强调徽标档 + 单选。
export { Radio } from './Radio'
