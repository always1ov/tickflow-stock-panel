/**
 * [fork 增强] 市场状态卡 —— 姿态/五个统计格/主线/中观合成一张。
 *
 * [R167] 从 Today.tsx 拆出。R142 把散文横幅改成统计格的那一版就在这里面。
 */
import { useState } from 'react'
import { ChevronDown, Compass, Layers } from 'lucide-react'
import type { TodayOverview } from '@/lib/api'
import { cn } from '@/lib/cn'

function sessionPhaseHint(live: boolean | undefined): { label: string; hint: string } {
  const now = new Date()
  const bj = new Date(now.toLocaleString('en-US', { timeZone: 'Asia/Shanghai' }))
  const day = bj.getDay()
  const mins = bj.getHours() * 60 + bj.getMinutes()
  if (day === 0 || day === 6) {
    return { label: '休市', hint: '周末休市 —— 复盘与做下周计划的时间,数据为上一交易日定稿。' }
  }
  if (mins < 9 * 60 + 30) {
    return {
      label: '盘前',
      hint: '计划时段:以昨收定稿数据定今天的计划 —— 该卖的(行动区)、该盯的(触发价+建仓路径)、买多少(建议仓位)。',
    }
  }
  if (mins < 15 * 60) {
    return live
      ? {
          label: '盘中',
          hint: '执行时段:按盘前计划执行到价预案;实时数字用来盯距离。盘中冒出的新信号只记录,等收盘确认再动手。',
        }
      : {
          label: '盘中',
          hint: '执行时段(实时行情未开):当前为昨收数据,打开左下角「实时行情」后可盘中盯距离。',
        }
  }
  if (mins < 20 * 60) {
    return {
      label: '盘后',
      hint: '日线一般 17:30~20:00 落盘;落盘后刷新,这里就是当日定稿 —— 纪律判定(生命线/出场线/六态)以定稿为准,顺手做明天的计划。',
    }
  }
  return { label: '盘后', hint: '当日数据应已定稿 —— 按定稿数据复盘,并做好明天的计划。' }
}

// [R40] 板块徽章。20cm 的两个板(创业/科创)与 30cm 的北交所用暖色标出来 ——
// 同一个把握分, 20cm 的票波动天然更大, 仓位不该一样。
// [R47] 机会区的通道档位标。与决策台「结论」列、导出件同一份数据 ——
// tone 由后端给, 界面不自己判, 三处不会各说各的。
const POSTURE_STYLE: Record<string, string> = {
  进攻: 'border-red-400/40 bg-red-400/10 text-red-400',
  谨慎: 'border-amber-400/40 bg-amber-400/10 text-amber-300',
  防守: 'border-emerald-400/40 bg-emerald-400/10 text-emerald-400',
  观察: 'border-border bg-base text-muted',
}

// ===== [R122 → R134] 机会区表格 =====
//
// R122 把 15 张同质卡片压成一行一只。R134 换了评分口径, R189 再换成两根轴,
// 这张表也跟着重做 —— 因为**旧版最要命的问题是把握分看不出所以然**: 用户截图里
// 顶上并排两个 100, 光看数字不知道一只强在量能、另一只强在位置, 更不知道是不是
// 因为缺数据被顶上去的。
//
// 现在每一行都能自己解释自己:
//   ┌────┬──────────┬──────────────┬────┬────┬────┬──────────┬────┬─┐
//   │分+ │ 名称/代码 │ 信号          │位置│量比│距触│ 注记      │仓位│▸│
//   │三条│           │               │    │    │发  │(不计分)   │    │ │
//   └────┴──────────┴──────────────┴────┴────┴────┴──────────┴────┴─┘
//
// 「分」下面的三条细条 = 趋势强度 / 量能确认 / 位置成本, 长度就是各自的维度分。
// 同样是 87 分, 三条的形状完全不同 —— 一眼看出这分是谁给的。
//
// 「注记」列摆的是**不参与打分**的佐证(主线/AI/历史胜率/通道档位)。单独成列
// 而不是混进信号里, 是为了让"哪些东西影响了排名"这件事在版面上就一目了然。
function StatCell({ label, value, sub, tone, title }: {
  label: string
  value: React.ReactNode
  sub?: React.ReactNode
  tone?: 'bull' | 'bear' | 'neutral'
  title?: string
}) {
  return (
    <div className="min-w-0 px-3 py-2" title={title}>
      <div className="truncate text-[10px] text-muted">{label}</div>
      <div className={cn('mt-0.5 truncate font-mono text-sm font-semibold',
        tone === 'bull' ? 'text-bull' : tone === 'bear' ? 'text-bear' : 'text-foreground')}>
        {value}
      </div>
      {sub && <div className="mt-0.5 truncate text-[10px] text-muted/80">{sub}</div>}
    </div>
  )
}

