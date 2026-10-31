"""Spider2-lite (local SQLite tasks) → Harbor task directories. CLI: main.py.

Reads the pinned Spider2 files from evals/.cache/spider2/ (see fetch.sh): spider2-lite.jsonl (questions),
spider2lite_eval.jsonl (ignore_order / condition_cols), gold/<id>[_x].csv, localdb/<db>.sqlite. Only `local*` ids
(SQLite) without external_knowledge are supported; BigQuery/Snowflake tasks are refused.
"""
from __future__ import annotations

import json
import shutil
import sqlite3
from pathlib import Path
from string import Template

from . import compare  # gold resolution must match the grader exactly
from . import olist

HERE = Path(__file__).resolve().parent
TEMPLATE = HERE / "task-template"
BUNDLE_TEMPLATE = HERE / "task-template-bundle"
# Bundles: several Spider2 questions on one db asked as a single request (questions verbatim; only the intro is ours),
# answers /app/answers/q<N>.csv, each graded by Spider2's compare against its own gold.
BUNDLES = {
    "log-web-funnel": {
        "ids": ["local329", "local330", "local331", "local360"],
        "intro": "our website's logs. We want to understand how visitors move through the site — where sessions "
                 "start and end, which paths they take, and how they reach registration and conversion. Answer these "
                 "four questions:",
    },
    # Spider2 ids mixed with our own questions (olist.Question: text + reference gold); "db" overrides the Spider2 db
    **olist.BUNDLES,
}
EVALS = HERE.parents[3]
CACHE = EVALS / ".cache" / "spider2"


def _jsonl(path: Path) -> dict[str, dict]:
    return {r["instance_id"]: r for r in (json.loads(l) for l in path.read_text().splitlines() if l.strip())}


def _render(template: Path, d: Path, vals: dict) -> None:
    if d.exists():
        shutil.rmtree(d)
    for src in template.rglob("*"):
        if src.is_file():
            dst = d / src.relative_to(template)
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_text(Template(src.read_text()).substitute(vals))
            dst.chmod(src.stat().st_mode)


def _source(iid: str, cache: Path) -> tuple[dict, dict, Path, list[Path]]:
    """(task row, eval standard, db path, gold paths) for one local task; refuses unsupported/missing ones."""
    if not iid.startswith("local"):
        raise SystemExit(f"{iid}: only local SQLite tasks are supported (got a cloud-warehouse task)")
    tasks, standards = _jsonl(cache / "spider2-lite.jsonl"), _jsonl(cache / "spider2lite_eval.jsonl")
    if iid not in tasks:
        raise SystemExit(f"{iid}: not in spider2-lite.jsonl")
    t, std = tasks[iid], {k: v for k, v in standards.get(iid, {}).items() if k in ("condition_cols", "ignore_order")}
    if t.get("external_knowledge"):
        raise SystemExit(f"{iid}: external_knowledge documents are not supported yet")
    db = cache / "localdb" / f"{t['db']}.sqlite"
    golds, _ = compare.gold_paths(cache / "gold", iid)
    if not db.exists() or not golds:
        raise SystemExit(f"{iid}: missing {db if not db.exists() else 'gold csv'} — run fetch.sh first")
    return t, std, db, golds


def make_task(iid: str, out: Path, cache: Path = CACHE) -> Path:
    t, std, db, golds = _source(iid, cache)
    vals = {"instance_id": iid, "db": t["db"], "question": t["question"].strip(),
            "commit": (cache / "COMMIT").read_text().strip(),
            "ignore_order": json.dumps(bool(std.get("ignore_order", False))),
            "condition_cols": json.dumps(std.get("condition_cols") or [])}
    d = out / iid
    _render(TEMPLATE, d, vals)
    (d / "environment" / "data").mkdir(parents=True)
    shutil.copy2(db, d / "environment" / "data" / db.name)
    shutil.copy2(HERE / "compare.py", d / "tests" / "compare.py")
    (d / "tests" / "eval.json").write_text(json.dumps(std))
    (d / "tests" / "gold").mkdir()
    for g in golds:
        shutil.copy2(g, d / "tests" / "gold" / g.name)
    shutil.copy2(golds[0], d / "solution" / "gold.csv")
    return d


