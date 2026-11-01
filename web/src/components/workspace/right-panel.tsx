import { SearchIcon } from "lucide-react"
import { useDeferredValue, useState, type ReactNode } from "react"
import { useNotebook } from "@/components/notebook/notebook-context"
import { KindBadge, StatusBadge } from "@/components/notebook/status-badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { blockLabel, isCompute, plural } from "@/lib/notebook"
import type { Settings } from "@/types"

export type PanelTab = "outputs" | "settings"

const label = "tb-label text-muted-foreground"

/** Variable explorer: every compute block of the current doc; click → trace drawer. */
function Outputs() {
  const { doc, openTrace } = useNotebook()
  const blocks = doc.blocks.filter(isCompute)
  if (!blocks.length) return <p className="px-3 py-4 text-xs text-muted-foreground">No sql/python/sheet blocks.</p>
  return (
    <ul className="flex flex-col py-2">
      {blocks.map((b) => (
        <li key={b.id}>
          <Button
            variant="ghost"
            className="h-auto w-full flex-col items-stretch gap-1 px-3 py-2 text-left font-normal whitespace-normal"
            onClick={() => openTrace(b.id)}
            title={`@${b.id}`}
          >
            <span className="flex min-w-0 items-center gap-2">
              <span className="min-w-0 flex-1 truncate text-xs font-medium">{blockLabel(b)}</span>
              <KindBadge kind={b.kind} />
              <StatusBadge status={b.status} />
            </span>
            <span className="text-[11px] text-muted-foreground">
              {b.rowCount != null ? plural(b.rowCount, "row") : "—"} · {plural(b.columns?.length ?? 0, "col")} · → used by {b.usedBy.length}
            </span>
          </Button>
        </li>
      ))}
    </ul>
  )
}

function Group({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="flex flex-col gap-1.5">
      <h3 className={label}>{title}</h3>
      {children}
    </section>
  )
}

function Row({ k, v }: { k: string; v: ReactNode }) {
  return (
    <div className="flex min-w-0 items-baseline gap-2 text-xs">
      <span className="min-w-0 truncate">{k}</span>
      <span className="ml-auto shrink-0 text-muted-foreground">{v}</span>
    </div>
  )
}

/** Read-only workspace settings (dev server only). */
function SettingsView({ s }: { s: Settings }) {
  const [query, setQuery] = useState("")
  const q = useDeferredValue(query.trim().toLowerCase())
  const pkgs = q ? s.packages.filter((p) => p.name.toLowerCase().includes(q)) : s.packages
  return (
    <div className="flex flex-col gap-5 px-3 py-4">
      <Group title="Runtime">
        <Row k="timezone" v={s.timezone} />
        <Row k="python" v={s.python} />
      </Group>
      <Group title="Engines">
        {Object.entries(s.engines).map(([k, v]) => (
          <Row key={k} k={k} v={v ?? "—"} />
        ))}
      </Group>
      <Group title="Packs">
        {s.packs.length ? s.packs.map((p) => <Row key={p.name} k={p.name} v={p.timezone ?? "—"} />) : <span className="text-xs text-muted-foreground">—</span>}
      </Group>
      <Group title="Python block namespace">
        <div className="flex flex-wrap gap-1">
          {s.pythonBlockNames.map((n) => (
            <code key={n} className="border px-1.5 py-0.5 text-[11px]">
              {n}
            </code>
          ))}
        </div>
      </Group>
      <Group title={`Installed packages · ${s.packages.length}`}>
        <div className="relative">
          <SearchIcon className="pointer-events-none absolute top-1/2 left-2 size-3.5 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Filter packages"
            aria-label="Filter packages"
            className="h-8 pl-7 text-xs"
          />
        </div>
        {pkgs.length ? pkgs.map((p) => <Row key={p.name} k={p.name} v={p.version} />) : <span className="text-xs text-muted-foreground">No match.</span>}
      </Group>
    </div>
  )
}

type Props = { tab: PanelTab; onTab: (t: PanelTab) => void; hasDoc: boolean; settings: Settings | null }

/** Right panel: OUTPUTS (current notebook's compute blocks) | SETTINGS (workspace, dev only). */
export function RightPanel({ tab, onTab, hasDoc, settings }: Props) {
  const value = settings ? tab : "outputs"
  return (
    <Tabs value={value} onValueChange={(v) => onTab(v as PanelTab)} className="h-full min-h-0 gap-0">
      <TabsList variant="line" className="h-10 w-full shrink-0 justify-start rounded-none border-b px-2">
        <TabsTrigger value="outputs" className="tb-label flex-none">
          Outputs
        </TabsTrigger>
        {settings ? (
          <TabsTrigger value="settings" className="tb-label flex-none">
            Settings
          </TabsTrigger>
        ) : null}
      </TabsList>
      <TabsContent value="outputs" className="min-h-0 overflow-y-auto">
        {hasDoc ? <Outputs /> : <p className="px-3 py-4 text-xs text-muted-foreground">Open a notebook to see its outputs.</p>}
      </TabsContent>
      {settings ? (
        <TabsContent value="settings" className="min-h-0 overflow-y-auto">
          <SettingsView s={settings} />
        </TabsContent>
      ) : null}
    </Tabs>
  )
}
