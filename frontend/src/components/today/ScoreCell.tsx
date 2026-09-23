/**
 * [fork 增强 R345] 「名次」那一格 —— **一处实现, 两页共用**。
 *
 * 原来它是 `OpportunityTable.tsx` 里的私有函数。模拟盘也要用这一格(用户:
 * 「这一列要移植」), **不复制一份**: 三条维度条的颜色、权重、悬停里那段解释
 * 两处各写一遍, 哪天权重改了必然漂 —— 而漂的表现是"两个页面对同一只票给出
 * 不同的说法", 看上去两边都没坏。
 *
 * 三条维度条的语义(颜色 = 哪个维度、长度 = 那一维的分)也一并搬过来,
 * 因为**离开那三条颜色, 上面那个名次就只是个号码**: 它说不出"为什么是这个名次"。
 */
import type { TodayOpportunity } from '@/lib/api'
import { cn } from '@/lib/cn'

// [R345] 这里**没有 `w` 字段**。原来有一个 `w: '45%'`, 但全项目没有任何地方读它
// —— 变异测试把它改空, 界面上一个字没变。权重真正露面的地方是下面 `what` 里的
// 那句话与 `ScoreCell` 悬停里那条公式。「没人调的代码看起来像在用」这个仓库
// 栽过好几次, 顺手删掉。
export const DIM_META = [
  { key: 'trend', cn: '趋势强度', cls: 'bg-red-400',
    what: '这只票的方向有多强 —— 权重 45%',
    hint: '新鲜度(主导) / 六态状态 / 相对强度' },
  { key: 'volume', cn: '量能确认', cls: 'bg-sky-400',
    what: '有没有人跟 —— 权重 30%',
    hint: '量比(主导,区间最优,峰在 1.3~2.5) / 换手率' },
  { key: 'position', cn: '位置成本', cls: 'bg-amber-400',
    what: '买在什么位置 —— 权重 25%',
    hint: '通道位置(甜区 50%~65%,越接近 100% 越是追高)' },
] as const

export function dimVerdict(t?: number | null, v?: number | null, p?: number | null): string | null {
  if (t == null || v == null || p == null) return null
  if (t >= 70 && v < 50) return '形态到了但没人跟 —— 等放量,别自己先冲'
  if (v >= 70 && p < 50) return '今天是有动静,但这个价已经不便宜 —— 追进去性价比低'
  if (t < 50 && v >= 70) return '有量但方向还没出来 —— 不值得占仓位'
  if (t >= 70 && v >= 70 && p >= 70) return '方向、量能、位置三样都在位'
  return null
}

/**
 * [R201] 「今天该看哪几只」这一格 —— **名次在前, 分数退到副位**。
 *
 * 为什么改: 把握分是五个因子加权平均再取几何平均, 而"平均"这件事本身就把
 * 取值挤向中间 —— 实测 p10~p90 只有 17 分(65~82)。于是 68 分这个数字对用户
 * **没有可读的含义**: 它既不是"及格", 也说不清是今天的第几档。名次和分位
 * 没有这个毛病, 它们天然是相对的, 一眼就知道该不该往下看。
 *
 * 分数仍然显示(台账要它做跨日比较, 用户也需要能核对), 只是不再当主角。
 */
export function ScoreCell({ o, rank, total }: { o: TodayOpportunity; rank: number; total: number }) {
  const dims = o.dims
  const detail = DIM_META
    .map(d => `${d.cn} ${dims?.[d.key] ?? '无数据'} — ${d.what}`)
    .join('\n')
  const verdict = dimVerdict(dims?.trend, dims?.volume, dims?.position)
  const pct = o.pct_rank != null ? Math.round((1 - o.pct_rank) * 100) : null
  return (
    <span
      className="inline-flex w-14 shrink-0 flex-col items-center gap-1"
      title={`今日候选里排第 ${rank}/${total}`
        + (pct != null ? `(前 ${Math.max(1, pct)}%)` : '')
        + `\n把握分 ${o.score} = 趋势强度×45% + 量能确认×30% + 位置成本×25%\n\n${detail}\n\n`
        + (verdict ? `${verdict}\n\n` : '')
        + (o.partial
          ? '⚠ 有因子没读到,那一份权重是靠剩下的顶上来的 —— 总分偏乐观,同分时优先选没带 * 的'
          : '三个维度的因子都齐全')}
    >
      <span className="font-mono text-xs font-semibold leading-none text-foreground">
        {rank}
        <span className="text-micro font-normal text-muted">/{total}</span>
      </span>
      <span className="font-mono text-micro leading-none text-muted">
        {o.score}
        {o.partial && (
          <span className="text-warning" title="有因子没读到, 总分偏乐观">*</span>
        )}
      </span>
      <span className="w-full space-y-[2px]">
        {DIM_META.map(d => {
          const v = dims?.[d.key]
          return (
            <span key={d.key} className="block h-[3px] overflow-hidden rounded-full bg-border/50">
              {v != null && (
                <span className={cn('block h-full rounded-full transition-ui duration-enter ease-smooth', d.cls)}
                      style={{ width: `${Math.max(3, Math.min(100, v))}%` }} />
              )}
            </span>
          )
        })}
      </span>
    </span>
  )
}
