import { MenuIcon, MoonIcon, PaletteIcon, PanelRightIcon, SunIcon } from "lucide-react"
import { Fragment } from "react"
import { Badge } from "@/components/ui/badge"
import { Breadcrumb, BreadcrumbItem, BreadcrumbList, BreadcrumbPage, BreadcrumbSeparator } from "@/components/ui/breadcrumb"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { useThemeMode } from "@/hooks/use-theme-mode"
import type { View } from "@/lib/notebook"
import { PALETTES, type Palette } from "@/lib/themes"
import type { Doc } from "@/types"

type Props = {
  crumbs: string[]
  doc: Doc | null
  view: View
  onView: (v: View) => void
  /** shown when the sidebar is a sheet (below lg) */
  onMenu?: () => void
  onPanel: () => void
}

function IconButton({ label, onClick, children }: { label: string; onClick: () => void; children: React.ReactNode }) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button variant="ghost" size="icon" onClick={onClick} aria-label={label}>
          {children}
        </Button>
      </TooltipTrigger>
      <TooltipContent>{label}</TooltipContent>
    </Tooltip>
  )
}

export function AppHeader({ crumbs, doc, view, onView, onMenu, onPanel }: Props) {
  const { mode, toggle, palette, setPalette } = useThemeMode()
  return (
    <header className="flex h-12 shrink-0 items-center gap-2 border-b px-2 sm:gap-3 sm:px-4">
      {onMenu ? (
        <IconButton label="Open sidebar" onClick={onMenu}>
          <MenuIcon />
        </IconButton>
      ) : null}
      <Breadcrumb className="min-w-0 flex-1">
        <BreadcrumbList className="flex-nowrap text-xs">
          {crumbs.map((c, i) => (
            <Fragment key={i}>
              {i ? <BreadcrumbSeparator className="max-sm:hidden" /> : null}
              <BreadcrumbItem className={i < crumbs.length - 1 ? "shrink-0 max-sm:hidden" : "min-w-0"}>
                {i === crumbs.length - 1 ? <BreadcrumbPage className="truncate font-medium">{c}</BreadcrumbPage> : c}
              </BreadcrumbItem>
            </Fragment>
          ))}
        </BreadcrumbList>
      </Breadcrumb>
      <div className="flex shrink-0 items-center gap-1 sm:gap-2">
        {doc ? (
          <Badge variant={doc.ok ? "outline" : "destructive"} className="tb-label rounded-none max-sm:hidden">
            {doc.ok ? "ok" : "error"}
          </Badge>
        ) : null}
        {doc ? (
          <ToggleGroup
            type="single"
            variant="outline"
            size="sm"
            value={view}
            onValueChange={(v) => (v === "notebook" || v === "report") && onView(v)}
            aria-label="View"
          >
            <ToggleGroupItem value="notebook" className="px-2 text-xs sm:px-3">
              Notebook
            </ToggleGroupItem>
            <ToggleGroupItem value="report" className="px-2 text-xs sm:px-3">
              Report
            </ToggleGroupItem>
          </ToggleGroup>
        ) : null}
        <DropdownMenu>
          <Tooltip>
            <TooltipTrigger asChild>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" size="icon" aria-label="Theme">
                  <PaletteIcon />
                </Button>
              </DropdownMenuTrigger>
            </TooltipTrigger>
            <TooltipContent>Theme</TooltipContent>
          </Tooltip>
          <DropdownMenuContent align="end">
            <DropdownMenuLabel>Theme</DropdownMenuLabel>
            <DropdownMenuRadioGroup value={palette} onValueChange={(v) => setPalette(v as Palette)}>
              {PALETTES.map((p) => (
                <DropdownMenuRadioItem key={p.id} value={p.id}>
                  {p.label}
                </DropdownMenuRadioItem>
              ))}
            </DropdownMenuRadioGroup>
          </DropdownMenuContent>
        </DropdownMenu>
        <IconButton label={mode === "dark" ? "Switch to light theme" : "Switch to dark theme"} onClick={toggle}>
          {mode === "dark" ? <SunIcon /> : <MoonIcon />}
        </IconButton>
        <IconButton label="Toggle outputs & settings panel" onClick={onPanel}>
          <PanelRightIcon />
        </IconButton>
      </div>
    </header>
  )
}
