/**
 * [fork 增强 R292] 复盘弹窗的「说明」页 —— 六态与通道档位各是什么意思。
 *
 * 用户: 「把全景按钮改成说明或者帮助按钮, 里面是解释每个六态状态、结论状态是
 * 什么意思」。
 *
 * ## 它的形态改过两次, 每次都是同一个问题在推
 *
 *   R289 「全景」  一层盖住整个正文的面板 → 「我点进去全屏了」
 *   R292 抽屉      从右边推进来占 26rem, 正文那一侧还看得见
 *   R301 页签      **换掉正文, 不再盖任何东西**
 *
 * 用户最后一句是: 「说明点击后不是弹窗, 和趋势状态一样内容区域显示」。
 *
 * **抽屉那一版的理由(边看边查, 一边对着行一边读释义)在实际用起来时不成立** ——
 * 26rem 的抽屉推开之后, 正文剩下的那一条恰恰是最右边几列, 而要对照的六态徽标
 * 在最左边, 被盖住了。真要边看边查, 抽屉得停在正文左侧; 而那又和"从右边推进来"
 * 的手势相反。既然这条路走不通, 就老老实实做成一页 —— 名实相符, 而且省掉了
 * 绝对定位、过渡、Esc 拦截、关闭按钮四样东西。
 *
 * ## 词条为什么从后端取
 *
 * 名字与结论文案的正主在 `livermore.STATE_LABELS` 与 `keltner._VERDICTS`。前端
 * 誊抄一份的话, 底层哪天改了措辞, 那份誊抄就开始说假话 —— 而且**没有任何东西
 * 会报错**。R203 的 27 格速查表当初就是为这个理由做成端点的。
 *
 * [R301] **没有动效了** —— 换页签不该有过渡(R301 之前那层 180ms 是抽屉推入的
 * 手势, 页签之间切换加过渡只会让每次点击都慢一拍)。Esc 的拦截也一并去掉:
 * 这一页不是"一层", Esc 该照旧关掉整个复盘弹窗。
 */
import { useQuery } from '@tanstack/react-query'
import { Loader2 } from 'lucide-react'
import { api } from '@/lib/api'
import { QK } from '@/lib/queryKeys'
import { cn } from '@/lib/cn'
import { trendBadgeCls } from '@/components/stock-analysis/TrendStateBar'
import { ComboGroups } from '@/components/stock-analysis/decision-board/ComboView'

// [R292 加, R300 删] `HelpButton` 在这里删掉了 —— 用户: 「"说明"这个按钮合并到
// 这里"趋势状态 通道档位 说明"」。入口搬进了页签组, 那一处直接写在
// `StockReviewDialog` 里(它要跟着页签共用同一套选中态与边框, 抽出来反而是
// 两处定义同一个外观)。**只剩一个入口了**, 组件本身没有第二个调用方。
const TONE_CLS: Record<string, string> = {
  sell: 'border-red-400/40 bg-red-400/10 text-red-400',
  buy: 'border-sky-400/40 bg-sky-400/10 text-sky-300',
  hold: 'border-amber-400/40 bg-amber-400/10 text-amber-400',
  avoid: 'border-border bg-base text-muted',
  watch: 'border-border bg-elevated/60 text-secondary',
}

