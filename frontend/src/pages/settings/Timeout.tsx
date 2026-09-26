/**
 * 超时设置面板 — 数据任务超时配置。
 */
import { JobTimeoutCard } from './JobTimeoutCard'

export function SettingsTimeoutPanel() {
  return (
    <div className="space-y-5">
      <JobTimeoutCard />
    </div>
  )
}
