/**
 * [fork 增强] 决策台的两个只读单元格: Keltner 三档位置 / 三档组合结论。
 *
 * [R167] 从 WatchlistDecisionBoard.tsx 拆出。各自带着自己的配色表 —— 配色表是
 * 实现细节, 不该摆在 933 行主文件的顶部让人以为是全局约定。
 */
import type { KeltnerBand, KeltnerVerdict, Urgency } from '@/lib/api'
import { VerdictHover } from '@/components/stock-analysis/VerdictHover'

/**
 * [R194] 决策台单元格的统一基线。**整张表只有这一处定义垂直对齐与行内边距。**
 *
 * 上一版参差的原因就是没有这一处: 行内 td 写 `py-2.5` 走默认居中、Keltner 与
 * 结论写 `px-1.5 py-2.5`、R193 的「该动」写 `py-1.5 align-top` —— 三套各写各的。
 * 平时看不出来, 一旦某行的「该动」是三行、「AI 信号」是三行, 单行的那几列
 * (现价/涨跌/浮盈/置信)就飘到了行的**垂直中间**, 而多行的那几列贴着顶,
 * 一屏扫下来没有任何一条共同的基线。
 *
 * 选 `align-top` 而不是 `align-middle`: 这张表有三列天然多行(该动 / AI 分析 /
 * AI 信号), 居中会让"这一行从哪儿开始读"每行都不一样。顶对齐之后,
 * **每一行的所有列都从同一条线起笔** —— 这才是"每一列每一行都整齐对齐"。
 */
export const TD_BASE = 'align-top py-2'

/**
 * 数字列的统一写法。`tabular-nums` 是**列对齐的关键**: 没有它, 比例字形下
 * `1` 比 `8` 窄, 386.50 与 1088.00 的小数点在列里就对不齐, 一列数字看着像
 * 波浪线。只给 `font-mono` 不够 —— 有些等宽字体的数字仍走比例宽度。
 */
export const NUM = 'font-mono tabular-nums'

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
    return <td className={`${TD_BASE} whitespace-nowrap px-1.5 text-center`}><span className="text-[10px] text-muted/40">—</span></td>
  }
  const pct = Math.round(band.pct * 100)
  return (
    <td className={`${TD_BASE} whitespace-nowrap px-1.5 text-center`}>
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
      <td className={`${TD_BASE} whitespace-nowrap px-1.5 text-center`}>
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
    <td className={`${TD_BASE} whitespace-nowrap px-1.5 text-center`}>
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

// [R193] 方向标。**档位管急不急, 方向管买还是卖 —— 两个正交的维度**,
// 原来只显示了前者。同样一个琥珀色的「逼近」, 可能是"再跌一点就破止损"
// 也可能是"再涨一点就转强", 不标方向的话扫表时长得一模一样。
const SIDE_CLS: Record<string, string> = {
  sell: 'border-rose-400/50 bg-rose-400/15 text-rose-300',
  buy: 'border-sky-400/50 bg-sky-400/15 text-sky-300',
  info: 'border-border/50 text-muted/70',
}

/**
 * 「该动了」单元格。
 *
 * [R193] 用户: 「这一列要把话说清楚, 太简洁了, 这也不行, 会误人子弟」。
 *
 * 原来只画一个「逼近 0.5%」的胶囊, 其余全在悬停的 title 里。**一列 80 行是
 * 用来扫的, 扫的时候没人会悬停** —— 所以那句解释等于不存在, 而缺了它,
 * 「该卖」和「该买」在这一列里完全同形。这是这一列唯一一处真会害人的地方。
 *
 * 现在单元格自己说三件事:
 *   ① 档位 + 距离   —— 有多急(已触发那一档给的是"已经破了多少", 不再是假的 0.0%)
 *   ② 方向          —— 买还是卖, 单独一个色块, 不靠语义色去暗示
 *   ③ 哪条线 / 该干嘛 —— 带上具体价位, 能直接照着挂单
 *
 * 判定还没回来时显示 "—" 而不是"无事" —— 那是两件事, 混在一起会让人以为
 * 今天真没事。每一档背后都是一条写死的规则(见 services/watchlist_urgency.py),
 * 这里显示的是后端给的原话, 前端不自己编。
 */
export function UrgencyCell({ u }: { u?: Urgency }) {
  if (!u) return <td className={`${TD_BASE} px-2 text-muted/30`}>—</td>
  if (u.level === 'idle') {
    return (
      <td className={`${TD_BASE} px-2`}>
        <span className="text-[10px] text-muted/30" title={u.reason}>无事</span>
      </td>
    )
  }
  const showDist = u.distance != null
  const side = u.side ?? 'info'
  return (
    <td className={`${TD_BASE} px-2`} title={u.reason}>
      <div className="flex flex-col items-start gap-0.5">
        <div className="flex items-center gap-1">
          <span className={`inline-flex items-center gap-1 whitespace-nowrap rounded border px-1.5 py-0.5 text-[10px] ${URGENCY_CLS[u.level]}`}>
            {u.label}
            {showDist && (
              <span className={`${NUM} opacity-70`}>{(u.distance! * 100).toFixed(1)}%</span>
            )}
          </span>
          {/* 方向单独一块。**这一格是整列的重点** —— 没有它, 「逼近」两个字
              在该卖的票和该买的票上完全一样 */}
          {u.side_cn && (
            <span className={`inline-flex shrink-0 rounded border px-1 py-0.5 text-[10px] font-medium ${SIDE_CLS[side]}`}>
              {u.side_cn}
            </span>
          )}
        </div>
        {/* 哪条线、什么价、差多远 —— 带价位才能直接照着挂单 */}
        {u.what && (
          <span className="text-[9px] leading-tight text-secondary/90">{u.what}</span>
        )}
        {/* 该干什么。刻意与上一行分开: 「差多远」是事实, 「该干嘛」是建议 */}
        {u.action && (
          <span className="text-[9px] leading-tight text-muted/80">{u.action}</span>
        )}
      </div>
    </td>
  )
}
