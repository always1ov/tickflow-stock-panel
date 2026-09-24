/**
 * AI 对话助手前端扩展 — 完全解耦模块。
 *
 * 注册两个插槽:
 *   · layout.navigation.extra —— 常驻挂载点(菜单里不渲染入口), 只管 ⌘K/Ctrl+K
 *     与页面上下文(见 AssistantLauncher);
 *   · minds.chat —— [R502 · fork] 对话面板本体, 嵌在 Minds 页「对话」一栏。
 *     原来的悬浮球 + AI 配置徽标旁入口 + 右缘抽屉随之去掉。
 * 删除本目录即整体卸载(Minds 的「对话」一栏显示未安装), 核心页面不 import 本目录;
 * 复用的核心能力均为只读 import(MarkdownRenderer、cn、设计令牌)。
 * 自包含 HTTP 客户端见 client.ts 的取舍说明。
 */
import type { FrontendExtension } from '@/extensions/types'
import { AssistantLauncher } from './AssistantLauncher'
import { AssistantPanel } from './ui/AssistantDrawer'

const extension: FrontendExtension = {
  id: 'assistant.chat',
  apiVersion: 1,
  slots: [
    {
      name: 'layout.navigation.extra',
      id: 'assistant-entry',
      order: 10,
      component: AssistantLauncher,
    },
    {
      name: 'minds.chat',
      id: 'assistant-chat',
      order: 10,
      component: AssistantPanel,
    },
  ],
}

export default extension
