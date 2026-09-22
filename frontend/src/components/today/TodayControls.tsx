/**
 * [fork 增强 R347] 门槛 / 体检 / 板块筛选 —— **一处实现, 两页共用**。
 *
 * 用户: 「门槛的东西非常重要, 体检和筛选功能也要能保留」。
 *
 * 这三样原来长在今日总览的机会区表头里。模拟盘要用它们, 而这段有近 260 行 ——
 * **手抄一遍必漂**: 板块过滤的乐观值、门槛的分位口径、AI 定时那两个开关的文案,
 * 任何一处改了另一处不改, 表现就是"两个页面对同一个设置说法不一样", 两边都不报错。
 *
 * ## 三样东西为什么必须放在一起
 *
 *   板块筛选  只看哪几个板块 —— **过滤在后端做**。前端筛的话会漏掉被 `max_show`
 *             截掉的票, 你看到的"主板机会"是残缺的**而你不会知道**。
 *   体检      这个门槛值不值 —— 完整候选池的分层胜率 / 名次段 / 因子归因。
 *   门槛      把握分下限(按**历史分位**, 不是绝对分)与最多显示条数。
 *
 * [R133] **门槛旁边就是体检**: 调门槛之前先看"这个门槛值不值", 两个按钮挨着放,
 * 才不会出现凭感觉拧滑块的情况。这个相邻关系是设计的一部分, 不是排版巧合。
 *
 * ## 在模拟盘上它管什么
 *
 * 模拟盘的名单**只由六态选**(R344), 这三样一个都不碰它。它们只作用于**打分那一层**:
 * 板块过滤改的是哪些票拿得到名次, 门槛改的是谁进候选池 —— 也就是只影响**先后与标注**,
 * 不影响谁在名单上、更不影响谁能出手。守卫钉着这条。
 */
import { useState, type ReactNode } from 'react'
import { useMutation } from '@tanstack/react-query'
import { BarChart3, Loader2, SlidersHorizontal } from 'lucide-react'
import {
  api, TODAY_BOARDS,
  type TodayOverview, type TodayPrefs,
} from '@/lib/api'
import { toast } from '@/components/Toast'
import { cn } from '@/lib/cn'
import { Button, Card, CardSection, Field, fieldInput } from '@/components/ui'
import { ScoreLedgerDialog } from '@/components/ScoreLedgerDialog'

