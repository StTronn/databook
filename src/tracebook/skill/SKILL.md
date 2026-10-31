---
name: tracebook
description: Build data notebooks/reports from data files or databases (CSV, Excel, JSON, SQLite, Parquet — payment exports, sales sheets, CRM dumps) with the `tracebook` CLI — SQL, Python and spreadsheet-model blocks, KPIs, charts, tables, every number traceable to the block that computed it, exported as a shareable HTML report (`tracebook export`) or a block's result as CSV (`tracebook export --block <id> <file.csv>`). Use when the user wants analysis, a dashboard, a funnel, cohorts, a what-if model or a report built from data, or mentions a tracebook project / notebook.md.
allowed-tools: Bash(tracebook:*), Bash(uv tool install:*)
---

# tracebook

A workspace is a folder with `notebooks/**/<name>.md` (you edit them; `tracebook new growth/cohorts` adds one; all share
the imported data, block ids are per notebook), `data/` (raw files, never modified), `models/` (.xlsx models for
`sheet` blocks) and `.tracebook/` (database + results; never edit). With several notebooks pass `--nb <name>`.

If `tracebook` is not on PATH: `uv tool install <path-to-repo>/tracebook` (or `pipx install …`).

## Workflow (always in this order)

0. `tracebook comments` — open review comments from the viewer: address each, then
   `tracebook comments resolve <id> --note '<what changed>'`.

1. `tracebook init <dir> [--template razorpay-funnel] [--tz Asia/Kolkata]` — new project only; create it inside the
   current working directory (e.g. `./analysis`) so it stays with the user's files.
2. `tracebook import data/<files>` — read every warning/error line. `✗ AMBIGUOUS_DATE` / `TYPE_MISMATCH` mean
   nothing was loaded for that table: rerun with `--types col=date:dmy` (or the type it names). When a line
   says a source pack matched (e.g. `razorpay.payments`), run `tracebook skill guide <pack>` once and follow it.
3. `tracebook schema` — learn tables, columns, types. `tracebook query "<sql>"` to explore (read-only).
   Databases need no import: `tracebook source add shop --type postgres --env SHOP_URL` (mysql/sqlite/duckdb too;
   the URL stays in the env var), then SQL blocks read `shop.<schema>.<table>` read-only. Filter and aggregate in
   that SQL block; python blocks read its result, never the source directly.
4. Edit the notebook file (block syntax below; full reference: `references/blocks.md` next to this file).
5. `tracebook check` — runs everything. Exit 0 = clean. Fix every `✗` line at the `<file>:<line>` it names,
   rerun until `✓`. `tracebook snapshot` shows each block's status and columns.
6. `tracebook export` → `dist/index.html` (refuses while errors remain). `tracebook dev` = live preview for the user.
   A requested answer file (CSV) comes from a block, never a side script: `tracebook export --block <id> <path.csv>`.
   After edits, `tracebook diff` lists per-block changes vs the previous run — tell the user which numbers moved.

Never claim the report is done until `tracebook check` prints `✓ … 0 error(s)`.

## Notebook shape

The notebook is the presentable result, like a dashboard or report in Power BI, Sheets or Hex, that someone opens to
see the answers.

- Lay it out like a notebook: `# Title`, one line on what it answers, then one `##` heading per question in the order asked.
- Under each heading, lead with the answer: a `kpi` card for the headline number (with `compare` when one exists), then
  one or two plain sentences stating the takeaway with `{{block.col}}` refs.
- Add a `chart` only when shape or trend matters, and a `table` only when the reader needs the rows; skip both if the
  card already answers it.
- Keep sql/python blocks next to the output they feed; they support the story, so don't narrate code in prose.
- Put definitions, assumptions and data-source notes in a short closing `## Notes` section, never at the top.
- Explain simply: everyday words, units on every number.
- A block exported as an answer file returns exactly what was asked (a count → one row with the count).

## Blocks

````markdown
```sql funnel "Funnel counts"    ← compute block: id required (title optional); one SELECT/WITH query; becomes table `funnel`
SELECT count(*) AS created, count(*) FILTER (WHERE status = 'paid') AS paid, paid / created AS conv
FROM orders
```
```python weekly                 ← upstream tables/blocks are DataFrames by name; `pd`, `TZ` available; must return a DataFrame
o = orders.copy(); o["day"] = o.created_at.dt.tz_convert(TZ).dt.date
return o.groupby("day").size().rename("orders").reset_index()
```
```sheet whatif                  ← .xlsx model you build with openpyxl; CLI writes inputs into a copy, recalcs (formualizer), reads outputs
file: models/whatif.xlsx
inputs: { Inputs!B2: funnel.created }      # constant cells only; value = block.column of a 1-row block, or a number
outputs: { Model!B7: uplift }             # → table `whatif` with column `uplift`
show: Model!A1:B7
```
```kpi
- { label: Conversion, value: funnel.conv, format: pct, compare: funnel_prev.conv }
```
```chart
{ type: funnel, data: funnel_stages, x: stage, y: n, variant: …, title: … }   ← types/variants/combo: `tracebook components`
```
```table
{ data: methods, columns: [method, success_rate], sort: lost_inr desc, format: { success_rate: pct } }
```
Prose: Paid conversion was **{{funnel.conv | pct}}**.   ← formats: int num pct inr inr_short usd usd_short gbp gbp_short date text
````

## Rules that keep numbers correct

- Never type a computed number into prose; use `{{block.column | fmt}}` (check flags `LITERAL_NUMBER_IN_PROSE`).
  `{{…}}`, kpi `value` and sheet `inputs` need a block that returns exactly 1 row.
- Count entities with `count(DISTINCT …)` when joining one-to-many (orders ↔ payments).
- Keep currencies separate (`WHERE currency = 'INR'` or `GROUP BY currency`); never sum across currencies.
- Money columns are exact DECIMAL; in Python they arrive as `Decimal` objects — keep them that way for sums.
- Timestamps with zones are `TIMESTAMPTZ`; `date_trunc`/`::DATE` already use the project time zone.
- Don't select personal data (email, contact, vpa) into blocks you display; check warns `PII_COLUMN_PUBLISHED`.
- Edit `.xlsx` models only through Python/openpyxl (bash heredoc), never with text-edit tools; model inputs must be
  plain constant cells (formulas there → `SHEET_INPUT_IS_FORMULA`).
- Model workflow: copy uploads into `models/` (never edit the original), `tracebook sheet <file>` to see cells/formulas/
  values and errors, edit, `tracebook sheet <file> --diff <before>` — every `FORMULA_REMOVED` must be intended.
- Python blocks: deterministic (seed any randomness), no network, return a DataFrame — or `{name: DataFrame}`,
  read downstream as `<block>__<name>` (e.g. `model__summary`).
