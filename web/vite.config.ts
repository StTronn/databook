import path from "node:path"
import tailwindcss from "@tailwindcss/vite"
import react from "@vitejs/plugin-react"
import { defineConfig, type Plugin } from "vite"
import { viteSingleFile } from "vite-plugin-singlefile"

const THEME_SLOT = '<style id="tb-theme">/*__TB_THEME__*/</style>'
const DATA_SLOT = "/*__TB_DATA__*/null"
const count = (s: string, sub: string) => s.split(sub).length - 1

// Vite minifies inline <style> (dropping the slot comment) and inlines the bundle CSS after it. Restore the theme slot
// at the end of <head> so a project theme.css always wins the cascade; fail the build unless each slot occurs exactly once.
function databookSlots(): Plugin {
  return {
    name: "databook-slots",
    enforce: "post",
    generateBundle: {
      order: "post",
      handler(_, bundle) {
        const html = bundle["index.html"]
        if (html?.type !== "asset") return this.error("index.html missing from bundle")
        let s = String(html.source)
        // Inlined JS contains "<head></head><body>" (DOMPurify), so anchor on the real </head>: the one before the app root.
        const head = /<\/head>(?=\s*<body>\s*<div id="root">)/g
        if (count(s, 'id="tb-theme"') !== 1 || (s.match(head) ?? []).length !== 1) this.error("expected one #tb-theme and one </head><body><div id=root>")
        s = s.replace(/<style id="tb-theme">[\s\S]*?<\/style>\s*/, "").replace(head, `  ${THEME_SLOT}\n  </head>`)
        if (count(s, THEME_SLOT) !== 1 || count(s, "/*__TB_THEME__*/") !== 1 || count(s, DATA_SLOT) !== 1)
          this.error("viewer slots must survive the build exactly once")
        html.source = s
      },
    },
  }
}

// One self-contained file (JS, CSS, fonts inlined) → shipped inside the Python package.
// `databook export` fills the data/theme slots in index.html; `vite` dev proxies a running `databook dev`.
export default defineConfig({
  plugins: [react(), tailwindcss(), viteSingleFile(), databookSlots()],
  resolve: { alias: { "@": path.resolve(import.meta.dirname, "src") } },
  build: { outDir: "../src/databook/viewer", emptyOutDir: true, assetsInlineLimit: () => true },
  server: { proxy: { "/results.json": "http://127.0.0.1:4321", "/version": "http://127.0.0.1:4321", "/theme.css": "http://127.0.0.1:4321", "/api": "http://127.0.0.1:4321" } },
})
