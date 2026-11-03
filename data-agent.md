# Data agent: pack + evals plan (working notes)

> Naming: the data-analysis "pack" below is now the **playbook** (`playbooks/data-analysis`, independent of Databook); "packs" inside Databook are only source packs (e.g. Razorpay import detection).


Status: planning, nothing below is built yet. Decisions marked ✅, open items marked ❓. Current tracer-bullet plan: `plan.md`.

## 1. Framing
Three layers; keep them separate when claiming results.
| Layer | What | Moves benchmark scores? |
|---|---|---|
| Knowledge = **pack** (`packs/growth/`) | metric definitions, traps, SQL snippets, templates, skill text | Yes, main driver; portable (works as plain skill without Databook) |
| Workflow = **Databook runtime** | typed import, schema-first, `check` + error codes, stale/cross-ref checks | Maybe ±; must be measured (adds turns/tokens) |
| Product = **Databook artifact** | trace, viewer, comments, diff, rerun, export | No; benchmarks are ask-once/grade-once. Proven by Databook-specific evals (§5.3) |

Data agent = model + Claude Code + pack. Databook = layer on top making answers checkable, reviewable, repeatable. Analogy: git + tests for coding agents.

## 2. Starter notebooks ✅
| Notebook | User gets | Data | Graded tasks (Spider2) |
|---|---|---|---|
| MRR | MRR/ARR over time; movements new/expansion/contraction/churn/reactivation; per plan | Spider2-DBT `mrr` db (mrr-playbook data), Zuora, Recharge | DBT `mrr001 mrr002 zuora001 recharge001 recharge002` |
| Customer 360 | row per customer: orders, spend, lifespan, RFM segment, engagement, support; drill-in | Olist (local), Shopify+Klaviyo, HubSpot, Intercom | DBT `shopify_holistic_reporting001 hubspot001 intercom001 recharge002`; lite `local003 local004 local029` + THELOOK (`sf_bq*`, Snowflake) |
| D2C onboarding/browsing funnel | landing→PLP→PDP→cart→checkout→purchase; step drop-off; activation; retention by first-visit week; channel×conversion | GA4/GA360 Google Merchandise Store (BigQuery public), local web log | lite `ga001–ga032` (17 GA4), 12 GA360 `bq001…bq374` (e.g. `bq270`), local `local075 local329 local330 local360`, firebase retention `ga005 ga028 ga030` |

Caveat: GA4/GA360/firebase tasks are BigQuery → one-time export to Parquet (Google Cloud sandbox, few GB) ❓. Until then funnel slice = 4 local tasks.
Spider2-DBT tasks are dbt projects (fill missing models; grader compares DuckDB tables) → Databook arm needs adapter copying notebook outputs into expected tables.

## 3. User journey (product)
1. `uv tool install databook` + growth pack; install skill into Claude Code.
2. `databook init shop` → `databook new funnel --template d2c-funnel` (working template, `TODO: map your columns`).
3. Exports into `data/` → `databook import data/*`.
4. Ask Claude Code ("adapt funnel; where do new visitors drop off?"): `schema` + sample rows → map columns per `definitions.md` → edit SQL blocks → `check` until clean → summary citing `{{block.col}}`.
5. `databook dev`: click number → query; comment ("sessions per day not per user") → agent fixes, resolves with note.
6. New export → rerun → `databook diff` explains movement → export HTML.

## 4. Repo structure (planned)
```
packs/growth/        pack.py, definitions.md (+provenance), snippets/*.sql, templates/{mrr,customer-360,d2c-funnel}/notebook.md
evals/
  agents/databook_claude.py      Harbor custom agent: Claude Code + installs databook & pack in sandbox
  adapters/spider2-lite/          our Harbor adapter for lite local SQLite tasks (Spider2 result comparison in tests/test.sh)
  configs/*.yaml                  one Harbor job config per arm (§5.2)
  slices/{mrr,customer360,funnel}.txt
  jobs/                           Harbor output (gitignored)
  results/evals.md                Databook notebook over jobs/*/result.json; log.md = hypothesis→result→flipped tasks
```
Rule: evals inject the same skill + pack users install (measure the shipped product).

