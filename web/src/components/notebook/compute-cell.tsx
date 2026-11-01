import { ChevronRightIcon } from "lucide-react"
import { useState } from "react"
import { BlockError } from "@/components/notebook/block-error"
import { ChipRow } from "@/components/notebook/chip-row"
import { useNotebook } from "@/components/notebook/notebook-context"
import { ResultTable } from "@/components/notebook/result-table"
import { SheetGrid } from "@/components/notebook/sheet-grid"
import { KindBadge, StatusBadge } from "@/components/notebook/status-badge"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"
import { blockLabel, isNumericType } from "@/lib/notebook"
import { cn } from "@/lib/utils"
import type { ComputeBlock } from "@/types"

export function CodeBlock({ code, className }: { code: string; className?: string }) {
  return <pre className={cn("overflow-x-auto bg-muted/40 px-3 py-2 text-xs leading-relaxed", className)}>{code}</pre>
}

/** Formatted output rows of a compute block (null when it produced none). */
export function ComputeResult({ block, highlight }: { block: ComputeBlock; highlight?: string }) {
  if (!block.columns?.length || !block.display) return null
  return (
    <ResultTable
      columns={block.columns.map((c) => c.name)}
      numeric={block.columns.map((c) => isNumericType(c.type))}
      rows={block.display}
      rowCount={block.rowCount}
      truncated={block.truncated}
      highlight={highlight}
    />
  )
}

function StatusNote({ block }: { block: ComputeBlock }) {
  if (block.status === "error") return <BlockError title={`${block.kind} failed`} message={block.error ?? "unknown error"} />
  if (block.status === "skipped")
    return <p className="text-xs text-muted-foreground">skipped{block.error ? `: ${block.error}` : " (an upstream block failed)"}</p>
  return null
}

/** Hex-style cell: header, code (collapsible), status, result preview; chip row underneath. Report view: sheet grid only. */
export function ComputeCell({ block }: { block: ComputeBlock }) {
  const { view } = useNotebook()
  const [codeOpen, setCodeOpen] = useState(true)

  if (view === "report") {
    return (
      <Card className="gap-2 py-3">
        <div className="tb-label px-3 text-muted-foreground">{blockLabel(block)}</div>
        <div className="flex flex-col gap-2 px-3">
          {block.grid ? <SheetGrid grid={block.grid} /> : null}
          <StatusNote block={block} />
        </div>
      </Card>
    )
  }

  return (
    <div className="min-w-0">
      <Card className="gap-0 py-0">
        <Collapsible open={codeOpen} onOpenChange={setCodeOpen}>
          <div className="flex min-w-0 items-center gap-2 px-2 py-1.5">
            <CollapsibleTrigger asChild>
              <Button variant="ghost" size="icon-xs" aria-label={codeOpen ? "Hide code" : "Show code"}>
                <ChevronRightIcon className={cn("size-(--chevron-size) text-muted-foreground transition-transform", codeOpen && "rotate-90")} />
              </Button>
            </CollapsibleTrigger>
            <KindBadge kind={block.kind} />
            <span className="min-w-0 flex-1 truncate font-medium">{blockLabel(block)}</span>
            {block.file ? <span className="hidden truncate text-[11px] text-muted-foreground sm:inline">{block.file}</span> : null}
            <StatusBadge status={block.status} />
          </div>
          <CollapsibleContent>
            <CodeBlock code={block.code} className="border-t" />
          </CollapsibleContent>
        </Collapsible>
        {block.status !== "ok" || block.grid || block.columns?.length ? (
          <div className="flex flex-col gap-3 border-t px-3 py-3">
            <StatusNote block={block} />
            {block.grid ? <SheetGrid grid={block.grid} /> : null}
            <ComputeResult block={block} />
          </div>
        ) : null}
      </Card>
      <ChipRow block={block} />
    </div>
  )
}
