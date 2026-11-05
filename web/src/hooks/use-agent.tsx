import { createContext, use, useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react"
import { useNotebook } from "@/components/notebook/notebook-context"
import { blockLabel } from "@/lib/notebook"
import type { Block } from "@/types"

// In-viewer agent: select something (or @-mention blocks) → ask anything. The dev server queues the request for the
// user's OPEN coding-agent session (Claude Code via `databook inbox --wait`, pi via its extension, Codex via
// `codex queue`); the agent answers or edits the notebook and reports with `databook reply`. This hook posts requests
// and polls the thread (/api/agent/thread); the server computes what changed and handles undo (databook/agent.py).

/** A block (or quoted selection) attached to a request. */
export type AgentContext = { blockId?: string; label: string; quote?: string }
export type AgentChange = { blockId: string | null; label: string; detail: string; change: string }
export type AgentStep = { text: string; done: boolean }
export type AgentMsg =
  | { id: string; role: "user"; text: string; contexts: AgentContext[] }
  | { id: string; role: "agent"; steps: AgentStep[]; text?: string; changes?: AgentChange[]; error?: string | null;
      status: "running" | "done" | "stopped" | "undone" | "failed"; checkOk?: boolean | null }
export type Composer = { context?: AgentContext; x: number; y: number }
export type Listener = { state: "listening" | "busy" | "offline"; agent?: string; session?: string | null }

type ServerReq = {
  id: string; text: string; status: "pending" | "claimed" | "done" | "failed" | "stopped"; undone: boolean
  contexts: { blockId?: string; label: string; quote?: string | null }[]
  events: { t: string; text: string }[]; answer: string | null; error: string | null
  changes: AgentChange[]; check_ok?: boolean | null
}

type AgentCtx = {
  thread: AgentMsg[]
  running: boolean
  listener: Listener
  error: string | null
  composer: Composer | null
  openComposer: (c: Composer) => void
  closeComposer: () => void
  send: (text: string, contexts: AgentContext[]) => void
  stop: () => void
  undo: (msgId: string) => void
  /** blocks the last change touched; the notebook rings them for a few seconds */
  highlighted: ReadonlySet<string>
  contextFor: (blockId: string, quote?: string) => AgentContext
}

const Ctx = createContext<AgentCtx | null>(null)
export const useAgent = () => {
  const c = use(Ctx)
  if (!c) throw new Error("useAgent outside AgentProvider")
  return c
}
/** null outside the provider (exported reports): callers hide agent UI. */
export const useAgentMaybe = () => use(Ctx)

export function labelOf(b: Block): string {
  if (b.kind === "kpi") return b.items[0]?.label ?? b.id
  if (b.kind === "md") return (b.text.replace(/<[^>]+>/g, "").split("\n").find((l) => l.trim()) ?? b.id).replace(/^#+\s*/, "").slice(0, 60)
  return blockLabel(b)
}

const token = () => (window as unknown as { __TB_TOKEN__?: string }).__TB_TOKEN__ ?? ""

async function post(path: string, body: unknown) {
  const r = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json", "X-Databook-Token": token() }, body: JSON.stringify(body) })
  const d = await r.json().catch(() => null)
  if (!r.ok) throw new Error(d?.error ?? `HTTP ${r.status}`)
  return d
}

function toMessages(reqs: ServerReq[], listener: Listener): AgentMsg[] {
  const out: AgentMsg[] = []
  for (const r of reqs) {
    out.push({ id: r.id + ":u", role: "user", text: r.text, contexts: r.contexts.map((c) => ({ blockId: c.blockId, label: c.label, quote: c.quote ?? undefined })) })
    const open = r.status === "pending" || r.status === "claimed"
    const steps: AgentStep[] = r.events.filter((e) => e.t === "step").map((e) => ({ text: e.text, done: true }))
    if (r.status === "pending")
      steps.unshift({ text: listener.state === "offline" ? "Waiting for an agent session to connect (see below)" : `Queued for ${listener.agent ?? "your agent"}`, done: false })
    else if (open) steps.push({ text: "Working…", done: false })
    out.push({
      id: r.id, role: "agent", steps, text: r.answer ?? undefined, changes: r.changes, error: r.error, checkOk: r.check_ok,
      status: open ? "running" : r.undone ? "undone" : (r.status as "done" | "failed" | "stopped"),
    })
  }
  return out
}

export function AgentProvider({ onActivity, children }: { onActivity: () => void; children: ReactNode }) {
  const { doc, byId } = useNotebook()
  const nb = doc.notebook
  const [reqs, setReqs] = useState<ServerReq[]>([])
  const [listener, setListener] = useState<Listener>({ state: "offline" })
  const [error, setError] = useState<string | null>(null)
  const [composer, setComposer] = useState<Composer | null>(null)
  const [highlighted, setHighlighted] = useState<ReadonlySet<string>>(() => new Set())
  const seenDone = useRef<Set<string> | null>(null)

  const refresh = useCallback(async () => {
    if (!nb) return
    try {
      const r = await fetch(`/api/agent/thread?nb=${encodeURIComponent(nb)}`, { cache: "no-store" })
      if (!r.ok) return
      const d: { listener: Listener; requests: ServerReq[] } = await r.json()
      setReqs(d.requests)
      setListener(d.listener)
      // first load: don't replay old highlights; later: ring blocks of requests that just finished with changes
      const done = new Set(d.requests.filter((x) => x.status === "done").map((x) => x.id))
      if (seenDone.current) {
        const fresh = d.requests.filter((x) => done.has(x.id) && !seenDone.current!.has(x.id) && x.changes.length)
        const ids = fresh.flatMap((x) => x.changes.map((c) => c.blockId).filter((b): b is string => !!b))
        if (ids.length) {
          setHighlighted(new Set(ids))
          setTimeout(() => setHighlighted(new Set()), 4000)
        }
      }
      seenDone.current = done
    } catch {
      // dev server restarting: keep the last state
    }
  }, [nb])

  useEffect(() => { seenDone.current = null; setReqs([]); void refresh() }, [nb, refresh])
  const running = reqs.some((r) => r.status === "pending" || r.status === "claimed")
  useEffect(() => {
    const t = setInterval(() => void refresh(), running ? 1000 : 3000)
    return () => clearInterval(t)
  }, [refresh, running])

  const thread = useMemo(() => toMessages(reqs, listener), [reqs, listener])

  const contextFor = useCallback((blockId: string, quote?: string): AgentContext => {
    const b = byId.get(blockId)
    return { blockId, label: b ? labelOf(b) : blockId, quote }
  }, [byId])

  const act = useCallback(async (fn: () => Promise<unknown>) => {
    setError(null)
    try { await fn() } catch (e) { setError(e instanceof Error ? e.message : String(e)) }
    void refresh()
  }, [refresh])

  const send = useCallback((text: string, contexts: AgentContext[]) => {
    if (!text.trim() || running) return
    setComposer(null)
    onActivity()
    void act(() => post("/api/agent/requests", { notebook: nb, text, contexts }))
  }, [act, nb, onActivity, running])

  const stop = useCallback(() => {
    const open = reqs.find((r) => r.status === "pending" || r.status === "claimed")
    if (open) void act(() => post("/api/agent/stop", { id: open.id }))
  }, [act, reqs])

  const undo = useCallback((id: string) => void act(() => post("/api/agent/undo", { id })), [act])

  const value = useMemo(() => ({
    thread, running, listener, error, composer, openComposer: setComposer, closeComposer: () => setComposer(null),
    send, stop, undo, highlighted, contextFor,
  }), [thread, running, listener, error, composer, send, stop, undo, highlighted, contextFor])
  return <Ctx value={value}>{children}</Ctx>
}