## 5. Evaluation
### 5.1 Harness: Harbor ✅ (docs.harborframework.com)
- Task = `instruction.md`, `environment/` (Dockerfile+data), `solution/`, `tests/test.sh` → `/logs/verifier/reward.txt`. Agent never sees `tests/`.
- `-a claude-code` built in; `--skill <dir>` (skill content hash recorded per job); `-k 3` attempts; local Docker; reward/cost/tokens/time/ATIF trajectory per trial.
- `harbor view jobs` viewer; `harbor job regrade` re-scores after grader fix without rerunning agent; ATIF passing trajectories → SFT data later.
- Existing parity-checked adapters: `spider2-dbt` (64), `dabstep` (450), `spreadsheetbench-verified` (400), `bird_bench`, `dacode`, `kramabench`, `crmarena` (1,170; CC BY-NC). Spider2-lite: no adapter → ours.
- ❓ Docker Desktop vs Apple `container`; ❓ model + ANTHROPIC_API_KEY/Claude Code token inside containers (Harbor parity runs used Haiku 4.5).

### 5.2 Arms (same tasks, grader untouched, 3 attempts each)
| Arm | Setup | Answers |
|---|---|---|
| B0 | bare Claude Code | baseline |
| K | + Anthropic data plugin (de facto) | worth of the de facto plugin |
| K+P | + growth pack | worth of our domain knowledge |
| T | Databook + pack | worth of executable checks / workflow |
(Earlier 2×2 pack×databook still valid as ablation.) Report per slice: solve rate mean±spread, $/solved, time/solved, turns, failure tags; for T also check-clean + % numbers traceable.

### 5.3 Databook-specific evals (benchmark data/gold, nothing invented)
1. Fault catching: inject wrong join / type error / stale table / dropped column / uncited number → caught by `check`/trace? fixed?
2. Verifiability: reviewer (human or artifact-only judge) locates + confirms source of each number; Databook notebook vs bare transcript.
3. Review loop: injected comment fixed correctly in one round, check stays clean.
4. Change over time: next-period data; rerun correct (gold recomputed via benchmark reference SQL); `diff` flags exactly what changed.

### 5.4 Later
DABStep (450, billing/fees, leaderboard) for scale + efficiency rung; specialist small model (Qwen ~4–9B, SFT on passing ATIF trajectories, then RL via `pi_xl/rl` verifiers scaffold) for one narrow sub-task.

## 6. Improve loop
Diagnose (viewer, tag failures) → one hypothesis → change pack/skill only → rerun same config, new job name → compare in `evals.md` → `log.md` entry (flipped tasks w/ trial links, still-failing + why) → grader bug ⇒ fix test + `harbor job regrade`.
Model for rigor: Harvard CS2680 assignments (fixed workload, untouched grader, baseline, one change per run, before/after with evidence).

## 7. Prior work to build on (pack)
| Source | Use |
|---|---|
| `anthropics/knowledge-work-plugins/data` (analyze, explore-data, sql-queries, write-query, validate-data, statistical-analysis, data-context-extractor) | baseline arm K; validate-data pitfalls (join explosion, incomplete period, denominator shift, avg-of-avg, timezone) → turn into executable `check` rules; data-context-extractor idea → workspace overrides |
| `dbt-labs/dbt-agent-skills` (semantic layer, NL questions, own `evals/`) | metric typing (MetricFlow: simple/ratio/cumulative/derived/conversion); copy eval approach |
| `dbt-labs/mrr-playbook`, Fivetran dbt packages (stripe, zuora, recharge, shopify, hubspot) | MRR movements, customer overview definitions |
| `Velir/dbt-ga4` (BigQuery only) | GA4 sessionization (`ga_session_id`+user), landing page, event modelling |
| Spider2 `external_knowledge` docs (e.g. RFM) | already given to agents in tasks |
"Better" = (1) prose checklists → executable checks with codes; (2) definitions distilled into dbt-free DuckDB snippets with provenance + traps; (3) company overrides as versioned pack config visible in trace.
Planned new `check` rules: row growth after join, declared grain violated, incomplete period, undeclared timezone.

⚠ Contamination: Spider2-DBT gold built from Fivetran-style package code. Pack carries definitions/patterns, never copied package models; keep provenance list; mark tasks whose gold derives from a used source as contaminated, report separately; clean claims on Spider2-lite + DABStep. ❓ check licenses (KWP data plugin; dbt packages typically Apache-2.0) before verbatim reuse.

