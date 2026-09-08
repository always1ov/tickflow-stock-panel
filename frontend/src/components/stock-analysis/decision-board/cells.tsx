/**
 * [fork 增强] 决策台的两个只读单元格: Keltner 三档位置 / 三档组合结论。
 *
 * [R167] 从 WatchlistDecisionBoard.tsx 拆出。各自带着自己的配色表 —— 配色表是
 * 实现细节, 不该摆在 933 行主文件的顶部让人以为是全局约定。
 */
import type { ReactNode } from 'react'
import type { ExitLine, KeltnerBand, KeltnerVerdict, Urgency } from '@/lib/api'
import { VerdictHover } from '@/components/stock-analysis/VerdictHover'

// [R42] Keltner 位置配色。破上轨/贴上轨用暖色(偏贵), 破下轨/贴下轨用冷色(偏便宜),
// 通道内保持中性 —— 位置是事实, 不替用户下买卖判断。
const KELTNER_CLS: Record<KeltnerBand['pos'], string> = {
  above: 'border-red-400/40 bg-red-400/10 text-red-400',
  near_upper: 'border-amber-400/40 bg-amber-400/10 text-amber-400',
  inside: 'border-border bg-base text-muted',
  near_lower: 'border-sky-400/40 bg-sky-400/10 text-sky-300',
  below: 'border-emerald-400/40 bg-emerald-400/10 text-emerald-400',
}

/**
 * 一档 Keltner 通道的单元格。
 *
 * 显示"贴上轨"这种五档文字, 悬停给出真实的上下轨价、通道内位置百分比,
 * 以及"还差几个 ATR 到轨" —— 只给一个标签等于让用户盲信一个没法复核的判断。
 * 该档算不出来(新股不够 120 根 / 均线列缺失)时显示 "—", 不编一个数出来。
 */
export function KeltnerCell({ band, close }: { band?: KeltnerBand; close: number | null }) {
  if (!band) {
    return <td className="whitespace-nowrap px-1.5 py-2.5 text-center"><span className="text-[10px] text-muted/40">—</span></td>
  }
  const pct = Math.round(band.pct * 100)
  return (
    <td className="whitespace-nowrap px-1.5 py-2.5 text-center">
      <span
        className={`inline-flex whitespace-nowrap rounded border px-1 py-0.5 text-[10px] ${KELTNER_CLS[band.pos]}`}
        title={
          `${band.band_cn}通道 ${band.lower.toFixed(2)} ~ ${band.upper.toFixed(2)}` +
          `${close != null ? `,收盘 ${close.toFixed(2)}` : ''}\n` +
          `通道内位置 ${pct}%(0% 贴下轨 / 100% 贴上轨)\n` +
          `距上轨 ${band.to_upper_atr ?? '—'} 个 ATR · 距下轨 ${band.to_lower_atr ?? '—'} 个 ATR\n` +
          `${band.hint}\n收盘口径 —— 通道要用 ATR 与均线, 实时价比昨天的通道会半新半旧`
        }
      >
        {band.pos_cn}
      </span>
    </td>
  )
}

// [R44] 三档组合的结论配色。tone 由后端给, 界面不自己判 ——
// 决策台、今日总览、悬停提示必须说同一句话。
const VERDICT_CLS: Record<KeltnerVerdict['tone'], string> = {
  sell: 'border-red-400/40 bg-red-400/10 text-red-400',
  buy: 'border-sky-400/40 bg-sky-400/10 text-sky-300',
  hold: 'border-amber-400/40 bg-amber-400/10 text-amber-400',
  avoid: 'border-border bg-base text-muted',
  // [R45] 观察档: 还不到动手的时候, 用最淡的一档, 跟四个动作档区分开
  watch: 'border-border bg-elevated/60 text-secondary',
}

/**
 * 「通道结论」单元格 —— 三档组合翻成一句人话。
 *
 * 徽标只放 4-6 字的结论标题, 悬停给分段排版的完整卡片(R49, 见 VerdictHover),
 * 点击翻这只票的逐日复盘(R48) —— 这一列说的话在它身上过去好不好使, 只有
 * 翻历史才知道。短期档在通道中部时显示 "—": 那时这一列确实没有信息。
 */
