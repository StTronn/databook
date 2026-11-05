import { useState } from "react"
import { Button } from "@/components/ui/button"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { plural } from "@/lib/notebook"
import { cn } from "@/lib/utils"

type Props = {
  columns: string[]
  rows: string[][]
  numeric: boolean[]
  /** total rows the query produced (rows may be capped by the runner) */
  rowCount?: number
  truncated?: boolean
  /** column to emphasise (trace of `block.col`) */
  highlight?: string
  limit?: number
  /** index of a column whose cells are links; onLink(row index) on click */
  linkCol?: number
  onLink?: (row: number) => void
}

/** Formatted result rows: first `limit`, with a show-all toggle; notes when the runner capped the rows. */
export function ResultTable({ columns, rows, numeric, rowCount, truncated, highlight, limit = 10, linkCol = -1, onLink }: Props) {
  const [all, setAll] = useState(false)
  const shown = all ? rows : rows.slice(0, limit)
  const hi = highlight ? columns.indexOf(highlight) : -1
  const cls = (i: number) => cn(numeric[i] && "text-right", i === hi && "bg-primary/10 text-primary")
  return (
    <div className="min-w-0">
      <Table className="text-xs tabular-nums">
        <TableHeader>
          <TableRow className="hover:bg-transparent">
            {columns.map((c, i) => (
              <TableHead key={c + i} className={cn("tb-label h-8 text-muted-foreground", cls(i))}>
                {c}
              </TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {shown.map((r, ri) => (
            <TableRow key={ri}>
              {r.map((v, i) => (
                <TableCell key={i} className={cn("py-1.5", cls(i))}>
                  {i === linkCol && onLink ? (
                    <button type="button" className="text-primary underline-offset-2 hover:underline" onClick={() => onLink(ri)}>{v}</button>
                  ) : v}
                </TableCell>
              ))}
            </TableRow>
          ))}
        </TableBody>
      </Table>
      {rows.length > limit || truncated ? (
        <div className="flex flex-wrap items-center gap-2 pt-1 text-[11px] text-muted-foreground">
          {rows.length > limit ? (
            <Button variant="link" size="xs" className="px-0" onClick={() => setAll((a) => !a)}>
              {all ? `show first ${limit}` : `show all ${rows.length.toLocaleString("en-US")}`}
            </Button>
          ) : null}
          {truncated ? <span>results capped: {rows.length.toLocaleString("en-US")} of {plural(rowCount ?? rows.length, "row")}</span> : null}
        </div>
      ) : null}
    </div>
  )
}
