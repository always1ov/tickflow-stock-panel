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
  // [R211] **第一节是几何含义, 不是词汇表。**
  //
  // 用户: 「这个叹号里面的东西不对, 解释含义才放里面, 比如几何解释这些」。
  // 原来这份从第一条起就在逐个解释列名 —— 那是词典, 不是说明。可这三条线
  // **为什么放在一起看**、它们的相对位置**在几何上意味着什么**, 才是所有
  // 后续判定的地基; 不先讲这个, 底下那些「间距」「挤在一起」都只能死记。
  //
  // 依旧守着「只讲含义、不讲算法」: 下面没有周期、没有倍数、没有公式,
  // 讲的全是"这个形状代表什么"。
  {
    title: '先说清楚:这三条线到底在说什么',
    note: '底下所有的判定 —— 贵不贵、通道态势、怎么办 —— 都是从这一件事推出来的。',
    items: [
      { term: '三条线 = 同一个价格的三种看法',
        meaning: '短期、中期、长期不是三个指标,是**同一只票的价格在三个时间尺度上各自的「合理区间」**。'
          + '短期那条问的是「按最近这一小段看,现在贵不贵」,长期那条问的是「按一大段看呢」。',
        read: '所以它们**天生可以直接比较**。一条线单独看只能说"到边了",三条一起看才能说"三种眼光是不是一致"。' },
      { term: '它们之间的距离 = 分歧有多大',
        meaning: '三条线挨得近,说明短、中、长三种看法认的是同一个价 —— 没有分歧;'
          + '离得远,说明它们对「什么价才合理」已经各说各的。',
        read: '**分歧就是趋势。** 没有分歧时价格只是在原地打转(方向未定);'
          + '分歧越拉越大,才说明有一股力量在把价格往一个方向推。' },
      { term: '谁在上面 = 方向',
        meaning: '短期那条跑到长期上面,是价格最近比过去贵了 —— 朝上;反过来就是朝下。',
        read: '距离说的是**走了多远**,谁在上面说的是**往哪走**。两个必须一起读:'
          + '同样是「离得很远」,朝上是涨了一大段,朝下是跌了一大段,该做的事正好相反。' },
      { term: '分歧太大 = 已经没有共同的合理价',
        meaning: '离得太远时,短期认的区间和长期认的区间**完全不重叠了** ——'
          + '任何一个价钱,按短期看是贵到极点,按长期看却还没到位。',
        read: '这时候争论「贵不贵」没有意义,得先想清楚你做的是哪一段。'
          + '这种状态很难维持,不是价格回来、就是长期那条慢慢跟上去。' },
      { term: '为什么用「倍日常波动」当尺子',
        meaning: '距离不按元也不按百分比,按「这只票平常一天大致会走多少」来量。',
        read: '**这样贵的票和便宜的票、急的票和慢的票之间才能直接比。**'
          + '同样差 3 块钱,对一只每天波动一毛的票是天大的事,对一只每天波动两块的票什么都不是。' },
    ],
  },
  {
    title: '怎么办(第一列)',
    note: '整张表唯一的收敛层 —— 把「该动了 / 六态趋势 / 贵不贵 / 通道态势 / AI 信号」五套判定合成一句话。第一条命中即止。',
    items: [
      { term: '按纪律走',
        meaning: '出场线或生命线已经破了。',
        read: '**这一档不看别的判定。** 出场纪律排在形态与模型之前,那是既定顺序,不参与讨论。' },
      { term: '今天就得动',
        meaning: '买点或卖点今天已经触发。',
        read: '徽标后面那个数就是要盯的价。旁边的「买」「卖」一定要看 —— 同样是触发,两个相反的动作。' },
      { term: '先别动',
        meaning: '几套判定互相矛盾 —— 比如趋势还往上、AI 却说卖出。',
        read: '**这一档最值得看。** 系统原来从不说这几套什么时候打架,而那恰恰是最该停手的时刻。'
          + '它刻意排在「盯着」之前:「还差 1.2% 到买点」这种话会诱人下手,而分歧时正是不该下手的时候。' },
      { term: '盯着',
        meaning: '快到某个价了,还没到。',
        read: '后面写着离哪个价还有多远。到价之前不必动,但值得放进今天的名单。' },
      { term: '留意 / 没事',
        meaning: '形态上有点意思,但不急;或者五套判定都没什么可说的。',
        read: '「没事」占大多数才正常 —— 自选一多,每天真该动的本来就只有几只。' },
    ],
  },
  {
    title: '通道态势',
    note: '两行都是判断,一个数字都没有:上面是处在哪一段,下面是走到哪一步、还有没有劲。点开是 27 种组合速查。',
    items: [
      { term: '上升中 / 下跌中',
        meaning: '三条线朝上散开,或朝下散开 —— 方向已经出来了。',
        read: '这是趋势的主体段。真正要盯的是什么时候开始走慢,那才是转折的先兆。' },
      { term: '横盘中 / 刚启动',
        meaning: '前者是三条线挤在一起、方向还没出来;后者是刚从那个状态里走出来。',
        read: '「横盘中」适合盯着等,不适合猜方向 —— 这种状态通常不会持续太久。'
          + '「刚启动」最关键:接着能不能继续走开,决定了这次是真启动还是又缩回去。' },
      { term: '涨势转弱',
        meaning: '已经走了不短一段,而最近走得比之前慢了。',
        read: '趋势本身还没坏,但推力在减弱。该开始想「什么情况下我就走」,而不是再加。' },
      { term: '涨过头 / 跌过头',
        meaning: '分歧大到短期看和长期看已经没有共同认可的合理价。',
        read: '**两个方向要分开处理。** 涨过头:再追性价比很低。跌过头:别急着抄 ——'
          + '跌到这个程度往往还要磨一段,等三条线重新靠拢再谈买点。' },
      { term: '走到哪一步(刚起步 / 走到中段 / 走了很长 / 走过头了)',
        meaning: '这一段已经走了多远。',
        read: '和打分那边用的是同一组刻度 —— 界面上说「走了很长」的那一刻,分数那边也正好在扣分。' },
      { term: '还有没有劲(还在加速 / 速度平稳 / 正在放慢)',
        meaning: '最近这一段比之前那一段走得快了还是慢了。',
        read: '和「走到哪一步」正交:一个说走了多远,一个说还有没有力气。'
          + '「走了很长 + 正在放慢」是最该警觉的组合。' },
    ],
  },
  {
    title: '贵不贵',
    note: '三条线的位置合起来读出的一句话。它说的是**位置**,不是方向 —— 要配着下面那行事件一起看。',
    items: [
      { term: '这一列答的是什么',
        meaning: '现在这个价,算贵、算便宜,还是还不到动手的时候。',
        read: '同一个「短线冲高」,在上涨趋势里是常态,在下跌趋势里是反弹撞到阻力 —— 位置本身分不出这两种。' },
      { term: '突破尝试 / 突破站稳',
        meaning: '前者是刚冲出去的第一天,后者是冲出去之后守住了。',
        read: '**这两个差的就是几天,意义完全不同** —— 第一天随时可能收回去。带问号的别当成已经成立。' },
      { term: '趋势中提速 / 主升浪特征',
        meaning: '趋势确认之后又上一个台阶;后者是几个条件同时成立的少见情形。',
        read: '这两种情况下沿着上沿走是常态,不必因为「到高位了」就减。' },
      { term: '涨势没劲',
        meaning: '还在高位待着,可最近走得比之前慢了。',
        read: '涨势没坏,只是没劲了 —— 该开始想退出计划,而不是加仓。' },
      { term: '反弹遇阻',
        meaning: '趋势本身往下,这次上冲只是撞到阻力。',
        read: '**最容易被读成突破的一种。** 看着像转强,其实方向没变。' },
      { term: '强势甩人',
        meaning: '趋势还是往上的,但价格短暂掉到了下沿之外。',
        read: '和「真跌破」长得像,区别在于大周期还站着。别把甩人当跌破,割在底部。' },
      { term: '憋着劲',
        meaning: '短、中、长三种看法认的是同一个价,方向还没出来。',
        read: '适合盯着等,不适合猜方向。' },
    ],
  },
  {
    title: '量化波动通道(三行竖排)',
    note: '这一列是**原始位置读数**:短期、中期、长期各自在自己那条通道里的高低。上面那些判定都是从它推出来的。',
    items: [
      { term: '短期 / 中期 / 长期',
        meaning: '这只票眼下的价格,在各自那个时间尺度里算高还是算低。',
        read: '短期那一行对突发消息最敏感,长期那一行只在真的换了阶段时才动。'
          + '所以「短期动而中长期不动」多半是一次性冲击,三行齐动才是状态变了。' },
      { term: '悬停里那几个数',
        meaning: '三线间距(短线比长线高/低多少)、快慢变化、已经挤了几天、这季平均重合、波动主要来自哪。**这几个数都不进把握分**,只用来读形态。',
        read: '**扫表时用不上,要核对时必须有** —— 所以它们在悬停里而不在列里。'
          + '「已经挤了几天」和「这季平均重合」要一起看:连着的天数是零而平均很高 = 刚刚才走出来。' },
      { term: '离得太远',
        meaning: '间距大到了极端 —— 就是上面第一节说的「已经没有共同的合理价」。',
        read: '按短线看贵到极点,按长线看还没到位。先想清楚你做的是哪一段。' },
      { term: '波动主要来自',
        meaning: '这只票眼下的上蹿下跳,主要是几天的短波动、一波行情的主体,还是更早就在的长期老趋势。',
        read: '短波动占多 = 更像消息和情绪在推;行情主体占多 = 正走在主升段;'
          + '长期老趋势占多 = 劲都在老趋势里,近期反而平静,动能在衰减。' },
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