export function VerdictCell({ v, onOpen }: { v?: KeltnerVerdict | null; onOpen: () => void }) {
  if (!v) {
    return (
      <td className="whitespace-nowrap px-1.5 py-2.5 text-center">
        <button
          onClick={onOpen}
          className="cursor-pointer text-[10px] text-muted/40 hover:text-sky-300"
          title="短期通道在中部 —— 位置上没有可说的, 听趋势和信号的。点击翻这只票过去出过哪些结论"
        >
          —
        </button>
      </td>
    )
  }
  return (
    <td className="whitespace-nowrap px-1.5 py-2.5 text-center">
      <VerdictHover v={v} note="点击摊开这只票过去每一档结论 —— 出现在哪几天、当时说了什么、之后走成什么样。">
        <button
          onClick={onOpen}
          className={`inline-flex cursor-pointer whitespace-nowrap rounded border px-1 py-0.5 text-[10px] transition-colors hover:brightness-125 ${VERDICT_CLS[v.tone]}`}
        >
          {v.title}
        </button>
      </VerdictHover>
    </td>
  )
}

// ===== [R46] 自包含 HTML 导出 =====
// 只导出「结论」列有内容的行 —— 三档都在通道中部的票没有位置信息,
// 导出来只是占地方。导出件里第一行就写清导出了几只、总共几只, 免得
// 看到 148 只自选导出 4 行时以为漏了。
//
// 与今日总览的导出同一套排版: 浅色、内联样式、无脚本无外链, 存档/打印/
// 转发都不依赖这个应用。



// [R178] 「该动了」配色。急的用暖色、无事的彻底压暗 —— 这一列的作用是让眼睛
// 在 80 行里一秒找到该看的那几行, 所以对比要拉开, 不能像别的列那样克制。
const URGENCY_CLS: Record<Urgency['level'], string> = {
  triggered: 'border-red-400/50 bg-red-400/15 text-red-400 font-medium',
  near: 'border-amber-400/40 bg-amber-400/10 text-amber-400',
  flip: 'border-violet-400/40 bg-violet-400/10 text-violet-300',
  band: 'border-sky-400/30 bg-sky-400/5 text-sky-300/90',
  idle: 'border-transparent text-muted/30',
}

/**
 * 「该动了」单元格。
 *
 * 显示档位 + 离触发多远, 悬停给判定理由 —— 只给一个"逼近"的标签而不说凭什么,
 * 用户没法复核, 那就跟 AI 随口说一句没有区别。这里每一档背后都是一条写死的
 * 规则(见 backend/app/services/watchlist_urgency.py), 理由是后端给的原话。
 *
 * 判定还没回来时显示 "—" 而不是"无事" —— 那是两件事, 混在一起会让人以为
 * 今天真没事。
 */
export function UrgencyCell({ u }: { u?: Urgency }) {
  if (!u) return <td className="px-2 py-1.5 text-center text-muted/30">—</td>
  const showDist = u.level !== 'idle' && u.distance != null
  return (
    <td className="whitespace-nowrap px-2 py-1.5 text-center">
      <span
        title={u.reason}
        className={`inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-[10px] ${URGENCY_CLS[u.level]}`}
      >
        {u.label}
        {showDist && (
          <span className="font-mono opacity-70">{(u.distance! * 100).toFixed(1)}%</span>
        )}
      </span>
    </td>
  )
}

// ============================================================================
// [R184] 行情 + 持仓 合并单元格
// ============================================================================
//
// 原来是 6 个独立列: 现价 / 涨跌 / 仓位 / 成本 / 浮盈 / 止盈线。问题不在于列多,
// 在于**后四列对绝大多数行是空的** —— 成本要手填、浮盈要成本、止盈线要"持有+
// 成本"。自选里空仓票占大头, 于是四列宽度长期空着, 还占着表格最中间的位置
// (成本/仓% 那两个输入框尤其宽, 空着也得留位)。
//
// 合成一列之后:
//   空仓行  一行:  [空仓]  现价  涨跌            ← 行高变矮, 一屏多看好几行
//   持有行  两行:  [持有]  现价  涨跌
//                  成本[_] 仓%[_] 批n · 浮盈 · 止盈线
//
// **合并唯一的真代价是丢排序键**(6 个 → 1 个), 所以表头改成可选排序目标的下拉,
// 六个一个不少 —— 见主文件 SortMenu。
//
// 一个刻意的细节: 现价与涨跌固定宽度 + tabular-nums。合并进一个单元格之后,
// 纵向对齐全靠这个 —— 数字不对齐, 这一列就没法一眼扫下去了。

