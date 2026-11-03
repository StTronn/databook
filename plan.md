# Databook data agent: tracer-bullet plan

One thin path through every layer on **one task** (Spider2-lite `local329`), measured end to end, then widened. Details and background live in `data-agent.md`.

## 1. Outcome
A user asks a data question about their own data in Claude Code and gets:
1. a **correct** answer (the playbook's job),
2. a **Databook notebook** that shows how it was computed, which they can check, comment on, and rerun (Databook's job).

Claim to prove, on externally defined tasks with an untouched grader:
- **Playbook:** CC+P ≥ CC on correctness, at a similar cost.
- **Databook:** CC+P+T matches CC+P on correctness, and only CC+P+T produces answers that are traceable, catch faults, survive review, and rerun on new data.

## 2. The shape
```
task (fixed)          setup (only thing that varies)        Harbor trial                  graders                 results
instruction.md   ──▶  CC      plain Claude Code        ──▶  docker, 3 attempts      ──▶  A correct (Spider2)  ──▶  evals.md (notebook)
data + gold           CC+P    + playbook skill              answer.csv + /app           B process (trajectory)    log.md (one change → result)
tests/ (hidden)       CC+P+T  + databook CLI/skill         trajectory (ATIF), cost     C trust (variants)
```
Validity on every task: oracle = 1, nop = 0; infra errors are rerun; timeouts count as 0.

## 3. User journey → what proves each step
| # | User journey step | Product piece | Eval that proves it | Kind |
|---|---|---|---|---|
| 1 | Asks a question over their data in Claude Code | model + playbook | Spider2 grader: reward 0/1, pass@1, pass^3; cost, turns | A, B |
| 2 | Agent works *inside* a notebook: schema → SQL blocks → `check` → answer from a block | Databook runtime | `answer_from_block` ≥ 90 %, `side_script` ≤ 10 %, check-fail-then-fix | B |
| 3 | Data has a trap (duplicate join, wrong type) | `check` rules | C1 fault variant of the task: caught + fixed; no-fault control has no false alarms | C1 |
| 4 | Opens the viewer, clicks a number → sees its query | artifact | C4 judge sees only the artifact, must find the source of each number and a planted wrong one | C4 |
| 5 | Comments "per user, not per session" → agent fixes it | review loop | C2: comment injected, new gold2 (two independent implementations agree) | C2 |
| 6 | New export → rerun → `diff` explains the change | rerun + diff | C3: next-period data, gold recomputed, diff flags exactly what changed | C3 |

Steps 1–2 hold for any benchmark task; steps 3–6 are variants built from the same task, with nothing invented beyond gold2.

## 4. Increments (XP: each ends with a run and a result line in `log.md`)
| Inc | Scope | Done when | LOC, Cx |
|---|---|---|---|
| I0 ✅ | Harbor wiring, adapter, 3 setups; setup v2 (built-in `claude-code` + mounts) | oracle 1 / nop 0; CC 2/3, CC+P 3/3, CC+P+T 3/3 (old CLAUDE.md, re-baseline) | done |
| I1 | Results notebook `evals/results/evals.md` over `jobs/*/result.json` | A + cost table per setup, with trial links | ~60, Low |
| I2 | `evals/analyze.py`: B metrics from trajectories + `answer_from_block` recheck | B columns in the table; classifier tests | ~120, Med |
| I3 | Steer, don't summarise: `databook export --block <id> --csv` + skill rule "answer comes from a block" | B: `answer_from_block` ≥ 90 % on CC+P+T | ~120, Med |
| I4 | C1: `local329-fault-dupjoin` variant + no-fault control + `ROW_GROWTH` check rule | fault caught on T; plain-SQL CC+P result reported alongside | ~100, High |
| I5 | C4: artifact-only judge with a planted wrong number | judge accuracy, T vs CC+P transcript | ~80, Med |
| I6 | C2 + C3 on local329 (gold2, next-period data) | review fixed in one round; diff correct | ~120, High |
| I7 | Widen: 4 local funnel tasks → MRR (Spider2-DBT) → customer 360; DABStep for scale | same table per slice, paired per-task comparison with CI | ~30 per slice |

**Tracer bullet is done** when `local329` has one row per setup with A, B and C1–C4 filled in, each backed by job and trial links.

## 5. Rules
- Same task for every setup; only `skills:` and databook mounts differ between `evals/configs/cc*.yaml`.
- One change per run (playbook, Databook or eval, never two); new job name; the grader is never edited to pass a run (grader bug → fix the test + `harbor job regrade`).
- Contamination: the playbook carries definitions, never copied package models; contaminated tasks reported separately.
- Limits: one task is a demo, not evidence; ~37 tasks detect only ≥ 10–15 point gaps; benchmarks don't measure real-user value.