export function MarketStatusCard({ d, meso, mainline }: {
  d: TodayOverview
  meso: TodayOverview['meso']
  mainline: NonNullable<TodayOverview['meso']>['mainline'] | null
}) {
  const [whyOpen, setWhyOpen] = useState(false)
  const w = d.weather
  const cap = d.position_hint?.posture_cap
  const phase = sessionPhaseHint(d.live)
  return (
    <div className="overflow-hidden rounded-lg border border-border/60 bg-surface/40">
      {/* 第一行: 结论徽章 —— 姿态是这张卡的标题, 给它最大的字重 */}
      <div className="flex flex-wrap items-center gap-2 border-b border-border/40 px-4 py-2.5">
        <Compass className="h-4 w-4 shrink-0 text-sky-400" />
        <span className={`inline-flex rounded-btn border px-3 py-0.5 text-sm font-medium ${POSTURE_STYLE[w.posture] ?? POSTURE_STYLE['观察']}`}>
          {w.posture}
        </span>
        <span title={phase.hint}
              className="rounded border border-border/60 bg-elevated/50 px-1.5 py-0.5 text-[10px] font-medium text-secondary">
          {phase.label}
        </span>
        {w.market && (
          <span
            title={
              `基准 ${w.market.benchmark_name ?? '—'}(${w.market.as_of ?? '—'})` +
              (w.market.metrics.close != null
                ? ` · 收盘 ${w.market.metrics.close} / 50日线 ${w.market.metrics.ma50} / 年线 ${w.market.metrics.ma200} / 年动量 ${((w.market.metrics.momentum_12m ?? 0) * 100).toFixed(1)}%`
                : '') +
              ` —— 最终姿态取大盘与自选中更保守的一方`
            }
            className={`inline-flex items-center gap-1 rounded-btn border px-2 py-0.5 text-[10px] ${POSTURE_STYLE[w.market.mode] ?? POSTURE_STYLE['观察']}`}
          >
            {w.market.benchmark_name ?? '大盘'}·{w.market.mode}
            {w.market.pending && <span className="opacity-70">(将转{w.market.pending.mode} {w.market.pending.streak}/{w.market.pending.need})</span>}
          </span>
        )}
        <button
          onClick={() => setWhyOpen(v => !v)}
          aria-expanded={whyOpen}
          className="ml-auto inline-flex items-center gap-1 rounded-btn border border-border bg-base px-2 py-0.5 text-[10px] text-muted transition-colors cursor-pointer hover:text-foreground"
        >
          为什么
          <ChevronDown className={cn('h-3 w-3 transition-transform duration-expand ease-smooth',
            whyOpen && 'rotate-180')} />
        </button>
      </div>

      {/* 第二行: 五个统计格。竖分隔线让它们读起来是一排并列的数, 不是一句话 */}
      <div className="grid grid-cols-2 divide-x divide-y divide-border/30 sm:grid-cols-3 lg:grid-cols-5 lg:divide-y-0">
        <StatCell
          label="总仓位基调"
          value={cap != null ? `≤${(cap * 10).toFixed(0)}成` : '—'}
          sub={`${w.posture}档`}
          title="由当前姿态决定的总仓位建议上限 —— 所有持仓加起来别超过这个数。展示用基调, 不是强制" />
        <StatCell
          label="出手结构"
          value={d.gates?.candidates ? `${d.gates.passed}/${d.gates.candidates}` : '—'}
          sub="只候选过门槛"
          tone={d.gates && d.gates.candidates
            ? (d.gates.passed / d.gates.candidates >= 0.4 ? 'bull' : 'bear') : undefined}
          title={d.gates?.text
            ? `${d.gates.text}\n\n候选一堆但过门槛的没几只, 说明信号在遍地开花而趋势结构没跟上 —— 那种日子最容易追在半山腰。`
            : '三道硬门槛: 六态多头侧 / 站上生命线 MA20 / 非长期下跌'} />
        <StatCell
          label="自选强弱"
          value={<><span className="text-bull">{w.bull}</span>
            <span className="mx-1 text-muted/40">/</span>
            <span className="text-bear">{w.bear}</span></>}
          sub={`刚转强 ${w.new_bull} · 刚转弱 ${w.new_bear}`}
          title="自选中处于涨势/跌势的只数; 下面是今天新转强/新转弱的只数" />
        {meso?.breadth ? (
          <StatCell
            label="全市场"
            value={<><span className="text-bull">{meso.breadth.up}</span>
              <span className="mx-1 text-muted/40">/</span>
              <span className="text-bear">{meso.breadth.down}</span></>}
            sub="涨 / 跌"
            title={`全市场涨跌家数(${meso.breadth.date})`} />
        ) : <StatCell label="全市场" value="—" />}
        {meso?.amount ? (
          <StatCell
            label="两市成交额"
            value={meso.amount.text}
            sub={meso.amount.pct_rank != null
              ? `${(meso.amount.pct_rank * 100).toFixed(0)}% 分位 · ${meso.amount.label}`
              : `样本仅 ${meso.amount.sample} 天`}
            title={
              `两市成交额 ${meso.amount.text}${meso.amount.date ? `(${meso.amount.date})` : ''}` +
              (meso.amount.pct_rank != null
                ? ` —— 在最近 ${meso.amount.sample} 个交易日里排在 ${(meso.amount.pct_rank * 100).toFixed(0)}% 分位`
                : ` —— 历史样本只有 ${meso.amount.sample} 天, 不足以给出分位`)
            } />
        ) : <StatCell label="两市成交额" value="—" />}
      </div>

      {/* 第三行: 主线 —— 它是"钱往哪儿聚", 与上面那排数不同层, 单独一行 */}
      {mainline && meso && (
        <div className="flex flex-wrap items-center gap-1.5 border-t border-border/40 px-4 py-2 text-[11px]">
          <span className="flex shrink-0 items-center gap-1.5 text-muted">
            <Layers className="h-3.5 w-3.5 text-fuchsia-400" />
            {mainline.stale ? '主线(数据已停更)' : '今日主线'}
          </span>
          {mainline.rows.slice(0, 3).map((m) => (
            <span
              key={m.member}
              title={`第 ${m.rank} 名 · ${m.limit_up_count} 家涨停 · 最高 ${m.max_boards} 连板${m.leader_symbol ? ` · 龙头 ${m.leader_symbol}` : ''}`}
              className={`shrink-0 rounded px-1.5 py-0.5 ${
                mainline.stale ? 'bg-border/40 text-muted' : 'bg-fuchsia-400/15 text-fuchsia-300'
              }`}
            >
              {m.member}
              <span className="ml-1 font-mono opacity-70">{m.limit_up_count} 家涨停</span>
            </span>
          ))}
          <span
            title={
              (mainline.stale
                ? `主线数据停在 ${mainline.date},已经 ${mainline.age_days} 天没更新 —— 只作展示, 不参与机会区打分。到「数据」页重跑一次涨停梯队相关批次即可恢复。`
                : `按 ${mainline.date} 的涨停梯队聚合:同一概念内涨停家数多、最高连板高、梯队不断层的排在前面。`) +
              ` ${meso.membership_note}`
            }
            className="shrink-0 cursor-help text-muted/60"
          >
            ⓘ
          </span>
        </div>
      )}

      {/* 展开: 原来那两句长散文。它是解释不是结论, 默认收起 */}
      {whyOpen && (
        <div className="animate-rise-in border-t border-border/40 bg-base/40 px-4 py-2.5 text-[11px] leading-relaxed text-muted">
          {w.posture_reason}
        </div>
      )}
    </div>
  )
}

/**
 * [R147] AI 导读·优选的「问一句」弹窗。
 *
 * 用户: 「点击后弹窗我能填点东西带着一起提问, 或者不填也能点击按钮分析」。
 * 所以这里的默认路径必须是**零输入**: 弹窗一开焦点就在「开始分析」上,
 * 回车即走 —— 想说话的人多打一句, 不想说话的人一下都不多点。
 *
 * 补充说明能改什么、不能改什么, 边界写在后端提示词里(见 _AI_SYSTEM 的 R147 段):
 * 它能改关注点与措辞, 改不了输出格式、事实校验与"宁缺毋滥"。这几条必须由
 * 系统契约守住 —— 一句随口的「多选几只」不该能绕过 R121 那套约束。
 */
