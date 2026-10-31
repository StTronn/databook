import { createContext, useCallback, useContext, useMemo, type ReactNode } from "react"
import { useLive } from "@/app/live-context"
import { useApi } from "@/hooks/use-schema"
import type { Comment } from "@/types"

type Comments = {
  enabled: boolean
  forBlock: (block: string) => Comment[]
  add: (block: string, anchor: string | undefined, text: string) => Promise<void>
  resolve: (id: number, note?: string) => Promise<void>
}

const NONE: Comment[] = []
const CommentsContext = createContext<Comments>({ enabled: false, forBlock: () => NONE, add: async () => {}, resolve: async () => {} })
export const useComments = () => useContext(CommentsContext)

async function post(url: string, body: unknown) {
  const r = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) })
  if (!r.ok) throw new Error((await r.json().catch(() => null))?.error ?? `HTTP ${r.status}`)
}

/** One fetch of the notebook's comments per live version (the server bumps it when comments.json changes). */
export function CommentsProvider({ notebook, children }: { notebook: string | null; children: ReactNode }) {
  const { live } = useLive()
  const { data } = useApi<{ comments: Comment[] }>(live && notebook ? `/api/comments?nb=${encodeURIComponent(notebook)}` : null)
  const byBlock = useMemo(() => {
    const m = new Map<string, Comment[]>()
    for (const c of data?.comments ?? []) if (!c.orphan) m.set(c.block, [...(m.get(c.block) ?? []), c])
    return m
  }, [data])
  const add = useCallback(
    (block: string, anchor: string | undefined, text: string) => post("/api/comments", { notebook, block, anchor, text }),
    [notebook],
  )
  const resolve = useCallback((id: number, note?: string) => post("/api/comments/resolve", { id, note }), [])
  const value = useMemo(
    () => ({ enabled: live && !!notebook, forBlock: (b: string) => byBlock.get(b) ?? NONE, add, resolve }),
    [live, notebook, byBlock, add, resolve],
  )
  return <CommentsContext value={value}>{children}</CommentsContext>
}
