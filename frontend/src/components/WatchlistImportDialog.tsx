import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { FileText, ImagePlus, Keyboard, Loader2, Plus, Sparkles, Upload, X } from 'lucide-react'
import { useQueryClient } from '@tanstack/react-query'
import { Modal } from '@/components/Modal'
import { toast } from '@/components/Toast'
import { api, type WatchlistGroup, type WatchlistGroupColor, type WatchlistImportCandidate, type WatchlistImportResult } from '@/lib/api'
import { QK } from '@/lib/queryKeys'
import { useWatchlistBatchAdd } from '@/lib/useSharedMutations'
import {
  DEFAULT_WATCHLIST_GROUP_COLOR,
  WATCHLIST_GROUP_COLORS,
  resolveWatchlistGroupColor,
} from '@/lib/watchlist-group-colors'
import { TYPE } from '@/components/ui'

interface Props {
  open: boolean
  onClose: () => void
  /** 页面当前所在分组，作为默认目标分组（null=未分组）。 */
  groupId?: string | null
  /** 分组列表与成员快照由页面持有并下发，避免弹窗重复拉取。 */
  groups: WatchlistGroup[]
  existingBySymbol: ReadonlyMap<string, string[]>
}

const MAX_IMPORT_IMAGES = 10
const NO_MATCH_MSG = '未能匹配证券主数据，已跳过'
const DROP_ACCEPT =
  'image/jpeg,image/png,image/webp,image/bmp,image/gif,text/csv,text/plain,' +
  '.csv,.txt,.jpg,.jpeg,.png,.webp,.bmp,.gif'

/**
 * [R267] 小分队 → 目标分组的两个哨兵值。
 *
 * 一个小分队有三种去向: 新建同名分组、并进某个已有分组、这一队不导入。后两种能用
 * 分组 id 和一个固定串表示, 「新建」只能用哨兵 —— 组还不存在, 拿不到 id。**建组
 * 推迟到点「导入」那一刻**: 在映射界面上改来改去的过程里就把组建出来, 用户改一次
 * 主意就留下一个空分组, 还删不掉。
 */
const SECTION_NEW = '__new__'
const SECTION_SKIP = '__skip__'

interface RowState {
  eligible: boolean
  inWatchlist: boolean
  inAllSelected: boolean
}

/**
 * 未分组目标（空数组）只收新增；选定分组时，同时属于全部所选分组的标的不再可加。
 * 其余已匹配标的可勾选（并入尚未属于的分组）。
 */
function rowState(
  sym: string | null,
  matched: boolean,
  membership: ReadonlyMap<string, string[]>,
  targetIds: string[],
): RowState {
  if (!matched || !sym) return { eligible: false, inWatchlist: false, inAllSelected: false }
  const gids = membership.get(sym)
  const inWatchlist = gids !== undefined
  const inAllSelected = targetIds.length > 0
    && gids !== undefined && targetIds.every(gid => gids.includes(gid))
  const eligible = targetIds.length === 0 ? !inWatchlist : !inAllSelected
  return { eligible, inWatchlist, inAllSelected }
}

function isImageFile(file: File): boolean {
  return file.type.startsWith('image/') || /\.(jpe?g|png|webp|bmp|gif)$/i.test(file.name)
}

function isCsvFile(file: File): boolean {
  return /\.(csv|txt)$/i.test(file.name)
}

/** 多来源候选（多图 / 截图+文件混搭）按 code 合并，保留已匹配项。 */
export function mergeImportCandidates(
  lists: WatchlistImportCandidate[][],
): WatchlistImportCandidate[] {
  const byCode = new Map<string, WatchlistImportCandidate>()
  for (const list of lists) {
    for (const c of list) {
      const prev = byCode.get(c.code)
      if (!prev) {
        byCode.set(c.code, c)
        continue
      }
      if (c.matched && !prev.matched) {
        byCode.set(c.code, c)
        continue
      }
      if (c.matched && prev.matched) {
        byCode.set(c.code, {
          ...prev,
          symbol: prev.symbol || c.symbol,
          name: prev.name || c.name,
          already_in_watchlist: prev.already_in_watchlist || c.already_in_watchlist,
        })
      }
    }
  }
  return [...byCode.values()]
}

type Row = { c: WatchlistImportCandidate; state: RowState }

