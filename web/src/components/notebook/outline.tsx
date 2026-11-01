import { useNotebook } from "@/components/notebook/notebook-context"
import { Button } from "@/components/ui/button"
import { blockLabel, isVisible } from "@/lib/notebook"

const scrollToId = (id: string) => document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" })

/** Table of contents: sections and their visible (non-md) cells. The workspace sidebar hosts and scrolls it. */
export function Outline() {
  const { sections, view, scrollTo } = useNotebook()
  return (
    <nav className="flex flex-col gap-3" aria-label="Outline">
      {sections.map((s) => {
        const cells = s.items.flatMap((it) => (it.type === "block" && isVisible(it.block, view) ? [it.block] : []))
        return (
          <div key={s.key} className="flex flex-col">
            {s.heading ? (
              <Button variant="ghost" size="xs" className="w-full min-w-0 justify-start font-medium" onClick={() => scrollToId(s.key)} title={s.heading.text}>
                <span className="truncate">{s.heading.text}</span>
              </Button>
            ) : null}
            {cells.map((b) => (
              <Button
                key={b.id}
                variant="ghost"
                size="xs"
                className="w-full min-w-0 justify-start pl-4 font-normal text-muted-foreground"
                onClick={() => scrollTo(b.id)}
                title={`${b.kind} · ${b.id}`}
              >
                <span className="w-9 shrink-0 text-left tb-label text-[10px] opacity-60">{b.kind}</span>
                <span className="truncate">{blockLabel(b)}</span>
              </Button>
            ))}
          </div>
        )
      })}
    </nav>
  )
}
