# Databook — product & evaluation plan

> Naming: the data-analysis "pack" below is now the **playbook** (`playbooks/data-analysis`, independent of Databook); "packs" inside Databook are only source packs (e.g. Razorpay import detection).


Databook turns business data (billing, customers, browsing events) into **analysis notebooks your own coding agent builds and you can check**. Every number in a report traces to the block/query that produced it; the agent is scored on public benchmarks and gets measurably better per version. Benchmarks are evidence, not the product.

## 1. Users & questions

| User | Typical question |
|---|---|
| Founder / CEO | "What's our MRR/ARR and why did it move this month?" |
| Finance / RevOps | "MRR movements: new, expansion, contraction, churn, reactivation." |
| Customer success / CRM | "Show me one customer end to end: orders, spend, lifespan, segment, engagement, support." |
| Growth (D2C) | "Where do new visitors drop off between landing and purchase? Which channel converts? Do they come back?" |

Common need: answers they can **trust and audit**, without a BI stack or writing SQL.

## 2. User journey

1. **Bring data** — Stripe / Lago / Shopify / QuickBooks / GA exports (CSV, xlsx, parquet) into `data/`; `databook import` → typed DuckDB tables.
2. **Ask in plain words** in Claude Code — "build my MRR view", "customer 360 for Acme", "where do new visitors drop off?".
3. **Agent builds a notebook** — starts from a pack template + `definitions.md`, reads schema first, writes SQL/Python + KPI/chart blocks, runs `databook check`, fixes its own errors.
4. **Review in viewer** — clean report; click any number → its block & query. Comment on a block ("exclude trials"); agent reads `databook comments`, fixes, resolves with a note.
5. **Keep alive** — new data → rerun; `databook diff` says what moved and why. Notebooks live in folders (`revenue/`, `customers/`, `growth/`) as standing reports.
6. **Share** — `databook export` → single HTML that keeps the trace.

## 3. What we build

| Piece | What | Status |
|---|---|---|
| Core | CLI + skill, DuckDB/pandas/xlsx blocks, check, history/diff, comments, viewer, export | Built |
| `packs/growth/` | `definitions.md` + 3 templates: `mrr`, `customer-360`, `d2c-funnel` | New |
| `evals/` | Harness: runs the agent on frozen benchmark slices, grades with the benchmark's own grader, logs pass / $ / time / turns / failure tag | New |
| Specialist model (later) | Small open model SFT→RL on our correct traces for one narrow sub-task | Later |

**Non-goals:** hosted BI, live connectors, multi-user permissions, forecasting.

### The 3 starter notebooks

| Notebook | User gets | Data | Graded tasks that check it |
|---|---|---|---|
| **MRR** | MRR/ARR over time; monthly movements (new/expansion/contraction/churn/reactivation); per-plan | Spider2-DBT `mrr` (dbt mrr-playbook data), Zuora, Recharge | DBT `mrr001`, `mrr002`, `zuora001`, `recharge001`, `recharge002` (~5) |
| **Customer 360** | One row per customer: orders, spend, lifespan, RFM segment, engagement, support; drill-in per customer | Olist (local), Shopify+Klaviyo, HubSpot, Intercom, THELOOK | DBT `shopify_holistic_reporting001`, `hubspot001`, `intercom001`, `recharge002`; Lite `local003` (RFM), `local004` (lifespan), `local029`, THELOOK customer tasks (~12) |
| **D2C onboarding / browsing funnel** | landing → PLP → PDP → cart → checkout → purchase; step drop-off; new-user activation; retention by first-visit week; channel × conversion | GA4 obfuscated sample + GA360 (Google Merchandise Store), local web `log` | Lite `ga001`–`ga032` (17 GA4), 12 GA360 (`bq001`…`bq374`, e.g. `bq270`), `local329`/`local330`/`local360` (registration/landing funnel), `local075` (view→cart→purchase), `ga005`/`ga028`/`ga030` (retention) (~37) |

## 4. What we want to show → how

| Claim | Shown by |
|---|---|
| Correct | Pass rate on the 3 Spider2 slices, rising per version |
| The method matters | Same model, bare vs + Databook + pack, same tasks — the delta is the product's value |
| Traceable | Share of displayed numbers that resolve to a block; `check` clean |
| Catches classic mistakes | Failures by tag (session definition, step order, annual ÷12, proration, trials, duplicate customers, timezone month) and which tag each version fixed |
| Reviewable | Scripted comment → fix rounds; fixed on first round? |
| Stays right | Rerun on new data; `diff` flags the right changes, no silent breakage |
| Efficient | $ and time per solved task drop at equal pass rate |
| Small model can do narrow parts (later) | Fine-tuned small model vs frontier on one sub-task: accuracy, $, latency |

## 5. Evaluation

