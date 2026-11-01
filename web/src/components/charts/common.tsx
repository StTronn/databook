import type { ReactNode } from "react"
import type { ChartPoint, ChartTooltipContent } from "@tanstack/charts"
import { d3Curve } from "@tanstack/charts"
import { tooltip } from "@tanstack/charts/tooltip"
import { scaleBand, scaleLinear, scalePoint } from "d3-scale"
import { curveMonotoneX, curveStep } from "d3-shape"
import type { ChartBlock } from "@/types"
import { clip, tickFormat } from "./format"

/** One row per (x, series) in data order. v=null is kept: lines/areas gap on it, bars/dots filter it out. */
export type Row = { i: number; x: string; k: string; name: string; v: number | null; v2: number | null; d: string; sub?: string }
export type ViewProps = { block: ChartBlock }
export type LegendItem = { label: string; color: string }

export const color = (k: number) => `var(--chart-${(k % 6) + 1})`
export const seriesKey = (k: number) => `s${k}`
export const smooth = d3Curve(curveMonotoneX) // monotone: smooth without inventing extrema between points
export const step = d3Curve(curveStep)
export const nonNull = (r: Row) => r.v !== null
export const rowKey = (r: Row) => `${r.i}:${r.k}`

export function toRows(block: ChartBlock, keep: (k: number) => boolean = () => true): Row[] {
  const labels = block.labels ?? []
  return block.series.flatMap((s, k) =>
    keep(k)
      ? labels.map((x, i) => ({ i, x, k: seriesKey(k), name: s.name, v: s.values[i] ?? null, v2: s.values2?.[i] ?? null, d: s.display[i] ?? "—" }))
      : [],
  )
}

/** Series colours: s0..sN → --chart-1..6 (cycled). */
export function seriesColor(block: ChartBlock) {
  const domain = block.series.map((_, k) => seriesKey(k))
  return { domain, range: domain.map((_, k) => color(k)) }
}

export const seriesLegend = (block: ChartBlock): LegendItem[] =>
  block.series.length > 1 ? block.series.map((s, k) => ({ label: s.name, color: color(k) })) : []

/** Tooltip rows come straight from Python's `display` strings (one row per series, deduped across layered marks). */
export function tipContent<T extends Row>(points: readonly ChartPoint<T>[]): ChartTooltipContent {
  const seen = new Set<string>()
  const order = (p: ChartPoint<T>) => Number(p.datum.k.slice(1)) // series / slice index → stable spec order
  const rows = points.toSorted((a, b) => order(a) - order(b)).flatMap((p) => {
    if (seen.has(p.datum.k)) return []
    seen.add(p.datum.k)
    const main = { label: p.datum.name, value: p.datum.d, color: p.color }
    return p.datum.sub ? [main, { label: "of first", value: p.datum.sub }] : [main]
  })
  return { title: points[0]?.datum.x || undefined, rows }
}
export const tip = { use: tooltip, content: tipContent<Row>, placement: "auto" } as const

export const bandScale = (labels: readonly string[], padding = 0.2) => scaleBand<string>().domain(labels).padding(padding)
export const pointScale = (labels: readonly string[]) => scalePoint<string>().domain(labels).padding(0.5)

// fontSize must match index.css `.ts-chart__axes text { font-size: 12px }` or auto-margins under-measure and clip labels.
const tickLabels = { fontSize: 12 }
export const categoryAxis = (n: number) => ({ line: false, ticks: { size: 0, padding: 8, format: clip(n) }, tickLabels })
// Value axes include 0 unless the spec says `zero: false`, so a 60→68% line isn't drawn as a cliff. Bars/areas already
// start at 0; lines and combos would otherwise take their range from the data alone.
export function zeroDomain(block: ChartBlock): [number, number] | undefined {
  if (block.zero === false) return undefined
  const vs = block.series.flatMap((s) => [...s.values, ...(s.values2 ?? [])]).filter((v): v is number => v !== null && Number.isFinite(v))
  if (!vs.length) return undefined
  const lo = Math.min(0, ...vs)
  const hi = Math.max(0, ...vs)
  return lo === hi ? undefined : (scaleLinear().domain([lo, hi]).nice().domain() as [number, number])
}

export const valueAxis = (format: string | null | undefined, opts: { domain?: [number, number] } = {}) => ({
  scale: opts.domain ? scaleLinear().domain(opts.domain) : scaleLinear,
  nice: !opts.domain,
  grid: true,
  axis: { line: false, ticks: { size: 0, format: tickFormat(format) }, tickLabels },
})

export function Legend({ items }: { items: readonly LegendItem[] }) {
  if (!items.length) return null
  return (
    <ul className="flex flex-wrap justify-center gap-x-4 gap-y-1 px-4 pt-2 text-[11px] text-muted-foreground">
      {items.map((it, i) => (
        <li key={i} className="flex min-w-0 items-center gap-1.5">
          <span aria-hidden className="size-2 shrink-0" style={{ background: it.color }} />
          <span className="truncate">{it.label}</span>
        </li>
      ))}
    </ul>
  )
}

/** Centre readout for donut-text / radial text. pointer-events-none keeps the chart hoverable underneath. */
export function Centre({ value, label }: { value: string; label?: string }) {
  return (
    <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
      <span className="text-xl font-semibold tabular-nums text-foreground">{value}</span>
      {label ? <span className="max-w-[40%] truncate tb-label text-[10px] text-muted-foreground">{label}</span> : null}
    </div>
  )
}

export function Plot({ children, overlay, legend = [] }: { children: ReactNode; overlay?: ReactNode; legend?: readonly LegendItem[] }) {
  return (
    <div>
      <div className="relative">
        {children}
        {overlay}
      </div>
      <Legend items={legend} />
    </div>
  )
}

/** Look up a variant without casting; undefined → caller renders the unknown-variant alert. */
export function pick<T>(variants: Readonly<Record<string, T>>, name: string): T | undefined {
  return Object.hasOwn(variants, name) ? variants[name] : undefined
}
