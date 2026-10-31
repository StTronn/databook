import { useEffect, useState } from "react"
import { useLive } from "@/app/live-context"
import type { SchemaTable } from "@/types"

type State<T> = { url: string | null; req: string | null; data: T | null; error: string | null }

/** GET `url` (JSON) once per (url, live version). Aborts on change/unmount, so a stale response never lands; on error
 *  keeps the last good data for the same url. 4xx/5xx bodies `{error}` become `error`. url=null or !live → idle. */
export function useApi<T>(url: string | null) {
  const { live, version } = useLive()
  const req = live && url !== null ? `${version}:${url}` : null
  const [s, set] = useState<State<T>>({ url: null, req: null, data: null, error: null })
  useEffect(() => {
    if (req === null || url === null) return
    const ctl = new AbortController()
    const keep = (p: State<T>) => (p.url === url ? p.data : null)
    fetch(url, { cache: "no-store", signal: ctl.signal })
      .then(async (r) => {
        const body = await r.json().catch(() => null)
        if (!r.ok) throw new Error(body?.error ?? `HTTP ${r.status}`)
        if (body === null) throw new Error("invalid JSON response")
        return body as T
      })
      .then(
        (data) => !ctl.signal.aborted && set({ url, req, data, error: null }),
        (e: unknown) => !ctl.signal.aborted && set((p) => ({ url, req, data: keep(p), error: e instanceof Error ? e.message : String(e) })),
      )
    return () => ctl.abort()
  }, [url, req])
  const same = s.url === url
  return { data: same ? s.data : null, error: same ? s.error : null, loading: req !== null && s.req !== req }
}

/** Imported + source tables of the dev-server workspace (`GET /api/schema`); refetches when the live version bumps.
 *  sourceErrors: sources that could not be attached (redacted message). */
export function useSchema() {
  const { data, error, loading } = useApi<{ tables: SchemaTable[]; sourceErrors?: Record<string, string> }>("/api/schema")
  return { tables: data?.tables ?? null, sourceErrors: data?.sourceErrors ?? {}, error, loading }
}
