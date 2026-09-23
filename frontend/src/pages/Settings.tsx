/**
 * 统一设置页面 — Tab 切换外壳。
 *
 * 通过 URL query param ?tab=xxx 同步 Tab 状态。
 */
import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { motion } from 'framer-motion'
import { BarChart3, Database, Radio, SlidersHorizontal, Sparkles, Settings2, PanelLeftClose, PanelLeftOpen, Clock3 } from 'lucide-react'
import { SettingsAIPanel } from './settings/AI'
import { SettingsMonitoringPanel } from './settings/Monitoring'
import { SettingsExtPagesPanel } from './settings/ExtPages'
import { SettingsMenuSettingsPanel } from './settings/MenuSettings'
import { SettingsTimeoutPanel } from './settings/Timeout'
import { SettingsSystemPanel } from './settings/System'
import { SettingsDataSourcesPanel } from './settings/DataSources'
import { PageHeader } from '@/components/PageHeader'
import { cn } from '@/lib/cn'

import type { ComponentType } from 'react'

// ===== Tab 定义 =====

type TabDef = {
  key: string
  label: string
  icon: ComponentType<{ className?: string }>
  panel: ComponentType<{ highlight?: string }>
  badge?: string
}

const TABS: readonly TabDef[] = [
  { key: 'data-sources', label: '数据源',     icon: Database,  panel: SettingsDataSourcesPanel },
  { key: 'ai',         label: 'AI 设置',    icon: Sparkles,  panel: SettingsAIPanel },
  { key: 'monitoring', label: '实时监控',   icon: Radio,     panel: SettingsMonitoringPanel },
  { key: 'ext-pages',  label: '扩展页面',   icon: BarChart3, panel: SettingsExtPagesPanel },
  { key: 'timeout',    label: '网络设置',   icon: Clock3,    panel: SettingsTimeoutPanel },
  { key: 'menus',      label: '菜单设置',   icon: SlidersHorizontal, panel: SettingsMenuSettingsPanel },
  { key: 'system',     label: '系统设置',   icon: Settings2, panel: SettingsSystemPanel },
]

type TabKey = (typeof TABS)[number]['key']

export function Settings() {
  const [searchParams, setSearchParams] = useSearchParams()
  const tabParam = searchParams.get('tab') as TabKey | null
  const activeTab = TABS.find((t) => t.key === tabParam) ?? TABS[0]
  const highlight = searchParams.get('highlight') ?? ''

  // 设置菜单收起状态 — 持久化到 localStorage
  // [R374] 窄屏(<768px)首次访问默认收起 nav, 否则左 144px + gap 80px = 224px
  // 直接顶掉右栏, 内容区只剩 151px 几乎不可读。用户已存的偏好不覆盖。
  const [collapsed, setCollapsed] = useState(() => {
    try {
      const stored = localStorage.getItem('tf-settings-nav-collapsed')
      if (stored !== null) return stored === '1'
      return !window.matchMedia('(min-width: 768px)').matches
    } catch { return false }
  })
  const toggleCollapsed = () => {
    setCollapsed(prev => {
      const next = !prev
      try { localStorage.setItem('tf-settings-nav-collapsed', next ? '1' : '0') } catch {}
      return next
    })
  }

  return (
    <>
      <PageHeader
        title="设置"
        subtitle="管理账户、数据刷新策略和高级功能配置。"
      />

      {/* [R60] 统一版式: 设置以表单与说明文字为主, 取「读」档
          [R115] 重排: 原来整块 mx-auto max-w-[1100px] 居中 + tab 列表垂直居中
          (justify-center min-h-[60vh]), 宽屏下导航浮在屏幕正中、两侧各留一大片
          空白, 内容区反被挤窄。改为**贴左贴顶**: 导航紧跟应用侧栏、从顶部开始,
          内容区吃掉剩余宽度(上限 1500px 防超宽屏行长失控, 左对齐不居中)。 */}
      {/* [R379 第二层] 设置区是**外围页** —— 这里没有一屏几百个数字要塞, 密度
          不是它的目标, 所以留白给到 WavMint 那一档(手册 §1.3: 手机页边距 18px,
          卡片间距 20~24px)。**只动这一个容器**, 七个面板一起受益, 不用逐个去改。
          看盘那些页一个像素没碰。 */}
      <div className="px-4 pb-8 pt-5 lg:px-6">
        <div className="w-full">
        <div className="flex gap-5 items-start">
          {/* ===== 竖向 Tab 侧栏 ===== */}
          <nav className={cn('shrink-0 transition-ui duration-expand ease-smooth', collapsed ? 'w-10' : 'w-36')}>
            <div className="flex flex-col gap-0.5 sticky top-3">
              {/* 收起/展开 按钮 */}
              <button
                onClick={toggleCollapsed}
                className={cn(
                  'flex items-center gap-2 rounded-btn text-muted hover:text-foreground hover:bg-elevated/60 transition-colors duration-hover ease-smooth mb-1',
                  collapsed ? 'justify-center px-0 py-2' : 'px-3 py-2 text-xs',
                )}
                title={collapsed ? '展开菜单' : '收起菜单'}
              >
                {collapsed
                  ? <PanelLeftOpen className="h-3.5 w-3.5 shrink-0" />
                  : <PanelLeftClose className="h-3.5 w-3.5 shrink-0" />
                }
                {!collapsed && <span>收起菜单</span>}
              </button>

              {/* Tab 按钮列表 — 收起时只显示图标 */}
              {TABS.map(({ key, label, icon: Icon, badge }) => (
                <button
                  key={key}
                  onClick={() => setSearchParams({ tab: key }, { replace: true })}
                  title={collapsed ? label : undefined}
                  className={cn(
                    'relative flex items-center rounded-btn text-sm transition-colors duration-hover ease-smooth',
                    collapsed ? 'justify-center px-0 py-2' : 'items-center gap-2 px-3 py-2 text-left',
                    activeTab.key === key
                      ? 'bg-accent-soft text-accent font-medium'
                      : 'text-secondary hover:text-foreground hover:bg-elevated/60',
                  )}
                >
                  <Icon className="h-3.5 w-3.5 shrink-0" />
                  {!collapsed && <span>{label}</span>}
                  {!collapsed && badge && (
                    <span className="ml-auto inline-flex items-center rounded-btn border border-warning/30 bg-warning/10 px-1.5 py-0.5 text-micro font-medium text-warning shrink-0">
                      {badge}
                    </span>
                  )}
                </button>
              ))}
            </div>
          </nav>

          {/* ===== Tab 内容 ===== */}
          <motion.div
            key={activeTab.key}
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.15 }}
            className="min-w-0 flex-1 max-w-[1500px]"
          >
            {activeTab.key === 'monitoring'
            ? <SettingsMonitoringPanel highlight={highlight} />
            : <activeTab.panel highlight={highlight} />}
          </motion.div>
        </div>
        </div>
      </div>
    </>
  )
}