export function PriceHoldingCell({
  r, manualCost, onSave, lotsLink,
}: {
  r: {
    symbol: string; close: number | null; changePct: number | null
    held: boolean; weight: number | null; pnl: number | null
    exit?: ExitLine
    costSource?: string | null; lotCost?: number | null; costDriftPct?: number | null
    lotCount: number
  }
  manualCost: number | null
  onSave: (patch: { held: boolean; cost: number | null; weight: number | null }) => void
  /** 批次入口由主文件传进来 —— 它要 Link, 不该让这个纯展示模块也依赖路由 */
  lotsLink: (opts: { stale?: boolean }) => ReactNode
}) {
  const up = (r.changePct ?? 0) > 0
  const down = (r.changePct ?? 0) < 0
  return (
    <td className="px-2 py-2 align-top">
      {/* 第一行: 每行都有 —— 持有开关 + 行情 */}
      <div className="flex items-center gap-2">
        <button
          onClick={() => onSave({ held: !r.held, cost: manualCost, weight: r.weight })}
          className={`shrink-0 whitespace-nowrap rounded border px-1.5 py-0.5 text-[10px] transition-colors cursor-pointer ${
            r.held ? 'border-amber-400/40 bg-amber-400/10 text-amber-400'
                   : 'border-border bg-base text-muted hover:border-amber-400/30'}`}
        >
          {r.held ? '持有' : '空仓'}
        </button>
        {/* 固定宽度 —— 合并之后纵向对齐全靠它 */}
        <span className="w-[4.5rem] shrink-0 text-right font-mono tabular-nums text-[12px] text-foreground">
          {r.close != null ? r.close.toFixed(2) : '—'}
        </span>
        <span className={`w-[3.75rem] shrink-0 text-right font-mono tabular-nums text-[11px] ${
          up ? 'text-red-400' : down ? 'text-emerald-400' : 'text-muted'}`}>
          {r.changePct != null ? `${(r.changePct * 100).toFixed(2)}%` : '—'}
        </span>
        {/* 空仓但批次还挂着 —— 多半是卖出后忘了删, 那两条监控规则还在跑 */}
        {!r.held && r.lotCount > 0 && lotsLink({ stale: true })}
      </div>

      {/* 第二行: 只有持有才画 —— 空仓行到此为止, 这就是省下来的宽度与行高 */}
      {r.held && (
        <div className="mt-1 flex flex-wrap items-center gap-1.5">
          <input
            type="number"
            defaultValue={manualCost ?? ''}
            placeholder={r.costSource === 'lots' && r.lotCost != null ? `批 ${r.lotCost.toFixed(2)}` : '成本'}
            title={r.costSource === 'lots' && r.lotCost != null
              ? `成本来自批次页的 ${r.lotCount} 笔(数量加权均价 ${r.lotCost.toFixed(2)})。留空即跟随批次; 填了以填的为准。`
              : '买入成本(手填)'}
            onBlur={(e) => {
              const v = e.target.value === '' ? null : Number(e.target.value)
              if (v !== manualCost) onSave({ held: true, cost: v, weight: r.weight })
            }}
            className={`h-5 w-14 rounded border bg-base px-1 text-right font-mono text-[10px] text-foreground focus:border-accent/50 focus:outline-none ${
              r.costSource === 'lots' ? 'border-accent/35 placeholder:text-accent/70' : 'border-border'}`}
          />
          <input
            type="number" min={0} max={100}
            defaultValue={r.weight ?? ''}
            placeholder="仓%"
            title="仓位比例(占总资金 %),可选 —— 填了今日总览才能算组合总仓位、净值回撤与超配提醒。"
            onBlur={(e) => {
              const v = e.target.value === '' ? null : Number(e.target.value)
              if (v !== r.weight) onSave({ held: true, cost: manualCost, weight: v })
            }}
            className="h-5 w-11 rounded border border-border bg-base px-1 text-right font-mono text-[10px] text-foreground focus:border-accent/50 focus:outline-none"
          />
          {lotsLink({})}
          {r.pnl != null && (
            <span className={`font-mono text-[10px] ${r.pnl > 0 ? 'text-red-400' : r.pnl < 0 ? 'text-emerald-400' : 'text-muted'}`}
                  title="浮盈 = (现价 − 成本) / 成本">
              {(r.pnl * 100).toFixed(1)}%
            </span>
          )}
          {r.exit && (
            <span
              className={`whitespace-nowrap font-mono text-[10px] ${
                r.exit.triggered ? 'text-red-400'
                  : r.exit.distance_pct > -0.03 ? 'text-amber-300' : 'text-muted'}`}
              title={`${r.exit.stage_cn} · ${r.exit.line_cn}\n跌破 ${r.exit.line.toFixed(2)} → ${r.exit.action}(k=${r.exit.k}, ATR14=${r.exit.atr})${
                r.exit.lifeline ? `\n生命线(20日线) ${r.exit.lifeline.toFixed(2)} — 收盘跌破无条件清仓` : ''}`}
            >
              {r.exit.stage === 'fatal' ? '⚠生命线破位' : r.exit.triggered
                ? `已破 ${r.exit.line.toFixed(2)}`
                : `${r.exit.line.toFixed(2)} 距${(r.exit.distance_pct * 100).toFixed(1)}%`}
            </span>
          )}
        </div>
      )}
    </td>
  )
}
