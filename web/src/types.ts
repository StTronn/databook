// Shape of .databook/results.json (written by databook/run.py). Keep in sync with run.py `_render` / `_chart`.
export type Diagnostic = { line: number; code: string; message: string; severity: "error" | "warning"; block?: string | null }
export type Column = { name: string; type: string }
// title: from ```sql id "Title" (null if absent); usedBy: ids of blocks that read this one
// reads: imported tables this block reads (data browser "used by")
// anchor: stable identity across runs (databook/core/anchors.py); comments attach to it, not to the id
type Base = { id: string; anchor?: string; line: number; deps: string[]; reads: string[]; usedBy: string[]; title?: string | null; error?: string }
export type SheetCell = { a: string; v: unknown; f: string | null; fmt: string | null; d: string }
export type ComputeBlock = Base & {
  kind: "sql" | "python" | "sheet"
  code: string
  status: "ok" | "error" | "skipped"
  columns?: Column[]
  rows?: unknown[][]
  display?: string[][]
  rowCount?: number
  truncated?: boolean
  file?: string
  outputs?: string[] // python block returning {name: DataFrame}: tables `<id>__<name>`
  grid?: { sheet: string; range: string; rows: SheetCell[][] } | null
}
export type MdBlock = Base & { kind: "md"; text: string }
export type KpiItem = { label: string; value: string; ref?: string; compareRef?: string; delta?: number; deltaText?: string; error?: string }
export type KpiBlock = Base & { kind: "kpi"; items: KpiItem[] }
export type TableBlock = Base & {
  kind: "table"; data: string; columns: string[]; display: string[][]; numeric: boolean[]; rowCount: number; truncated: boolean
  link?: { column: string; param: string; values: unknown[] } // clicking a cell of `column` picks values[row] for `param`
}
// combo series carry `mark`; band marks carry values (low) + values2 (high); display = Python-formatted text per row
export type Series = { name: string; mark?: "bar" | "line" | "dot" | "area" | "band"; values: (number | null)[]; values2?: (number | null)[]; display: string[] }
export type ChartBlock = Base & {
  kind: "chart"
  data: string
  type: "bar" | "line" | "area" | "pie" | "funnel" | "radial" | "combo"
  variant: string
  title?: string | null
  description?: string | null
  x?: string | null
  y: string[]
  format?: string | null
  labels?: string[]
  series: Series[]
  total?: string
  share?: string[]
  max?: number
  zero?: boolean // false = y axis fits the data instead of starting at 0 (line/combo)
}
export type Block = MdBlock | ComputeBlock | KpiBlock | TableBlock | ChartBlock
// Notebook parameter (frontmatter `params:`): options are [value, label] from the `from` block; value = the one used
export type Param = { name: string; label: string; value: unknown; display: string; options: [unknown, string][]; truncated: boolean }
export type Doc = {
  notebook: string // key, e.g. "growth/cohorts"
  path: string // file relative to the workspace, e.g. "notebooks/growth/cohorts.md" (use in copy-ref)
  title: string
  meta: { title?: string; description?: string; theme?: string; view?: "report" | "notebook" }
  ranAt: string
  timezone: string
  ok: boolean
  params?: Param[]
  blocks: Block[]
  diagnostics: Diagnostic[]
}

// ── dev-server workspace API (databook/src/databook/workspace.py). Not available in exported files. ──
export type NotebookEntry = {
  key: string; path: string; title: string; ran: boolean; ok: boolean; errors: number; warnings: number; ranAt: string | null
}
export type Settings = {
  timezone: string
  python: string
  engines: Record<string, string | null>
  packs: { name: string; timezone: string | null }[]
  pythonBlockNames: string[]
  packages: { name: string; version: string }[]
}
export type Workspace = { name: string; timezone: string; notebooks: NotebookEntry[]; templates: string[]; settings: Settings }
export type SchemaColumn = { name: string; type: string; source?: string | null; values?: string[] } // values: all distinct when ≤ 10
export type SchemaTable = {
  // source tables (`shop.sales.orders`, source "shop.postgres"): readOnly, rows null (never counted remotely)
  name: string; source: string; rows: number | null; files: string[]; columns: SchemaColumn[]; usedBy: { notebook: string; block: string }[]
  readOnly?: boolean
}
export type Preview = { table: string; columns: Column[]; rows: unknown[][]; display: string[][]; rowCount: number | null; truncated: boolean }

// Review comments (GET/POST /api/comments, dev only); the agent resolves them with `databook comments resolve`.
export type Comment = {
  id: number; notebook: string; path: string; block: string; line: number; text: string
  status: "open" | "resolved"; created: string; resolution: string | null; resolved: string | null
  // outdated: block changed since the comment (seen = then, now = today); orphan: block gone (never shown on another block)
  anchor?: string; state: "attached" | "outdated" | "orphan"; orphan: boolean; now?: string; seen?: { brief: string; ranAt: string | null }
}
