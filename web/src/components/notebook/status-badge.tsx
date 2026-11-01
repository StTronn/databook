import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"
import type { ComputeBlock } from "@/types"

export const tagClass = "tb-label rounded-none px-1.5 py-0 text-[10px]"

export function KindBadge({ kind }: { kind: string }) {
  return (
    <Badge variant="outline" className={cn(tagClass, "text-muted-foreground")}>
      {kind}
    </Badge>
  )
}

const STATUS = { ok: "border-success/40 text-success", error: "border-destructive/50 text-destructive", skipped: "text-muted-foreground" }

export function StatusBadge({ status }: { status: ComputeBlock["status"] }) {
  return (
    <Badge variant="outline" className={cn(tagClass, STATUS[status])}>
      {status}
    </Badge>
  )
}
