/**
 * [fork 增强 R170 → R183] 仓位中心 —— **模拟盘**。
 *
 * R170 时这里是两个 tab: 「我的批次」(真钱买入记录, 上游功能)与「AI 操盘手」
 * (模拟盘)。R183 按用户要求并成一个:
 *   「ai操盘手可以删除了…我的批次改造成模拟盘, 全权交给ai打理, 也就是说
 *     ai操盘手的功能移植融合到我的批次」
 *   「真实成本和我持仓是分离的, 这个部分是专门给ai自己操作的」
 *
 * 所以这一页现在**整页都是模拟盘**, 没有 tab 了。真实持仓的成本走决策台手填
 * 那条路(`services/positions.py`), 与这里彻底分开。
 *
 * ## 上游的 Lots 页面怎么处理
 *
 * `Lots.tsx` / `api/lots.py` / `strategy/lots.py` **全是上游代码, 一行没动** ——
 * 它仍挂在 `/lots-registry` 路由上可以打开, 只是不再出现在这个页面里, 也不在
 * 导航中。这样上游同步在批次那一块**依然零冲突**, 而且哪天想用回真钱批次登记,
 * 它原封不动还在。
 *
 * ## 为什么持仓不写进作者的 lots.json
 *
 * 用户要求「把操盘手的持仓写进批次表」—— 界面上确实是批次表, 但数据是**派生**
 * 的(见 `services/paper_lots.py`)。写进真 lots 会有两个后果: 每条批次派生两条
 * 监控规则(你会收到模拟持仓的止损推送), 以及经 `effective_positions` 流进决策台
 * 的成本/浮盈与今日总览的持仓体检 —— 那几列管的是真钱。
 */
import { AlertTriangle } from 'lucide-react'
import { PageHeader } from '@/components/PageHeader'
import { PaperTrading } from '@/pages/PaperTrading'

export function PositionsHub() {
  return (
    <div className="flex h-full flex-col">
      <PageHeader
        title="模拟盘"
        subtitle="全权交给 AI 打理 · 体检这套系统给的信息够不够模型做决定"
      />
      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="px-3 pt-3 lg:px-4">
          <div className="flex items-start gap-2 rounded-lg border border-warning/30 bg-warning/[0.07] px-3 py-2 text-[11px] leading-relaxed text-warning">
            <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
            <span>
              <b>模拟盘 · 非真实资金。</b>
              这里的持仓、成本、盈亏全部是 AI 自己跑出来的,
              与你的真实持仓<b>完全分开</b> ——
              真实成本走决策台手填那条路, 不受这一页影响, 这一页也不会给你推送。
            </span>
          </div>
        </div>
        <PaperTrading embedded />
      </div>
    </div>
  )
}
