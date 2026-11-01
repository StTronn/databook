// Palettes for <html data-palette>; each non-default one is src/themes/<id>.css (imported by index.css).
// Light/dark mode stays orthogonal (data-theme). A project theme.css still overrides any token on top.
export const PALETTES = [
  { id: "terminal", label: "Terminal" },        // index.css defaults (smui, monospace)
  { id: "enterprise", label: "Enterprise" },    // after panxo.com
] as const
export type Palette = (typeof PALETTES)[number]["id"]