function Dropzone({
  busy,
  label,
  onPick,
}: {
  busy: boolean
  label: string
  onPick: (list: FileList | File[] | null | undefined) => void
}) {
  const inputRef = useRef<HTMLInputElement>(null)
  return (
    <>
      <input
        ref={inputRef}
        type="file"
        multiple
        accept={DROP_ACCEPT}
        className="hidden"
        onChange={e => {
          onPick(e.target.files)
          e.target.value = ''
        }}
      />
      <button
        type="button"
        disabled={busy}
        onClick={() => inputRef.current?.click()}
        onDragOver={e => { e.preventDefault(); e.stopPropagation() }}
        onDrop={e => {
          e.preventDefault()
          onPick(e.dataTransfer.files)
        }}
        className="w-full flex flex-col items-center justify-center gap-2 rounded-btn border border-dashed border-border bg-elevated/40 hover:bg-elevated/70 px-4 py-6 text-secondary transition-colors disabled:opacity-50"
      >
        {busy ? (
          <Loader2 className="h-6 w-6 animate-spin text-accent" />
        ) : (
          <ImagePlus className="h-6 w-6 text-accent" />
        )}
        <span className="text-xs">{busy ? label : '点击选择或拖拽券商自选截图 / CSV / TXT'}</span>
      </button>
    </>
  )
}

