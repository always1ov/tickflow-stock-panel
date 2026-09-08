/**
 * [R198] 「这些词是什么意思」—— 决策台角上那个感叹号。
 *
 * ## 一条硬规矩: 只说含义, 不说算法
 *
 * 用户: 「点击就显示这些东西的含义, **但是不能告诉别人具体是怎么算出来的**」。
 * 这与把 Keltner 改名成「量化波动通道」是同一个目的 —— 指标本身是要藏的。
 *
 * 所以这份文案里**不出现**: 均线周期(20/60/120)、ATR 倍数(2/2.5/3)、任何阈值
 * (0.8 / 5 个 ATR / 2 天 / 1.35)、任何公式或比例(9.5:20:30、59/19)、
 * 「三带交集 ÷ 短带宽度」这类构造说明。有测试(test_glossary_hides_math)扫这个
 * 文件, 出现这些就红。
 *
 * 能说的是**读法**: 这个数高说明什么、低说明什么、看到它该想什么。那是用户
 * 自己每天要用的东西, 藏了反而没法用。
 */
import { useState } from 'react'
import { Info, X } from 'lucide-react'

type Entry = { term: string; meaning: string; read: string }

const GROUPS: { title: string; note?: string; items: Entry[] }[] = [
  {
    title: '量化波动通道',
    note: '同一只票在三个时间尺度上的位置读数,竖排三行:短期、中期、长期。三行同向说明三种看法一致;打架说明它们在说不同的事。',
    items: [
      { term: '短期 / 中期 / 长期',
        meaning: '这只票眼下的价格,在各自那个时间尺度里算高还是算低。',
        read: '短期那一行对突发消息最敏感,长期那一行只在真的换了阶段时才动。所以「短期动而中长期不动」多半是一次性冲击,三行齐动才是状态变了。' },
      { term: '结论',
        meaning: '把三行合起来读出的一句话 —— 这个位置是偏贵、偏便宜,还是还不到动手的时候。',
        read: '它说的是**位置**,不是方向。同一个「短线冲高」,在上升趋势里是常态,在下跌趋势里是反弹撞到阻力 —— 所以要配着下面那行事件一起看。' },
    ],
  },
  {
    title: '事件(结论下面那一行小字)',
    note: '位置 + 趋势方向 + 已经持续多久,三样合起来才回答「这到底是什么事」。带问号的表示还没站稳。',
    items: [
      { term: '突破尝试 / 突破站稳',
        meaning: '前者是刚冲出去的第一天,后者是冲出去之后守住了。',
        read: '**这两个差的就是几天,但意义完全不同** —— 第一天随时可能收回去。带问号的别当成已经成立。' },
      { term: '趋势中提速 / 主升浪特征',
        meaning: '趋势已经确认之后又上一个台阶;后者是几个条件同时成立的那种少见情形。',
        read: '这两种情况下沿着上沿走是常态,不必因为「到高位了」就减。' },
      { term: '涨势没劲',
        meaning: '还在高位待着,可是最近走得比之前慢了。',
        read: '涨势没坏,只是没劲了 —— 该开始想「什么情况下我就走」,而不是加仓。' },
      { term: '反弹遇阻',
        meaning: '趋势本身是向下的,这次上冲只是撞到阻力。',
        read: '**最容易被读成突破的一种。** 看着像转强,其实方向没变。' },
      { term: '强势甩人',
        meaning: '趋势还是往上的,但价格短暂掉到了下沿之外。',
        read: '和「真跌破」长得像,区别在于大周期还站着。别把甩人当跌破,割在底部。' },
      { term: '憋着劲',
        meaning: '短、中、长三种看法认的是同一个价,方向还没出来。',
        read: '方向还没出来,但这种状态往往不会持续太久。适合盯着等,不适合猜方向。' },
    ],
  },
  {
    title: '几个数',
    note: '这几个数都用同一把尺子 ——「倍日常波动」。1 倍就是这只票平常一天大致会走的幅度,所以贵的票和便宜的票、慢的票和急的票之间可以直接比。',
    items: [
      { term: '快慢变化',
        meaning: '最近这一段比之前那一段是走得更快了还是更慢了。为零表示速度没变。',
        read: '**不是越大越好。** 稍微快一点是行情刚起来;冲得太猛往往出现在一波的末尾,不是起点。' },
      { term: '三线间距',
        meaning: '短线和长线离多远,带方向 —— 正的是朝上散开,负的是朝下散开,接近零是挤在一起。',
        read: '接近零 = 方向还没出来;适中 = 趋势立住了;太大 = 已经走了很长一段,再追进去不划算。' },
      { term: '离得太远',
        meaning: '间距大到了极端 —— 按短线看和按长线看,已经没有一个共同认可的合理价。',
        read: '同一个价钱,按短线看贵到极点,按长线看还没到位。这时候争论「贵不贵」没有意义,得先想清楚你做的是哪一段。' },
      { term: '已经挤了 N 天 / 这季平均重合',
        meaning: '前者是**连着**多少天三种看法都一致,后者是整个季度**平均**有多一致。',
        read: '**两个要一起看。** 连着的天数是零而平均很高 = 刚刚才走出来;连着的天数不短但平均不高 = 反复散开又挤回去。' },
      { term: '波动主要来自',
        meaning: '这只票眼下的上蹿下跳,主要是几天的短波动、一波行情的主体,还是更早就在的长期老趋势。',
        read: '短波动占多 = 更像消息和情绪在推;一波行情的主体占多 = 正走在主升段上;长期老趋势占多 = 劲都在老趋势里,近期反而平静,动能在衰减。' },
    ],
  },
  {
    title: '该动了(标的名字下面那行)',
    items: [
      { term: '已触发 / 逼近 / 刚变盘 / 到轨',
        meaning: '今天该先看哪几只 —— 从最急到最缓。',
        read: '**一定要连着旁边的「买」「卖」一起读。** 同样是「逼近」,可能是再跌一点就该走了,也可能是再涨一点就是买点 —— 两个相反的动作。' },
    ],
  },
]

