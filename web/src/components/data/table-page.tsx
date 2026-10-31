import { AlertCircleIcon, CheckIcon, CopyIcon } from "lucide-react"
import { useState } from "react"
import { useLive } from "@/app/live-context"
import { count, isNumeric, selectSql, typeNote } from "@/components/data/schema"
import { tagClass } from "@/components/notebook/status-badge"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { useCopy } from "@/hooks/use-copy"
import { usePreview } from "@/hooks/use-preview"
import { useSchema } from "@/hooks/use-schema"
import { plural } from "@/lib/notebook"
import { cn } from "@/lib/utils"
import type { Preview, SchemaColumn, SchemaTable } from "@/types"

// Contract (owned by the data-browser pass): main-area page for one imported table (Columns | Preview tabs).
// onOpenBlock navigates to a notebook cell that reads this table.
export type TablePageProps = { table: string; onOpenBlock?: (notebook: string, block: string) => void }

const label = "text-[11px] tracking-wider text-muted-foreground uppercase"
const head = cn(label, "h-8 font-normal")

function ErrorAlert({ title, message }: { title: string; message: string }) {
  return (
    <Alert variant="destructive" className="rounded-none">
      <AlertCircleIcon />
      <AlertTitle>{title}</AlertTitle>
      <AlertDescription className="break-all">{message}</AlertDescription>
    </Alert>
  )
}

const Loading = () => (
  <div className="flex flex-col gap-2" aria-busy>
    <Skeleton className="h-6 w-1/3" />
    <Skeleton className="h-4 w-full" />
    <Skeleton className="h-4 w-2/3" />
  </div>
)

function CopySql({ name }: { name: string }) {
  const { status, copy } = useCopy()
  const [hover, setHover] = useState(false)
  const sql = selectSql(name)
  return (
    <Tooltip open={hover || status !== "idle"} onOpenChange={setHover}>
      <TooltipTrigger asChild>
        <Button variant="outline" size="xs" className="rounded-none" onClick={() => void copy(sql)}>
          {status === "copied" ? <CheckIcon /> : <CopyIcon />}
          copy SQL
        </Button>
      </TooltipTrigger>
      <TooltipContent className="font-mono">{status === "copied" ? "Copied" : status === "failed" ? "Copy failed" : sql}</TooltipContent>
    </Tooltip>
  )
}

function TypeCell({ type }: { type: string }) {
  const note = typeNote(type)
  if (!note) return <span className="text-muted-foreground">{type}</span>
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span tabIndex={0} className="cursor-help text-primary underline decoration-dotted underline-offset-4">
          {type}
        </span>
      </TooltipTrigger>
      <TooltipContent>{note}</TooltipContent>
    </Tooltip>
  )
}

