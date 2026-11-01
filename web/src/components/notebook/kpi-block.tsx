import { BlockError } from "@/components/notebook/block-error"
import { useNotebook } from "@/components/notebook/notebook-context"
import { tagClass } from "@/components/notebook/status-badge"
import { Badge } from "@/components/ui/badge"
import { Card } from "@/components/ui/card"
import { cn } from "@/lib/utils"
import type { KpiBlock, KpiItem } from "@/types"

const deltaClass = (d?: number) =>
  d == null || d === 0 ? "text-muted-foreground" : d > 0 ? "border-success/40 text-success" : "border-destructive/50 text-destructive"

function Kpi({ item }: { item: KpiItem }) {
  const { openRef } = useNotebook()
  const ref = item.ref
  const trace = ref ? () => openRef(ref) : undefined
  return (
    <Card
      role={trace ? "button" : undefined}
      tabIndex={trace ? 0 : undefined}
      onClick={trace}
      onKeyDown={trace ? (e) => (e.key === "Enter" || e.key === " ") && (e.preventDefault(), trace()) : undefined}
      title={item.error ?? (ref ? `trace ${ref}` : undefined)}
      className={cn("min-w-0 gap-2 px-3 py-3", trace && "cursor-pointer transition-colors outline-none hover:border-border-hover focus-visible:border-ring")}
    >
      <div className="tb-label truncate text-muted-foreground">{item.label}</div>
      <div className={cn("tb-kpi truncate", item.error && "text-destructive")}>{item.value || (item.error ? "#REF" : "—")}</div>
      {item.error ? (
        <div className="truncate text-[11px] text-destructive">{item.error}</div>
      ) : item.deltaText ? (
        <Badge variant="outline" className={cn(tagClass, deltaClass(item.delta))}>
          {item.deltaText}
        </Badge>
      ) : null}
    </Card>
  )
}

export function KpiGrid({ block }: { block: KpiBlock }) {
  return (
    <div className="flex flex-col gap-2">
      {block.error ? <BlockError title="KPI error" message={block.error} /> : null}
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-[repeat(auto-fit,minmax(9.5rem,1fr))]">
        {block.items.map((it, i) => (
          <Kpi key={`${it.label}-${i}`} item={it} />
        ))}
      </div>
    </div>
  )
}