export function GlossaryDialog({ onClose }: { onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm"
         onClick={onClose}>
      <div role="dialog" aria-modal="true"
           className="flex max-h-[86vh] w-full max-w-2xl flex-col overflow-hidden rounded-lg border border-border bg-surface shadow-2xl"
           onClick={e => e.stopPropagation()}>
        <header className="flex items-center gap-2 border-b border-border px-4 py-3">
          <Info className="h-4 w-4 shrink-0 text-accent" />
          <span className="text-sm font-medium text-foreground">这些词是什么意思</span>
          <span className="text-[10px] text-muted">只讲怎么读,不讲怎么算</span>
          <button onClick={onClose} className="ml-auto text-muted hover:text-foreground">
            <X className="h-4 w-4" />
          </button>
        </header>
        <div className="min-h-0 flex-1 space-y-4 overflow-auto px-4 py-3">
          {GROUPS.map(g => (
            <section key={g.title}>
              <h3 className="text-xs font-semibold text-foreground">{g.title}</h3>
              {!!g.note && <p className="mt-0.5 text-[10px] leading-relaxed text-muted">{g.note}</p>}
              <dl className="mt-1.5 space-y-2">
                {g.items.map(it => (
                  <div key={it.term} className="rounded border border-border/50 bg-elevated/25 px-2.5 py-2">
                    <dt className="text-[11px] font-medium text-foreground/90">{it.term}</dt>
                    <dd className="mt-0.5 text-[10px] leading-relaxed text-secondary">{it.meaning}</dd>
                    <dd className="mt-1 text-[10px] leading-relaxed text-muted">{it.read}</dd>
                  </div>
                ))}
              </dl>
            </section>
          ))}
          <p className="pt-1 text-[10px] leading-relaxed text-muted/70">
            以上全部是规则算出来的固定判定,AI 不参与 —— 它只解释,不决定顺序也不改分数。
            所有位置类读数一律按收盘算。
          </p>
        </div>
      </div>
    </div>
  )
}

/** 角上那个感叹号 —— 单独导出, 方便别的表也挂同一份说明。 */
export function GlossaryButton() {
  const [open, setOpen] = useState(false)
  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        title="这些词是什么意思"
        aria-label="这些词是什么意思"
        className="inline-flex h-6 w-6 items-center justify-center rounded-btn border border-border/60 text-[11px] font-semibold text-muted transition-colors hover:border-accent/40 hover:text-accent"
      >
        !
      </button>
      {open && <GlossaryDialog onClose={() => setOpen(false)} />}
    </>
  )
}
