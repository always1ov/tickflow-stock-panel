import { useState } from 'react'
import { SlidersHorizontal, Waypoints } from 'lucide-react'
import { StrategyOptimizer } from './StrategyOptimizer'
import { StrategyWalkForward } from './StrategyWalkForward'
import { SEG, SEG_ITEM, SEG_ON, SEG_OFF } from '@/components/ui'
import { cn } from '@/lib/cn'

type Mode = 'sensitivity' | 'walkforward'

export function RobustnessValidation() {
  const [mode, setMode] = useState<Mode>('sensitivity')
  return (
    <div className="flex h-full min-h-0 flex-col gap-3">
      <div className="flex shrink-0 items-center border-b border-border/70 px-1 pb-2">
        <div className={SEG}>
          {([
            ['sensitivity', '参数优化', SlidersHorizontal],
            ['walkforward', '步进优化', Waypoints],
          ] as const).map(([value, label, Icon]) => (
            <button
              key={value}
              type="button"
              onClick={() => setMode(value)}
              className={cn(SEG_ITEM, 'gap-1.5 px-3', mode === value ? SEG_ON : SEG_OFF)}
            >
              <Icon className="h-3.5 w-3.5" />
              {label}
            </button>
          ))}
        </div>
      </div>
      <div className="min-h-0 flex-1">
        {mode === 'sensitivity' ? <StrategyOptimizer /> : <StrategyWalkForward />}
      </div>
    </div>
  )
}
