import { AlertCircleIcon } from "lucide-react"
import { useState, type FormEvent } from "react"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectSeparator, SelectTrigger, SelectValue } from "@/components/ui/select"

// Radix Select values can't be "": sentinels (":" is not valid in notebook names, so no clash with real folders)
const ROOT = ":root"
const NEW = ":new"
const BLANK = ":blank"

// Mirrors databook/project.py (KEY, schema_for) so bad names never reach the server; it still re-validates.
const KEY = /^[A-Za-z0-9_-]+(?:\/[A-Za-z0-9_-]+)*$/
const schemaFor = (key: string) => "nb_" + key.toLowerCase().replace(/[^a-z0-9]+/g, "_")

export function nameProblem(key: string, existing: string[]): string | null {
  if (!KEY.test(key)) return "Use letters, digits, - and _ (folders with /), e.g. growth/retention"
  if (existing.includes(key)) return `Notebook ${key} already exists`
  const clash = existing.find((k) => schemaFor(k) === schemaFor(key))
  return clash ? `Too similar to ${clash} (differs only in case or punctuation)` : null
}

type Props = {
  open: boolean
  onOpenChange: (open: boolean) => void
  folders: string[]
  existing: string[]
  templates: string[]
  /** called with the created key after the POST succeeded */
  onCreated: (key: string) => Promise<void> | void
}

/** POST /api/notebooks {name: "<folder>/<name>", template?}; server errors (400) are shown inline. */
export function NewNotebookDialog({ open, onOpenChange, folders, existing, templates, onCreated }: Props) {
  const [folder, setFolder] = useState(ROOT)
  const [newFolder, setNewFolder] = useState("")
  const [name, setName] = useState("")
  const [template, setTemplate] = useState(BLANK)
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)

  const dir = (folder === NEW ? newFolder : folder === ROOT ? "" : folder).trim().replace(/^\/+|\/+$/g, "")
  const leaf = name.trim().replace(/^\/+|\/+$/g, "")
  const full = dir && leaf ? `${dir}/${leaf}` : leaf
  const problem = leaf ? nameProblem(full, existing) : null

  // closing resets the form, so every open starts clean; no closing while the POST is in flight
  const change = (o: boolean) => {
    if (pending) return
    if (!o) {
      setFolder(ROOT)
      setNewFolder("")
      setName("")
      setTemplate(BLANK)
      setError(null)
    }
    onOpenChange(o)
  }

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    if (!leaf || problem || pending) return
    setPending(true)
    setError(null)
    try {
      const r = await fetch("/api/notebooks", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(template === BLANK ? { name: full } : { name: full, template }),
      })
      const body = await r.json().catch(() => null)
      if (!r.ok || typeof body?.key !== "string") throw new Error(body?.error ?? `HTTP ${r.status}`)
      await onCreated(body.key)
      setPending(false)
      change(false)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
      setPending(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={change}>
      <DialogContent className="sm:max-w-md">
        <form onSubmit={submit} className="flex flex-col gap-4">
          <DialogHeader>
            <DialogTitle>New notebook</DialogTitle>
            <DialogDescription>Creates notebooks/{full || "<name>"}.md and runs it.</DialogDescription>
          </DialogHeader>
          <div className="flex flex-col gap-2">
            <Label htmlFor="nb-folder">Folder</Label>
            <Select value={folder} onValueChange={setFolder} disabled={pending}>
              <SelectTrigger id="nb-folder" className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={ROOT}>(root)</SelectItem>
                {folders.map((f) => (
                  <SelectItem key={f} value={f}>
                    {f}
                  </SelectItem>
                ))}
                <SelectSeparator />
                <SelectItem value={NEW}>New folder…</SelectItem>
              </SelectContent>
            </Select>
            {folder === NEW ? (
              <Input
                aria-label="New folder path"
                placeholder="e.g. growth/cohorts"
                value={newFolder}
                onChange={(e) => setNewFolder(e.target.value)}
                disabled={pending}
                autoFocus
              />
            ) : null}
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="nb-name">Name</Label>
            <Input id="nb-name" placeholder="e.g. retention" value={name} onChange={(e) => setName(e.target.value)} disabled={pending} autoComplete="off" />
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="nb-template">Template</Label>
            <Select value={template} onValueChange={setTemplate} disabled={pending}>
              <SelectTrigger id="nb-template" className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={BLANK}>blank</SelectItem>
                {templates.map((t) => (
                  <SelectItem key={t} value={t}>
                    {t}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          {problem || error ? (
            <Alert variant="destructive">
              <AlertCircleIcon />
              <AlertDescription className="break-words">{problem ?? error}</AlertDescription>
            </Alert>
          ) : null}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => change(false)} disabled={pending}>
              Cancel
            </Button>
            <Button type="submit" disabled={!leaf || !!problem || pending}>
              {pending ? "Creating…" : "Create"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
