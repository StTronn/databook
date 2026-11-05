import { ArrowUpIcon, SquareIcon, XIcon } from "lucide-react"
import { forwardRef, useImperativeHandle, useMemo, useRef, useState } from "react"
import { useNotebook } from "@/components/notebook/notebook-context"
import { KindBadge } from "@/components/notebook/status-badge"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { labelOf, type AgentContext } from "@/hooks/use-agent"
import { cn } from "@/lib/utils"

/** A block (or quoted selection) attached to a message. */
export function ContextChip({ ctx, onRemove }: { ctx: AgentContext; onRemove?: () => void }) {
  return (
    <span className="inline-flex max-w-full min-w-0 items-center gap-1 border bg-muted px-1.5 py-0.5 text-[11px] text-muted-foreground">
      <span className="shrink-0">@</span>
      <span className="truncate">{ctx.label}</span>
      {ctx.quote ? <span className="truncate italic">· “{ctx.quote}”</span> : null}
      {onRemove ? (
        <button type="button" aria-label={`Remove ${ctx.label}`} onClick={onRemove} className="ml-0.5 shrink-0 hover:text-foreground">
          <XIcon className="size-3" />
        </button>
      ) : null}
    </span>
  )
}

const key = (c: AgentContext) => `${c.blockId ?? ""}|${c.quote ?? ""}`
const MENTION = /(^|\s)@([^\s@]*)$/              // "@query" right before the caret

export type PromptBoxHandle = { focus: () => void }
type Props = {
  initial?: AgentContext[]
  placeholder: string
  running?: boolean
  onStop?: () => void
  onSubmit: (text: string, contexts: AgentContext[]) => void
  rows?: number
}

/** Prompt with attached-block chips; typing @ opens a block picker (↑/↓, Enter or click to attach, Esc to close). */
export const PromptBox = forwardRef<PromptBoxHandle, Props>(function PromptBox({ initial, placeholder, running, onStop, onSubmit, rows = 2 }, ref) {
  const { doc } = useNotebook()
  const [text, setText] = useState("")
  const [ctxs, setCtxs] = useState<AgentContext[]>(initial ?? [])
  const [query, setQuery] = useState<string | null>(null)
  const [active, setActive] = useState(0)
  const ta = useRef<HTMLTextAreaElement>(null)
  useImperativeHandle(ref, () => ({ focus: () => ta.current?.focus() }), [])

  const options = useMemo(() => {
    if (query === null) return []
    const q = query.toLowerCase()
    return doc.blocks
      .filter((b) => !ctxs.some((c) => c.blockId === b.id && !c.quote))
      .map((b) => ({ b, label: labelOf(b) }))
      .filter(({ b, label }) => !q || label.toLowerCase().includes(q) || b.id.toLowerCase().includes(q))
      .slice(0, 8)
  }, [query, doc.blocks, ctxs])

  const onChange = (v: string, caret: number) => {
    setText(v)
    const m = MENTION.exec(v.slice(0, caret))
    setQuery(m ? m[2] : null)
    setActive(0)
  }
  const pick = (i: number) => {
    const o = options[i]
    if (!o) return
    const caret = ta.current?.selectionStart ?? text.length
    const before = text.slice(0, caret).replace(MENTION, (_, sp) => sp)
    setText(before + text.slice(caret))
    setCtxs((c) => (c.some((x) => key(x) === key({ blockId: o.b.id, label: o.label })) ? c : [...c, { blockId: o.b.id, label: o.label }]))
    setQuery(null)
    requestAnimationFrame(() => ta.current?.focus())
  }
  const submit = () => {
    if (!text.trim() || running) return
    onSubmit(text, ctxs)
    setText("")
    setCtxs([])
  }

  return (
    <div className="relative flex flex-col gap-1.5">
      {ctxs.length ? (
        <div className="flex flex-wrap gap-1">
          {ctxs.map((c) => <ContextChip key={key(c)} ctx={c} onRemove={() => setCtxs((all) => all.filter((x) => key(x) !== key(c)))} />)}
        </div>
      ) : null}
      <Textarea
        ref={ta}
        rows={rows}
        value={text}
        placeholder={placeholder}
        className="min-h-12 resize-none pr-9 text-sm"
        onChange={(e) => onChange(e.target.value, e.target.selectionStart)}
        onKeyDown={(e) => {
          if (query !== null && options.length) {
            if (e.key === "ArrowDown") { e.preventDefault(); setActive((a) => (a + 1) % options.length); return }
            if (e.key === "ArrowUp") { e.preventDefault(); setActive((a) => (a - 1 + options.length) % options.length); return }
            if (e.key === "Enter" || e.key === "Tab") { e.preventDefault(); pick(active); return }
          }
          if (e.key === "Escape" && query !== null) { e.stopPropagation(); setQuery(null); return }
          if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit() }
        }}
      />
      <div className="absolute right-1.5 bottom-1.5">
        {running && onStop ? (
          <Button variant="outline" size="icon-xs" aria-label="Stop" onClick={onStop}><SquareIcon /></Button>
        ) : (
          <Button size="icon-xs" aria-label="Send" disabled={!text.trim() || running} onClick={submit}><ArrowUpIcon /></Button>
        )}
      </div>
      {query !== null ? (
        <ul role="listbox" aria-label="Attach a block"
          className="absolute bottom-full left-0 z-50 mb-1 max-h-64 w-full overflow-y-auto border bg-popover py-1 shadow-lg"
          style={{ borderRadius: "var(--radius)" }}>
          {options.length ? options.map(({ b, label }, i) => (
            <li key={b.id} role="option" aria-selected={i === active}>
              <button type="button" onMouseDown={(e) => e.preventDefault()} onClick={() => pick(i)} onMouseEnter={() => setActive(i)}
                className={cn("flex w-full items-center gap-2 px-2 py-1 text-left text-xs", i === active && "bg-accent")}>
                <KindBadge kind={b.kind} />
                <span className="min-w-0 flex-1 truncate">{label}</span>
                <span className="shrink-0 text-[10px] text-muted-foreground">{b.id}</span>
              </button>
            </li>
          )) : <li className="px-2 py-1 text-xs text-muted-foreground">No matching block</li>}
        </ul>
      ) : null}
    </div>
  )
})