## 8. Effort estimate (LOC, complexity)
| Item | Est. | Cx |
|---|---|---|
| `evals/agents/databook_claude.py` | ~60 | Med |
| `evals/adapters/spider2-lite/` | ~180 | Med |
| `evals/configs/*.yaml` ×4, `slices/*.txt` ×3 | ~55 | Low |
| `evals/results/evals.md` | ~60 | Low |
| fault-injection step (§5.3) | ~100 | Med |
| `packs/growth/` definitions + provenance | ~200 | High |
| `packs/growth/snippets/*.sql` | ~150 | High |
| `packs/growth/templates/` ×3 + pack.py | ~350 | High |
| new `check` rules + tests | ~120 | High |

## 9. Next steps
1. M0: Harbor installed; B0 on `spider2-dbt` MRR slice (no adapter work) → proves pipeline.
2. Read mrr-playbook, Fivetran stripe/zuora/recharge/shopify, dbt-ga4 → draft `definitions.md` (sources + traps) for review before code.
3. Arm K run; then pack; then T; then Databook-specific evals.
4. spider2-lite-local adapter; GA4 export decision.

## 10. Context / background research
- Coinbase (Armstrong, 2026-10-11): fine-tuned Qwen3.5-9B on internal data beat frontier on narrow fraud task.
- Ramp Labs Fast Ask: RL (GRPO, 100 steps, Prime Intellect) on Qwen3.5-35B-A3B spreadsheet-retrieval subagent; 3 tools, 15 turns, synthetic finance workbooks, 14 task types, exact-match reward; 66.3% vs Opus 4.6 61.9%, Haiku-level latency.
- Rejected directions: payments fraud (needs big-company data); self-invented tasks/generators (answers "in our head") → use externally defined benchmarks.

## Sources
- Harbor: https://docs.harborframework.com/ · adapters https://github.com/harbor-framework/harbor/tree/main/adapters
- Spider2: https://github.com/xlang-ai/Spider2
- DABStep: https://huggingface.co/datasets/adyen/DABstep
- Anthropic data plugin: https://github.com/anthropics/knowledge-work-plugins/tree/main/data
- dbt agent skills: https://github.com/dbt-labs/dbt-agent-skills · mrr-playbook: https://github.com/dbt-labs/mrr-playbook · dbt-ga4: https://github.com/Velir/dbt-ga4 · Fivetran zuora: https://github.com/fivetran/dbt_zuora
- Use cases: https://equals.com/use-cases/ · https://hex.tech/templates/
- Method: https://cs2680.seas.harvard.edu/assignments/
- Ramp: https://labs.ramp.com/research/prime-rl-post-training/

## 11. Build status (tracer bullet: Spider2-lite `local329`, 3 setups × 3 attempts, 4 graders: correct · cost · method (judge) · traceable (judge))
- I0 ✅ wiring: `evals/adapters/spider2-lite/` (Harbor std layout: fetch.sh pinned to Spider2 commit, src/spider2_lite/{adapter,main,compare}.py; compare.py = Spider2 compare copied verbatim, MIT) → oracle 1.0, nop 0.0 ("no answer file"); 10 tests in `evals/tests`. Gold for local329 = 1 (only `local329_a.csv`); data lives in `form_log`.
- Known limit: Docker Desktop kernel lacks CONFIG_NFT_FIB_INET → no network allowlist; mitigated by `disable_web_search` + flagging network commands in trajectories. Use a Linux/remote sandbox for clean claims.
- CC (`evals/run.sh evals/configs/cc.yaml`): 2/3, $0.11; miss = never opened `form_log`, substituted `/input`. CC+P v1: skill never invoked (2/3, miss = wrote session id not count) → description says "Load BEFORE any SQL/pandas query" + `when_to_use` → v2: invoked 3/3, 3/3 correct, $0.14. Track `skill invoked` per trial.
- Setup v2: no custom agent; all setups = Harbor built-in `claude-code`. `run.sh` → `prefetch.py` caches the Linux Claude Code build + `uv pip install --target` databook; configs bind-mount them read-only (`environment.mounts`, `${EVALS_RT}`), plus the databook skill → `~/.claude/skills`, `CLAUDE.md` → `/app` (now project-level, so re-baseline cc-p-t). Agent setup 24 s → 0.5–2.4 s. Local Docker only (remote sandboxes can't use host mounts).
- Next: I1 results notebook + judges → I3 Databook setup (CC+P+T).
