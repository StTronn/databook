// Dev-only (vite serve /gallery.html): every chart block of the running `databook dev` + synthetic type×variant fixtures.
import { StrictMode, useEffect, useState } from "react"
import { createRoot } from "react-dom/client"
import { ChartCard } from "@/components/charts/chart-card"
import type { ChartBlock, Doc, Series } from "@/types"
import "@/index.css"

const weeks = ["2026-04-27", "2026-05-04", "2026-05-11", "2026-05-18", "2026-05-25", "2026-06-01"]
const fmt = (v: number | null) => (v === null ? "—" : v.toLocaleString("en-US"))
const ser = (name: string, values: (number | null)[], extra: Partial<Series> = {}): Series => ({ name, values, display: values.map(fmt), ...extra })
let n = 0
const fx = (type: ChartBlock["type"], variant: string, series: Series[], extra: Partial<ChartBlock> = {}): ChartBlock => ({
  id: `fx_${++n}`, kind: "chart", line: 0, deps: [], reads: [], usedBy: [], data: "fixture", type, variant,
  title: `${type} · ${variant}`, y: series.map((s) => s.name), labels: weeks, series, ...extra,
})

const a = ser("orders", [109, 306, 286, null, 269, 301])
const b = ser("paid", [69, 202, 191, 155, 176, 210])
const c = ser("refunded", [5, 12, 9, 14, 7, 11])
const methods = ["card", "upi", "netbanking", "wallet"]
const pieS = { name: "lost_inr", values: [115236, 109534, 21688, 4100], display: ["₹1,15,236", "₹1,09,534", "₹21,688", "₹4,100"] }

const fixtures: ChartBlock[] = [
  fx("bar", "default", [a]),
  fx("bar", "default", [a, b, c], { description: "grouped, null in orders wk4" }),
  fx("bar", "stacked", [b, c]),
  fx("bar", "stacked", [b], { description: "one-series stacked" }),
  fx("bar", "horizontal", [ser("failed", [120, 80, 44, 12])], { labels: ["upi · UPI app declined the request", "card · Payment failed due to incorrect OTP", "netbanking · Bank server unavailable", "wallet · timeout"] }),
  fx("bar", "label", [ser("delta", [40, -25, 12, null, -8, 30])], { description: "negatives + null" }),
  fx("line", "default", [a, b]),
  fx("line", "dots", [ser("conversion", [0.633, 0.66, 0.668, 0.574, 0.654, 0.7], { display: ["63.3%", "66.0%", "66.8%", "57.4%", "65.4%", "70.0%"] })], { format: "pct" }),
  fx("line", "linear", [a]),
  fx("line", "step", [b]),
  fx("line", "label", [a]),
  fx("area", "default", [a, b]),
  fx("area", "gradient", [b, c]),
  fx("area", "stacked", [b, c]),
  fx("area", "expanded", [b, c]),
  fx("area", "linear", [a], { format: "inr_short" }),
  fx("area", "step", [b], { format: "inr" }),
  ...["pie", "donut", "donut-text", "label"].map((v) => fx("pie", v, [pieS], { labels: methods, total: "₹2,50,558", format: "inr" })),
  fx("funnel", "default", [ser("n", [1240, 935, 793, 793, 734])], { labels: ["Orders created", "Checkout attempted", "Paid", "Captured", "Settled"], share: ["100.0%", "75.4%", "64.0%", "64.0%", "59.2%"], total: "4,495" }),
  fx("radial", "default", [ser("conv", [0.42], { display: ["42.0%"] })], { labels: undefined, max: 1 }),
  fx("radial", "text", [ser("attainment", [1.3], { display: ["130.0%"] })], { labels: undefined, max: 1, description: "over max → full ring" }),
  fx("combo", "default", [
    ser("Orders", [109, 306, 286, 270, 269, 301], { mark: "bar" }),
    ser("Paid", [69, 202, 191, null, 176, 210], { mark: "line" }),
    { name: "Forecast band", mark: "band", values: [60, 180, 170, 150, 160, 190], values2: [80, 220, 210, 175, 195, 235], display: ["60 – 80", "180 – 220", "170 – 210", "150 – 175", "160 – 195", "190 – 235"] },
    ser("Target", [100, 200, 200, 200, 200, 220], { mark: "dot" }),
    ser("Area", [30, 50, 40, 60, 55, 70], { mark: "area" }),
  ]),
  fx("bar", "default", [a], { error: "CHART_COLUMN_MISSING: chart columns ['amt'] not in methods (has method, payments)" }),
  fx("bar", "bogus", [a], { description: "unknown variant" }),
  { ...fx("bar", "default", [a]), type: "heatmap" as ChartBlock["type"], title: "unknown type" },
  fx("line", "default", [ser("empty", [])], { labels: [], title: "empty" }),
]

function Gallery() {
  const [live, setLive] = useState<ChartBlock[]>([])
  const [traced, setTraced] = useState("")
  useEffect(() => {
    fetch("/results.json").then((r) => r.json()).then((d: Doc) => setLive(d.blocks.filter((b): b is ChartBlock => b.kind === "chart")), () => {})
  }, [])
  const theme = (t: string) => () => (document.documentElement.dataset.theme = t)
  return (
    <main className="mx-auto flex max-w-4xl flex-col gap-6 px-4 py-6">
      <div className="flex gap-3 text-xs">
        <button onClick={theme("dark")}>dark</button>
        <button onClick={theme("light")}>light</button>
        <span id="traced">{traced}</span>
      </div>
      {[...live, ...fixtures].map((b) => <ChartCard key={b.id} block={b} onTrace={setTraced} />)}
    </main>
  )
}

createRoot(document.getElementById("root")!).render(<StrictMode><Gallery /></StrictMode>)
