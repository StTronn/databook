import { useCallback, useState } from "react"
import { PALETTES, type Palette } from "@/lib/themes"

export type ThemeMode = "dark" | "light"

// index.html applies the stored mode to <html data-theme> before first paint; the DOM attribute is the source of truth.
export const THEME_STORAGE_KEY = "tb-theme-mode"
export const PALETTE_STORAGE_KEY = "tb-palette"

const current = (): ThemeMode => (document.documentElement.dataset.theme === "light" ? "light" : "dark")
const currentPalette = (): Palette =>
  PALETTES.find((p) => p.id === document.documentElement.dataset.palette)?.id ?? "terminal"

function store(key: string, value: string) {
  try {
    localStorage.setItem(key, value)
  } catch {
    // storage blocked (private mode, file:// policies): the choice still applies for this page view
  }
}

export function useThemeMode() {
  const [mode, setModeState] = useState<ThemeMode>(current)

  const setMode = useCallback((m: ThemeMode) => {
    document.documentElement.dataset.theme = m
    store(THEME_STORAGE_KEY, m)
    setModeState(m)
  }, [])

  const toggle = useCallback(() => setMode(current() === "dark" ? "light" : "dark"), [setMode])

  const [palette, setPaletteState] = useState<Palette>(currentPalette)
  const setPalette = useCallback((p: Palette) => {
    document.documentElement.dataset.palette = p
    store(PALETTE_STORAGE_KEY, p)
    setPaletteState(p)
  }, [])

  return { mode, setMode, toggle, palette, setPalette }
}
