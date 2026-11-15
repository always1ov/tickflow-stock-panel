import type {
  IChartApi, ISeriesApi, ISeriesPrimitive, IPrimitivePaneView, IPrimitivePaneRenderer,
  SeriesAttachedParameter, SeriesType, Time,
} from 'lightweight-charts'
import { HOLLOW_DASH, ICON_UP, ICON_DOWN, ICON_W } from '@/lib/quantMacdSeries'

/** [R724] 趋势量化删除后, 字道常量随之消失; 剩下的右端名字 / DRAWTEXT 还用同一套字与光晕。 */
const LANE_FONT = 11
const LANE_HALO = { stroke: '#000000', lineWidth: 3 }

/**
 * [R616] 副图上那些 lightweight 原生系列画不出来的图元 —— 按 R565(还是 ECharts 时)
 * 的画法补画:
 *
 *   · 量化MACD: DIFF 实心柱只露 DEA 之外那一截、DEA 空心点线框、金叉 / 死叉 13×18 箭头、
 *     共振黄柱;
 *   · 主力COME: 红空心柱 / 绿实心柱 / 红主力柱 / 白字;
 *   · ATR 原始版: 上穿参考线那颗向上箭头。
 *
 * **只画, 不算**: 所有数值与颜色都由调用方从现有数据、按旧代码的规则算好再传进来;
 * 这里不碰请求、不改字段、不新增判定。画法常量(柱宽 / 图标尺寸)来自
 * `lib/quantMacdSeries.ts`, 不在这份文件里复制。
 *
 * 坐标: 纵向走所挂 series 的 `priceToCoordinate`(它就在这张副图的 pane 里), 横向走
 * `chart.timeScale().timeToCoordinate`; 画之前按 pane 尺寸裁剪。
 */
export type DecorItem =
  /** 实心柱: 从 from 画到 to, 宽 = K 线间距 × ratio(或直接给像素宽 widthPx) */
  | { kind: 'stick'; time: string; from: number; to: number; color: string; ratio?: number; widthPx?: number }
  /** 空心柱: 只描边, 默认 1 点 1 空点线(DEA 用); dashed:false 是通达信 STICKLINE 的实线空心 */
  | { kind: 'hollow'; time: string; from: number; to: number; color: string; ratio?: number; widthPx?: number; dashed?: boolean }
  /** 箭头图标: 顶端对准 value、水平居中于那根 K 线 */
  | { kind: 'icon'; time: string; value: number; up: boolean; color: string }
  /** [R638] 参考线右端名字(超买 / 超卖): 不跟日期走, 贴着副图右边写在该值的高度上 */
  | { kind: 'label'; value: number; text: string; color: string }
  /** [R714] 钉在某天某价上的字(通达信 DRAWTEXT): 横坐标对那天, 字底边压在 value 上方 */
  | { kind: 'note'; time: string; value: number; text: string; color: string }

export interface PaneDecorData {
  items: DecorItem[]
}

const EMPTY: PaneDecorData = { items: [] }

/** [R641] 右端名字脚下的半透明底: 压住副图右下角可能挤过来的信号字。 */
const LABEL_BG = 'rgba(0, 0, 0, 0.55)'

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
    target.useMediaCoordinateSpace(({ context: ctx, mediaSize }) => {
      const ts = chart.timeScale()
      const { width, height } = mediaSize
      const barSpacing = ts.options().barSpacing
      // [R638] 右端名字不挂在某一天上, 没有 x 可算 —— 收起来最后画, 压在最上面
      const labels: Extract<DecorItem, { kind: 'label' }>[] = []
      // [R714] DRAWTEXT 那种"钉在某天某价上的字": 等柱子和图标画完再写, 保证压在最上层
      const notes: Extract<DecorItem, { kind: 'note' }>[] = []
      ctx.save()
      ctx.beginPath(); ctx.rect(0, 0, width, height); ctx.clip()
      for (const item of this.data.items) {
        if (item.kind === 'label') { labels.push(item); continue }
        if (item.kind === 'note') { notes.push(item); continue }
        const x = ts.timeToCoordinate(item.time as Time)
        if (x == null || x < -24 || x > width + 24) continue
        if (item.kind === 'stick' || item.kind === 'hollow') {
          const a = series.priceToCoordinate(item.from)
          const b = series.priceToCoordinate(item.to)
          if (a == null || b == null) continue
          const w = Math.max(1, item.widthPx ?? barSpacing * (item.ratio ?? 1))
          const top = Math.min(a, b), h = Math.max(1, Math.abs(a - b))
          if (item.kind === 'stick') {
            ctx.fillStyle = item.color
            ctx.fillRect(x - w / 2, top, w, h)
          } else {
            ctx.strokeStyle = item.color; ctx.lineWidth = 1
            ctx.setLineDash(item.dashed === false ? [] : HOLLOW_DASH)
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
        }
      }
      // [R638] 参考线右端名字: 贴右边、纵向对准那条线的值, 同样垫一层黑描边当光晕。
      // [R641] 半透明底: 副图右下角常压着柱子/箭头, 纯描边在图形挤到一起时仍会串行 ——
      // 先铺一块暗底把底下的笔画盖掉, 再看清名字。底色与副图的底色同族,
      // 亮暗主题下都不会突兀。
      if (labels.length) {
        ctx.textAlign = 'right'
        ctx.textBaseline = 'middle'
        ctx.font = `${LANE_FONT}px "JetBrains Mono", monospace`
        ctx.lineWidth = LANE_HALO.lineWidth
        ctx.strokeStyle = LANE_HALO.stroke
        for (const label of labels) {
          const y = series.priceToCoordinate(label.value)
          if (y == null) continue
          const x = width - 4
          const w = ctx.measureText(label.text).width
          ctx.fillStyle = LABEL_BG
          ctx.fillRect(x - w - 3, y - LANE_FONT / 2 - 1, w + 6, LANE_FONT + 2)
          ctx.strokeText(label.text, x, y)
          ctx.fillStyle = label.color
          ctx.fillText(label.text, x, y)
        }
      }
      // [R714] 通达信 DRAWTEXT(cond, 60, '主力COME'): 字底边压在 60 那条高度线上, 水平居中于当天。
      if (notes.length) {
        ctx.textAlign = 'center'
        ctx.textBaseline = 'bottom'
        ctx.font = `${LANE_FONT}px "JetBrains Mono", monospace`
        ctx.lineWidth = LANE_HALO.lineWidth
        ctx.strokeStyle = LANE_HALO.stroke
        for (const note of notes) {
          const x = ts.timeToCoordinate(note.time as Time)
          const y = series.priceToCoordinate(note.value)
          if (x == null || y == null) continue
          ctx.strokeText(note.text, x, y - 1)
          ctx.fillStyle = note.color
          ctx.fillText(note.text, x, y - 1)
        }
      }
      ctx.restore()
    })
  }
}
