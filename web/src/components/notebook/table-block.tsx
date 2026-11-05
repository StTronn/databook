import { CornerDownRightIcon } from "lucide-react"
import { useLive } from "@/app/live-context"
import { BlockError } from "@/components/notebook/block-error"
import { useNotebook } from "@/components/notebook/notebook-context"
import { ResultTable } from "@/components/notebook/result-table"
import { Button } from "@/components/ui/button"
import { pickParam } from "@/components/notebook/param-bar"
import { Card } from "@/components/ui/card"
import { plural } from "@/lib/notebook"
import type { TableBlock } from "@/types"

export function TableView({ block }: { block: TableBlock }) {
  const { openTrace, doc } = useNotebook()
  const { live } = useLive()
  const link = live ? block.link : undefined                  // exported reports have no server to rerun with a pick
  const onLink = link
    ? (row: number) => void pickParam(doc.notebook, link.param, link.values[row]).then(() =>
        document.getElementById("tb-params")?.scrollIntoView({ behavior: "smooth", block: "start" }))
    : undefined
  return (
    <Card className="gap-2 py-3">
      <div className="flex min-w-0 items-center gap-2 px-3">
        <span className="min-w-0 flex-1 truncate tb-label text-muted-foreground">
          {block.title ?? `${block.data} · ${plural(block.rowCount ?? 0, "row")}`}
        </span>
        <Button variant="ghost" size="xs" className="text-[11px] text-muted-foreground" onClick={() => openTrace(block.data)}>
          <CornerDownRightIcon />
          {block.data}
        </Button>
      </div>
      <div className="px-3">
        {block.error ? (
          <BlockError title="Table error" message={block.error} />
        ) : (
          <ResultTable
            columns={block.columns}
            numeric={block.numeric}
            rows={block.display}
            rowCount={block.rowCount}
            truncated={block.truncated}
            limit={25}
            linkCol={link ? block.columns.indexOf(link.column) : -1}
            onLink={onLink}
          />
        )}
      </div>
    </Card>
  )
}