export function ReviewHelpView({ here = null }: {
  /** [R296] 你现在在 27 格的哪一格 —— 那张表拿它高亮 */
  here?: string | null
}) {
  // 结果恒定, 拉一次就够 —— 与 27 格速查表同一个缓存策略。
  // [R301] `enabled` 去掉了: 这个组件只在「说明」页签选中时才挂载,
  // "开着才拉"这件事由挂载与否表达, 再加一个开关就是两处说同一件事。
  const q = useQuery({
    queryKey: QK.glossary,
    queryFn: () => api.glossary(),
    staleTime: 24 * 3600_000,
  })
  // [R296] 27 格谱系并进来了 —— 用户: 「组合速查合并到通道结论里面去」。
  // **它进这一页而不是进那两页**: 那张表是**恒定的**(与今天这只票无关), 属于
  // 查表用的参考; 那两页讲的是这只票的时间序列。这条分界与 R292 定的同一条 ——
  // R301 把这一页从抽屉改成页签, 分界没变, 只是承载它的东西换了。
  const combo = useQuery({
    queryKey: QK.comboTable,
    queryFn: () => api.comboTable(),
    staleTime: 24 * 3600_000,
  })

  return (
    // [R301] 与「趋势状态」「通道档位」同一个骨架: 一块占满剩余高度、自己滚动的
    // 正文。**两栏铺开** —— 这一页横向有整个弹窗可用(抽屉那版只有 26rem),
    // 六态六档与结论十档并排, 一屏就看得完, 不必上下翻。
    <div className="min-h-0 flex-1 overflow-auto px-4 py-3">
      <p className="mb-3 text-[10px] text-muted">
        这些词各是什么意思 —— 与哪只票无关, 是这两层判定的固定词表。
      </p>
      <div className="[column-gap:1rem] lg:columns-2">
        {q.isLoading && (
          <div className="flex items-center gap-2 py-10 text-[11px] text-muted">
            <Loader2 className="h-3.5 w-3.5 animate-spin" /> 正在取…
          </div>
        )}
        {q.isError && <div className="py-10 text-center text-[11px] text-red-400">说明加载失败</div>}

        {q.data && (
          <>
            <Section
              title="六态状态"
              note="这一列的徽标。六档是一条从强到弱的连续轴, 不是六个并列的标签"
            >
              {q.data.trend.map((t) => (
                <Term
                  key={t.code}
                  badge={<span className={cn('inline-flex whitespace-nowrap rounded border px-1.5 py-0.5 text-[10px]',
                                             trendBadgeCls(t.code as Parameters<typeof trendBadgeCls>[0]))}>{t.title}</span>}
                  side={t.side}
                  meaning={t.meaning}
                  action={t.action}
                />
              ))}
            </Section>

            <Section
              title="通道档位"
              note="十档按偏买 → 偏卖排, 与别处的排序同一个次序"
            >
              {q.data.verdict.map((v) => (
                <Term
                  key={v.code}
                  badge={<span className={cn('inline-flex whitespace-nowrap rounded border px-1.5 py-0.5 text-[10px]',
                                             TONE_CLS[v.tone] ?? TONE_CLS.avoid)}>{v.title}</span>}
                  meaning={v.meaning}
                  action={v.action}
                />
              ))}
              {/* [R302] 「按档位买卖」那一栏的**口径偏差**搬到这里。原来它常年
                  挂在「通道档位」页头部卡上, 用琥珀警告色 —— 而它**不随票变**,
                  每只票每次打开都是同一段。它属于"这十档怎么被翻成买卖动作",
                  正好是这一节在讲的事。

                  **搬走不等于藏起来**: 界面上那一行写着「口径与作者原话的出入见
                  『说明』」, 指过来。真正该常驻正文的是「样本太少」「撞上涨跌停」
                  那几条 —— 它们是**这只票的**, 一条没动。 */}
              <div className="px-2.5 py-2 text-[10px] leading-relaxed text-muted">
                <b className="font-medium text-secondary">按档位买卖的口径</b>:
                「拿着」「等着」「三档都在中部」<b className="text-secondary">都不动手</b> ——
                那是作者写的原话(「拿着, 别在这加仓」「等短期入场点」), 不是买卖信号。
                另: 「该止盈了」原话是「可落袋一部分」、「大顶区域」是「动仓位基调」,
                这里一律<b className="text-secondary">按清空模拟, 比原话重</b>。
              </div>
            </Section>

            {/* [R296] 27 格 —— 上面十档结论**就是从这 27 格出来的**(穷举 125 种
                三档位置验过: 同一个三字码永远给同一个结论, 零冲突)。所以它排在
                结论后面: 先说这一档什么意思, 再说它是从哪几格来的。 */}
            {!!combo.data && (
              <Section
                title="27 种三档组合"
                note="三档各在上/中/下。上面那十档就是从这里出来的; 有 3 格给不出档位"
              >
                <div className="px-2 py-2">
                  {/* [R294 → R296] 那个取舍的交代。R294 时它印在「组合速查」页上
                      (用户点名要那一页也有战绩, 不说会以为漏做了); R296 那一页
                      并掉之后, 交代跟着搬到这里 —— 问题还在, 只是换了个人问。 */}
                  <p className="mb-2 leading-relaxed text-muted">
                    按三档组合换格买卖的成绩与「按档位买卖」那一栏逐字相同, 所以只摆一份:
                    换格比换档密, 但多出来的换格两边同向 —— 只是把同一段多切几刀,
                    而段与段之间没有缝, 复利一乘就抵回去了。
                  </p>
                  <ComboGroups rows={combo.data.rows} here={here} />
                </div>
              </Section>
            )}
          </>
        )}
      </div>
    </div>
  )
}

function Section({ title, note, children }: {
  title: string; note: string; children: React.ReactNode
}) {
  return (
    // [R301] `break-inside-avoid`: 两栏是 CSS multi-column, 默认会把一节从中间
    // 劈开接到下一栏 —— 六态那六档被切成"三档在左栏、三档在右栏"就彻底读不成了。
    <section className="mb-4 break-inside-avoid last:mb-0">
      <div className="mb-1.5 flex flex-wrap items-baseline gap-x-2">
        <h3 className="text-[11px] font-medium text-foreground">{title}</h3>
        <span className="text-[10px] text-muted">{note}</span>
      </div>
      <div className="divide-y divide-border/40 rounded-btn border border-border/60">{children}</div>
    </section>
  )
}

function Term({ badge, side, meaning, action }: {
  badge: React.ReactNode; side?: string; meaning: string; action: string
}) {
  return (
    <div className="px-2.5 py-2">
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        {badge}
        {!!side && <span className="text-[10px] text-muted">{side}侧</span>}
      </div>
      <p className="mt-1 text-[10px] leading-relaxed text-secondary">{meaning}</p>
      {/* 「该怎么办」是作者那一层的原话 —— 与释义分开排, 免得读成同一句 */}
      {!!action && (
        <p className="mt-0.5 text-[10px] leading-relaxed text-muted">
          <span className="opacity-60">怎么做:</span> {action}
        </p>
      )}
    </div>
  )
}
