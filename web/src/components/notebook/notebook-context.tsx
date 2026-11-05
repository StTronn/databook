import { createContext, use, useCallback, useMemo, useRef, useState, type ReactNode } from "react"
import { flushSync } from "react-dom"
import { buildSections, splitRef, type Section, type View } from "@/lib/notebook"
import type { Block, Doc } from "@/types"

export type Trace = { id: string; col?: string; open: boolean }

type NotebookCtx = {
  doc: Doc
  view: View
  sections: Section[]
  byId: Map<string, Block>
  /** last opened trace; kept while the drawer animates closed */
  trace: Trace | null
  openTrace: (id: string, col?: string) => void
  /** "block.col" (prose refs, KPI refs) */
  openRef: (ref: string) => void
  closeTrace: () => void
  /** Expand the owning section and scroll to `#cell-<id>`; if not rendered (hidden in this view), trace it instead. */
  scrollTo: (id: string) => void
  collapsed: ReadonlySet<string>
  setSectionOpen: (key: string, open: boolean) => void
  /** set before closing the drawer to navigate, so Radix doesn't restore focus (and scroll) to the trigger */
  skipFocusRestore: React.RefObject<boolean>
}

const Ctx = createContext<NotebookCtx | null>(null)

export function useNotebook(): NotebookCtx {
  const c = use(Ctx)
  if (!c) throw new Error("useNotebook outside NotebookProvider")
  return c
}

export function NotebookProvider({ doc, view, children }: { doc: Doc; view: View; children: ReactNode }) {
  const [trace, setTrace] = useState<Trace | null>(null)
  const [collapsed, setCollapsed] = useState<ReadonlySet<string>>(() => new Set())
  const skipFocusRestore = useRef(false)
  // another notebook in the same (kept-mounted) provider: drop per-notebook UI state
  const [nb, setNb] = useState(doc.notebook)
  if (nb !== doc.notebook) {
    setNb(doc.notebook)
    setTrace(null)
    setCollapsed(new Set())
  }

  // A `# Title` heading that repeats the page title shows as "Overview" (the header already shows the title).
  const sections = useMemo(() => buildSections(doc.blocks).map((sec) =>
    sec.heading?.level === 1 && sec.heading.text.trim().toLowerCase() === doc.title.trim().toLowerCase()
      ? { ...sec, heading: { ...sec.heading, html: "Overview", text: "Overview" } } : sec), [doc.blocks, doc.title])
  const byId = useMemo(() => new Map(doc.blocks.map((b) => [b.id, b])), [doc.blocks])
  const sectionOf = useMemo(() => {
    const m = new Map<string, string>()
    for (const s of sections) for (const it of s.items) if (!m.has(it.block.id)) m.set(it.block.id, s.key)
    for (const s of sections) if (s.heading?.anchor) m.set(s.heading.anchor, s.key)
    return m
  }, [sections])

  const openTrace = useCallback((id: string, col?: string) => setTrace({ id, col, open: true }), [])
  const openRef = useCallback((ref: string) => openTrace(...splitRef(ref)), [openTrace])
  const closeTrace = useCallback(() => setTrace((t) => (t ? { ...t, open: false } : t)), [])

  const setSectionOpen = useCallback((key: string, open: boolean) => {
    setCollapsed((c) => {
      if (c.has(key) !== open) return c
      const n = new Set(c)
      if (open) n.delete(key)
      else n.add(key)
      return n
    })
  }, [])

  const scrollTo = useCallback(
    (id: string) => {
      const sec = sectionOf.get(id)
      if (sec) flushSync(() => setSectionOpen(sec, true))
      const el = document.getElementById(`cell-${id}`)
      if (!el) return openTrace(id)
      el.scrollIntoView({ behavior: "smooth", block: "start" })
      el.focus({ preventScroll: true })
    },
    [sectionOf, setSectionOpen, openTrace],
  )

  const value = useMemo(
    () => ({ doc, view, sections, byId, trace, openTrace, openRef, closeTrace, scrollTo, collapsed, setSectionOpen, skipFocusRestore }),
    [doc, view, sections, byId, trace, openTrace, openRef, closeTrace, scrollTo, collapsed, setSectionOpen],
  )
  return <Ctx value={value}>{children}</Ctx>
}