**Benchmarks (defined by others, never edited):** Spider 2.0-DBT (68 dbt-on-DuckDB projects, gold tables, `evaluate.py`) and Spider 2.0-lite (547 questions, gold result CSVs) — sliced as in §3. Later: DABStep (450, leaderboard), SpreadsheetBench Verified 400 (spreadsheet control).

**Fixed rules:** grader untouched; 3 runs per task (agents are non-deterministic → report mean & spread); same model tier and budget/timeout across arms; agent never sees gold.

**Arms:**
- **Bare** — `claude -p` in a folder with the question + data only.
- **Databook** — same folder + Databook skill + pack; agent works in a notebook, `check` clean, answer exported from the final block.

**Layers:**
- **A — proficiency:** pass rate per slice per arm.
- **B — product check:** each template run on its slice's data passes `check`, every number traces, key numbers match the overlapping gold.
- **C — human loop:** injected comments fixed correctly; rerun on new data → correct `diff`.

### Worked example (`local329`, funnel slice)

Task: "How many unique sessions visited `/regist/input` and then `/regist/confirm`, in that order?" Data: SQLite `log`. Gold: 1-row CSV.

1. **Prepare** — `run.py` makes a fresh temp folder per run: `question.md` (question + "write `answer.csv`") and `data/log.sqlite`. Gold is never copied in.
2. **Bare arm** — `claude -p` reads SQLite however it likes, writes `answer.csv`.
3. **Databook arm** — `databook init` + import → agent writes `notebooks/answer.md` (SQL blocks) → `check` until clean → `answer.csv` from the final block. The notebook remains as the trace.
4. **Grade** — `grade.py` hands `answer.csv` + gold to Spider2's grader → pass/fail.
5. **Log** — pass, $, time, turns (from `claude -p --output-format json`); Databook arm also: `check` clean, numbers traced; failure tag after reading the trace ("ignored step order", "wrong session key").
6. **Aggregate** — ×3 runs × every slice task × both arms → e.g. "funnel: bare 14/37, Databook 21/37, $/solved, time/solved, top failure tags".

### Improvement loop

Read failures by tag → write the hypothesis first → change **one** thing (e.g. sharpen session definition in `definitions.md`; skill rule "sample rows before writing funnel steps") → rerun the same slice → note in `evals/results/results.md`: which tasks flipped and why, which still fail, with log evidence.

Ladder: **B0** bare → **+pack** (definitions) → **+Databook** (schema-first, check, trace) → **+efficiency** (context/cost) → **+specialist model**.

## 6. Repo layout

```
src/databook/            core (exists)
packs/razorpay/           exists
packs/growth/             definitions.md, templates/{mrr,customer-360,d2c-funnel}
evals/
  spider2/                downloaded tasks, gold, grader (untouched, gitignored)
  slices.yaml             task ids per slice: mrr / customer-360 / funnel
  run.py                  one arm × one slice × 3 runs, temp folder per run
  grade.py                calls Spider2's grader
  results/
    runs/<date>-<arm>/    raw logs + answers per task
    results.md            before/after notes per version
    notebooks/            Databook notebook charting all runs
```

Results stay in the repo (no public page).

## 7. Known catches

1. **DBT tasks are dbt projects** (missing models; grader checks final DuckDB tables). Databook arm needs an adapter copying the notebook's output tables into the task's DuckDB under the expected names.
2. **GA4 / GA360 / Firebase are BigQuery public datasets.** Local runs need a one-time BigQuery → Parquet export (Google Cloud account; free sandbox works; a few GB). Gold stays valid (same data). Until then the funnel slice = `local075`, `local329`, `local330`, `local360`.
3. **THELOOK tasks are Snowflake** (`sf_bq*`) — same export issue; customer-360 starts on Olist + DBT tasks.

## 8. Milestones

| M | Deliverable | Proof |
|---|---|---|
| M0 | Download Spider2 (repo, DBT DBs, lite local SQLite); `slices.yaml`; `run.py` + `grade.py`; bare arm on local tasks of all 3 slices | Baseline table: pass, $/solved, time/solved, failure tags |
| M1 | `packs/growth/definitions.md` + 3 templates; Databook arm + DBT adapter | First before/after: bare vs +pack vs +Databook |
| M2 | GA4/GA360 export → full funnel slice; layers B and C | Templates pass product check; review-loop and rerun/diff results |
| M3 | Efficiency pass; DABStep | $/time down at equal pass; leaderboard submission |
| M4 | Specialist small model for one sub-task | Small vs frontier: accuracy, $, latency |

## 9. Open

- Permission to download into `evals/spider2/` (`gdown` from Google Drive; sizes unknown until fetched).
- GA4 export: set up a Google Cloud account now, or start the funnel on local log data?
