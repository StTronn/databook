import { CheckIcon, CircleIcon, LoaderCircleIcon, PlusIcon, Undo2Icon } from "lucide-react"
import { useEffect, useMemo, useRef } from "react"
import { ContextChip, PromptBox } from "@/components/agent/prompt-box"
import { useNotebook } from "@/components/notebook/notebook-context"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { useAgent, type AgentMsg, type Listener } from "@/hooks/use-agent"
import { renderMarkdown } from "@/lib/markdown"
import { cn } from "@/lib/utils"

/** Agent answer: sanitized markdown (like prose); `@block_id` mentions of this notebook's blocks scroll to the block. */
function Answer({ text, struck }: { text: string; struck: boolean }) {
  const { byId, scrollTo } = useNotebook()
  const html = useMemo(() => renderMarkdown(text.replace(/@([A-Za-z_][A-Za-z0-9_]*)/g, (m, id: string) =>
    byId.has(id) ? `<span class="tb-ref" data-ref="${id}" tabindex="0">@${id}</span>` : m)), [text, byId])
  return (
    <div
      className={cn("tb-prose prose prose-sm max-w-none", struck && "line-through opacity-60")}
      onClick={(e) => {
        const id = (e.target as Element).closest?.(".tb-ref[data-ref]")?.getAttribute("data-ref")
        if (id) scrollTo(id)
      }}
      dangerouslySetInnerHTML={{ __html: html }}
    />
  )
}

function AgentReply({ m }: { m: Extract<AgentMsg, { role: "agent" }> }) {
  const { undo } = useAgent()
  const { scrollTo } = useNotebook()
  return (
    <div className="flex flex-col gap-2">
      <ul className="flex flex-col gap-1">
        {m.steps.map((s, i) => (
          <li key={i} className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
            {s.done ? <CheckIcon className="size-3 shrink-0 text-success" /> : <LoaderCircleIcon className="size-3 shrink-0 animate-spin" />}
            {s.text}
          </li>
        ))}
      </ul>
      {m.status === "stopped" ? <p className="text-xs text-muted-foreground">Stopped.</p> : null}
      {m.error ? <p className="text-xs text-destructive">{m.error}</p> : null}
      {m.text ? <Answer text={m.text} struck={m.status === "undone"} /> : null}
      {m.checkOk === false ? <p className="text-xs text-destructive">databook check reports errors after this change.</p> : null}
      {m.changes?.length ? (
        <div className="flex flex-col gap-1.5 border p-2" style={{ borderRadius: "var(--radius)" }}>
          <div className="flex items-center gap-2">
            <span className="tb-label text-muted-foreground">What changed · {m.changes.length}</span>
            {m.status === "undone" ? (
              <Badge variant="outline" className="ml-auto">undone</Badge>
            ) : (
              <Button variant="ghost" size="xs" className="ml-auto" onClick={() => undo(m.id)}>
                <Undo2Icon /> Undo
              </Button>
            )}
          </div>
          {m.changes.map((c, i) => (
            <button key={c.blockId ?? c.label + i} type="button" disabled={!c.blockId} onClick={() => c.blockId && scrollTo(c.blockId)}
              className="flex flex-col items-start gap-0.5 px-1 py-1 text-left text-xs enabled:hover:bg-accent">
              <span className="font-medium">@{c.label}</span>
              <span className="break-all text-muted-foreground">{c.detail}</span>
            </button>
          ))}
        </div>
      ) : null}
    </div>
  )
}

function Status({ l }: { l: Listener }) {
  const name = { claude: "Claude Code", codex: "Codex", pi: "pi", opencode: "OpenCode" }[l.agent ?? ""] ?? l.agent ?? "agent"
  if (l.state === "offline")
    return (
      <div className="mb-3 flex flex-col gap-1 border border-dashed px-2 py-1.5 text-[11px] text-muted-foreground">
        <span className="flex items-center gap-1.5"><CircleIcon className="size-2.5" /> No agent connected</span>
        <span>
          In your Claude Code / Codex / pi session in this folder, ask: <em>“listen for databook viewer requests”</em>. Claude Code then runs
          <code className="mx-1">databook inbox --wait</code>in the background; pi does it via its extension.
        </span>
      </div>
    )
  return (
    <p className="mb-3 flex items-center gap-1.5 text-[11px] text-muted-foreground">
      <CircleIcon className={cn("size-2.5", l.state === "listening" ? "fill-success text-success" : "fill-warning text-warning")} />
      {name} {l.state === "listening" ? "connected" : "busy"}{l.session ? ` · ${l.session.slice(0, 8)}` : ""}
    </p>
  )
}

/** Agent tab: one thread per notebook. Requests go to your open agent session; follow-ups typed below. */
export function AgentPanel() {
  const { thread, running, send, stop, listener, error } = useAgent()
  const end = useRef<HTMLDivElement>(null)
  useEffect(() => {
    end.current?.scrollIntoView({ block: "end" })
  }, [thread])
  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="min-h-0 flex-1 overflow-y-auto px-3 py-3">
        <Status l={listener} />
        {thread.length === 0 ? (
          <p className="text-xs text-muted-foreground">
            Select text, use a block's <PlusIcon className="inline size-3" /> button (⌘K), or type @ below to attach blocks; then ask about them or ask for a change.
          </p>
        ) : (
          <div className="flex flex-col gap-4">
            {thread.map((m) =>
              m.role === "user" ? (
                <div key={m.id} className="flex flex-col items-end gap-1">
                  {m.contexts.length ? <div className="flex flex-wrap justify-end gap-1">{m.contexts.map((c, i) => <ContextChip key={i} ctx={c} />)}</div> : null}
                  <div className="max-w-[90%] bg-secondary px-2.5 py-1.5 text-sm whitespace-pre-wrap" style={{ borderRadius: "var(--radius)" }}>{m.text}</div>
                </div>
              ) : (
                <AgentReply key={m.id} m={m} />
              ),
            )}
          </div>
        )}
        {error ? (
          <Alert variant="destructive" className="mt-3"><AlertDescription className="break-words">{error}</AlertDescription></Alert>
        ) : null}
        <div ref={end} />
      </div>
      <div className="border-t p-2">
        <PromptBox placeholder="Ask anything · @ to attach a block" running={running} onStop={stop} onSubmit={send} />
      </div>
    </div>
  )
}
