export function Skeleton({ w = 'w-full', h = 'h-3.5', radius = 'rounded-btn', className = '' }: {
  w?: string; h?: string; radius?: string; className?: string
}) {
  return (
    <div className={`${w} ${h} ${radius} bg-elevated/60 animate-pulse ${className}`} />
  )
}
