import { ChevronRightIcon, SearchIcon, TableIcon } from "lucide-react"
import { useDeferredValue, useMemo, useState } from "react"
import { useLive } from "@/app/live-context"
import { buildTree, count } from "@/components/data/schema"
import { tagClass } from "@/components/notebook/status-badge"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"
import { Input } from "@/components/ui/input"
import { Skeleton } from "@/components/ui/skeleton"
import { useSchema } from "@/hooks/use-schema"
import { cn } from "@/lib/utils"

// Contract (owned by the data-browser pass): sidebar tree of imported tables grouped by source, with search.
export type DataTreeProps = { selected?: string | null; onOpen: (table: string) => void }

const label = "tb-label text-[10px] text-muted-foreground"

export function DataTree({ selected, onOpen }: DataTreeProps) {
  const { live } = useLive()
  const { tables, sourceErrors, error } = useSchema()
  const [query, setQuery] = useState("")
  const q = useDeferredValue(query)
  const [collapsed, setCollapsed] = useState<ReadonlySet<string>>(() => new Set())
  const groups = useMemo(() => (tables ? buildTree(tables, q) : []), [tables, q])
  if (!live) return null

  const toggle = (g: string, open: boolean) =>
    setCollapsed((s) => {
      const n = new Set(s)
      if (open) n.delete(g)
      else n.add(g)
      return n
    })

  return (
    <div className="flex min-h-0 flex-col gap-2">
      <div className="relative">
        <SearchIcon className="pointer-events-none absolute top-1/2 left-2 size-3.5 -translate-y-1/2 text-muted-foreground" />
        <Input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="search tables, columns"
          aria-label="Search tables and columns"
          className="h-8 rounded-none pl-7 text-xs md:text-xs"
        />
      </div>
      {Object.entries(sourceErrors).map(([name, msg]) => (
        <Alert key={name} variant="destructive" className="rounded-none px-3 py-2">
          <AlertDescription className="text-xs break-all">
            source {name} unavailable: {msg}
          </AlertDescription>
        </Alert>
      ))}
      {error && !tables ? (
        <Alert variant="destructive" className="rounded-none px-3 py-2">
          <AlertDescription className="text-xs break-all">{error}</AlertDescription>
        </Alert>
      ) : !tables ? (
        <div className="flex flex-col gap-1.5" aria-busy>
          {[0, 1, 2].map((i) => <Skeleton key={i} className="h-6 w-full" />)}
        </div>
      ) : tables.length === 0 && Object.keys(sourceErrors).length === 0 ? (
        <p className="px-1 text-xs leading-relaxed text-muted-foreground">
          No data imported. Run <code className="text-foreground">databook import data/*</code>
        </p>
      ) : groups.length === 0 ? (
        <p className="px-1 text-xs text-muted-foreground">No tables or columns match “{q.trim()}”.</p>
      ) : (
        <div className="flex min-h-0 flex-col gap-2 overflow-y-auto">
          {groups.map(({ group, tables: rows }) => {
            const open = q.trim() !== "" || !collapsed.has(group)
            return (
              <Collapsible key={group} open={open} onOpenChange={(o) => toggle(group, o)}>
                <CollapsibleTrigger asChild>
                  <Button variant="ghost" size="xs" className={cn(label, "w-full justify-start rounded-none px-1")}>
                    <ChevronRightIcon className={cn("transition-transform", open && "rotate-90")} />
                    {group}
                    <span className="ml-auto tabular-nums">{rows.length}</span>
                  </Button>
                </CollapsibleTrigger>
                <CollapsibleContent className="flex flex-col">
                  {rows.map(({ table, kind, columns }) => {
                    const active = table.name === selected
                    return (
                      <div key={table.name}>
                        <Button
                          variant="ghost"
                          size="xs"
                          aria-current={active ? "page" : undefined}
                          title={table.name}
                          onClick={() => onOpen(table.name)}
                          className={cn(
                            "h-7 w-full justify-start gap-1.5 rounded-none pl-5 font-normal",
                            active && "bg-accent text-accent-foreground hover:bg-accent",
                          )}
                        >
                          <TableIcon className="text-muted-foreground" />
                          <span className="truncate">{table.name}</span>
                          {kind ? (
                            <Badge variant="outline" className={cn(tagClass, "shrink text-muted-foreground")}>
                              {kind}
                            </Badge>
                          ) : null}
                          <span className="ml-auto pl-2 text-[11px] text-muted-foreground tabular-nums">{table.rows === null ? "source" : count(table.rows)}</span>
                        </Button>
                        {columns.length ? (
                          <ul className="flex flex-col pb-1 pl-10 text-[11px] text-muted-foreground" aria-label={`Matching columns in ${table.name}`}>
                            {columns.map((c) => (
                              <li key={c} className="truncate">
                                <span aria-hidden>· </span>
                                {c}
                              </li>
                            ))}
                          </ul>
                        ) : null}
                      </div>
                    )
                  })}
                </CollapsibleContent>
              </Collapsible>
            )
          })}
        </div>
      )}
    </div>
  )
}
