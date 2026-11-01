import { Component, type ReactNode } from "react"
import { Button } from "@/components/ui/button"
import { Card, CardAction, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card"
import { Table, TableBody, TableCell, TableFooter, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import type { ChartBlock } from "@/types"
import { viewFor } from "./registry"
import { ChartAlert } from "./unknown-variant"

// Contract (owned by the charts pass): one card per chart block. `onTrace(blockId)` opens the trace drawer.
export type ChartCardProps = { block: ChartBlock; onTrace?: (blockId: string) => void }

const label = "tb-label"

/** A drawing bug in one chart must not take down the notebook. */
type BoundaryProps = { block: ChartBlock; children: ReactNode }
class ChartBoundary extends Component<BoundaryProps, { error: string | null; block: ChartBlock }> {
  state: { error: string | null; block: ChartBlock } = { error: null, block: this.props.block }
  static getDerivedStateFromError(e: unknown) {
    return { error: e instanceof Error ? e.message : String(e) }
  }
  // A new run (new block object) gets a fresh attempt.
  static getDerivedStateFromProps(p: BoundaryProps, s: { block: ChartBlock }) {
    return p.block === s.block ? null : { error: null, block: p.block }
  }
  render() {
    return this.state.error ? <ChartAlert title="Chart failed to draw" message={this.state.error} /> : this.props.children
  }
}

function DataTable({ block }: { block: ChartBlock }) {
  const labels = block.labels ?? (block.type === "radial" ? [""] : [])
  const share = block.type === "funnel" ? block.share : undefined
  return (
    <Table className="text-xs">
      <TableHeader>
        <TableRow>
          <TableHead className={label}>{block.x ?? ""}</TableHead>
          {block.series.map((s, k) => (
            <TableHead key={k} className={`${label} text-right`}>{s.name}</TableHead>
          ))}
          {share ? <TableHead className={`${label} text-right`}>of first</TableHead> : null}
        </TableRow>
      </TableHeader>
      <TableBody>
        {labels.map((x, i) => (
          <TableRow key={i}>
            <TableCell className="whitespace-normal">{x}</TableCell>
            {block.series.map((s, k) => (
              <TableCell key={k} className="text-right tabular-nums">{s.display[i] ?? "—"}</TableCell>
            ))}
            {share ? <TableCell className="text-right tabular-nums">{share[i] ?? "—"}</TableCell> : null}
          </TableRow>
        ))}
      </TableBody>
      {block.total ? (
        <TableFooter>
          <TableRow>
            <TableCell className={label}>Total</TableCell>
            <TableCell className="text-right tabular-nums">{block.total}</TableCell>
            {share ? <TableCell /> : null}
          </TableRow>
        </TableFooter>
      ) : null}
    </Table>
  )
}

function Body({ block }: { block: ChartBlock }) {
  if (block.error) return <ChartAlert title="Chart error" message={block.error} />
  const View = viewFor(block.type)
  if (!View) return <ChartAlert title="Unsupported chart" message={`chart type "${block.type}" is not drawn by this viewer`} />
  if (block.type !== "radial" && !block.labels?.length) return <p className="py-8 text-center text-xs text-muted-foreground">No rows</p>
  return (
    <ChartBoundary block={block}>
      <View block={block} />
    </ChartBoundary>
  )
}

export function ChartCard({ block, onTrace }: ChartCardProps) {
  const drawable = !block.error && viewFor(block.type) !== undefined
  const trace = block.data ? (
    <CardFooter className="px-4">
      {onTrace ? (
        <Button variant="ghost" size="xs" className="-ml-2 rounded-none font-mono text-[11px] text-muted-foreground" onClick={() => onTrace(block.data)}>
          ↳ {block.data}
        </Button>
      ) : (
        <span className="font-mono text-[11px] text-muted-foreground">↳ {block.data}</span>
      )}
    </CardFooter>
  ) : null
  return (
    <Card data-chart={block.id} className="min-w-0 gap-3 rounded-none py-4">
      <Tabs defaultValue="chart" className="gap-3">
        <CardHeader className="px-4">
          {block.title ? <CardTitle className="text-sm font-medium">{block.title}</CardTitle> : null}
          {block.description ? <CardDescription className="text-xs">{block.description}</CardDescription> : null}
          {drawable ? (
            <CardAction>
              <TabsList variant="line" className="h-7">
                <TabsTrigger value="chart" className={`rounded-none ${label}`}>Chart</TabsTrigger>
                <TabsTrigger value="table" className={`rounded-none ${label}`}>Table</TabsTrigger>
              </TabsList>
            </CardAction>
          ) : null}
        </CardHeader>
        <TabsContent value="chart" className="min-w-0 px-2 sm:px-4">
          <Body block={block} />
        </TabsContent>
        {drawable ? (
          <TabsContent value="table" className="min-w-0 px-4">
            <DataTable block={block} />
          </TabsContent>
        ) : null}
        {trace}
      </Tabs>
    </Card>
  )
}
