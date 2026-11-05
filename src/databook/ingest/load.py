"""Import pipeline: read → detect pack → type every column → load into DuckDB → record in import.json."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from databook.ingest import types as T
from databook.ingest.read import RawTable, read_file, snake
from databook.packs import DetectError, Match, detect
from databook.project import Project


@dataclass
class Report:
    tables: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _column_plan(t: RawTable, m: Match | None, overrides: dict[str, str], rep: Report):
    """→ list of (column, duckdb_type, converter, converter_name, source) or None if a column is ambiguous."""
    plan, ok = [], True
    pack_cols = {}
    if m:
        pack_cols = {**m.spec.columns, **(m.spec.json_columns if t.minor_units else {})}
    for j, col in enumerate(t.headers):
        if col in overrides:
            name, src = overrides[col], "--types"
        elif col in pack_cols:
            name, src = pack_cols[col], m.label
        else:
            try:
                name, why = T.infer([r[j] for r in t.rows])
                src = f"inferred: {why}"
            except T.Ambiguous as e:
                rep.errors.append(f"{e.code} {t.source} column {col}: {e}")
                ok = False
                continue
        try:
            dtype, fn = T.resolve(name)
        except ValueError as e:
            rep.errors.append(f"{t.source} column {col}: {e}")
            ok = False
            continue
        plan.append((col, dtype, fn, name, src))
    return plan if ok else None


def _convert(t: RawTable, plan, tz: ZoneInfo, rep: Report) -> list[list] | None:
    idx = {c: j for j, c in enumerate(t.headers)}
    out, bad = [], {}
    for i, r in enumerate(t.rows):
        ctx = T.Ctx(tz, t.minor_units, dict(zip(t.headers, r)))
        row = []
        for col, _, fn, _, _ in plan:
            v = r[idx[col]]
            if v is None or (isinstance(v, str) and not v.strip()):
                row.append(None)
                continue
            try:
                row.append(fn(v, ctx))
            except ValueError as e:
                bad.setdefault(col, []).append(f"row {i + 1}: {e}")
                row.append(None)
        out.append(row)
    for col, msgs in bad.items():
        more = f" (+{len(msgs) - 3} more)" if len(msgs) > 3 else ""
        rep.errors.append(f"TYPE_MISMATCH {t.source} column {col}: {'; '.join(msgs[:3])}{more}; "
                          f"pass --types {col}=<type> to override")
    return None if bad else out


def import_files(project: Project, paths: list[Path], forced: str | None = None,
                 overrides: dict[str, str] | None = None, name: str | None = None) -> Report:
    rep, overrides = Report(), {snake(k): v for k, v in (overrides or {}).items()}
    tz = ZoneInfo(project.config["timezone"])
    staged: dict[str, dict] = {}          # table → {plan, rows, files, match, warnings}
    for p in paths:
        label = str(p.resolve().relative_to(project.root)) if p.resolve().is_relative_to(project.root) else str(p)
        if p.suffix.lower() == ".parquet":
            tname = name or snake(p.stem)
            staged.setdefault(tname, {"parquet": p, "files": [], "warnings": []})["files"].append(
                {"path": label, "sha256": _sha(p)})
            continue
        try:
            raws = read_file(p, label)
        except Exception as e:  # unreadable file: report and continue with the others
            rep.errors.append(f"{label}: cannot read ({type(e).__name__}: {e})")
            continue
        if not raws:
            rep.warnings.append(f"{label}: no data found")
        for t in raws:
            rep.warnings += [f"{t.source}: {w}" for w in t.warnings]
            try:
                m, hint = detect(t.headers, t.entity, forced)
            except DetectError as e:
                rep.errors.append(f"{t.source}: {e}")
                continue
            if hint:
                rep.warnings.append(f"{t.source}: {hint}")
            if m and m.spec.prepare:
                n = len(t.warnings)
                m.spec.prepare(t)
                rep.warnings += [f"{t.source}: {w}" for w in t.warnings[n:]]
            plan = _column_plan(t, m, overrides, rep)
            if plan is None:
                continue
            rows = _convert(t, plan, tz, rep)
            if rows is None:
                continue
            tname = name or (m.spec.table if m else t.table or snake(Path(t.source.split("#")[0]).stem +
                                                           ("_" + t.source.split("#")[1] if "#" in t.source else "")))
            st = staged.setdefault(tname, {"plan": plan, "rows": [], "files": [], "match": m, "warnings": []})
            if [(c, d) for c, d, *_ in st["plan"]] != [(c, d) for c, d, *_ in plan]:
                rep.errors.append(f"SCHEMA_MISMATCH {t.source}: columns/types differ from other files for "
                                  f"table {tname}; import it separately with --name")
                continue
            if m and not m.spec.key and st["rows"]:   # keyless (lines, events, ad rows): never drop, but flag overlap
                prev = set(map(tuple, st["rows"]))
                if dup := sum(tuple(r) in prev for r in rows):
                    rep.warnings.append(f"{t.source}: {dup} row(s) identical to rows of another file in {tname}; "
                                        "overlapping exports double-count — import non-overlapping date ranges")
            st["rows"] += rows
            st["files"].append({"path": label, "sha256": _sha(p), "rows": len(rows)})
    if not staged:
        return rep
    manifest = project.manifest
    with project.lock():
        con = project.connect()
        try:
            for tname, st in staged.items():
                prev = manifest["tables"].get(tname)
                if prev and {f["path"] for f in prev["files"]} - {f["path"] for f in st["files"]}:
                    rep.warnings.append(f"table {tname} replaced (was from {', '.join(f['path'] for f in prev['files'])})")
                entry = _load(con, tname, st, rep)
                manifest["tables"][tname] = entry
                rep.tables.append({"table": tname, **entry})
        finally:
            con.close()
        project.save_manifest(manifest)
    return rep


def _load(con, tname: str, st: dict, rep: Report) -> dict:
    q = f'"{tname}"'
    if "parquet" in st:
        con.execute(f"CREATE OR REPLACE TABLE {q} AS SELECT * FROM read_parquet(?)", [str(st["parquet"])])
        cols = [{"name": c, "type": t, "source": "parquet"} for c, t, *_ in con.execute(f"DESCRIBE {q}").fetchall()]
        return {"files": st["files"], "source": "parquet", "rows": con.execute(f"SELECT count(*) FROM {q}").fetchone()[0],
                "columns": cols}
    plan, rows, m = st["plan"], st["rows"], st["match"]
    key = [plan.index(next(p for p in plan if p[0] == k)) for k in m.spec.key] \
        if m and m.spec.key and all(any(p[0] == k for p in plan) for k in m.spec.key) else None
    if key:
        seen, uniq, conflicts = {}, [], 0
        for r in rows:
            k = tuple(r[i] for i in key)
            if k in seen:
                conflicts += seen[k] != r
                continue
            seen[k] = r
            uniq.append(r)
        if len(uniq) != len(rows):
            rep.warnings.append(f"{tname}: dropped {len(rows) - len(uniq)} duplicate row(s) by key "
                                f"({', '.join(m.spec.key)})" + (f"; {conflicts} had differing values, first kept"
                                                                 if conflicts else ""))
        rows = uniq
    df = pd.DataFrame(rows, columns=[p[0] for p in plan], dtype=object)
    con.register("__tb_src", df)
    sel = ", ".join(f'CAST("{c}" AS {d}) AS "{c}"' for c, d, *_ in plan)
    con.execute(f"CREATE OR REPLACE TABLE {q} AS SELECT {sel} FROM __tb_src")
    con.unregister("__tb_src")
    return {"files": st["files"], "source": m.label if m else "generic", "rows": len(rows),
            "columns": [{"name": c, "type": d, "as": n, "source": s} for c, d, _, n, s in plan]}