export function TodayControls({ d, refetch, isFetching, extra }: {
  d: TodayOverview
  /** 存完偏好要重取 —— 候选集变了 */
  refetch: () => Promise<unknown>
  isFetching: boolean
  /**
   * [R358] 挂在筛选条下面、**同一张卡里**的一块。用户: 「净值走势图和这两行收益
   * 都融合到页面开头的第一个卡片里面」→「我是想合并到筛选的卡片里面」。
   *
   * **做成插槽而不是把成绩搬进来**: 这个组件管的是"看哪些票/什么门槛", 对模拟盘
   * 的净值、月度收益一无所知, 也不该知道 —— 它当初立起来的理由就是**一处实现**
   * (R347), 把某一页的数据结构焊进来, 下一个用它的页面就得先绕过这段。
   * 插槽只承诺一件事: 这块东西长在同一张卡里, 与筛选条之间有条分隔线。
   */
  extra?: ReactNode
}) {
  const [prefsOpen, setPrefsOpen] = useState(false)
  const [ledgerOpen, setLedgerOpen] = useState(false)   // [R133] 把握分体检弹窗
  // 滑块拖动中的即时值(null = 用服务端返回的偏好); 松手才落库
  const [minPct, setMinPct] = useState<number | null>(null)
  // [R140] 板块过滤的**乐观值**。null = 用服务端偏好。
  //
  // 原来按钮亮不亮完全取决于 `d.prefs.boards`, 而那要等一次 PUT + 一次 GET
  // 回来才更新 —— 中间那段时间按钮纹丝不动, 看起来就是"点了没反应", 于是
  // 用户会再点一次(第二次读到的还是旧的 boardFilter, 于是又发了一遍同样的
  // 请求, 屏幕上叠出两个一样的 toast)。先本地亮起来, 服务端回来再对齐。
  const [boardDraft, setBoardDraft] = useState<string[] | null>(null)

  const prefsMut = useMutation({
    mutationFn: (body: Partial<TodayPrefs>) => api.todaySavePrefs(body),
    onSuccess: async (p, vars) => {
      toast(
        'boards' in vars
          ? (p.boards.length ? `只看:${p.boards.join('、')}` : '板块过滤已取消,全部板块都看')
          : `门槛已保存:只看历史前 ${100 - p.min_hist_pct}%,最多 ${p.max_show} 条`,
        'success')
      setMinPct(null)
      // 等这次重取真的落地再撤掉乐观值 —— 提前撤会让按钮闪回旧状态
      await refetch()
      setBoardDraft(null)
    },
    onError: (e: Error) => {
      toast(`保存失败: ${e.message}`, 'error')
      setMinPct(null)
      setBoardDraft(null)   // 存失败就退回服务端的真实值, 不留一个假的高亮
    },
  })

  const boardFilter = boardDraft ?? d.prefs?.boards ?? []
  const toggleBoard = (b: string | null) => {
    const next = b === null ? []
      : boardFilter.includes(b) ? boardFilter.filter(x => x !== b) : [...boardFilter, b]
    setBoardDraft(next)
    prefsMut.mutate({ boards: next })
  }

  return (
    <>
      {/* [R358] 卡的外壳挪到这一层, 好让 `extra` 与筛选条**长在同一张卡里**。
          里面那层只剩 flex 与内边距 —— 筛选条是横排的, 而 `extra` 是一整块,
          塞进同一个 flex 容器会被当成又一个横排的项。 */}
      <Card padding="none">
      <div className="flex flex-wrap items-center gap-g4 px-s2 py-s1">
        {/* [R40] 板块筛选。过滤在后端做 —— 前端筛的话会漏掉被 max_show 截掉的票,
            看到的"主板机会"是残缺的而你不会知道 */}
        <div className="flex items-center gap-g2">
          <Button
            size="xs"
            selected={boardFilter.length === 0}
            onClick={() => toggleBoard(null)}
            disabled={prefsMut.isPending}
            title="不过滤, 所有板块都看"
          >
            全部
          </Button>
          {/* [R140] 正在落库/重取时给个明确的进行态。/api/today 要跑
              Keltner 批量、MA120 批量、几十只的历史胜率, 一次好几秒 ——
              没有这个提示, 那几秒就是"点了没反应", 用户会重复点。 */}
          {TODAY_BOARDS.map((b) => {
            const on = boardFilter.includes(b)
            return (
              <Button
                key={b}
                size="xs"
                selected={on}
                onClick={() => toggleBoard(b)}
                disabled={prefsMut.isPending}
                title={`${on ? '取消' : '只看'}${b}(可多选)`}
              >
                {b}
              </Button>
            )
          })}
          {(prefsMut.isPending || (boardDraft !== null && isFetching)) && (
            <span className="inline-flex items-center gap-g2 pl-g3 text-micro text-muted">
              <Loader2 className="h-3 w-3 animate-spin" />
              筛选中
            </span>
          )}
        </div>
        <div className="ml-auto flex items-center gap-g4">
          {/* [R133] 门槛旁边就是体检 —— 调门槛前先看"这个门槛值不值",
              两个按钮挨着放, 才不会出现凭感觉拧滑块的情况 */}
          <Button
            size="xs"
            onClick={() => setLedgerOpen(true)}
            title="把握分体检: 完整候选池的分层胜率/名次段/因子归因, 并可一键导出给外部做调参"
          >
            <BarChart3 className="h-3 w-3" />
            体检
          </Button>
          <Button
            size="xs"
            selected={prefsOpen}
            onClick={() => setPrefsOpen((v) => !v)}
            title="调整显示门槛(把握分下限与最多显示条数)"
          >
            <SlidersHorizontal className="h-3 w-3" />
            门槛
          </Button>
        </div>
      </div>
      {extra && <CardSection>{extra}</CardSection>}
      </Card>
      {prefsOpen && (
        <Card padding="md" className="flex flex-wrap items-center gap-x-s4 gap-y-s1 bg-base/40">
          {/* [R220] 门槛的单位从绝对把握分换成了历史分位。
              绝对分那个旋钮几乎没有作用(实测 60 分只挡掉约 1.6% 的候选),
              因为分数被"平均"挤在中间一段;分位天然均匀,拖到哪儿都真的在挡人。
              台账没攒够时**禁用并说明**,而不是让人拖一个没反应的旋钮。 */}
          <Field label="入选门槛" disabled={!d.hist_pct_ready}>
            <input
              type="range" min={0} max={90} step={5}
              disabled={!d.hist_pct_ready}
              value={minPct ?? d.prefs.min_hist_pct}
              onChange={(e) => setMinPct(Number(e.target.value))}
              onPointerUp={() => {
                if (minPct != null && minPct !== d.prefs.min_hist_pct) prefsMut.mutate({ min_hist_pct: minPct })
              }}
              className="w-36 accent-accent cursor-pointer disabled:cursor-not-allowed"
            />
            <span className="w-24 whitespace-nowrap font-mono text-foreground">
              {(minPct ?? d.prefs.min_hist_pct) > 0
                ? `历史前 ${100 - (minPct ?? d.prefs.min_hist_pct)}%`
                : '不过滤'}
            </span>
            {!d.hist_pct_ready && (
              <span className="text-micro text-amber-300/80"
                    title="分位要跟历史比才算得出来。台账攒够约一个月的记录(400 条)之后这个门槛自动开始起作用 —— 在那之前它谁也不挡, 而不是偷偷把页面挡空。">
                台账还没攒够,暂不起作用
              </span>
            )}
          </Field>
          <Field label="最多显示" unit="条">
            <input
              type="number" min={1} max={50}
              defaultValue={d.prefs.max_show}
              onBlur={(e) => {
                const v = Number(e.target.value)
                if (v && v !== d.prefs.max_show) prefsMut.mutate({ max_show: v })
              }}
              className={cn(fieldInput, 'w-14')}
            />
          </Field>
          <Field label="单票上限" unit="%" title="单只票最多占总资金的比例;建议仓位 = 上限 × 把握分系数 × 波动率压缩">
            <input
              type="number" min={5} max={100} step={5}
              defaultValue={d.prefs.max_single}
              onBlur={(e) => {
                const v = Number(e.target.value)
                if (v && v !== d.prefs.max_single) prefsMut.mutate({ max_single: v })
              }}
              className={cn(fieldInput, 'w-14')}
            />
          </Field>
          <Field label="目标日波动" unit="%" title="能接受的单日波动;票的日波幅(ATR/价)超过它时按比例压低建议仓位,只压不加">
            <input
              type="number" min={1} max={10}
              defaultValue={d.prefs.target_vol}
              onBlur={(e) => {
                const v = Number(e.target.value)
                if (v && v !== d.prefs.target_vol) prefsMut.mutate({ target_vol: v })
              }}
              className={cn(fieldInput, 'w-14')}
            />
          </Field>
          {/* [R340] 「回撤纪律线」这个输入框跟着一起撤了。它**只喂一个消费者**
              —— `api/today.py` 里那条 `portfolio_drawdown` 提醒, 而那条提醒
              只出现在刚被删掉的「需要行动」区。留着就是一个调了不产生任何
              可见结果的旋钮, 比没有更坏。
              后端 `today_prefs` 的字段没动: 要把那一区加回来, 它原样还在。 */}
          <Field label="试仓" unit="%" title="建仓路径第一步: 试仓占目标仓位的比例(买'对不对')">
            <input
              type="number" min={10} max={60} step={5}
              defaultValue={d.prefs.pyramid_probe}
              onBlur={(e) => {
                const v = Number(e.target.value)
                if (v && v !== d.prefs.pyramid_probe) prefsMut.mutate({ pyramid_probe: v })
              }}
              className={cn(fieldInput, 'w-14')}
            />
          </Field>
          <Field label="确认加至" unit="%" title="建仓路径第二步: 站稳关键点 N 日后加至目标仓位的比例(买'稳不稳'), 第三步回踩不破上满">
            <input
              type="number" min={40} max={90} step={5}
              defaultValue={d.prefs.pyramid_confirm}
              onBlur={(e) => {
                const v = Number(e.target.value)
                if (v && v !== d.prefs.pyramid_confirm) prefsMut.mutate({ pyramid_confirm: v })
              }}
              className={cn(fieldInput, 'w-14')}
            />
          </Field>
          <Field label="站稳" unit="日" title="'站稳'的定义: 收盘连续 N 日守住关键点才执行加仓">
            <input
              type="number" min={1} max={5}
              defaultValue={d.prefs.pyramid_days}
              onBlur={(e) => {
                const v = Number(e.target.value)
                if (v && v !== d.prefs.pyramid_days) prefsMut.mutate({ pyramid_days: v })
              }}
              className={cn(fieldInput, 'w-14')}
            />
          </Field>
          <span className="text-micro text-muted/70">
            把握分调高更严格;单票上限与目标日波动决定「建议仓位」;试仓/确认加至/站稳决定「建仓路径」。卖出提醒不受任何门槛影响。
          </span>
          {/* [R27 → R435] 「AI 定时自动运行」那一行撤了: 定时导读·优选早在 R352 删了,
              剩下的「定时个股信号」随 AI 信号整套停用一起删(后端定时任务与接口同步撤)。 */}
          {prefsMut.isPending && <Loader2 className="h-3 w-3 animate-spin text-muted" />}
        </Card>
      )}
      {ledgerOpen && <ScoreLedgerDialog onClose={() => setLedgerOpen(false)} />}
    </>
  )
}