def make_bundle(name: str, out: Path, cache: Path = CACHE, bundles: dict = BUNDLES) -> Path:
    if name not in bundles:
        raise SystemExit(f"{name}: unknown bundle (known: {', '.join(bundles)})")
    items, intro, db_name = bundles[name]["ids"], bundles[name]["intro"], bundles[name].get("db")
    spider = {i: _source(i, cache) for i in items if isinstance(i, str)}
    dbs = {db for _, _, db, _ in spider.values()} if not db_name else {cache / "localdb" / f"{db_name}.sqlite"}
    if len(dbs) != 1:
        raise SystemExit(f"{name}: questions must share one db, got {sorted(p.stem for p in dbs)}")
    db = dbs.pop()
    if not db.exists():
        raise SystemExit(f"{name}: missing {db} — run fetch.sh first")
    ids = [i if isinstance(i, str) else i.id for i in items]
    qs = {f"q{n}": iid for n, iid in enumerate(ids, 1)}
    text = [spider[i][0]["question"].strip() if isinstance(i, str) else i.text for i in items]
    ours = [i for i in ids if i not in spider]
    vals = {"name": name, "db": db.stem, "intro": intro, "commit": (cache / "COMMIT").read_text().strip(),
            "ids": ", ".join(ids), "ids_json": json.dumps(ids),
            "description": f"Spider2-lite bundle {name}: {', '.join(ids)} on local SQLite db `{db.stem}` asked as one "
                           f"request" + (f" ({', '.join(ours)}: ours, gold from adapter olist.py)" if ours else ""),
            "questions": "\n".join(f"{n}. {t}" for n, t in enumerate(text, 1)),
            "answer_files": ", ".join(f"`/app/answers/{q}.csv`" for q in qs)}
    d = out / name
    _render(BUNDLE_TEMPLATE, d, vals)
    (d / "environment" / "data").mkdir(parents=True)
    shutil.copy2(db, d / "environment" / "data" / db.name)
    shutil.copy2(HERE / "compare.py", d / "tests" / "compare.py")
    (d / "tests" / "bundle.json").write_text(json.dumps({"questions": qs}))
    (d / "tests" / "gold").mkdir()
    (d / "solution" / "answers").mkdir()
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        for q, item in zip(qs, items):
            if isinstance(item, str):
                _, std, _, golds = spider[item]
            else:                                 # our question: gold from its reference code
                std, golds = item.standard, [d / "tests" / "gold" / f"{item.id}.csv"]
                item.gold(con).to_csv(golds[0], index=False)
            (d / "tests" / f"eval_{qs[q]}.json").write_text(json.dumps(std))
            for g in golds:
                if g.parent != d / "tests" / "gold":
                    shutil.copy2(g, d / "tests" / "gold" / g.name)
            shutil.copy2(golds[0], d / "solution" / "answers" / f"{q}.csv")
    finally:
        con.close()
    return d


class Spider2LiteAdapter:
    def __init__(self, output_dir: Path, limit: int | None = None, overwrite: bool = False,
                 task_ids: list[str] | None = None, cache: Path = CACHE):
        self.output_dir, self.limit, self.overwrite, self.task_ids, self.cache = output_dir, limit, overwrite, task_ids, cache

    def eligible_ids(self) -> list[str]:  # upstream jsonl order
        return [i for i, t in _jsonl(self.cache / "spider2-lite.jsonl").items()
                if i.startswith("local") and not t.get("external_knowledge")]

    def run(self) -> list[Path]:
        ids = self.task_ids or self.eligible_ids()  # explicit ids are validated (and refused) by make_task
        done = []
        for iid in ids[: self.limit] if self.limit is not None else ids:
            if (self.output_dir / iid).exists() and not self.overwrite:
                print(f"{iid}: exists, skipped (use --overwrite)")
                continue
            done.append(make_task(iid, self.output_dir, self.cache))
            print(done[-1])
        return done
