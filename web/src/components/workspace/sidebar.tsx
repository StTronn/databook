import { ChevronRightIcon, PlusIcon } from "lucide-react"
import { useMemo, useState, type ReactNode } from "react"
import { DataTree } from "@/components/data/data-tree"
import { Outline } from "@/components/notebook/outline"
import { Button } from "@/components/ui/button"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"
import { NewNotebookDialog } from "@/components/workspace/new-notebook-dialog"
import { buildTree, NotebookTree } from "@/components/workspace/notebook-tree"
import { cn } from "@/lib/utils"
import type { Workspace } from "@/types"

function Section({ label, action, children }: { label: string; action?: ReactNode; children: ReactNode }) {
  const [open, setOpen] = useState(true)
  return (
    <Collapsible open={open} onOpenChange={setOpen} className="flex flex-col gap-1">
      <div className="flex items-center gap-1">
        <CollapsibleTrigger asChild>
          <Button variant="ghost" size="xs" className="min-w-0 flex-1 justify-start tb-label text-muted-foreground">
            <ChevronRightIcon className={cn("transition-transform", open && "rotate-90")} />
            {label}
          </Button>
        </CollapsibleTrigger>
        {action}
      </div>
      <CollapsibleContent>{children}</CollapsibleContent>
    </Collapsible>
  )
}

type Props = {
  /** null in exported files: only the outline is shown */
  ws: Workspace | null
  live: boolean
  currentNotebook: string | null
  currentTable: string | null
  /** a notebook doc is shown (outline available) */
  hasDoc: boolean
  onOpenTable: (table: string) => void
  onCreated: (key: string) => Promise<void>
  /** after any navigation (closes the mobile sheet) */
  onNavigate?: () => void
}

/** Workspace sidebar: NOTEBOOKS (folder tree + new) · DATA (imported tables) · OUTLINE (current notebook). */
export function Sidebar({ ws, live, currentNotebook, currentTable, hasDoc, onOpenTable, onCreated, onNavigate }: Props) {
  const [creating, setCreating] = useState(false)
  const tree = useMemo(() => (ws ? buildTree(ws.notebooks) : null), [ws])
  return (
    <div className="flex flex-col gap-4 px-2 py-4">
      {live ? (
        <Section
          label="Notebooks"
          action={
            <Button variant="ghost" size="icon-xs" aria-label="New notebook" title="New notebook" onClick={() => setCreating(true)} disabled={!ws}>
              <PlusIcon />
            </Button>
          }
        >
          {tree ? (
            <NotebookTree root={tree.root} current={currentNotebook} onNavigate={onNavigate} />
          ) : (
            <p className="px-2 text-xs text-muted-foreground">Loading…</p>
          )}
        </Section>
      ) : null}
      {live ? (
        <Section label="Data">
          <DataTree
            selected={currentTable}
            onOpen={(t) => {
              onOpenTable(t)
              onNavigate?.()
            }}
          />
        </Section>
      ) : null}
      {hasDoc ? (
        <Section label="Outline">
          {/* outline buttons scroll the notebook: close the mobile sheet so the target is visible */}
          <div onClick={(e) => (e.target as Element).closest("button") && onNavigate?.()}>
            <Outline />
          </div>
        </Section>
      ) : null}
      {ws && tree ? (
        <NewNotebookDialog
          open={creating}
          onOpenChange={setCreating}
          folders={tree.folders}
          existing={ws.notebooks.map((n) => n.key)}
          templates={ws.templates}
          onCreated={async (key) => {
            await onCreated(key)
            onNavigate?.()
          }}
        />
      ) : null}
    </div>
  )
}
