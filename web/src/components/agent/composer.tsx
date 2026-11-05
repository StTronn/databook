import { PlusIcon, XIcon } from "lucide-react"
import { useEffect, useRef, useState } from "react"
import { PromptBox, type PromptBoxHandle } from "@/components/agent/prompt-box"
import { useNotebook } from "@/components/notebook/notebook-context"
import { Button } from "@/components/ui/button"
import { useAgent } from "@/hooks/use-agent"

const W = 380

/** Floating composer (⌘K / + button / text selection): attached blocks + prompt; @ attaches more. */
export function Composer() {
  const { composer, closeComposer, send, running } = useAgent()
  const box = useRef<PromptBoxHandle>(null)
  useEffect(() => {
    if (composer) requestAnimationFrame(() => box.current?.focus())
  }, [composer])
  if (!composer) return null
  const x = Math.max(12, Math.min(composer.x, window.innerWidth - W - 12))
  const y = Math.min(composer.y, window.innerHeight - 200)
  return (
    <div
      role="dialog"
      aria-label="Ask the agent"
      className="fixed z-50 flex flex-col gap-2 border bg-popover p-2 text-popover-foreground shadow-lg"
      style={{ left: x, top: y, width: W, borderRadius: "calc(var(--radius) * 1.4)" }}
      onKeyDown={(e) => e.key === "Escape" && closeComposer()}
    >
      <div className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
        <PlusIcon className="size-3.5 text-primary" />
        <span>Ask or request a change · type @ to attach more blocks</span>
        <Button variant="ghost" size="icon-xs" className="ml-auto" aria-label="Close" onClick={closeComposer}>
          <XIcon />
        </Button>
      </div>
      <PromptBox
        key={composer.x + ":" + composer.y}
        ref={box}
        initial={composer.context ? [composer.context] : []}
        placeholder="e.g. why did AOV drop? · split this by state"
        running={running}
        onSubmit={send}
      />
    </div>
  )
}

/** "+" pill on text selection inside the notebook, and ⌘K / Ctrl+K for the selection or focused block. */
export function SelectionAsk() {
  const { openComposer, contextFor, composer } = useAgent()
  const { doc } = useNotebook()
  const [pill, setPill] = useState<{ x: number; y: number; blockId?: string; quote: string } | null>(null)

  useEffect(() => {
    const blockOf = (n: Node | null) => (n instanceof Element ? n : n?.parentElement)?.closest("[id^='cell-']")?.id.slice(5)
    const read = () => {
      const s = window.getSelection()
      const quote = s?.toString().trim() ?? ""
      if (!s || !quote || s.rangeCount === 0 || !document.querySelector("main")?.contains(s.anchorNode)) return null
      const r = s.getRangeAt(0).getBoundingClientRect()
      return { x: r.left + r.width / 2, y: r.bottom, blockId: blockOf(s.anchorNode), quote: quote.slice(0, 120) }
    }
    const onUp = () => setTimeout(() => setPill(read()), 0)
    const onSel = () => { if (!window.getSelection()?.toString().trim()) setPill(null) }   // selection cleared → hide pill
    const onKey = (e: KeyboardEvent) => {
      if (!(e.key === "k" && (e.metaKey || e.ctrlKey))) return
      e.preventDefault()
      const sel = read()
      const focused = blockOf(document.activeElement)
      const blockId = sel?.blockId ?? focused
      const r = (sel ? { left: sel.x - 190, bottom: sel.y } : document.activeElement?.getBoundingClientRect()) ?? { left: 200, bottom: 120 }
      openComposer({ context: blockId ? contextFor(blockId, sel?.quote) : undefined, x: r.left, y: r.bottom + 8 })
      setPill(null)
    }
    document.addEventListener("mouseup", onUp)
    document.addEventListener("keydown", onKey)
    document.addEventListener("selectionchange", onSel)
    return () => {
      document.removeEventListener("mouseup", onUp)
      document.removeEventListener("keydown", onKey)
      document.removeEventListener("selectionchange", onSel)
    }
  }, [openComposer, contextFor, doc.notebook])

  if (!pill || composer) return null
  return (
    <Button
      size="xs"
      className="fixed z-40 shadow-md"
      style={{ left: pill.x - 30, top: pill.y + 6 }}
      onMouseDown={(e) => e.preventDefault()} // keep the selection
      onClick={() => {
        openComposer({ context: pill.blockId ? contextFor(pill.blockId, pill.quote) : { label: "selection", quote: pill.quote }, x: pill.x - 190, y: pill.y + 8 })
        setPill(null)
      }}
    >
      <PlusIcon /> Ask <kbd className="ml-1 text-[10px] opacity-70">⌘K</kbd>
    </Button>
  )
}