export function WatchlistImportDialog({
  open,
  onClose,
  groupId,
  groups,
  existingBySymbol,
}: Props) {
  const abortRef = useRef<AbortController | null>(null)
  const genRef = useRef(0)
  const qc = useQueryClient()

  const [busy, setBusy] = useState(false)
  const [progress, setProgress] = useState<{ done: number; total: number } | null>(null)
  const [candidates, setCandidates] = useState<WatchlistImportCandidate[]>([])
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [previewUrls, setPreviewUrls] = useState<string[]>([])
  const [sourceFile, setSourceFile] = useState('')
  const [pasteOpen, setPasteOpen] = useState(false)
  const [codesText, setCodesText] = useState('')
  const [showSkipped, setShowSkipped] = useState(false)
  const [targetGroupIds, setTargetGroupIds] = useState<string[]>([])
  /** [R267] 文章里分好的小分队(按出现顺序); 非空即进入「分队映射」模式 */
  const [sections, setSections] = useState<string[]>([])
  /** [R267] 小分队名 → 目标分组 id / SECTION_NEW / SECTION_SKIP */
  const [sectionMap, setSectionMap] = useState<Record<string, string>>({})
  const [newGroupOpen, setNewGroupOpen] = useState(false)
  const [newGroupName, setNewGroupName] = useState('')
  const [newGroupColor, setNewGroupColor] = useState<WatchlistGroupColor>(DEFAULT_WATCHLIST_GROUP_COLOR)
  const [creatingGroup, setCreatingGroup] = useState(false)
  const batchAdd = useWatchlistBatchAdd()

  const membership = existingBySymbol
  const groupNameById = useMemo(() => {
    const m = new Map<string, string>()
    for (const g of groups) m.set(g.id, g.name)
    return m
  }, [groups])

  const sectionMode = sections.length > 0

  /**
   * [R267] 这一行要进哪几个分组。
   *
   * 分队模式下**每行各算各的** —— 文章里「船舶」那队进 A 组、「军工」那队进 B 组,
   * 一个全局目标说不清这件事。一只票同时属于两个小分队就同时进两个分组, 这正是
   * 自选多组模型该有的样子。返回值里可能有 SECTION_NEW(组还没建), 那种一定不在
   * 现有成员关系里, 所以「已在所选分组」的判断天然为假, 不用特殊处理。
   */
  const rowTargets = useCallback((c: WatchlistImportCandidate): string[] => {
    if (!sectionMode) return targetGroupIds
    const out: string[] = []
    for (const g of c.groups ?? []) {
      const t = sectionMap[g]
      if (!t || t === SECTION_SKIP) continue
      if (!out.includes(t)) out.push(t)
    }
    return out
  }, [sectionMode, sectionMap, targetGroupIds])

  const { eligible, skipped } = useMemo(() => {
    const eligible: Row[] = []
    const skipped: Row[] = []
    for (const c of candidates) {
      const targets = rowTargets(c)
      const state = rowState(c.symbol, c.matched, membership, targets)
      // 分队模式下, 所属小分队全被设成「不导入」的票不该还能勾 —— 勾了也无处可去
      const orphan = sectionMode && (c.groups?.length ?? 0) > 0 && targets.length === 0
      ;(state.eligible && !orphan ? eligible : skipped).push({ c, state })
    }
    return { eligible, skipped }
  }, [candidates, membership, rowTargets, sectionMode])
  const skippedCount = skipped.length
  const matchedCount = useMemo(
    () => candidates.filter(c => c.matched && c.symbol).length,
    [candidates],
  )

  const abortInFlight = useCallback(() => {
    abortRef.current?.abort()
    abortRef.current = null
    genRef.current += 1
  }, [])

  const revokePreviews = useCallback((urls: string[]) => {
    for (const url of urls) URL.revokeObjectURL(url)
  }, [])

  const reset = useCallback(() => {
    abortInFlight()
    setBusy(false)
    setProgress(null)
    setCandidates([])
    setSelected(new Set())
    setPreviewUrls(prev => {
      revokePreviews(prev)
      return []
    })
    setSourceFile('')
    setPasteOpen(false)
    setCodesText('')
    setSections([])
    setSectionMap({})
    setShowSkipped(false)
    setNewGroupOpen(false)
    setNewGroupName('')
    setNewGroupColor(DEFAULT_WATCHLIST_GROUP_COLOR)
  }, [abortInFlight, revokePreviews])

  useEffect(() => {
    if (!open) {
      reset()
      return
    }
    setTargetGroupIds(groupId ? [groupId] : [])
  }, [open, groupId, reset])

  const defaultSelection = (list: WatchlistImportCandidate[]) => {
    const out = new Set<string>()
    for (const c of list) {
      if (c.matched && c.symbol && !membership.has(c.symbol)) out.add(c.symbol)
    }
    return out
  }

  /** 切目标分组后，只摘掉不再可选的已勾标的（新增默认勾选在解析时一次性设定）。 */
  const changeTargetGroups = (next: string[]) => {
    setTargetGroupIds(next)
    const eligibleNow = new Set<string>()
    for (const c of candidates) {
      const sym = c.symbol
      // 分队模式下目标由映射决定, 全局芯片不参与
      const targets = sectionMode ? rowTargets(c) : next
      if (sym && rowState(sym, c.matched, membership, targets).eligible) eligibleNow.add(sym)
    }
    setSelected(prev => {
      let changed = false
      const kept = new Set<string>()
      for (const sym of prev) {
        if (eligibleNow.has(sym)) kept.add(sym)
        else changed = true
      }
      return changed ? kept : prev
    })
  }

  const stage = async (run: (signal: AbortSignal) => Promise<WatchlistImportResult>) => {
    abortInFlight()
    const controller = new AbortController()
    abortRef.current = controller
    const gen = genRef.current
    setBusy(true)
    try {
      const res = await run(controller.signal)
      if (gen !== genRef.current) return
      setCandidates(res.candidates)
      setSelected(defaultSelection(res.candidates))
      // [R267] 文章自己分好的小分队 —— 默认同名已有分组直接并入, 没有就新建同名。
      // 这两个默认覆盖了绝大多数情况: 第一次导某个题材就建组, 之后再导就并进去。
      const secs = res.section_names ?? []
      setSections(secs)
      setSectionMap(Object.fromEntries(secs.map(name => {
        const hit = groups.find(g => g.name.trim().toLowerCase() === name.trim().toLowerCase())
        return [name, hit ? hit.id : SECTION_NEW]
      })))
      if (res.candidates.length > 0 && res.matched_count === 0) toast(NO_MATCH_MSG, 'error')
    } catch {
      /* 请求错误已由 request 封装弹出 */
    } finally {
      if (gen === genRef.current) setBusy(false)
    }
  }

  const runRecognizeQueue = async (files: File[]) => {
    const images = files.filter(isImageFile)
    const queue = images.slice(0, MAX_IMPORT_IMAGES)
    if (images.length > MAX_IMPORT_IMAGES) {
      toast(`一次最多识别 ${MAX_IMPORT_IMAGES} 张，已取前 ${MAX_IMPORT_IMAGES} 张`, 'error')
    }
    setPreviewUrls(prev => {
      revokePreviews(prev)
      return queue.map(f => URL.createObjectURL(f))
    })
    setSourceFile('')
    setShowSkipped(false)
    const controller = new AbortController()
    abortRef.current = controller
    const gen = genRef.current
    const merged: WatchlistImportCandidate[][] = []
    let failed = 0
    let lastError = ''
    setProgress({ done: 0, total: queue.length })
    setBusy(true)
    try {
      for (let i = 0; i < queue.length; i++) {
        try {
          const res = await api.watchlistImportImage(queue[i], controller.signal, true)
          merged.push(res.candidates)
        } catch (err) {
          if (gen !== genRef.current || controller.signal.aborted) return
          failed += 1
          lastError = err instanceof Error ? err.message : ''
        }
        setProgress({ done: i + 1, total: queue.length })
      }
      if (gen !== genRef.current) return
      const all = mergeImportCandidates(merged)
      setCandidates(all)
      setSelected(defaultSelection(all))
      if (all.length === 0) {
        toast(
          lastError
            || (failed > 0 ? '识别失败或未识别到股票代码' : '未识别到股票代码，请换更清晰的截图'),
          'error',
        )
      } else if (all.every(c => !c.matched)) {
        toast(NO_MATCH_MSG, 'error')
      } else if (failed > 0) {
        toast(`有 ${failed} 张识别失败，已合并其余结果`, 'error')
      }
    } finally {
      if (gen === genRef.current) {
        setBusy(false)
        setProgress(null)
      }
    }
  }

  const runCsvImport = async (file: File) => {
    setSourceFile(file.name)
    setPreviewUrls(prev => { revokePreviews(prev); return [] })
    setShowSkipped(false)
    await stage(signal => api.watchlistImportCsv(file, signal))
  }

  const runCodesParse = async () => {
    setSourceFile('')
    setShowSkipped(false)
    await stage(signal => api.watchlistImportCodes(codesText.trim(), signal))
  }

  /**
   * [R265] 粘一段话交给 AI 抽个股。
   *
   * 与「解析代码」共用同一个输入框: 那条只认六位数字, 复盘笔记 / 研报 / 群消息里
   * 的票多半**只有名字**, 老路一只都抽不出来。返回结构一致, 所以下面的勾选、
   * 目标分组、"已在自选就并组不新增"整套照旧, 一行都不用改。
   */
  const runTextParse = async () => {
    setSourceFile('')
    setShowSkipped(false)
    await stage(async signal => {
      const res = await api.watchlistImportText(codesText.trim(), signal)
      if (res.truncated) toast('正文过长, 已取前面一段解析', 'error')
      return res
    })
  }

  const runText = async () => {
    if (!codesText.trim()) {
      toast('请先粘贴要解析的内容', 'error')
      return
    }
    await runTextParse()
  }

  const onSourcePick = async (list: FileList | File[] | null | undefined) => {
    if (!list || list.length === 0) return
    const files = Array.from(list)
    const images = files.filter(isImageFile)
    const csvs = files.filter(isCsvFile)
    if (csvs.length > 0) {
      if (csvs.length > 1 || images.length > 0) {
        toast('截图与 CSV 请分别导入', 'error')
        return
      }
      await runCsvImport(csvs[0])
      return
    }
    if (images.length > 0) {
      if (images.length < files.length) toast('已忽略非截图文件', 'error')
      await runRecognizeQueue(images)
      return
    }
    toast('请选择券商自选截图或 CSV / TXT 文件', 'error')
  }

  const runCodes = async () => {
    if (!codesText.trim()) {
      toast('请粘贴或输入股票代码', 'error')
      return
    }
    await runCodesParse()
  }

  const createGroup = async () => {
    const name = newGroupName.trim()
    if (!name) return
    setCreatingGroup(true)
    try {
      const data = await api.watchlistGroupCreate(name, newGroupColor)
      // 服务端返回全量分组列表；侧栏/分组条与本弹窗共用 QK.watchlistGroups 缓存
      qc.setQueryData(QK.watchlistGroups, { groups: data.groups })
      changeTargetGroups(
        targetGroupIds.includes(data.group.id)
          ? targetGroupIds
          : [...targetGroupIds, data.group.id],
      )
      setNewGroupOpen(false)
      setNewGroupName('')
      setNewGroupColor(DEFAULT_WATCHLIST_GROUP_COLOR)
    } catch {
      /* 已由 request 弹出 */
    } finally {
      setCreatingGroup(false)
    }
  }

  const toggle = (symbol: string) => {
    setSelected(prev => {
      const next = new Set(prev)
      if (next.has(symbol)) next.delete(symbol)
      else next.add(symbol)
      return next
    })
  }

  let allSelected = eligible.length > 0
  for (const row of eligible) {
    if (!selected.has(row.c.symbol!)) {
      allSelected = false
      break
    }
  }

  const toggleAll = () => {
    setSelected(prev => {
      const next = new Set(prev)
      for (const row of eligible) {
        if (allSelected) next.delete(row.c.symbol!)
        else next.add(row.c.symbol!)
      }
      return next
    })
  }

  /**
   * [R267] 分队模式的导入: 先把要新建的组建出来, 再按「目标分组集合」分批写。
   *
   * 分批是必须的 —— `batchAdd` 一次调用只能给一组标的挂同一批分组, 而这里每个小分队
   * 的去向不同。按去向集合归堆之后, 通常就是每队一次调用; 同时属于两队的票会落进
   * 自己那一堆(去向是两个组), 一次调用就同时并进两个分组。
   */
  const confirmAddBySection = async (symbols: string[]) => {
    const bySymbol = new Map(candidates.filter(c => c.symbol).map(c => [c.symbol!, c]))
    // 1) 建组推迟到此刻 —— 在映射界面上改主意的过程里建组会留下删不掉的空分组
    const idByName: Record<string, string> = {}
    let created = 0
    for (const name of sections) {
      const target = sectionMap[name]
      if (!target || target === SECTION_SKIP) continue
      if (target !== SECTION_NEW) { idByName[name] = target; continue }
      const color = WATCHLIST_GROUP_COLORS[created % WATCHLIST_GROUP_COLORS.length].id
      const data = await api.watchlistGroupCreate(name, color)
      qc.setQueryData(QK.watchlistGroups, { groups: data.groups })
      idByName[name] = data.group.id
      created += 1
    }
    // 2) 按去向集合归堆
    const buckets = new Map<string, { gids: string[]; syms: string[] }>()
    for (const sym of symbols) {
      const gids = [...new Set((bySymbol.get(sym)?.groups ?? [])
        .map(g => idByName[g]).filter((v): v is string => !!v))].sort()
      const bucket = buckets.get(gids.join(',')) ?? { gids, syms: [] }
      bucket.syms.push(sym)
      buckets.set(gids.join(','), bucket)
    }
    for (const b of buckets.values()) {
      await batchAdd.mutateAsync({ symbols: b.syms, groupIds: b.gids })
    }
    return created
  }

  const confirmAdd = async () => {
    const symbols = [...selected]
    if (symbols.length === 0) {
      toast('请至少选择一只股票', 'error')
      return
    }
    const newCount = symbols.filter(sym => !membership.has(sym)).length
    const mergedCount = symbols.length - newCount
    if (sectionMode) {
      try {
        const created = await confirmAddBySection(symbols)
        const used = sections.filter(n => sectionMap[n] !== SECTION_SKIP).length
        toast(
          `已按 ${used} 个小分队导入 ${symbols.length} 只`
          + (created > 0 ? `（新建 ${created} 个分组）` : '')
          + (mergedCount > 0 ? `，其中 ${mergedCount} 只已在自选、只并入分组` : ''),
          'success',
        )
        onClose()
      } catch {
        /* 已由 request 弹出 */
      }
      return
    }
    try {
      await batchAdd.mutateAsync({ symbols, groupIds: targetGroupIds })
      const names = targetGroupIds
        .map(id => groupNameById.get(id))
        .filter((n): n is string => !!n)
        .join('、')
      if (names) {
        toast(
          mergedCount > 0
            ? `已导入 ${symbols.length} 只到「${names}」（新增 ${newCount}，并入 ${mergedCount}）`
            : `已导入 ${newCount} 只到「${names}」`,
          'success',
        )
      } else {
        toast(`已添加 ${newCount} 只自选`, 'success')
      }
      onClose()
    } catch {
      /* 已由 request 弹出 */
    }
  }

  if (!open) return null

  const progressLabel =
    progress && progress.total > 1
      ? `识别中 ${progress.done}/${progress.total}…`
      : progress
        ? '识别中…'
        : null

  const renderRow = ({ c, state }: Row) => {
    const sym = c.symbol
    const checked = !!sym && selected.has(sym)
    let status: ReactNode = null
    if (!c.matched || !sym) {
      // [R265] AI 那条路知道**为什么**没匹配上(名称与代码对不上/重名/主数据里没有),
      // 说清楚比统一一句「已跳过」有用得多 —— 尤其是"对不上"那种, 正是拦下一次错导。
      status = <span className="text-micro text-warning/90">{c.warn || NO_MATCH_MSG}</span>
    } else if (state.inAllSelected) {
      status = <span className="text-micro text-muted">已在所选分组</span>
    } else if (state.inWatchlist) {
      status = (
        <span className="text-micro text-muted">
          {targetGroupIds.length > 0 ? '已在自选 · 将并入所选分组' : '已在自选'}
        </span>
      )
    }
    return (
      // AI 那条路的未匹配项可能没有代码, 光用 code 做 key 会撞在一起
      <li key={sym ?? `${c.code}|${c.mention ?? ''}`}>
        <label
          className={`flex items-center gap-3 px-3 py-2.5 text-sm ${
            state.eligible ? 'cursor-pointer hover:bg-elevated/50' : 'opacity-50 cursor-not-allowed'
          }`}
        >
          <input
            type="checkbox"
            disabled={!state.eligible}
            checked={checked}
            onChange={() => sym && toggle(sym)}
            className="rounded border-border"
          />
          <div className="flex-1 min-w-0">
            <div className="flex items-baseline gap-2">
              {/* [R267] 原文里加粗的是作者标出的重点票 —— 这个信号在文章里明摆着, 丢了可惜 */}
              {c.starred && <span className="shrink-0 text-xs text-amber-400" title="原文里加粗标注">★</span>}
              <span className="font-medium text-foreground truncate">
                {c.name || c.mention || (c.matched && sym ? sym : '未匹配')}
              </span>
              <span className="text-xs text-muted tabular-nums shrink-0">
                {c.code}
                {sym ? ` · ${sym}` : ''}
              </span>
            </div>
            {status}
            {/* [R267] 它属于哪几个小分队。同时挂两个标签的票会同时进两个分组 */}
            {(c.groups?.length ?? 0) > 0 && (
              <div className="mt-0.5 flex flex-wrap items-center gap-1">
                {c.groups!.map(g => {
                  const skip = sectionMap[g] === SECTION_SKIP
                  return (
                    <span
                      key={g}
                      title={skip ? `小分队「${g}」已设为不导入` : `来自小分队「${g}」`}
                      className={`rounded px-1 py-px text-micro ${
                        skip ? 'bg-elevated/40 text-muted/50 line-through' : 'bg-accent/10 text-accent/80'
                      }`}
                    >
                      {g}
                    </span>
                  )
                })}
              </div>
            )}
            {/* [R265] 原文里提到它的那半句 —— 让人一眼核对 AI 有没有抽错票 */}
            {c.quote && (
              <p className="text-micro text-muted truncate" title={c.quote}>「{c.quote}」</p>
            )}
          </div>
        </label>
      </li>
    )
  }

  return (
    <Modal
      onClose={onClose}
      labelledBy="watchlist-import-title"
      panelClassName="w-[92vw] max-w-lg max-h-[85vh] flex flex-col bg-surface border border-border rounded-card shadow-xl"
    >
      <div className="flex items-center justify-between px-4 py-3 border-b border-border shrink-0">
        <div>
          <h2 id="watchlist-import-title" className={TYPE.section}>
            批量导入自选
          </h2>
          <p className="text-xs text-muted mt-0.5">
            截图 / CSV / TXT / 代码均支持，也可粘整篇文章让 AI 认票并按文中小分队归类；
            一律按证券主数据匹配，已在自选的只并入分组不重复添加
          </p>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="h-8 w-8 inline-flex items-center justify-center rounded-btn text-secondary hover:bg-elevated"
          aria-label="关闭"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      <div className="px-4 py-3 overflow-y-auto flex-1 space-y-3">
        {busy && progressLabel && (
          <p className="text-xs text-muted">{progressLabel}</p>
        )}

        <div className="space-y-2">
          <Dropzone busy={busy} label={progressLabel ?? '解析中…'} onPick={(l) => void onSourcePick(l)} />
          {!pasteOpen ? (
            <button
              type="button"
              onClick={() => setPasteOpen(true)}
              className="w-full inline-flex items-center justify-center gap-1.5 rounded-btn border border-dashed border-border bg-elevated/40 px-3 py-2 text-xs text-secondary hover:bg-elevated/70"
            >
              <Keyboard className="h-3.5 w-3.5 text-accent" />
              或粘贴证券代码 / 整篇文章
            </button>
          ) : (
            <div className="space-y-2 rounded-btn border border-border bg-elevated/40 p-2.5">
              <textarea
                autoFocus
                value={codesText}
                onChange={e => setCodesText(e.target.value)}
                onKeyDown={e => {
                  if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') void runCodes()
                }}
                placeholder={'纯代码：600519、000001 平安银行\n\n'
                  + '或直接粘整篇文章（Markdown 也行），交给 AI 认里面的票：\n'
                  + '文章里用 **船舶** **军工** 这样分好的小分队会被认出来，\n'
                  + '导入时每队各进各的分组。'}
                rows={5}
                className="w-full resize-y rounded-btn border border-border bg-surface px-3 py-2 text-xs text-foreground placeholder:text-muted focus:border-accent/50 focus:outline-none"
              />
              <div className="flex items-center justify-between gap-2">
                <span className="text-xs text-muted min-w-0">
                  代码用「解析代码」，整篇文章用「AI 认股票」
                </span>
                <div className="flex items-center gap-1.5 shrink-0">
                  <button
                    type="button"
                    onClick={() => { setPasteOpen(false); setCodesText('') }}
                    className="h-7 px-2 rounded-btn text-xs text-secondary hover:bg-elevated"
                  >
                    收起
                  </button>
                  <button
                    type="button"
                    disabled={busy || !codesText.trim()}
                    onClick={() => void runCodes()}
                    title="只认六位代码，不调 AI，最快"
                    className="h-7 px-2.5 rounded-btn text-xs inline-flex items-center gap-1.5 border border-border bg-elevated text-secondary hover:text-foreground disabled:opacity-40"
                  >
                    <Keyboard className="h-3.5 w-3.5" />
                    解析代码
                  </button>
                  <button
                    type="button"
                    disabled={busy || !codesText.trim()}
                    onClick={() => void runText()}
                    title="把整篇文章交给 AI：认出提到的个股（只有名字也认），并按文章自己分好的小分队归类"
                    className="h-7 px-2.5 rounded-btn text-xs inline-flex items-center gap-1.5 bg-accent text-white hover:bg-accent/90 disabled:opacity-40"
                  >
                    {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Sparkles className="h-3.5 w-3.5" />}
                    AI 认股票
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>

        {previewUrls.length > 0 && (
          <div className="flex gap-2 overflow-x-auto pb-1">
            {previewUrls.map((url, i) => (
              <div
                key={url}
                className="shrink-0 w-16 h-16 rounded-btn overflow-hidden border border-border bg-black/40"
              >
                <img src={url} alt={`预览 ${i + 1}`} className="w-full h-full object-contain" />
              </div>
            ))}
          </div>
        )}

        {sourceFile && (
          <div className="flex items-center gap-2 rounded-btn border border-border bg-elevated/40 px-3 py-2 text-xs text-secondary">
            <FileText className="h-3.5 w-3.5 shrink-0 text-accent" />
            <span className="truncate flex-1">{sourceFile}</span>
          </div>
        )}

        {candidates.length > 0 && (
          <div className="space-y-2">
            <div className="flex items-center justify-between gap-2">
              <span className="text-xs text-secondary">
                {candidates.length} 个代码 · 匹配 {matchedCount} · 可添加 {eligible.length}
              </span>
              {eligible.length > 0 ? (
                <button
                  type="button"
                  onClick={toggleAll}
                  className="text-xs text-accent hover:underline shrink-0"
                >
                  {allSelected ? '取消全选' : '全选可添加'}
                </button>
              ) : matchedCount > 0 ? (
                <span className="text-xs text-muted shrink-0">所选目标分组已包含这些标的，无需导入</span>
              ) : null}
            </div>

            {skippedCount > 0 && (
              <button
                type="button"
                onClick={() => setShowSkipped(v => !v)}
                className="flex items-center gap-1 text-xs text-muted hover:text-secondary"
              >
                <span className="transition-transform" style={{ transform: showSkipped ? 'rotate(90deg)' : undefined }}>▸</span>
                已略过 {skippedCount} 个（已在自选/所选分组，或主数据未匹配）
              </button>
            )}

            <ul className="divide-y divide-border/60 rounded-btn border border-border overflow-hidden">
              {eligible.map(renderRow)}
              {showSkipped && skipped.map(renderRow)}
            </ul>
          </div>
        )}
      </div>

      <div className="px-4 py-3 border-t border-border shrink-0 space-y-2.5">
        {/* [R267] 分队模式: 文章自己分好了队, 这里只决定每队去哪个分组。
            全局的「导入到分组」在这种时候是错的 —— 一个全局目标说不清「船舶那队进 A、
            军工那队进 B」, 所以整块换掉而不是并排摆两套。 */}
        {sectionMode ? (
          <div className="space-y-1.5">
            <div className="flex items-baseline gap-2">
              <span className="text-xs text-secondary">文章里分好的小分队</span>
              <span className="text-micro text-muted">
                各自导入到下面选定的分组;一只票同时属于两队就同时进两个分组
              </span>
            </div>
            <div className="max-h-32 space-y-1 overflow-y-auto pr-1">
              {sections.map(name => {
                const target = sectionMap[name] ?? SECTION_NEW
                const count = candidates.filter(c => c.matched && c.groups?.includes(name)).length
                return (
                  <div key={name} className="flex items-center gap-2">
                    <span
                      className={`min-w-0 flex-1 truncate text-xs ${
                        target === SECTION_SKIP ? 'text-muted/50 line-through' : 'text-foreground'
                      }`}
                      title={name}
                    >
                      {name}
                      <span className="ml-1 text-micro text-muted tabular-nums">{count} 只</span>
                    </span>
                    <span className="shrink-0 text-micro text-muted">→</span>
                    <select
                      value={target}
                      onChange={e => setSectionMap(prev => ({ ...prev, [name]: e.target.value }))}
                      aria-label={`小分队「${name}」导入到`}
                      className="h-6 w-36 shrink-0 rounded-btn border border-border bg-base px-1.5 text-xs text-foreground focus:border-accent/50 focus:outline-none"
                    >
                      <option value={SECTION_NEW}>新建「{name}」</option>
                      {groups.map(g => <option key={g.id} value={g.id}>并入 {g.name}</option>)}
                      <option value={SECTION_SKIP}>不导入这一队</option>
                    </select>
                  </div>
                )
              })}
            </div>
          </div>
        ) : (
        <div className="space-y-1.5">
          <div className="flex items-start gap-2">
            <span className="text-xs text-secondary pt-1.5 shrink-0">导入到分组</span>
            <div className="flex flex-wrap items-center gap-1.5 min-w-0">
              <button
                type="button"
                onClick={() => changeTargetGroups([])}
                aria-pressed={targetGroupIds.length === 0}
                className={`inline-flex items-center gap-1 rounded-full border px-2 py-1 text-xs transition-colors ${
                  targetGroupIds.length === 0
                    ? 'border-accent/40 bg-accent/10 text-accent'
                    : 'border-border bg-elevated text-secondary hover:text-foreground'
                }`}
                title="不加到任何分组，仅新增标的到自选"
              >
                未分组
              </button>
              <span className="mx-1 h-3 w-px shrink-0 self-center bg-border/60" aria-hidden="true" />
              {groups.map(g => {
                const active = targetGroupIds.includes(g.id)
                const c = resolveWatchlistGroupColor(g.color)
                return (
                  <button
                    key={g.id}
                    type="button"
                    onClick={() => changeTargetGroups(
                      active
                        ? targetGroupIds.filter(id => id !== g.id)
                        : [...targetGroupIds, g.id],
                    )}
                    aria-pressed={active}
                    className={`inline-flex items-center gap-1 rounded-full border px-2 py-1 text-xs transition-colors ${
                      active
                        ? `${c.border} ${c.background} ${c.text}`
                        : 'border-border bg-elevated text-secondary hover:bg-elevated/80 hover:text-foreground'
                    }`}
                    title={`${active ? '移出' : '加入'}目标分组「${g.name}」`}
                  >
                    <span className={`h-1.5 w-1.5 rounded-full ${active ? c.dot : 'bg-border'}`} />
                    {g.name}
                  </button>
                )
              })}
              {!newGroupOpen && (
                <button
                  type="button"
                  onClick={() => setNewGroupOpen(true)}
                  className="inline-flex items-center gap-1 rounded-full border border-dashed border-border bg-elevated/40 px-2 py-1 text-xs text-accent hover:bg-elevated/70"
                  title="新建分组接收这批导入"
                >
                  <Plus className="h-3 w-3" />
                  新建
                </button>
              )}
            </div>
          </div>
          {newGroupOpen && (
            <div className="rounded-btn border border-border bg-elevated/40 p-2 space-y-2">
              <div className="flex items-center gap-1.5">
                <input
                  autoFocus
                  maxLength={24}
                  value={newGroupName}
                  onChange={e => setNewGroupName(e.target.value)}
                  onKeyDown={e => {
                    if (e.key === 'Enter') void createGroup()
                    if (e.key === 'Escape') { setNewGroupOpen(false); setNewGroupName(''); setNewGroupColor(DEFAULT_WATCHLIST_GROUP_COLOR) }
                  }}
                  placeholder="新分组名称，Enter 创建"
                  className="h-8 min-w-0 flex-1 rounded-btn border border-border bg-surface px-2 text-xs text-foreground placeholder:text-muted focus:border-accent/50 focus:outline-none"
                  aria-label="新分组名称"
                />
                <button
                  type="button"
                  onClick={() => void createGroup()}
                  disabled={creatingGroup || !newGroupName.trim()}
                  title="创建分组，并作为本次导入的目标分组"
                  className="h-8 shrink-0 px-3 rounded-btn text-xs inline-flex items-center gap-1.5 bg-accent text-white hover:bg-accent/90 disabled:opacity-40"
                >
                  {creatingGroup ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Plus className="h-3.5 w-3.5" />}
                  创建
                </button>
              </div>
              <div className="flex items-center gap-2 pl-1">
                <span className="text-xs text-secondary shrink-0">颜色</span>
                <div className="flex flex-wrap items-center gap-1.5">
                  {WATCHLIST_GROUP_COLORS.map(option => {
                    const active = option.id === newGroupColor
                    return (
                      <button
                        key={option.id}
                        type="button"
                        onClick={() => setNewGroupColor(option.id)}
                        aria-pressed={active}
                        aria-label={`颜色 ${option.label}`}
                        title={option.label}
                        className={`h-4 w-4 rounded-full transition-transform ${option.dot} ${active ? `ring-2 ${option.ring} scale-110` : 'hover:scale-110'}`}
                      />
                    )
                  })}
                </div>
              </div>
            </div>
          )}
        </div>
        )}

        <div className="flex items-center justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="h-8 px-3 rounded-btn text-xs text-secondary hover:bg-elevated"
          >
            取消
          </button>
          <button
            type="button"
            disabled={selected.size === 0 || batchAdd.isPending || busy}
            onClick={() => void confirmAdd()}
            className="h-8 px-3 rounded-btn text-xs inline-flex items-center gap-1.5 bg-accent text-white hover:bg-accent/90 disabled:opacity-40"
          >
            {batchAdd.isPending ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Upload className="h-3.5 w-3.5" />
            )}
            导入所选 ({selected.size})
          </button>
        </div>
      </div>
    </Modal>
  )
}
