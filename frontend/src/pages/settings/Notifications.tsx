/**
 * [R534] 设置 → 通知 —— 告警怎么找到你, 都在这一栏。
 *
 * 用户: 「通知设置合到一栏」。原来分在两处:
 *   · 推送通知(飞书 / 企业微信 / 钉钉 / 第三方 / 邮件 / 企微智能机器人)在「实时监控」;
 *   · 通知弹窗、语音播报在「系统」。
 * 三张卡原样搬过来, 每个开关、输入框、测试按钮都没改; 左边外部推送, 右边站内弹窗与语音。
 * `?tab=monitoring&highlight=webhooks` 这类老链接由 Settings.tsx 转到这一栏。
 */
import { PushChannelsCard } from './Monitoring'
import { AlertPopupSettings } from './System'

export function SettingsNotificationsPanel({ highlight }: { highlight?: string } = {}) {
  return (
    <div className="grid max-w-5xl grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
      <div className="space-y-6">
        <PushChannelsCard highlight={highlight} />
      </div>
      <AlertPopupSettings />
    </div>
  )
}
