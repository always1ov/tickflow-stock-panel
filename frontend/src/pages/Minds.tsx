/**
 * [R502 · fork 增强] Minds —— 记下来 → 提炼成洞见 → 整理成交易计划, 有问题随时在「对话」里问。
 *
 * 用户: 「系统里面悬浮的那个 ai 助手改造复刻成这三张图 minds 的功能, 也做成一个菜单选项在左侧」。
 * 几轮问答定下来的(全部「按推荐」):
 *   · 菜单「消息面」原位改名 Minds, 旧地址 /usage-notes 重定向到 /minds?tab=notes;
 *   · 四栏: 笔记(原消息面整页, 一个字没动) / 洞见 / 交易计划 / 对话(原悬浮 AI 助手原样搬进来);
 *   · 洞见与交易计划**不进 AI 决策、不进规则层** —— 进 AI 决策的仍只有笔记那一段总览;
 *   · 交易计划只看不执行。
 *
 * 「对话」一栏走 `minds.chat` 插槽, 本页不 import 扩展目录 —— 删掉 AI 助手扩展,
 * 这一栏显示未安装, 其余三栏照常。
 *
 * 分栏跟因子页同一个做法: 页头右侧一组分段按钮, 当前栏写在 `?tab=` 里(可收藏、刷新不丢)。
 * 切栏是瞬时的, 不加过渡 —— 这是高频操作。
 * [R512] 分栏条抽成 `components/PageTabs.tsx`, 模拟盘也用它 —— 两页一份实现。
 */
import { useQuery } from '@tanstack/react-query'
import { ClipboardList, Lightbulb, MessagesSquare, NotebookPen } from 'lucide-react'
import { PageHeader } from '@/components/PageHeader'
import { EmptyState } from '@/components/EmptyState'
import { ExtensionSlot } from '@/extensions/ExtensionSlot'
import { getFrontendSlotRegistrations } from '@/extensions/registry'
import { api } from '@/lib/api'
import { QK } from '@/lib/queryKeys'
import { PageTabs, usePageTab, type PageTabDef } from '@/components/PageTabs'
import { NotesPanel } from './UsageNotes'

export type MindsTab = 'notes' | 'insights' | 'plans' | 'chat'

export const MINDS_TABS: Record<MindsTab, PageTabDef> = {
  notes: { title: '笔记', icon: NotebookPen },
  insights: { title: '洞见', icon: Lightbulb },
  plans: { title: '交易计划', icon: ClipboardList },
  chat: { title: '对话', icon: MessagesSquare },
}

export function Minds() {
  const [activeTab, changeTab] = usePageTab(MINDS_TABS, 'notes')

  // 笔记条数挂在分栏上 —— 与笔记栏同一个查询键, 不多发请求
  const notesQ = useQuery({ queryKey: QK.usageNotes, queryFn: api.usageNotesList })
  const counts: Partial<Record<MindsTab, number>> = { notes: notesQ.data?.items.length }

  return (
    <div className="flex h-full flex-col">
      <PageHeader
        title="Minds"
        subtitle={<span className="hidden md:inline">记下来 → 提炼成洞见 → 整理成交易计划 · 有问题随时在「对话」里问</span>}
        className="shrink-0 flex-wrap gap-x-4 gap-y-2"
        right={<PageTabs tabs={MINDS_TABS} active={activeTab} onChange={changeTab} counts={counts} label="Minds 分栏" />}
      />

      {activeTab === 'chat' ? (
        // 对话一栏占满剩下的高度, 消息列表在面板里自己滚; 矮屏给个下限, 不至于挤成一条缝
        <main className="min-h-[420px] flex-1 px-3 pb-3 pt-3 lg:px-4 lg:pb-4">
          <ChatTab />
        </main>
      ) : (
        <main className="min-h-0 flex-1 overflow-y-auto px-3 pb-4 pt-3 lg:px-4">
          {activeTab === 'notes' && <NotesPanel />}
          {activeTab === 'insights' && (
            <EmptyState
              icon={Lightbulb}
              title="洞见还没上线"
              hint="下一步做: 挑一段时间或几条笔记, 让 AI 起草一条洞见, 你改过再存。洞见只给你看, 不进 AI 决策、不进规则层。"
            />
          )}
          {activeTab === 'plans' && (
            <EmptyState
              icon={ClipboardList}
              title="交易计划还没上线"
              hint="洞见之后做: 从一条洞见整理出买入、持有、离场、仓位四项。只看不执行, 不会替你下单。"
            />
          )}
        </main>
      )}
    </div>
  )
}

function ChatTab() {
  if (getFrontendSlotRegistrations('minds.chat').length === 0) {
    return (
      <EmptyState
        icon={MessagesSquare}
        title="对话没有装"
        hint="「对话」由 AI 助手扩展提供(frontend/src/custom/assistant)。装回这个目录后重新构建即可。"
      />
    )
  }
  return <ExtensionSlot name="minds.chat" context={{}} />
}
