import type {
  IChartApi, ISeriesApi, ISeriesPrimitive, IPrimitivePaneView, IPrimitivePaneRenderer,
  SeriesAttachedParameter, SeriesType, Time,
} from 'lightweight-charts'
import { HOLLOW_DASH, ICON_UP, ICON_DOWN, ICON_W } from '@/lib/quantMacdSeries'
import { LANE_BOTTOM_PAD, LANE_FONT, LANE_HALO, LANE_ROWS, LANE_ROW_H, LANE_TOP_PAD } from '@/lib/trendQuantSeries'

/**
 * [R616] 两张副图上那些 lightweight 原生系列画不出来的图元 —— 按 R565(还是 ECharts 时)
 * 的画法补画:
 *
 *   · 趋势量化: 红绿短柱**从昨值连到今值**(原生 Histogram 只能从 0 起画)、吸筹白细柱、
 *     八种字(极底 / 升 / 顶 / 下 / 建仓 / 逃 / 见底 / 绝底)排在上下两条字道;
 *   · 量化MACD: DIFF 实心柱只露 DEA 之外那一截、DEA 空心点线框、金叉 / 死叉 13×18 箭头、
 *     共振黄柱。
 *
 * **只画, 不算**: 所有数值与颜色都由 `AnalysisKChart` 从现有数据、按旧代码的规则算好再传进来;
 * 这里不碰请求、不改字段、不新增判定。画法常量(柱宽 / 图标尺寸 / 字道)全部来自
 * `lib/quantMacdSeries.ts` 与 `lib/trendQuantSeries.ts`, 不在这份文件里复制。
 *
 * 坐标: 纵向走所挂 series 的 `priceToCoordinate`(它就在这张副图的 pane 里), 横向走
 * `chart.timeScale().timeToCoordinate`; 画之前按 pane 尺寸裁剪。
 */
export type DecorItem =
  /** 实心柱: 从 from 画到 to, 宽 = K 线间距 × ratio */
  | { kind: 'stick'; time: string; from: number; to: number; color: string; ratio: number }
  /** 空心柱: 只描边, 1 点 1 空点线(DEA 用) */
  | { kind: 'hollow'; time: string; from: number; to: number; color: string; ratio: number }
  /** 箭头图标: 顶端对准 value、水平居中于那根 K 线 */
  | { kind: 'icon'; time: string; value: number; up: boolean; color: string }
  /** 字道文字: 顶 / 底各两行, 按真实像素宽度分行, 一个字的横坐标对准它那一天 */
  | { kind: 'text'; time: string; text: string; color: string; lane: 'top' | 'bottom' }

export interface PaneDecorData {
  items: DecorItem[]
  /**
   * 副图顶上给 pane 标题留的一条带(px)。R565 的标题画在图外, 现在画在图里, 顶字道
   * 要从这条带下面开始 —— 这个值与纵轴范围的换算必须同源, 见 `tqYRange(paneH, headerPx)`。
   */
  headerH?: number
}

const EMPTY: PaneDecorData = { items: [] }

export class PaneDecor implements ISeriesPrimitive<Time> {
  private chart?: IChartApi
  private series?: ISeriesApi<SeriesType>
  private requestUpdate?: () => void
  private data: PaneDecorData = EMPTY
  private view: IPrimitivePaneView = {
    zOrder: () => 'top',
    renderer: () => ({ draw: target => this.draw(target) }),
  }

  attached({ chart, series, requestUpdate }: SeriesAttachedParameter<Time>) {
    this.chart = chart; this.series = series; this.requestUpdate = requestUpdate
    this.requestUpdate?.()
  }

  detached() { this.chart = undefined; this.series = undefined; this.requestUpdate = undefined }

  paneViews() { return [this.view] }

  update(data: PaneDecorData = EMPTY) {
    this.data = data
    this.requestUpdate?.()
  }

  private draw(target: Parameters<IPrimitivePaneRenderer['draw']>[0]) {
    const chart = this.chart, series = this.series
    if (!chart || !series) return
    const headerH = this.data.headerH ?? 0
    target.useMediaCoordinateSpace(({ context: ctx, mediaSize }) => {
      const ts = chart.timeScale()
      const { width, height } = mediaSize
      const barSpacing = ts.options().barSpacing
      // 字道分行: 每条道两行, 记已占到的右边界; 放不下才换第二行(与 R559 的 laneLayout 同一规则)
      const right: Record<'top' | 'bottom', number[]> = {
        top: Array(LANE_ROWS).fill(-Infinity), bottom: Array(LANE_ROWS).fill(-Infinity),
      }
      ctx.save()
      ctx.beginPath(); ctx.rect(0, 0, width, height); ctx.clip()
      for (const item of this.data.items) {
        const x = ts.timeToCoordinate(item.time as Time)
        if (x == null || x < -24 || x > width + 24) continue
        if (item.kind === 'stick' || item.kind === 'hollow') {
          const a = series.priceToCoordinate(item.from)
          const b = series.priceToCoordinate(item.to)
          if (a == null || b == null) continue
          const w = Math.max(1, barSpacing * item.ratio)
          const top = Math.min(a, b), h = Math.max(1, Math.abs(a - b))
          if (item.kind === 'stick') {
            ctx.fillStyle = item.color
            ctx.fillRect(x - w / 2, top, w, h)
          } else {
            ctx.strokeStyle = item.color; ctx.lineWidth = 1; ctx.setLineDash(HOLLOW_DASH)
            ctx.strokeRect(x - w / 2 + 0.5, top + 0.5, Math.max(1, w - 1), Math.max(1, h - 1))
            ctx.setLineDash([])
          }
        } else if (item.kind === 'icon') {
          const y = series.priceToCoordinate(item.value)
          if (y == null) continue
          ctx.save()
          ctx.translate(x - ICON_W / 2, y)
          ctx.fillStyle = item.color
          // ICON_UP / ICON_DOWN 是 ECharts 的 `path://` 写法, Path2D 只吃后半段
          ctx.fill(new Path2D((item.up ? ICON_UP : ICON_DOWN).replace('path://', '')))
          ctx.restore()
        } else {
          ctx.font = `${LANE_FONT}px "JetBrains Mono", monospace`
          const textW = ctx.measureText(item.text).width + 4
          const left = x - textW / 2
          const rows = right[item.lane]
          let row = rows.findIndex(itemRight => itemRight <= left)
          if (row < 0) row = rows.indexOf(Math.min(...rows))
          rows[row] = left + textW
          const y = item.lane === 'top'
            ? headerH + LANE_TOP_PAD + row * LANE_ROW_H
            : height - LANE_BOTTOM_PAD - (row + 1) * LANE_ROW_H
          ctx.textAlign = 'center'
          ctx.textBaseline = 'top'
          // 描边当底色光晕: 图里有柱子和线, 纯色小字压上去会糊
          ctx.lineWidth = LANE_HALO.lineWidth
          ctx.strokeStyle = LANE_HALO.stroke
          ctx.strokeText(item.text, x, y)
          ctx.fillStyle = item.color
          ctx.fillText(item.text, x, y)
        }
      }
      ctx.restore()
    })
  }
}
