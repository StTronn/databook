import { AlertCircleIcon } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { AppHeader } from "@/app/app-header";
import { embedded } from "@/app/live-context";
import { TablePage } from "@/components/data/table-page";
import { Diagnostics } from "@/components/notebook/diagnostics";
import { Notebook } from "@/components/notebook/notebook";
import {
  NotebookProvider,
  useNotebook,
} from "@/components/notebook/notebook-context";
import { CommentsProvider } from "@/hooks/use-comments";
import { TraceDrawer } from "@/components/notebook/trace-drawer";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { entryLabel, StatusDot } from "@/components/workspace/notebook-tree";
import { RightPanel, type PanelTab } from "@/components/workspace/right-panel";
import { Sidebar } from "@/components/workspace/sidebar";
import { notebookHref, tableHref, useHashRoute } from "@/hooks/use-hash-route";
import { useMediaQuery } from "@/hooks/use-media-query";
import { useResults } from "@/hooks/use-results";
import { useViewMode } from "@/hooks/use-view-mode";
import { useWorkspace } from "@/hooks/use-workspace";
import { formatRanAt } from "@/lib/format";
import type { Doc, NotebookEntry } from "@/types";

// NotebookProvider stays mounted across routes (keeps the shell's DOM/state); this stands in when no doc is shown.
const NO_DOC: Doc = {
  notebook: "",
  path: "",
  title: "",
  meta: {},
  ranAt: "",
  timezone: "UTC",
  ok: true,
  blocks: [],
  diagnostics: [],
};

type Target = { nb: string; block: string };

/** After cross-route navigation (data browser → notebook cell): scroll once the target notebook's doc is rendered. */
function PendingScroll({
  target,
  done,
}: {
  target: Target | null;
  done: () => void;
}) {
  const { doc, scrollTo } = useNotebook();
  useEffect(() => {
    if (!target || doc.notebook !== target.nb) return;
    const id = requestAnimationFrame(() => {
      scrollTo(target.block);
      done();
    });
    return () => cancelAnimationFrame(id);
  }, [target, doc, scrollTo, done]);
  return null;
}

function NotebookList({ notebooks }: { notebooks: NotebookEntry[] }) {
  return (
    <ul className="flex flex-col border">
      {notebooks.map((n) => (
        <li key={n.key} className="border-b last:border-b-0">
          <Button
            asChild
            variant="ghost"
            className="w-full justify-start font-normal"
          >
            <a href={notebookHref(n.key)}>
              <span className="truncate">{entryLabel(n)}</span>
              <span className="truncate text-xs text-muted-foreground">
                {n.key}
              </span>
              <StatusDot nb={n} />
            </a>
          </Button>
        </li>
      ))}
    </ul>
  );
}

function Loading() {
  return (
    <div
      className="flex flex-col gap-3"
      aria-busy="true"
      aria-label="Loading results"
    >
      <Skeleton className="h-6 w-1/3" />
      <Skeleton className="h-4 w-full" />
      <Skeleton className="h-4 w-2/3" />
    </div>
  );
}

