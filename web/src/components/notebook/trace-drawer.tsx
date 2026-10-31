import { CrosshairIcon } from "lucide-react"
import { useRef, type ReactNode } from "react"
import { BlockComments } from "@/components/notebook/block-comments"
import { BlockError } from "@/components/notebook/block-error"
import { CodeBlock, ComputeResult } from "@/components/notebook/compute-cell"
import { CopyRefButton } from "@/components/notebook/copy-ref-button"
import { useNotebook } from "@/components/notebook/notebook-context"
import { SheetGrid } from "@/components/notebook/sheet-grid"
import { KindBadge, StatusBadge } from "@/components/notebook/status-badge"
import { Button } from "@/components/ui/button"
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet"
import { useComments } from "@/hooks/use-comments"
import { blockLabel, isCompute, plural } from "@/lib/notebook"
import type { Block } from "@/types"

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <section className="flex min-w-0 flex-col gap-1.5">
      <h3 className="text-[11px] tracking-[1.5px] text-muted-foreground uppercase">{label}</h3>
      {children}
    </section>
  )
}

function Links({ ids }: { ids: string[] }) {
  const { openTrace, byId } = useNotebook()
  if (!ids.length) return <span className="text-xs text-muted-foreground">—</span>
  return (
    <div className="flex flex-wrap gap-1">
      {ids.map((id) => (
        <Button key={id} variant="outline" size="xs" onClick={() => openTrace(id)} title={byId.get(id) ? blockLabel(byId.get(id)!) : "not in this run"}>
          {id}
        </Button>
      ))}
    </div>
  )
}

/** One-line spec of a display block (what it reads and how). */
function spec(b: Block): string | null {
  switch (b.kind) {
    case "chart":
      return [
        `${b.type}${b.variant && b.variant !== "default" ? `/${b.variant}` : ""}`,
        `data: ${b.data}`,
        b.x ? `x: ${b.x}` : null,
        `y: ${b.y.join(", ")}`,
        b.format ? `format: ${b.format}` : null,
      ]
        .filter(Boolean)
        .join("\n")
    case "table":
      return `data: ${b.data}\ncolumns: ${b.columns.join(", ")}`
    case "kpi":
      return b.items.map((it) => `${it.label}: ${it.ref ?? "—"}${it.compareRef ? ` vs ${it.compareRef}` : ""}`).join("\n")
    case "md":
      return b.text.trim()
    default:
      return null
  }
}

function TraceBody({ block, col }: { block: Block; col?: string }) {
  const { scrollTo, closeTrace, skipFocusRestore, view, doc } = useNotebook()
  const comments = useComments()
  const compute = isCompute(block) ? block : null
  const code = compute ? compute.code : spec(block)
  const goTo = () => {
    skipFocusRestore.current = true
    closeTrace()
    requestAnimationFrame(() => scrollTo(block.id))
  }
  const hiddenHere = view === "report" && (block.kind === "sql" || block.kind === "python")
  return (
    <>
      <SheetHeader className="gap-2 border-b pr-12">
        <div className="flex flex-wrap items-center gap-2">
          <KindBadge kind={block.kind} />
          {compute ? <StatusBadge status={compute.status} /> : null}
          {col ? <span className="text-[11px] text-primary">.{col}</span> : null}
        </div>
        <SheetTitle className="text-base break-words">{blockLabel(block)}</SheetTitle>
        <SheetDescription className="text-xs">
          @{block.id} · {doc.path || "notebook.md"}:{block.line}
        </SheetDescription>
        <div className="flex flex-wrap gap-1">
          <CopyRefButton block={block} withText />
          {hiddenHere ? null : (
            <Button variant="ghost" size="xs" className="text-muted-foreground" onClick={goTo}>
              <CrosshairIcon />
              go to cell
            </Button>
          )}
        </div>
      </SheetHeader>
      <div className="flex min-h-0 flex-1 flex-col gap-5 overflow-y-auto px-4 pb-6">
        {block.error ? <BlockError message={block.error} /> : null}
        {code ? (
          <Field label={compute ? "Code" : "Spec"}>
            <CodeBlock code={code} className="border whitespace-pre" />
          </Field>
        ) : null}
        {comments.enabled ? (
          <Field label={`Comments · ${comments.forBlock(block.id).filter((c) => c.status === "open").length} open`}>
            <BlockComments block={block.id} anchor={block.anchor} />
          </Field>
        ) : null}
        <Field label="Depends on">
          <Links ids={block.deps} />
        </Field>
        <Field label="Used by">
          <Links ids={block.usedBy} />
        </Field>
        {compute?.grid ? (
          <Field label={`Sheet · ${compute.grid.sheet}!${compute.grid.range}`}>
            <SheetGrid grid={compute.grid} />
          </Field>
        ) : null}
        {compute?.columns?.length ? (
          <Field label={compute.rowCount != null ? `Result · ${plural(compute.rowCount, "row")}` : "Result"}>
            <ComputeResult block={compute} highlight={col} />
          </Field>
        ) : null}
      </div>
    </>
  )
}

/** Right drawer: provenance of one block (code/spec, deps, dependants, rows). Re-targets in place via openTrace. */
export function TraceDrawer() {
  const { trace, byId, closeTrace, skipFocusRestore } = useNotebook()
  const block = trace ? byId.get(trace.id) : undefined
  const panel = useRef<HTMLDivElement>(null)
  return (
    <Sheet open={!!trace?.open} onOpenChange={(o) => !o && closeTrace()}>
      <SheetContent
        ref={panel}
        side="right"
        className="w-full gap-0 sm:max-w-xl"
        // focus the panel, not the first button (whose tooltip would pop open on every trace)
        onOpenAutoFocus={(e) => {
          e.preventDefault()
          panel.current?.focus()
        }}
        onCloseAutoFocus={(e) => {
          if (skipFocusRestore.current) e.preventDefault()
          skipFocusRestore.current = false
        }}
      >
        {block ? (
          <TraceBody key={block.id} block={block} col={trace?.col} />
        ) : (
          <SheetHeader>
            <SheetTitle>Unknown block</SheetTitle>
            <SheetDescription>“{trace?.id}” is not in this run (removed or failed to parse).</SheetDescription>
          </SheetHeader>
        )}
      </SheetContent>
    </Sheet>
  )
}
