import { PlusIcon } from "lucide-react"
import { ChartCard } from "@/components/charts/chart-card"
import { BlockError } from "@/components/notebook/block-error"
import { ComputeCell } from "@/components/notebook/compute-cell"
import { KpiGrid } from "@/components/notebook/kpi-block"
import { useNotebook } from "@/components/notebook/notebook-context"
import { Prose } from "@/components/notebook/prose"
import { TableView } from "@/components/notebook/table-block"
import { Button } from "@/components/ui/button"
import { useAgentMaybe } from "@/hooks/use-agent"
import { isVisible, type Item } from "@/lib/notebook"
import { cn } from "@/lib/utils"
import type { Block } from "@/types"

function Body({ block }: { block: Block }) {
  const { openTrace } = useNotebook()
  switch (block.kind) {
    case "sql":
    case "python":
    case "sheet":
      return <ComputeCell block={block} />
    case "kpi":
      return <KpiGrid block={block} />
    case "table":
      return <TableView block={block} />
    case "chart":
      // errored charts may lack series data → never hand them to the renderer
      return block.error ? <BlockError title={`Chart error · ${block.title ?? block.id}`} message={block.error} /> : <ChartCard block={block} onTrace={openTrace} />
    case "md":
      return null
  }
}

/** Hover "Ask" button (dev viewer only) + ring on blocks the agent just changed. */
function AskWrap({ id, children }: { id: string; children: React.ReactNode }) {
  const agent = useAgentMaybe()
  if (!agent) return <>{children}</>
  return (
    <div className={cn("group/ask relative transition-shadow", agent.highlighted.has(id) && "ring-2 ring-primary ring-offset-4 ring-offset-background")}
      style={{ borderRadius: "calc(var(--radius) * 1.4)" }}>
      {children}
      <Button
        variant="outline"
        size="icon-xs"
        aria-label="Ask about this block"
        title="Ask the agent about this block (⌘K)"
        className="absolute -top-2.5 -right-2.5 z-10 bg-background opacity-0 shadow-sm transition-opacity group-hover/ask:opacity-100 focus-visible:opacity-100"
        onClick={(e) => {
          const r = e.currentTarget.getBoundingClientRect()
          agent.openComposer({ context: agent.contextFor(id), x: r.right - 380, y: r.bottom + 6 })
        }}
      >
        <PlusIcon />
      </Button>
    </div>
  )
}

/** One section item; carries the `#cell-<id>` scroll target. */
export function ItemView({ item }: { item: Item }) {
  const { view } = useNotebook()
  if (item.type === "prose") {
    const anchor = item.anchor
    return (
      <div id={anchor ? `cell-${anchor}` : undefined} tabIndex={anchor ? -1 : undefined} className="flex scroll-mt-4 flex-col gap-2 outline-none">
        {anchor && item.block.error ? <BlockError title="Prose error" message={item.block.error} /> : null}
        {item.text ? <AskWrap id={item.block.id}><Prose text={item.text} /></AskWrap> : null}
      </div>
    )
  }
  if (!isVisible(item.block, view)) return null
  return (
    <div id={`cell-${item.block.id}`} tabIndex={-1} className="min-w-0 scroll-mt-4 outline-none">
      <AskWrap id={item.block.id}><Body block={item.block} /></AskWrap>
    </div>
  )
}
