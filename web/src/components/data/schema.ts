import type { SchemaTable } from "@/types"

/** `razorpay.payments` → group "razorpay", kind "payments"; plain imports (`file`, no dot) → group "files". */
export function sourceParts(source: string): { group: string; kind: string | null } {
  const i = source.indexOf(".")
  return i > 0 ? { group: source.slice(0, i), kind: source.slice(i + 1) || null } : { group: "files", kind: null }
}

export type TreeGroup = { group: string; tables: { table: SchemaTable; kind: string | null; columns: string[] }[] }

/** Filter by case-insensitive name match on table or column (column hits are listed), then group; groups A→Z with
 *  "files" last, tables A→Z. */
export function buildTree(tables: SchemaTable[], query: string): TreeGroup[] {
  const q = query.trim().toLowerCase()
  const groups = new Map<string, TreeGroup>()
  for (const table of tables) {
    const columns = q ? table.columns.filter((c) => c.name.toLowerCase().includes(q)).map((c) => c.name) : []
    if (q && !table.name.toLowerCase().includes(q) && columns.length === 0) continue
    const { group, kind } = sourceParts(table.source)
    const g = groups.get(group) ?? groups.set(group, { group, tables: [] }).get(group)!
    g.tables.push({ table, kind, columns })
  }
  const rank = (g: string) => (g === "files" ? 1 : 0)
  return [...groups.values()]
    .sort((a, b) => rank(a.group) - rank(b.group) || a.group.localeCompare(b.group))
    .map((g) => ({ ...g, tables: g.tables.toSorted((a, b) => a.table.name.localeCompare(b.table.name)) }))
}

export const count = (n: number) => n.toLocaleString("en-US")

/** DuckDB numeric types (right-aligned). Anchored so INTERVAL / POINT etc. don't match. */
export const isNumeric = (t: string) => /^(U?(TINY|SMALL|BIG|HUGE)?INT(EGER)?|DECIMAL|NUMERIC|DOUBLE|FLOAT|REAL|VARINT|BIGNUM)\b/i.test(t)

/** Types worth a note: exact decimals (money) and zoned timestamps. */
export function typeNote(t: string): string | null {
  if (/^(DECIMAL|NUMERIC)\b/i.test(t)) return "Exact decimal: money-safe arithmetic, no float rounding."
  if (/^(TIMESTAMPTZ|TIMESTAMP WITH TIME ZONE)$/i.test(t)) return "Zoned timestamp: an absolute instant, shown in the workspace timezone."
  return null
}

const RESERVED = new Set("all and any as asc by case create default desc distinct else end from group having in is join limit not null offset on or order select table then union user using when where with".split(" "))

const ident = (p: string) => (/^[a-z_][a-z0-9_]*$/.test(p) && !RESERVED.has(p) ? p : `"${p.replaceAll('"', '""')}"`)

/** `SELECT * FROM <name> LIMIT 100`, quoting each part unless it is a plain lowercase non-reserved name. Imported
 *  table names never contain dots, so a dot always separates source.schema.table. */
export const selectSql = (name: string) => `SELECT * FROM ${name.split(".").map(ident).join(".")} LIMIT 100`
