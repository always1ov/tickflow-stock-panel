/**
 * 统一设置页面 — 分栏外壳。
 *
 * 通过 URL query param ?tab=xxx 同步当前栏(键名一个没改, 老书签与各处「去设置」的深链照旧)。
 *
 * [R533] 用户: 「设置页面也要整改」。原来是页面里再套一列 144px 的竖向菜单(带「收起菜单」按钮, 手机上收成一列图标),
 * 与 Minds / 模拟盘 / 监控中心那套页头分栏是两种长相。现在同一份 `PageTabs`:
 *   · 分栏条在页头右侧, 手机上横向滚动, 不再占一整列;
 *   · 栏名去掉重复的「设置」二字(AI 设置 → AI、网络设置 → 网络、菜单设置 → 菜单、系统设置 → 系统);
 *   · 「菜单」挪到「扩展页面」旁边 —— 扩展页面建出来的就是一条菜单;
 *   · 切栏瞬时, 不再淡入上移(高频操作不加动效, AGENTS.md 动效硬规则第 4 条);
 *   · 页头副标题「管理账户、数据刷新策略和高级功能配置」撤掉 —— 这里没有账户。
 * 七个面板的内容一个没动。
 */
import { useEffect } from 'react'
import { BarChart3, Bell, Clock3, Database, Radio, Settings2, SlidersHorizontal, Sparkles } from 'lucide-react'
import { useSearchParams } from 'react-router-dom'
import { SettingsAIPanel } from './settings/AI'
import { SettingsMonitoringPanel } from './settings/Monitoring'
import { SettingsExtPagesPanel } from './settings/ExtPages'
import { SettingsMenuSettingsPanel } from './settings/MenuSettings'
import { SettingsTimeoutPanel } from './settings/Timeout'
import { SettingsSystemPanel } from './settings/System'
import { SettingsDataSourcesPanel } from './settings/DataSources'
import { SettingsNotificationsPanel } from './settings/Notifications'
import { PageHeader } from '@/components/PageHeader'
import { PageTabs, usePageTab, type PageTabDef } from '@/components/PageTabs'

import type { ComponentType } from 'react'

export type SettingsTab = 'data-sources' | 'monitoring' | 'notifications' | 'ai' | 'menus' | 'ext-pages' | 'timeout' | 'system'

/** 栏的顺序就是这张表的顺序 */
export const SETTINGS_TABS: Record<SettingsTab, PageTabDef> = {
  'data-sources': { title: '数据源', icon: Database },
  monitoring: { title: '实时监控', icon: Radio },
  // [R534] 推送通知(原在实时监控) + 通知弹窗 / 语音播报(原在系统) 合成一栏
  notifications: { title: '通知', icon: Bell },
  ai: { title: 'AI', icon: Sparkles },
  menus: { title: '菜单', icon: SlidersHorizontal },
  'ext-pages': { title: '扩展页面', icon: BarChart3 },
  timeout: { title: '网络', icon: Clock3 },
  system: { title: '系统', icon: Settings2 },
}

const PANELS: Record<SettingsTab, ComponentType<{ highlight?: string }>> = {
  'data-sources': SettingsDataSourcesPanel,
  monitoring: SettingsMonitoringPanel,
  notifications: SettingsNotificationsPanel,
  ai: SettingsAIPanel,
  menus: SettingsMenuSettingsPanel,
  'ext-pages': SettingsExtPagesPanel,
  timeout: SettingsTimeoutPanel,
  system: SettingsSystemPanel,
}

export function Settings() {
  const [activeTab, changeTab] = usePageTab(SETTINGS_TABS, 'data-sources')
  const [searchParams, setSearchParams] = useSearchParams()
  const highlight = searchParams.get('highlight') ?? ''
  // [R534] 推送通知搬到了「通知」栏: 老书签 / 老链接 `?tab=monitoring&highlight=webhooks` 转过去, 定位照旧
  useEffect(() => {
    if (searchParams.get('tab') === 'monitoring' && highlight === 'webhooks') {
      const next = new URLSearchParams(searchParams)
      next.set('tab', 'notifications')
      setSearchParams(next, { replace: true })
    }
  }, [searchParams, highlight, setSearchParams])
  const Panel = PANELS[activeTab]

  return (
    <div className="flex h-full flex-col">
      <PageHeader
        title="设置"
        className="shrink-0 flex-wrap gap-x-4 gap-y-2"
        right={<PageTabs tabs={SETTINGS_TABS} active={activeTab} onChange={changeTab} label="设置分栏" />}
      />
      {/* [R60] 统一版式: 设置以表单与说明文字为主, 取「读」档。
          [R379 第二层] 设置区是**外围页**, 留白给到 WavMint 那一档(手机页边距 18px, 卡片间距 20~24px);
          **只动这一个容器**, 七个面板一起受益。[R533] 竖向菜单撤了, 内容区直接吃满, 上限 1500px 防超宽屏行长失控。
          [R535] 八栏统一 1024px(max-w-5xl): 原来各面板自带上限 —— AI 672、通知/数据源/菜单 1024、网络/系统/扩展页面
          一路铺到 1500 —— 切栏时左右边界来回跳。宽度只在这一处定, 面板里不再各写各的。 */}
      <main className="min-h-0 flex-1 overflow-y-auto px-4 pb-8 pt-5 lg:px-6">
        <div className="w-full max-w-5xl">
          <Panel highlight={highlight} />
        </div>
      </main>
    </div>
  )
}