function ColumnsTable({ columns }: { columns: SchemaColumn[] }) {
  return (
    <Table className="text-xs">
      <TableHeader>
        <TableRow className="hover:bg-transparent">
          <TableHead className={head}>column</TableHead>
          <TableHead className={head}>type</TableHead>
          <TableHead className={head}>source</TableHead>
          <TableHead className={head}>values</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {columns.map((c) => (
          <TableRow key={c.name}>
            <TableCell className="py-1.5 font-medium">{c.name}</TableCell>
            <TableCell className="py-1.5">
              <TypeCell type={c.type} />
            </TableCell>
            <TableCell className="py-1.5 text-muted-foreground">{c.source ?? "—"}</TableCell>
            <TableCell className="py-1.5 whitespace-normal">
              {c.values === undefined ? null : c.values.length === 0 ? (
                <span className="text-muted-foreground italic">all null</span>
              ) : (
                <div className="flex min-w-72 flex-wrap gap-1">
                  {c.values.map((v) => (
                    <Badge key={v} variant="secondary" className="rounded-none px-1.5 py-0 text-[11px] font-normal">
                      {v}
                    </Badge>
                  ))}
                </div>
              )}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}

function PreviewTable({ preview }: { preview: Preview }) {
  const numeric = preview.columns.map((c) => isNumeric(c.type))
  return (
    <div className="flex min-w-0 flex-col gap-2">
      {/* one scroll box for both axes so the sticky header works; the Table's own x-scroll wrapper is neutralised */}
      <div className="max-h-[70vh] overflow-auto border [&>[data-slot=table-container]]:overflow-visible">
        <Table className="text-xs tabular-nums">
          <TableHeader className="sticky top-0 z-10 bg-background">
            <TableRow className="hover:bg-transparent">
              {preview.columns.map((c, i) => (
                <TableHead key={c.name} title={c.type} className={cn(head, numeric[i] && "text-right")}>
                  {c.name}
                </TableHead>
              ))}
            </TableRow>
          </TableHeader>
          <TableBody>
            {preview.display.map((r, ri) => (
              <TableRow key={ri}>
                {r.map((v, i) =>
                  preview.rows[ri]?.[i] === null ? (
                    <TableCell key={i} className={cn("py-1.5 text-muted-foreground/60", numeric[i] && "text-right")} aria-label="null">
                      ∅
                    </TableCell>
                  ) : (
                    <TableCell key={i} className={cn("max-w-80 truncate py-1.5", numeric[i] && "text-right")} title={v}>
                      {v}
                    </TableCell>
                  ),
                )}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
      <p className="text-[11px] text-muted-foreground">
        showing first {count(preview.display.length)}
        {preview.rowCount === null ? " rows" : ` of ${plural(preview.rowCount, "row")}`}
      </p>
    </div>
  )
}

function Header({ meta }: { meta: SchemaTable }) {
  return (
    <header className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <h1 className="min-w-0 font-mono text-2xl font-semibold break-all">{meta.name}</h1>
        <Badge variant="outline" className={cn(tagClass, "text-muted-foreground")}>
          {meta.source}
        </Badge>
        <CopySql name={meta.name} />
      </div>
      <p className="flex flex-wrap gap-x-3 text-xs text-muted-foreground">
        <span className="tabular-nums">{meta.rows === null ? "read-only source (rows not counted)" : plural(meta.rows, "row")}</span>
        <span>{plural(meta.columns.length, "column")}</span>
        {meta.files.length ? <span className="break-all">from {meta.files.join(", ")}</span> : null}
      </p>
    </header>
  )
}

function UsedBy({ usedBy, onOpenBlock }: { usedBy: SchemaTable["usedBy"]; onOpenBlock?: TablePageProps["onOpenBlock"] }) {
  if (usedBy.length === 0) return null
  return (
    <section className="flex flex-col gap-1.5">
      <h2 className={label}>used by</h2>
      <div className="flex flex-wrap gap-1.5">
        {usedBy.map(({ notebook, block }) => (
          <Button
            key={`${notebook}\u0000${block}`}
            variant="outline"
            size="xs"
            className="rounded-none font-normal"
            disabled={!onOpenBlock}
            onClick={() => onOpenBlock?.(notebook, block)}
          >
            {notebook} <span className="text-muted-foreground">›</span> {block}
          </Button>
        ))}
      </div>
    </section>
  )
}

export function TablePage({ table, onOpenBlock }: TablePageProps) {
  const { live } = useLive()
  const schema = useSchema()
  const meta = schema.tables?.find((t) => t.name === table)
  const missing = schema.tables !== null && !meta
  const { preview, error, loading } = usePreview(live && !missing ? table : null)

  if (!live)
    return (
      <p className="p-6 text-xs text-muted-foreground">
        The data browser is available in <code className="text-foreground">tracebook dev</code>.
      </p>
    )
  return (
    <div className="flex min-w-0 flex-col gap-5 p-4 md:p-6">
      {schema.error ? <ErrorAlert title={meta ? "Showing last loaded schema" : "Could not load schema"} message={schema.error} /> : null}
      {missing ? (
        <ErrorAlert title="Unknown table" message={`No imported or source table named “${table}”.`} />
      ) : !meta ? (
        schema.error ? null : <Loading />
      ) : (
        <>
          <Header meta={meta} />
          <Tabs defaultValue="columns" className="min-w-0 gap-3">
            <TabsList variant="line" className="h-8 rounded-none border-b p-0">
              <TabsTrigger value="columns" className={cn(label, "rounded-none px-3")}>
                columns
              </TabsTrigger>
              <TabsTrigger value="preview" className={cn(label, "rounded-none px-3")}>
                preview
              </TabsTrigger>
            </TabsList>
            <TabsContent value="columns" className="min-w-0">
              <ColumnsTable columns={meta.columns} />
            </TabsContent>
            <TabsContent value="preview" className="flex min-w-0 flex-col gap-2">
              {error ? <ErrorAlert title={preview ? "Showing last loaded preview" : "Could not load preview"} message={error} /> : null}
              {preview ? <PreviewTable preview={preview} /> : loading ? <Loading /> : null}
            </TabsContent>
          </Tabs>
          <UsedBy usedBy={meta.usedBy} onOpenBlock={onOpenBlock} />
        </>
      )}
    </div>
  )
}
