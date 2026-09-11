import { type LucideIcon, Construction } from 'lucide-react'

interface Props {
  icon?: LucideIcon
  title: string
  hint?: string
}

// §6.0.5 四态评审 — empty 状态:图示 + 引导,而不是一句"暂无数据"
export function EmptyState({ icon: Icon = Construction, title, hint }: Props) {
  return (
    // [R317] 整组轻微上移 + 淡入, 跟 emil-design-eng 的"列表项入场"档一致
    // (rise-in 260ms, 终态 transform: none 不残留包含块)。空态出现时那一帧
    // 不会再硬切, 与弹窗、Toast 的入场曲线统一 —— 用户连翻几个空页面时,
    // 节奏是连续而不是每页各自"啪"一下。
    <div className="h-full grid place-items-center px-8 py-16 animate-rise-in">
      <div className="text-center max-w-md">
        <Icon className="mx-auto h-10 w-10 text-muted" strokeWidth={1.5} />
        <h2 className="mt-4 text-base font-medium text-foreground">{title}</h2>
        {hint && <p className="mt-2 text-sm text-secondary leading-relaxed">{hint}</p>}
      </div>
    </div>
  )
}