export function App() {
  const { route, navigate } = useHashRoute();
  const { ws, refresh } = useWorkspace();
  const lg = useMediaQuery("(min-width: 1024px)");
  const xl = useMediaQuery("(min-width: 1280px)");
  const [leftSheet, setLeftSheet] = useState(false);
  const [rightOpen, setRightOpen] = useState(true); // xl+ inline panel
  const [rightSheet, setRightSheet] = useState(false); // below xl
  const [tab, setTab] = useState<PanelTab>("outputs");
  const [pending, setPending] = useState<Target | null>(null);

  // Export: the embedded doc only. Dev: #/n/<key>, #/t/<table>, home = first notebook.
  const nbKey = embedded
    ? embedded.notebook || "notebook" // results written before Doc.notebook existed
    : route.kind === "notebook"
      ? route.key
      : route.kind === "home"
        ? (ws?.notebooks[0]?.key ?? null)
        : null;
  const table = !embedded && route.kind === "table" ? route.table : null;
  const unknown =
    !embedded &&
    nbKey !== null &&
    ws !== null &&
    !ws.notebooks.some((n) => n.key === nbKey);
  const { doc, loaded, error, live } = useResults(unknown ? null : nbKey);
  const [view, setView] = useViewMode(doc?.meta.view, live);

  useEffect(() => setPending((p) => (p && p.nb !== nbKey ? null : p)), [nbKey]);
  const clearPending = useCallback(() => setPending(null), []);
  const openBlock = useCallback(
    (nb: string, block: string) => {
      setPending({ nb, block });
      navigate(notebookHref(nb));
    },
    [navigate],
  );
  const onCreated = useCallback(
    async (key: string) => {
      await refresh().catch(() => {}); // the new key must be known before routing to it (else "unknown notebook")
      navigate(notebookHref(key));
    },
    [refresh, navigate],
  );

  const wsName = ws?.name || "workspace";
  const crumbs = table
    ? [wsName, "data", table]
    : nbKey
      ? [
          ...(embedded ? [] : [wsName]),
          ...nbKey.split("/").slice(0, -1),
          doc?.title ||
            ws?.notebooks.find((n) => n.key === nbKey)?.title ||
            nbKey,
        ]
      : [wsName];

  const banner = error ? (
    <Alert variant="destructive">
      <AlertCircleIcon />
      <AlertTitle>{doc ? "Showing last good run" : "Run failed"}</AlertTitle>
      <AlertDescription className="break-all">{error}</AlertDescription>
    </Alert>
  ) : null;

  let body;
  if (table) body = <TablePage table={table} onOpenBlock={openBlock} />;
  else if (unknown || (live && ws && !nbKey))
    body = (
      <div className="flex flex-col gap-4">
        <p className="text-muted-foreground">
          {unknown
            ? `No notebook “${nbKey}” in this workspace.`
            : "No notebooks yet — create one from the sidebar (+)."}
        </p>
        {ws?.notebooks.length ? (
          <NotebookList notebooks={ws.notebooks} />
        ) : null}
      </div>
    );
  else if (doc)
    body = (
      <>
        {banner}
        <div className="flex flex-col gap-1">
          <h1 className="tb-title">{doc.title}</h1>
          {doc.meta.description ? (
            <p className="text-xs text-muted-foreground">
              {doc.meta.description}
            </p>
          ) : null}
          <p className="text-[11px] tracking-wider text-muted-foreground">
            {formatRanAt(doc.ranAt, doc.timezone)} · {doc.timezone}
            {live ? " · live" : null}
          </p>
        </div>
        {view === "notebook" ? <Diagnostics /> : null}
        <Notebook />
      </>
    );
  else
    body = (
      <>
        {banner}
        {loaded && !error ? (
          <p className="text-muted-foreground">
            This notebook has not run yet.
          </p>
        ) : error ? null : (
          <Loading />
        )}
      </>
    );

  const sidebar = embedded ? (
    doc ? (
      <Sidebar
        ws={null}
        live={false}
        currentNotebook={nbKey}
        currentTable={null}
        hasDoc
        onOpenTable={() => {}}
        onCreated={async () => {}}
      />
    ) : null
  ) : (
    <Sidebar
      ws={ws}
      live={live}
      currentNotebook={nbKey}
      currentTable={table}
      hasDoc={!!doc && !table}
      onOpenTable={(t) => navigate(tableHref(t))}
      onCreated={onCreated}
      onNavigate={lg ? undefined : () => setLeftSheet(false)}
    />
  );
  const panel = (
    <RightPanel
      tab={tab}
      onTab={setTab}
      hasDoc={!!doc && !table}
      settings={ws?.settings ?? null}
    />
  );

  return (
    <NotebookProvider doc={doc && !table ? doc : NO_DOC} view={view}>
      <CommentsProvider notebook={doc && !table ? doc.notebook : null}>
        <div className="flex h-svh flex-col">
          <AppHeader
            crumbs={crumbs}
            doc={table ? null : doc}
            view={view}
            onView={setView}
            onMenu={lg || !sidebar ? undefined : () => setLeftSheet(true)}
            onPanel={() => (xl ? setRightOpen((o) => !o) : setRightSheet(true))}
          />
          <div className="flex min-h-0 flex-1">
            {lg && sidebar ? (
              <aside className="w-64 shrink-0 overflow-y-auto border-r">
                {sidebar}
              </aside>
            ) : null}
            <main
              key={table ? `t:${table}` : `n:${nbKey}`}
              className="min-w-0 flex-1 overflow-y-auto"
            >
              <div
                className={
                  table
                    ? "flex flex-col gap-6 px-4 py-6 sm:px-6"
                    : "mx-auto flex w-full max-w-4xl flex-col gap-6 px-4 py-6 sm:px-6"
                }
              >
                {body}
              </div>
            </main>
            {xl && rightOpen ? (
              <aside
                className="flex w-80 shrink-0 flex-col border-l"
                aria-label="Outputs and settings"
              >
                {panel}
              </aside>
            ) : null}
          </div>
        </div>
        {!lg && sidebar ? (
          <Sheet open={leftSheet} onOpenChange={setLeftSheet}>
            <SheetContent
              side="left"
              className="w-72 gap-0 overflow-y-auto p-0 pt-8"
            >
              <SheetHeader className="sr-only">
                <SheetTitle>Sidebar</SheetTitle>
                <SheetDescription>Notebooks, data and outline</SheetDescription>
              </SheetHeader>
              {sidebar}
            </SheetContent>
          </Sheet>
        ) : null}
        {!xl ? (
          <Sheet open={rightSheet} onOpenChange={setRightSheet}>
            <SheetContent side="right" className="w-80 gap-0 p-0 pt-10">
              <SheetHeader className="sr-only">
                <SheetTitle>Outputs and settings</SheetTitle>
                <SheetDescription>
                  Compute blocks of this notebook and workspace settings
                </SheetDescription>
              </SheetHeader>
              {panel}
            </SheetContent>
          </Sheet>
        ) : null}
        <TraceDrawer />
        <PendingScroll target={pending} done={clearPending} />
      </CommentsProvider>
    </NotebookProvider>
  );
}
