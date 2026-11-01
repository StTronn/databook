import { CheckIcon } from "lucide-react"
import { useState, type FormEvent } from "react"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { useComments } from "@/hooks/use-comments"

/** Review thread for one block: open/resolved comments + a box to add one. The agent picks them up with
 *  `tracebook comments` and answers with `tracebook comments resolve <id> --note …`. */
export function BlockComments({ block, anchor }: { block: string; anchor?: string }) {
  const { forBlock, add, resolve } = useComments()
  const [text, setText] = useState("")
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const items = forBlock(block)

  const run = async (fn: () => Promise<void>, after?: () => void) => {
    setPending(true)
    setError(null)
    try {
      await fn()
      after?.()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setPending(false)
    }
  }
  const submit = (e: FormEvent) => {
    e.preventDefault()
    if (text.trim()) void run(() => add(block, anchor, text), () => setText(""))
  }

  return (
    <div className="flex flex-col gap-2">
      {items.map((c) => (
        <div key={c.id} className="flex flex-col gap-1 border p-2 text-xs">
          <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
            <span>#{c.id}</span>
            <Badge variant={c.status === "open" ? "secondary" : "outline"} className="tb-label">
              {c.status}
            </Badge>
            {c.state === "outdated" ? (
              <Badge variant="outline" className="tb-label">
                changed since
              </Badge>
            ) : null}
            {c.status === "open" ? (
              <Button variant="ghost" size="xs" className="ml-auto text-muted-foreground" disabled={pending} onClick={() => void run(() => resolve(c.id))}>
                <CheckIcon />
                resolve
              </Button>
            ) : null}
          </div>
          <p className="break-words whitespace-pre-wrap">{c.text}</p>
          {c.state === "outdated" && c.seen ? (
            <p className="break-words text-muted-foreground">
              was “{c.seen.brief}” · now “{c.now}”
            </p>
          ) : null}
          {c.resolution ? <p className="break-words whitespace-pre-wrap text-muted-foreground">→ {c.resolution}</p> : null}
        </div>
      ))}
      <form onSubmit={submit} className="flex flex-col gap-2">
        <Textarea
          aria-label="Comment for the agent"
          placeholder="Ask for a change; the agent sees it in `tracebook comments`"
          value={text}
          onChange={(e) => setText(e.target.value)}
          disabled={pending}
          rows={3}
          maxLength={4000}
        />
        {error ? (
          <Alert variant="destructive">
            <AlertDescription className="break-words">{error}</AlertDescription>
          </Alert>
        ) : null}
        <Button type="submit" size="sm" className="self-end" disabled={pending || !text.trim()}>
          {pending ? "Sending…" : "Comment"}
        </Button>
      </form>
    </div>
  )
}
