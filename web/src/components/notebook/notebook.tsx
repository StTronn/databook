import { ChevronRightIcon } from "lucide-react"
import type { KeyboardEvent, MouseEvent } from "react"
import { BlockError } from "@/components/notebook/block-error"
import { ItemView } from "@/components/notebook/block-view"
import { useNotebook } from "@/components/notebook/notebook-context"
import { Button } from "@/components/ui/button"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"
import { isVisible, plural, type Section } from "@/lib/notebook"
import { cn } from "@/lib/utils"

const refOf = (t: EventTarget) => (t instanceof Element ? t.closest(".tb-ref[data-ref]")?.getAttribute("data-ref") : null)

function SectionView({ section }: { section: Section }) {
  const { view, collapsed, setSectionOpen, byId } = useNotebook()
  const items = section.items.map((it) => <ItemView key={it.key} item={it} />)
  const h = section.heading
  if (!h) return <div className="flex flex-col gap-6">{items}</div>
  const open = !collapsed.has(section.key)
  const cells = section.items.filter((it) => it.type === "block" && isVisible(it.block, view)).length
  const anchorErr = h.anchor ? byId.get(h.anchor)?.error : undefined
  const Tag = h.level === 1 ? "h2" : "h3"
  return (
    <Collapsible open={open} onOpenChange={(o) => setSectionOpen(section.key, o)} className="flex flex-col gap-6">
      <div
        id={h.anchor ? `cell-${h.anchor}` : undefined}
        tabIndex={h.anchor ? -1 : undefined}
        className={cn("flex scroll-mt-4 items-center gap-2 border-b pb-2 outline-none", h.level === 1 ? "pt-2" : "pt-4")}
      >
        <CollapsibleTrigger asChild>
          <Button variant="ghost" size="icon-xs" aria-label={open ? `Collapse ${h.text}` : `Expand ${h.text}`}>
            <ChevronRightIcon className={cn("size-(--chevron-size) text-muted-foreground transition-transform", open && "rotate-90")} />
          </Button>
        </CollapsibleTrigger>
        <Tag
          id={section.key}
          className={cn("min-w-0 flex-1 scroll-mt-4", h.level === 1 ? "tb-h2" : "tb-h3")}
          dangerouslySetInnerHTML={{ __html: h.html }}
        />
        {!open && cells ? <span className="shrink-0 text-[11px] text-muted-foreground">{plural(cells, "cell")}</span> : null}
      </div>
      {anchorErr ? <BlockError title="Prose error" message={anchorErr} /> : null}
      <CollapsibleContent className="flex flex-col gap-6">{items}</CollapsibleContent>
    </Collapsible>
  )
}

/** Sections in document order. One delegating listener turns `.tb-ref` spans (prose + headings) into trace triggers. */
export function Notebook() {
  const { sections, openRef } = useNotebook()
  const onClick = (e: MouseEvent) => {
    const ref = refOf(e.target)
    if (ref) openRef(ref)
  }
  const onKeyDown = (e: KeyboardEvent) => {
    const ref = (e.key === "Enter" || e.key === " ") && e.target === (e.target as Element).closest?.(".tb-ref") ? refOf(e.target) : null
    if (!ref) return
    e.preventDefault()
    openRef(ref)
  }
  if (!sections.length) return <p className="text-muted-foreground">This notebook has no blocks.</p>
  return (
    <div className="flex flex-col gap-8" onClick={onClick} onKeyDown={onKeyDown}>
      {sections.map((s) => (
        <SectionView key={s.key} section={s} />
      ))}
    </div>
  )
}
