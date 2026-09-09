/**
 * [R49] 「结论」的悬停卡片。
 *
 * 之前这一列用的是原生 title="" 。它有三个治不好的毛病, 而这一列恰恰是最需要
 * 看清楚的一列:
 *   · 要悬停一秒多才弹, 扫一列票的时候根本等不及;
 *   · 系统渲染, 不能分层次 —— "怎么做"、"为什么"、"依据"三段被 \n\n 挤成
 *     一坨同样大小的灰字, 等于没有重点;
 *   · 决策台的表格在 overflow-auto 里, 靠边那几行的原生提示会被裁掉。
 *
 * 所以改成自己画: 立刻弹出、分三段排版、position:fixed + portal 挂到 body,
 * 不受任何祖先的 overflow 影响, 空间不够时自动上下翻面并水平夹进视口。
 *
 * 内容仍然全部来自后端的 verdict —— 界面只负责排版, 不在这里补任何判定。
 */
import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { type KeltnerVerdict } from '@/lib/api'

const TONE_ACCENT: Record<KeltnerVerdict['tone'], string> = {
  sell: 'text-red-400',
  buy: 'text-sky-300',
  hold: 'text-amber-400',
  avoid: 'text-muted',
  watch: 'text-secondary',
}
const TONE_BAR: Record<KeltnerVerdict['tone'], string> = {
  sell: 'bg-red-400',
  buy: 'bg-sky-400',
  hold: 'bg-amber-400',
  avoid: 'bg-border',
  watch: 'bg-secondary/60',
}
// tone 的字面意思。徽标只有 4-6 个字, 光看"候选池"分不出它是该动手还是先盯着
const TONE_CN: Record<KeltnerVerdict['tone'], string> = {
  sell: '偏贵 · 考虑减',
  buy: '偏便宜 · 考虑吸',
  hold: '别动 · 尤其别加',
  avoid: '别碰',
  watch: '先盯着 · 还不到动手的时候',
}

const CARD_W = 300
const GAP = 8
const EDGE = 8

type Placement = { left: number; top: number; below: boolean }

/**
 * `note` 给调用方补一句只在该处成立的话 —— 同一个"到上沿", 持仓侧是止盈时机,
 * 买入候选侧是追高。这个差别不能写死在 verdict 里, 它对两边都得成立。
 */
export function VerdictHover({ v, note, children }: {
  v: KeltnerVerdict
  note?: string
  children: ReactNode
}) {
  const ref = useRef<HTMLSpanElement>(null)
  const [pos, setPos] = useState<Placement | null>(null)

  const place = useCallback(() => {
    const el = ref.current
    if (!el) return
    const r = el.getBoundingClientRect()
    // 估个高度用来决定上下翻面。宁可估大 —— 估小了会在下边缘贴出去一截
    const guess = 210
    const below = r.bottom + GAP + guess <= window.innerHeight || r.top - GAP - guess < 0
    const left = Math.min(
      Math.max(EDGE, r.left + r.width / 2 - CARD_W / 2),
      window.innerWidth - CARD_W - EDGE,
    )
    setPos({ left, top: below ? r.bottom + GAP : r.top - GAP, below })
  }, [])

  // 表格是可滚动的 —— 卡片用 fixed 定位, 不跟着滚就会浮在原地指着别的行
  useEffect(() => {
    if (!pos) return
    const hide = () => setPos(null)
    window.addEventListener('scroll', hide, true)
    window.addEventListener('resize', hide)
    return () => {
      window.removeEventListener('scroll', hide, true)
      window.removeEventListener('resize', hide)
    }
  }, [pos])

  return (
    <>
      <span
        ref={ref}
        tabIndex={0}
        onMouseEnter={place}
        onMouseLeave={() => setPos(null)}
        onFocus={place}
        onBlur={() => setPos(null)}
        className="outline-none"
      >
        {children}
      </span>
      {pos && createPortal(
        <div
          role="tooltip"
          style={{
            position: 'fixed', left: pos.left, top: pos.top, width: CARD_W,
            transform: pos.below ? undefined : 'translateY(-100%)',
          }}
          className="pointer-events-none z-[60] overflow-hidden rounded-lg border border-border bg-surface shadow-2xl"
        >
          <div className="flex items-stretch">
            <div className={`w-1 shrink-0 ${TONE_BAR[v.tone]}`} />
            <div className="min-w-0 flex-1 px-3 py-2.5">
              <div className="flex items-baseline justify-between gap-2">
                <span className={`text-xs font-medium ${TONE_ACCENT[v.tone]}`}>
                  {v.title}
                  {/* [R233] 连着第几天。**中间断一天就重新起算** ——
                      出现 3 天、隔一天、再 2 天是两次独立的出现, 说成 5 天
                      会把这一档持续了多久说多。 */}
                  {/* [R237] 状态时长的完整说法: 已经多久 + 从哪天起。
                      徽标上只放得下数字, 这里给能核对的那一份。 */}
                  {v.days != null && (
                    <span className="ml-1 text-[10px] font-normal text-muted"
                          title={'这是**当前这一段**连着多少个交易日,不是历史累计。'
                            + '含今天;中间只要断一天(换了一档或没有结论)就从头重新起算。'
                            + (v.capped ? '\n\n已经数到能看到的最早一根,实际可能更长。' : '')}>
                      {`已连着 ${v.days} 个交易日${v.capped ? '以上' : ''}`}
                      {v.since ? ` · 自 ${v.since}` : ''}
                    </span>
                  )}
                </span>
                <span className="shrink-0 text-[9px] text-muted">{TONE_CN[v.tone]}</span>
              </div>

              {/* 怎么做 —— 这一行是用户真正要的那句, 排在最上面且最显眼 */}
              <div className="mt-2 rounded border border-border/60 bg-elevated/40 px-2 py-1.5">
                <div className="text-[9px] text-muted">怎么做</div>
                <div className="mt-0.5 text-[11px] leading-snug text-foreground">{v.action}</div>
              </div>

              <div className="mt-2">
                <div className="text-[9px] text-muted">为什么</div>
                <div className="mt-0.5 text-[10px] leading-relaxed text-secondary">{v.detail}</div>
              </div>

              <div className="mt-2 flex items-baseline gap-1.5">
                <span className="shrink-0 text-[9px] text-muted">依据</span>
                <span className="text-[10px] leading-snug text-secondary">{v.bands_text}</span>
                <span
                  className="ml-auto shrink-0 rounded border border-border/60 px-1 text-[9px] text-muted"
                  title="有几档通道指向同一边"
                >
                  {v.bands_aligned} 档共振
                </span>
              </div>

              {note && (
                <div className="mt-2 border-t border-border/40 pt-1.5 text-[9px] leading-relaxed text-muted">
                  {note}
                </div>
              )}
              <div className="mt-1.5 text-[9px] leading-relaxed text-muted/80">
                这是「位置」结论 —— 说的是贵不贵, 不是会不会继续涨。
                清仓与否看止盈线/生命线, 优先级在通道之上。收盘口径。
              </div>
            </div>
          </div>
        </div>,
        document.body,
      )}
    </>
  )
}
