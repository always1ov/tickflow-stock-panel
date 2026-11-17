/**
 * C 区 · 复盘正文 (R791) — 目录 / 面包屑 / 工具条 / 正文。
 *
 * 改版要点:
 *  - 取消外层 `max-h` 内滚, 交给整页滚动(避免「滚动套滚动」);
 *  - 左目录按正文里**真实出现的 H2** 生成, 点击滚到对应标题(不改 MarkdownRenderer);
 *  - 查看历史时顶部有面包屑, 后台还在生成时带「生成中 · 切回」;
 *  - 空态收成一行引导, 不再占 28rem 插画(生成前 A/B 区已经有用)。
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import {
  AlertTriangle, BookOpenCheck, ChevronDown, ChevronUp, Copy, Download, List,
  RefreshCw, Sparkles,
} from 'lucide-react'

import type { AiReviewReport } from '@/lib/api'
import type { ReviewPhase } from '@/lib/reviewStore'
import { cn } from '@/lib/cn'
import { MarkdownRenderer } from '@/components/financials/MarkdownRenderer'
import { scoreColor } from './shared'

const REPORT_SECTIONS = '报告包含: 一句话定调 · 盘面总览 · 板块主线 · 资金情绪 · 消息催化 · 明日计划 · 风险提示'

/** 从正文里抓 H2 标题(真实出现的, 不预设七节都有)。 */
function useHeadings(content: string): { level: number; title: string }[] {
  return useMemo(() => {
    const out: { level: number; title: string }[] = []
    for (const line of content.split('\n')) {
      const m = /^(##|###)\s+(.+?)\s*$/.exec(line)
      if (m) out.push({ level: m[1].length, title: m[2] })
    }
    return out.slice(0, 24)
  }, [content])
}

export interface ReportReaderProps {
  phase: ReviewPhase
  content: string
  error: string
  generating: boolean
  /** 正在查看的历史报告(全文); null = 看最新/流式内容 */
  viewing: AiReviewReport | null
  /** 档案带点开某篇、全文还在路上 */
  detailLoading?: boolean
  onCopy: () => void
  onDownload: () => void
  onRegenerate: () => void
  onBackToLatest: () => void
}

export function ReportReader({
  phase, content, error, generating, viewing, detailLoading,
  onCopy, onDownload, onRegenerate, onBackToLatest,
}: ReportReaderProps) {
  const bodyRef = useRef<HTMLDivElement>(null)
  const endRef = useRef<HTMLDivElement>(null)
  const [collapsed, setCollapsed] = useState(false)
  const [tocOpen, setTocOpen] = useState(false)
  const headings = useHeadings(content)

  // 流式时跟到底部; 只在「正在生成且没看历史」时滚, 避免打断阅读
  useEffect(() => {
    if (generating && !viewing) {
      endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
    }
  }, [content, generating, viewing])

  const jumpTo = (title: string) => {
    const root = bodyRef.current
    if (!root) return
    const target = title.replace(/\s/g, '')
    const el = Array.from(root.querySelectorAll('h2, h3'))
      .find(h => (h.textContent ?? '').replace(/\s/g, '').includes(target))
    el?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    setTocOpen(false)
  }

  if (phase === 'error') {
    return (
      <section className="flex flex-col items-center justify-center gap-3 rounded-card border border-border bg-surface/80 px-6 py-12">
        <div className="grid h-11 w-11 place-items-center rounded-full bg-danger/10">
          <AlertTriangle className="h-5 w-5 text-danger" />
        </div>
        <div className="text-sm font-medium text-foreground">复盘失败</div>
        <div className="max-w-md text-center text-xs text-secondary">{error || '请检查 AI 配置后重试'}</div>
        <button
          onClick={onRegenerate}
          className="mt-1 inline-flex items-center gap-1.5 rounded-btn border border-border bg-surface px-3 py-1.5 text-xs text-foreground transition-colors hover:bg-elevated"
        >
          <RefreshCw className="h-3.5 w-3.5" />重新生成
        </button>
      </section>
    )
  }

  if (detailLoading) {
    return (
      <section className="space-y-2 rounded-card border border-border bg-surface/80 p-4">
        <div className="h-4 w-40 animate-pulse rounded-btn bg-elevated/70" />
        <div className="h-3 w-full animate-pulse rounded-btn bg-elevated/50" />
        <div className="h-3 w-11/12 animate-pulse rounded-btn bg-elevated/50" />
        <div className="h-3 w-4/5 animate-pulse rounded-btn bg-elevated/50" />
      </section>
    )
  }

  if (phase === 'idle' && !content && !viewing) {
    return (
      <section className="flex flex-wrap items-center gap-3 rounded-card border border-dashed border-border bg-surface/50 px-4 py-5">
        <span className="grid h-9 w-9 shrink-0 place-items-center rounded-dialog bg-accent-soft ring-1 ring-accent/25">
          <BookOpenCheck className="h-4 w-4 text-accent" strokeWidth={1.8} />
        </span>
        <div className="min-w-0">
          <div className="text-xs font-medium text-foreground">还没有今日复盘</div>
          <p className="mt-0.5 text-micro text-muted">{REPORT_SECTIONS}</p>
        </div>
        <span className="ml-auto inline-flex items-center gap-1 text-micro text-muted">
          <Sparkles className="h-3 w-3 text-accent" />点上方「生成复盘」开始
        </span>
      </section>
    )
  }

  const isLoading = phase === 'loading' && !content
  const showCursor = generating && !viewing
  const showActions = !!content && (!generating || !!viewing)

  return (
    <section className="rounded-card border border-border bg-surface/80">
      {/* 面包屑: 查看历史时不再有隐性状态 */}
      {viewing && (
        <div className="flex flex-wrap items-center gap-2 border-b border-border bg-elevated/30 px-3 py-1.5 text-micro">
          <span className="text-secondary">
            正在查看 <span className="font-mono text-foreground">{viewing.as_of}</span> 复盘
          </span>
          {viewing.emotion_score != null && (
            <span className="inline-flex items-center gap-1 text-secondary">
              · 情绪
              <span
                className="rounded-btn px-1 font-mono font-semibold"
                style={{ color: scoreColor(viewing.emotion_score), backgroundColor: `${scoreColor(viewing.emotion_score)}1a` }}
              >
                {viewing.emotion_score}
              </span>
              {viewing.emotion_label ?? ''}
            </span>
          )}
          <button onClick={onBackToLatest} className="text-accent hover:underline">返回最新</button>
          {generating && (
            <button onClick={onBackToLatest} className="ml-auto inline-flex items-center gap-1 text-accent hover:underline">
              <RefreshCw className="h-3 w-3 animate-spin" />生成中 · 切回
            </button>
          )}
        </div>
      )}

      {/* 工具条 */}
      <div className="flex flex-wrap items-center gap-2 border-b border-border px-3 py-2">
        <div className="flex items-center gap-1.5">
          {generating && !viewing
            ? <RefreshCw className="h-3.5 w-3.5 animate-spin text-accent" />
            : <BookOpenCheck className="h-3.5 w-3.5 text-accent" />}
          <span className="text-xs font-medium text-foreground">
            {viewing ? `历史复盘 · ${viewing.as_of}` : generating ? 'AI 正在复盘…' : '复盘报告'}
          </span>
          {generating && !viewing && (
            <span className="rounded-btn bg-accent/10 px-1.5 py-px text-micro text-accent">
              已写入 {headings.length} 节
            </span>
          )}
        </div>
        <div className="ml-auto flex items-center gap-1">
          {headings.length > 0 && (
            <button
              onClick={() => setTocOpen(v => !v)}
              className="inline-flex items-center gap-1 rounded-btn border border-border bg-surface px-2 py-1 text-xs text-foreground transition-colors hover:bg-elevated/70 lg:hidden"
            >
              <List className="h-3 w-3" />目录
            </button>
          )}
          {showActions && (
            <>
              <button onClick={onCopy} className="inline-flex items-center gap-1 rounded-btn border border-border bg-surface px-2 py-1 text-xs text-foreground transition-colors hover:bg-elevated/70" title="复制全文">
                <Copy className="h-3 w-3" />复制
              </button>
              <button onClick={onDownload} className="inline-flex items-center gap-1 rounded-btn border border-border bg-surface px-2 py-1 text-xs text-foreground transition-colors hover:bg-elevated/70" title="下载为 Markdown">
                <Download className="h-3 w-3" />下载
              </button>
            </>
          )}
          <button
            onClick={() => setCollapsed(v => !v)}
            className="inline-flex items-center gap-1 rounded-btn px-1.5 py-1 text-micro text-muted transition-colors hover:text-foreground"
            title={collapsed ? '展开正文' : '收起正文'}
          >
            {collapsed ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronUp className="h-3.5 w-3.5" />}
            {collapsed ? '展开' : '收起'}
          </button>
        </div>
      </div>

      {tocOpen && headings.length > 0 && (
        <div className="border-b border-border bg-base/40 px-3 py-2 lg:hidden">
          <Toc headings={headings} onJump={jumpTo} />
        </div>
      )}

      {!collapsed && (
        <div className="flex gap-4 px-4 py-3">
          {/* 左目录: 桌面常驻; 点击滚到正文对应标题 */}
          {headings.length > 0 && (
            <aside className="hidden w-44 shrink-0 lg:block">
              <div className="sticky top-2">
                <div className="mb-1 text-micro text-muted">目录</div>
                <Toc headings={headings} onJump={jumpTo} />
              </div>
            </aside>
          )}
          <div ref={bodyRef} className="min-w-0 flex-1">
            {isLoading ? (
              <div className="flex flex-col items-center justify-center gap-3 py-14">
                <div className="relative">
                  <div className="grid h-11 w-11 place-items-center rounded-full border border-accent/30 bg-accent-soft">
                    <Sparkles className="h-5 w-5 animate-pulse text-accent" />
                  </div>
                  <RefreshCw className="absolute -inset-1 h-13 w-13 animate-spin text-accent/30" style={{ animationDuration: '3s' }} />
                </div>
                <div className="text-sm text-foreground">AI 正在复盘今日盘面…</div>
                <div className="text-xs text-secondary">分析指数结构 · 连板梯队 · 板块轮动 · 资金情绪</div>
              </div>
            ) : (
              <div className="prose prose-invert max-w-[75ch]">
                <MarkdownRenderer content={content} />
                {showCursor && (
                  <span className="ml-0.5 inline-block h-4 w-1.5 animate-pulse rounded-btn bg-accent align-middle" />
                )}
              </div>
            )}
            <div ref={endRef} />
          </div>
        </div>
      )}
    </section>
  )
}

function Toc({ headings, onJump }: {
  headings: { level: number; title: string }[]
  onJump: (title: string) => void
}) {
  return (
    <nav className="space-y-0.5">
      {headings.map((h, i) => (
        <button
          key={`${h.title}-${i}`}
          onClick={() => onJump(h.title)}
          className={cn(
            'block w-full truncate rounded-btn px-1.5 py-1 text-left text-micro text-secondary transition-colors hover:bg-elevated/70 hover:text-foreground',
            h.level === 3 && 'pl-4 text-muted',
          )}
          title={h.title}
        >
          {h.title}
        </button>
      ))}
    </nav>
  )
}
