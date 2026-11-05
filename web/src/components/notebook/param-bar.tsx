import { useEffect, useMemo, useState } from "react"
import { useLive } from "@/app/live-context"
import { useNotebook } from "@/components/notebook/notebook-context"
import { Input } from "@/components/ui/input"
import type { Param } from "@/types"

/** Store a picked value; the dev server reruns the notebook and the viewer refetches. */
export async function pickParam(notebook: string, name: string, value: unknown) {
  const r = await fetch("/api/params", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ notebook, values: { [name]: value } }),
  })
  if (!r.ok) throw new Error((await r.json().catch(() => null))?.error ?? `HTTP ${r.status}`)
}

/** Option text shown in the picker: the label, plus the value when two options share a label. */
function choices(p: Param): Map<string, unknown> {
  const seen = new Map<string, number>()
  for (const [, l] of p.options) seen.set(l, (seen.get(l) ?? 0) + 1)
  return new Map(p.options.map(([v, l]) => [seen.get(l)! > 1 ? `${l} (${String(v)})` : l, v]))
}

function Picker({ p }: { p: Param }) {
  const { doc } = useNotebook()
  const opts = useMemo(() => choices(p), [p])
  const current = [...opts].find(([, v]) => String(v) === String(p.value))?.[0] ?? p.display
  const [text, setText] = useState(current)
  const [err, setErr] = useState<string | null>(null)
  useEffect(() => setText(current), [current])               // a rerun (or a table click) changed the value
  const listId = `tb-param-${p.name}`
  return (
    <label className="flex min-w-0 flex-1 flex-col gap-1 text-xs">
      <span className="tb-label text-muted-foreground">{p.label}</span>
      <Input
        list={listId}
        value={text}
        onFocus={(e) => e.currentTarget.select()}
        onChange={(e) => {
          const t = e.currentTarget.value
          setText(t)
          if (opts.has(t) && t !== current) pickParam(doc.notebook, p.name, opts.get(t)).then(() => setErr(null), (x) => setErr(String(x)))
        }}
        onKeyDown={(e) => {                                   // Enter: an exact id, or the one label starting with the text
          if (e.key !== "Enter") return
          const t = text.trim().toLowerCase()
          const hits = [...opts].filter(([l, v]) => String(v).toLowerCase() === t || l.toLowerCase() === t)
          const pre = hits.length ? hits : [...opts].filter(([l]) => l.toLowerCase().startsWith(t))
          if (pre.length !== 1) return setErr(pre.length ? `${pre.length} matches; keep typing` : "no such value")
          setText(pre[0][0])
          if (pre[0][0] !== current) pickParam(doc.notebook, p.name, pre[0][1]).then(() => setErr(null), (x) => setErr(String(x)))
          else setErr(null)
        }}
        onBlur={() => !opts.has(text) && setText(current)}
        className="h-8"
      />
      <datalist id={listId}>
        {[...opts.keys()].map((k) => <option key={k} value={k} />)}
      </datalist>
      {err ? <span className="text-destructive">{err}</span> : null}
      {p.truncated ? <span className="text-muted-foreground">Only the first {p.options.length.toLocaleString("en-US")} values are listed.</span> : null}
    </label>
  )
}

/** Parameter pickers above the notebook. Exported reports show the values they were built with. */
export function ParamBar() {
  const { doc } = useNotebook()
  const { live } = useLive()
  if (!doc.params?.length) return null
  return (
    <div id="tb-params" className="flex scroll-mt-4 flex-wrap gap-3 border p-3" style={{ borderRadius: "var(--radius)" }}>
      {doc.params.map((p) =>
        live ? <Picker key={p.name} p={p} /> : (
          <div key={p.name} className="flex flex-col gap-1 text-xs">
            <span className="tb-label text-muted-foreground">{p.label}</span>
            <span className="text-sm">{p.display}</span>
          </div>
        ),
      )}
    </div>
  )
}
