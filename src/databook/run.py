"""Run a notebook: compute blocks in dependency order, validate, and write results.json."""
from __future__ import annotations

import hashlib
import json
import re
import traceback
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

import duckdb
import pandas as pd

from databook.core import anchors
from databook.core.notebook import COMPUTE, INTERP, REF, Block, Diag, Notebook, bind_params, parse, resolve, sql_params
from databook.core.values import FORMATS, as_number, fmt, fmt_cell, to_json
from databook import history
from databook.engine import sheet as sheet_engine
from databook.project import NotebookRef, Project, schema_for

ROW_CAP = 1000
PARAM_OPTIONS = 50000
_PNAME = re.compile(r"^[a-z_][a-z0-9_]*$")
REGISTRY = json.loads((Path(__file__).parent / "components.json").read_text())
_STARTS = ("select", "with", "from", "values", "table", "pivot", "unpivot", "(")
_LITERAL = re.compile(r"(?<![\w.{])([₹$€£]\s?\d[\d,]*(?:\.\d+)?|\d[\d,]*(?:\.\d+)?\s?%|\d{1,3}(?:,\d{2,3})+(?:\.\d+)?|\d{3,}(?:\.\d+)?)")
_PII = re.compile(r"(^|_)(email|contact|phone|mobile|vpa|pan|aadhaar|card_number)($|_)")


def fingerprint(project: Project, nb_text: str, nb: Notebook, live: str = "") -> dict:
    """notebookHash: the notebook + its sheet models. dataHash: imports, time zone, source config and `live` (result
    hashes of blocks reading sources: a database has no file to hash, so what was read stands in for it)."""
    h = hashlib.sha256(nb_text.encode())
    for b in nb.blocks:
        if b.kind == "sheet" and isinstance(b.spec, dict) and (f := project.root / str(b.spec.get("file", ""))).is_file():
            h.update(f.read_bytes())
    data = json.dumps([project.manifest, project.sources], sort_keys=True, default=str) + project.config["timezone"] + live
    return {"notebookHash": h.hexdigest(), "dataHash": hashlib.sha256(data.encode()).hexdigest()}


def _q(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _fq(schema: str, name: str) -> str:
    return f"{_q(schema)}.{_q(name)}"


def _table_result(con, fq: str) -> dict:
    cols = [(c, t) for c, t, *_ in con.execute(f"DESCRIBE {fq}").fetchall()]
    n = con.execute(f"SELECT count(*) FROM {fq}").fetchone()[0]
    rows = con.execute(f"SELECT * FROM {fq} LIMIT {ROW_CAP}").fetchall()
    # Whole result, independent of row order (count + sum of row hashes): what run diffs compare, not the shown rows.
    h = con.execute(f"SELECT sum(hash(*COLUMNS(*))::HUGEINT) FROM {fq}").fetchall()[0][0]
    return {"columns": [{"name": c, "type": t} for c, t in cols], "rows": rows, "rowCount": n, "truncated": n > ROW_CAP,
            "hash": f"{n}:{h or 0}"}


def _top_level(con, sql: str) -> tuple[bool, bool]:
    """(has ORDER BY, picks rows arbitrarily: LIMIT / DISTINCT ON without ORDER BY) for the query's own top level.
    A statement DuckDB can't serialize (PIVOT …) counts as ordered if it says ORDER BY anywhere, so an author's
    order is never overridden."""
    try:
        j = json.loads(con.execute("SELECT json_serialize_sql(?)", [sql]).fetchall()[0][0])
        mods = None if j.get("error") else j["statements"][0]["node"].get("modifiers", [])
    except Exception:
        mods = None
    if mods is None:
        return bool(re.search(r"\border\s+by\b", sql, re.I)), False
    ordered = any(m["type"] == "ORDER_MODIFIER" for m in mods)
    picks = any(m["type"] in ("LIMIT_MODIFIER", "LIMIT_PERCENT_MODIFIER") or
                (m["type"] == "DISTINCT_MODIFIER" and m.get("distinct_on_targets")) for m in mods)
    return ordered, picks and not ordered


def _load_df(con, fq: str) -> pd.DataFrame:
    """Table → DataFrame; DECIMAL columns become exact Python Decimals (DuckDB's .df() would make floats)."""
    df = con.execute(f"SELECT * FROM {fq}").df()
    for c, t, *_ in con.execute(f"DESCRIBE {fq}").fetchall():
        if t.startswith("DECIMAL"):
            df[c] = pd.Series([r[0] for r in con.execute(f"SELECT {_q(c)} FROM {fq}").fetchall()],
                              dtype=object, index=df.index)
    return df


def _store_df(con, fq: str, df) -> None:
    if not isinstance(df, pd.DataFrame):
        raise TypeError("PY_NOT_DATAFRAME python block must `return` a pandas DataFrame (or {name: DataFrame}), "
                        f"got {type(df).__name__}")
    if isinstance(df.columns, pd.MultiIndex):
        raise TypeError("PY_BAD_COLUMNS returned DataFrame has multi-level columns; flatten them first")
    df = df.copy()
    if not isinstance(df.index, pd.RangeIndex) or any(n is not None for n in df.index.names):
        df = df.reset_index()                 # keep groupby keys instead of silently dropping the index
    df.columns = [str(c) for c in df.columns]
    if len(set(df.columns)) != len(df.columns):
        raise TypeError("PY_BAD_COLUMNS returned DataFrame has duplicate column names")
    casts = {}
    for c in df.columns:
        s = df[c]
        if isinstance(s.dtype, pd.PeriodDtype):
            df[c] = s.astype(str)
        elif s.dtype == object:
            vals = [v for v in s if v is not None and not (isinstance(v, float) and v != v)]
            if vals and all(isinstance(v, Decimal) for v in vals):
                scale = max(max(-v.as_tuple().exponent, 0) for v in vals)
                casts[c] = f"DECIMAL({18 if scale <= 6 else 38},{scale})"
                df[c] = s.map(lambda v: None if v is None else str(v))
            elif vals and not all(type(v) is type(vals[0]) for v in vals):
                df[c] = s.map(lambda v: None if v is None else str(v))
    con.register("__tb_py", df)
    sel = ", ".join(f"CAST({_q(c)} AS {casts[c]}) AS {_q(c)}" if c in casts else _q(c) for c in df.columns)
    con.execute(f"CREATE OR REPLACE TABLE {fq} AS SELECT {sel} FROM __tb_py")
    con.unregister("__tb_py")


_OUT_NAME = re.compile(r"^[A-Za-z0-9_]+$")


def _run_python(con, b: Block, nb_line: int, tz: str, schema: str, taken: set[str], params: dict) -> list[str]:
    """Run a python block. A DataFrame return → table `<id>`; a dict {name: DataFrame} → tables `<id>__<name>`
    (the first one is also `<id>`). → names of the named-output tables."""
    ns = {"pd": pd, "Decimal": Decimal, "TZ": tz, "params": dict(params)}
    for d in sorted(b.deps):
        ns[d] = _load_df(con, _fq(schema, d))
    have = {t for (t,) in con.execute("SELECT table_name FROM duckdb_tables() WHERE database_name = current_database() AND schema_name = ?", [schema]).fetchall()}
    for u in sorted(b.uses):
        if u not in have:
            raise BlockError("REF_UNKNOWN", f"{u}: block {u.split('__')[0]!r} returned no output named "
                                            f"{u.partition('__')[2]!r}", nb_line)
        ns[u] = _load_df(con, _fq(schema, u))
    for t in sorted(b.tables):
        ns[t] = _load_df(con, _fq("main", t))
    src = "def __tb_block__():\n" + "\n".join("    " + ln for ln in b.body.split("\n"))
    fname = f"<block {b.id}>"
    try:
        exec(compile(src, fname, "exec"), ns)
        out = ns["__tb_block__"]()
    except Exception as e:
        frames = [f for f in traceback.extract_tb(e.__traceback__) if f.filename == fname]
        line = nb_line + frames[-1].lineno - 2 if frames else nb_line   # src line 1 is the def header
        raise BlockError("PY_ERROR", f"{type(e).__name__}: {e}", line) from None
    if isinstance(out, dict):
        if not out:
            raise BlockError("PY_NOT_DATAFRAME", "returned an empty dict; return {name: DataFrame, …}", nb_line)
        for k in out:
            name = f"{b.id}__{k}"
            if not isinstance(k, str) or not _OUT_NAME.match(k):
                raise BlockError("PY_BAD_OUTPUTS", f"output name {k!r}: use letters, digits and _", nb_line)
            if name in taken:
                raise BlockError("PY_BAD_OUTPUTS", f"output {name!r} collides with a block or imported table", nb_line)
    items = list(out.items()) if isinstance(out, dict) else [(None, out)]
    try:
        for k, df in items:
            _store_df(con, _fq(schema, f"{b.id}__{k}" if k else b.id), df)
        if isinstance(out, dict):
            first = _fq(schema, f"{b.id}__{items[0][0]}")
            con.execute(f"CREATE OR REPLACE TABLE {_fq(schema, b.id)} AS SELECT * FROM {first}")
    except TypeError as e:
        code, _, msg = str(e).partition(" ")
        raise BlockError(code, msg, nb_line) from None
    return [f"{b.id}__{k}" for k, _ in items if k]


class BlockError(Exception):
    def __init__(self, code, msg, line=None):
        super().__init__(msg)
        self.code, self.line = code, line


def _single(res: dict, bid: str, col: str):
    """Value of res[col] for a 1-row result, else raise."""
    names = [c["name"] for c in res["columns"]]
    if col not in names:
        raise BlockError("REF_UNKNOWN", f"{bid} has no column {col!r} (columns: {', '.join(names)})")
    if res["rowCount"] != 1:
        raise BlockError("INTERP_MULTIROW", f"{bid}.{col} needs a 1-row result; {bid} has {res['rowCount']} rows")
    return res["rows"][0][names.index(col)], res["columns"][names.index(col)]["type"]


def _param_specs(nb: Notebook) -> dict[str, dict]:
    """Frontmatter `params: {name: {from: block.column, show?: block.column, default?, label?}}` → validated specs."""
    raw, out = nb.meta.get("params"), {}
    if raw is None:
        return out
    if not isinstance(raw, dict):
        nb.diags.append(Diag(1, "BAD_PARAM", "params must map a name to {from: block.column, default?, label?, show?}"))
        return out
    for name, sp in raw.items():
        m = REF.match(str(sp.get("from", ""))) if isinstance(sp, dict) else None
        if not (isinstance(name, str) and _PNAME.match(name)) or not m:
            nb.diags.append(Diag(1, "BAD_PARAM", f"param {name!r}: use a lower-case name and `from: block.column`"))
            continue
        if (b := nb.get(m[1])) is None or b.kind not in COMPUTE:
            nb.diags.append(Diag(1, "BAD_PARAM", f"param {name}: `from` must name a sql/python/sheet block, not {m[1]!r}"))
            continue
        show = REF.match(str(sp["show"])) if sp.get("show") is not None else None
        if sp.get("show") is not None and (not show or show[1] != m[1]):
            nb.diags.append(Diag(1, "BAD_PARAM", f"param {name}: `show` must be a column of {m[1]} (block.column)"))
            continue
        out[name] = {"label": str(sp.get("label") or name), "block": m[1], "col": m[2],
                     "show": show[2] if show else None, "default": sp.get("default")}
    return out


def _same(option, value) -> bool:
    """A picked/default value (JSON or YAML) equals an option (DuckDB-typed): numerically for numeric options."""
    if isinstance(option, bool) or not isinstance(option, (int, float, Decimal)):
        return str(option) == str(value)
    if isinstance(value, bool):
        return False
    try:                                             # exact: ids beyond 2**53 must not match a neighbour
        return Decimal(str(option)) == Decimal(str(value))
    except InvalidOperation:
        return False


def _param_value(con, schema: str, name: str, sp: dict, picked: dict, warn) -> dict:
    """Options from the `from` block; value = picked (if still an option) → default → first option. Sets the variable."""
    cols = _q(sp["col"]) + (f", {_q(sp['show'])}" if sp["show"] else "")
    try:
        rows = con.execute(f"SELECT DISTINCT {cols} FROM {_fq(schema, sp['block'])} WHERE {_q(sp['col'])} IS NOT NULL "
                           f"ORDER BY ALL LIMIT {PARAM_OPTIONS + 1}").fetchall()
    except duckdb.Error as e:
        raise BlockError("BAD_PARAM", f"param {name}: {str(e).splitlines()[0]}") from None
    opts: dict = {}
    for r in rows[:PARAM_OPTIONS]:
        opts.setdefault(r[0], r[-1])                 # first label wins when one value has several
    if not opts:
        raise BlockError("BAD_PARAM", f"param {name}: {sp['block']}.{sp['col']} has no values to pick from")
    if len(rows) > PARAM_OPTIONS:
        warn("PARAM_OPTIONS_TRUNCATED", f"param {name}: only the first {PARAM_OPTIONS} values can be picked")
    find = lambda v: next((o for o in opts if _same(o, v)), None)
    value = None
    if name in picked and (value := find(picked[name])) is None:
        warn("PARAM_VALUE_MISSING", f"param {name}: picked value {picked[name]!r} is no longer an option; using the default")
    if value is None and sp["default"] is not None and (value := find(sp["default"])) is None:
        warn("PARAM_DEFAULT_MISSING", f"param {name}: default {sp['default']!r} is not an option; using the first one")
    if value is None:
        value = next(iter(opts))
    con.execute(f'SET VARIABLE "{name}" = ?', [value])
    return {"name": name, "label": sp["label"], "value": to_json(value), "display": fmt_cell(opts[value]),
            "options": [[to_json(o), fmt_cell(t)] for o, t in opts.items()], "truncated": len(rows) > PARAM_OPTIONS,
            "py": value}


def run_notebook(project: Project, key: str | None = None) -> dict:
    ref = project.nb(key)
    text = ref.path.read_text()
    nb = parse(text)
    tables = set(project.manifest["tables"])
    nb.params = specs = _param_specs(nb)
    uses: dict[str, set[str]] = {}                       # block → params it reads (implicit dep on the `from` block)
    for b in nb.blocks:
        if b.kind not in ("sql", "python"):
            continue
        used = {n for *_, n in sql_params(b.body)} if b.kind == "sql" else set(specs) if _mentions(b.body, "params") else set()
        for n in sorted(used - specs.keys()):
            nb.diags.append(Diag(b.line, "PARAM_UNKNOWN", f"{b.id} uses ${n}, but the notebook declares no param {n!r} "
                                 "(frontmatter `params:`)", block=b.id))
        uses[b.id] = used & specs.keys()
        for n in sorted(uses[b.id]):
            if specs[n]["block"] == b.id:
                nb.diags.append(Diag(b.line, "CYCLE", f"{b.id} lists the options of param {n} and also reads it",
                                     block=b.id))
            else:
                b.deps.add(specs[n]["block"])
    picked, pvals = project.params(ref.key), {}
    order = resolve(nb, tables, frozenset(project.sources))
    for b in nb.blocks:
        b.tables = {t for t in tables if b.kind == "python" and _mentions(b.body, t)}
    results: dict[str, dict] = {}
    failed: set[str] = set()
    status: dict[str, dict] = {}
    with project.lock():
        con = project.connect(schema=ref.schema)
        try:
            # Removed blocks/notebooks must not leave stale tables behind. Block tables only ever live in a notebook
            # schema, so `main` keeps exactly the imported tables (older versions wrote blocks there).
            ids = {b.id for b in nb.blocks}
            live = {schema_for(k) for k in project.notebooks()}
            here = "WHERE database_name = current_database()"     # never an attached source's tables
            for sch, t in con.execute(f"SELECT schema_name, table_name FROM duckdb_tables() {here}").fetchall():
                if (sch == "main" and t not in tables) or (sch == ref.schema and t not in ids):
                    con.execute(f"DROP TABLE {_fq(sch, t)}")
            for (sch,) in con.execute(f"SELECT schema_name FROM duckdb_schemas() {here} AND starts_with(schema_name, 'nb_')").fetchall():
                if sch not in live:
                    con.execute(f"DROP SCHEMA {_q(sch)} CASCADE")
            down = project.attach_sources(con)                   # after cleanup: attached tables are never dropped
            blocked = {d.block for d in nb.diags if d.severity == "error" and d.block}
            for b in order:
                if b.kind not in COMPUTE:
                    continue
                bad = (b.deps & failed) or (b.id in blocked)
                if bad:
                    failed.add(b.id)
                    con.execute(f"DROP TABLE IF EXISTS {_fq(ref.schema, b.id)}")
                    status[b.id] = {"status": "skipped" if b.id not in blocked else "error",
                                    "error": f"depends on failed block(s): {', '.join(sorted(b.deps & failed))}"
                                    if b.id not in blocked else "see diagnostics"}
                    continue
                try:
                    if gone := sorted({r.split(".")[0] for r in b.reads if "." in r} & down.keys()):
                        raise BlockError("SOURCE_UNAVAILABLE", "; ".join(down[n] for n in gone))
                    extra = _compute(con, project, ref, b, results, tables | ids,
                                     {n: pvals[n]["py"] for n in uses.get(b.id, ())})
                    for code, msg in extra.pop("warnings", []):
                        nb.diags.append(Diag(b.line, code, msg, "warning", b.id))
                    results[b.id] = _table_result(con, _fq(ref.schema, b.id))
                    for name in extra.get("outputs", []):
                        results[name] = _table_result(con, _fq(ref.schema, name))
                    status[b.id] = {"status": "ok", **extra}
                    for n, sp in specs.items():          # options come from this block: settle the value now
                        if sp["block"] == b.id:
                            pvals[n] = _param_value(con, ref.schema, n, sp, picked, lambda c, m: nb.diags.append(
                                Diag(1, c, m, "warning", b.id)))
                except BlockError as e:
                    failed.add(b.id)
                    con.execute(f"DROP TABLE IF EXISTS {_fq(ref.schema, b.id)}")
                    nb.diags.append(Diag(e.line or b.line, e.code, str(e), block=b.id))
                    status[b.id] = {"status": "error", "error": f"{e.code}: {e}",
                                    **({"file": b.spec.get("file")} if b.kind == "sheet" and isinstance(b.spec, dict) else {})}
        finally:
            con.close()
    hints = _format_hints(nb)
    out_blocks = [_render(b, results, status, nb, hints) for b in nb.blocks]
    for o in out_blocks:                                  # reverse deps: which blocks read this one
        o["usedBy"] = [u["id"] for u in out_blocks if o["id"] in u["deps"] and u is not o]
    anchors.assign(out_blocks)
    for b in nb.blocks:
        if b.kind == "md":
            _check_prose(b, nb)
    errors = sum(d.severity == "error" for d in nb.diags)
    doc = {
        "notebook": ref.key,
        "path": ref.path.relative_to(project.root).as_posix(),
        **fingerprint(project, text, nb, json.dumps(
            {b.id: results[b.id]["hash"] if b.id in results else status.get(b.id, {}).get("error")
             for b in nb.blocks if any("." in r for r in b.reads)}, sort_keys=True)
            + json.dumps({n: v["value"] for n, v in pvals.items()}, sort_keys=True, default=str)),
        "ranAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "timezone": project.config["timezone"],
        "title": nb.meta.get("title") or next((ln[2:].strip() for b in nb.blocks if b.kind == "md"
                                                for ln in b.body.split("\n") if ln.startswith("# ")), "Notebook"),
        "meta": {k: v for k, v in nb.meta.items() if k in ("title", "description", "publish", "theme", "view")},
        "params": [{k: v for k, v in pvals[n].items() if k != "py"} for n in specs if n in pvals],
        "blocks": out_blocks,
        "diagnostics": [vars(d) for d in sorted(nb.diags, key=lambda d: d.line)],
        "ok": errors == 0,
    }
    ref.results_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = ref.results_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(doc, default=to_json, indent=1))
    tmp.replace(ref.results_path)
    history.save(ref.history_dir, doc)
    return doc


def _mentions(body: str, name: str) -> bool:
    return re.search(rf"(?<![\w.]){re.escape(name)}(?!\w)", body) is not None


def _compute(con, project: Project, nbr: NotebookRef, b: Block, results: dict, taken: set[str],
             params: dict | None = None) -> dict:
    if b.kind == "sql":
        sql = bind_params(b.body.strip().rstrip(";").strip())
        if not sql.lower().startswith(_STARTS):
            raise BlockError("SQL_ERROR", "sql blocks must be a single query (SELECT / WITH / FROM …)")
        ordered, arbitrary = _top_level(con, sql)
        fq = _fq(nbr.schema, b.id)
        # Unordered results are stored sorted by every column: parallel scans otherwise return a different order
        # each run, so shown rows, charts, CSVs and python inputs would change on an identical rerun.
        # Newlines keep a trailing `-- comment` from swallowing the wrapper.
        try:
            if ordered:
                raise LookupError
            con.execute(f"CREATE OR REPLACE TABLE {fq} AS SELECT * FROM (\n{sql}\n) ORDER BY ALL")
        except Exception:
            try:                                  # author's order, or a query/type the wrapper can't take
                con.execute(f"CREATE OR REPLACE TABLE {fq} AS {sql}")
            except Exception as e:
                raise BlockError("SQL_ERROR", project.redact(str(e).replace("\n", " "))[:500]) from None
        return {"warnings": [("UNORDERED_LIMIT", f"{b.id} uses LIMIT / DISTINCT ON without ORDER BY, so which rows "
                              "it keeps can change between runs; add an ORDER BY")]} if arbitrary else {}
    if b.kind == "python":
        outs = _run_python(con, b, b.line + 1, project.config["timezone"], nbr.schema, taken, params or {})
        return {"outputs": outs} if outs else {}
    spec = b.spec if isinstance(b.spec, dict) else {}
    inputs = {}
    for ref, src in (spec.get("inputs") or {}).items():
        if isinstance(src, str) and (m := REF.match(src)):
            if m[1] not in results:
                raise BlockError("REF_UNKNOWN", f"input {ref} reads {src!r}; only block outputs can feed a model")
            inputs[ref] = _single(results[m[1]], m[1], m[2])[0]
        elif isinstance(src, (int, float)) and not isinstance(src, bool):
            inputs[ref] = src
        else:
            raise BlockError("BAD_SPEC", f"input {ref}: value must be a number or block.column, got {src!r}")
    try:
        r = sheet_engine.run(spec, project.root, nbr.work_dir, b.id, inputs)
    except sheet_engine.SheetError as e:
        raise BlockError(e.code, str(e)) from None
    if r["errors"]:
        code, msg = r["errors"][0]
        more = f" (+{len(r['errors']) - 1} more)" if len(r["errors"]) > 1 else ""
        raise BlockError(code, msg + more)
    if not r["outputs"]:
        raise BlockError("BAD_SPEC", "sheet block needs at least one `outputs:` cell")
    row = {k: (float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else v) for k, v in r["outputs"].items()}
    _store_df(con, _fq(nbr.schema, b.id), pd.DataFrame([row]))
    return {"grid": r["grid"], "file": spec["file"]}


def _ref_value(ref: str, results: dict):
    m = REF.match(ref or "")
    if not m:
        raise BlockError("BAD_SPEC", f"{ref!r} is not a block.column reference")
    if m[1] not in results:
        raise BlockError("REF_UNKNOWN", f"{m[1]!r} has no result (missing or failed block)")
    return _single(results[m[1]], m[1], m[2])


def _format_hints(nb: Notebook) -> dict[tuple[str, str], str]:
    """(block, column) → format, collected from md {{…|fmt}}, kpi, table and chart specs."""
    h = {}
    for b in nb.blocks:
        s = b.spec
        if b.kind == "md":
            h.update({(m[1], m[2]): m[3] for m in INTERP.finditer(b.body) if m[3] in FORMATS})
        elif b.kind == "kpi" and isinstance(s, list):
            for it in s:
                if isinstance(it, dict) and it.get("format") in FORMATS:
                    for k in ("value", "compare"):
                        if isinstance(it.get(k), str) and (m := REF.match(it[k])):
                            h[(m[1], m[2])] = it["format"]
        elif b.kind in ("table", "chart") and isinstance(s, dict) and isinstance(s.get("data"), str):
            if isinstance(s.get("format"), dict):
                h.update({(s["data"], c): f for c, f in s["format"].items() if f in FORMATS})
            elif s.get("format") in FORMATS:
                ys = s.get("y") if isinstance(s.get("y"), list) else [s.get("y")]
                ys = [c for y in ys for c in ((lambda v: v if isinstance(v, list) else [v])(y.get("col"))
                                              if isinstance(y, dict) else [y])]
                h.update({(s["data"], y): s["format"] for y in ys if isinstance(y, str)})
    return h


def _render(b: Block, results: dict, status: dict, nb: Notebook, hints: dict) -> dict:
    out = {"id": b.id, "kind": b.kind, "line": b.line, "deps": sorted(b.deps), "reads": sorted(b.reads), "title": b.title,
           **({"auto": True} if b.auto else {})}

    def diag(e: BlockError):
        nb.diags.append(Diag(b.line, e.code, str(e), block=b.id))
        return {"error": f"{e.code}: {e}"}

    if b.kind in COMPUTE:
        r = results.get(b.id)
        out.update({"code": b.body, **status.get(b.id, {"status": "error"})})
        if r:
            out.update({"columns": r["columns"], "rows": [[to_json(v) for v in row] for row in r["rows"]],
                        "display": [[fmt(v, hints[(b.id, c["name"])]) if (b.id, c["name"]) in hints else fmt_cell(v)
                                     for v, c in zip(row, r["columns"])] for row in r["rows"]],
                        "rowCount": r["rowCount"], "truncated": r["truncated"], "rowsHash": r["hash"]})
            pii = [c["name"] for c in r["columns"] if _PII.search(c["name"].lower())]
            if pii:
                nb.diags.append(Diag(b.line, "PII_COLUMN_PUBLISHED", f"{b.id} output includes personal data columns "
                                     f"{pii}; its rows ship with exports — select only what the report needs",
                                     "warning", b.id))
        return out
    if b.kind == "md":
        def sub(m):
            try:
                v, t = _ref_value(f"{m[1]}.{m[2]}", results)
                if m[3] and m[3] not in FORMATS:
                    raise BlockError("BAD_SPEC", f"unknown format {m[3]!r}; use {', '.join(FORMATS)}")
                return f'<span class="tb-ref" data-ref="{m[1]}.{m[2]}">{fmt(v, m[3], t)}</span>'
            except BlockError as e:
                diag(e)
                return f'<span class="tb-ref tb-err" data-ref="{m[1]}.{m[2]}">#REF</span>'
        out["text"] = INTERP.sub(sub, b.body)
        return out
    s = b.spec
    if b.kind == "kpi":
        items = []
        for it in s if isinstance(s, list) else []:
            if not isinstance(it, dict):
                continue
            card = {"label": str(it.get("label", it.get("value", ""))), "ref": it.get("value"), "format": it.get("format")}
            try:
                v, t = _ref_value(it.get("value"), results)
                card["value"] = fmt(v, it.get("format"), t)
                if it.get("compare"):
                    c, _ = _ref_value(it["compare"], results)
                    card["compareRef"] = it["compare"]
                    a, z = as_number(v), as_number(c)
                    if a is not None and z is not None:
                        if it.get("format") == "pct":
                            card["delta"], card["deltaText"] = a - z, f"{(a - z) * 100:+.1f} pp"
                        elif z:
                            card["delta"], card["deltaText"] = a - z, f"{(a - z) / abs(z) * 100:+.1f}%"
            except BlockError as e:
                card.update(value="#REF", **diag(e))
            items.append(card)
        if not items:
            diag(BlockError("BAD_SPEC", "kpi block must be a YAML list of {label, value, format?, compare?}"))
        out["items"] = items
        return out
    if not isinstance(s, dict) or not isinstance(s.get("data"), str):
        out.update(diag(BlockError("BAD_SPEC", f"{b.kind} block needs `data: <block id>`")))
        return out
    r = results.get(s["data"])
    if not r:
        out.update(diag(BlockError("REF_UNKNOWN", f"{s['data']!r} has no result (missing or failed block)")))
        return out
    names = [c["name"] for c in r["columns"]]
    rows = list(r["rows"])
    if b.kind == "table":
        if s.get("sort"):
            col, _, direction = str(s["sort"]).partition(" ")
            if col not in names:
                out.update(diag(BlockError("CHART_COLUMN_MISSING", f"sort column {col!r} not in {s['data']}")))
                return out
            i = names.index(col)
            rows.sort(key=lambda row: (row[i] is None, row[i] if row[i] is not None else 0),
                      reverse=direction.strip().lower() == "desc")
            if direction.strip().lower() == "desc":   # keep NULLs last for desc too
                rows = [x for x in rows if x[i] is not None] + [x for x in rows if x[i] is None]
        cols = s.get("columns") or names
        missing = [c for c in cols if c not in names]
        if missing:
            out.update(diag(BlockError("CHART_COLUMN_MISSING", f"columns {missing} not in {s['data']}")))
            return out
        if (lk := s.get("link")) is not None:      # { column, param }: clicking a cell picks that value
            if not (isinstance(lk, dict) and lk.get("column") in cols and lk.get("param") in getattr(nb, "params", {})):
                out.update(diag(BlockError("BAD_SPEC", "link must be { column: <shown column>, param: <declared param> }")))
                return out
            out["link"] = {"column": lk["column"], "param": lk["param"],
                           "values": [to_json(row[names.index(lk["column"])]) for row in rows[:int(s.get("limit", ROW_CAP))]]}
        limit = int(s.get("limit", ROW_CAP))
        fmts = s.get("format") or {}
        idx = [names.index(c) for c in cols]
        out.update({"data": s["data"], "columns": cols, "rowCount": r["rowCount"], "truncated": r["truncated"],
                    "display": [[fmt(row[i], fmts.get(names[i])) if names[i] in fmts else fmt_cell(row[i])
                                 for i in idx] for row in rows[:limit]],
                    "numeric": [r["columns"][i]["type"].split("(")[0] in
                                ("BIGINT", "INTEGER", "DECIMAL", "DOUBLE", "HUGEINT", "FLOAT") for i in idx]})
        pii = [c for c in cols if _PII.search(c.lower())]
        if pii:
            nb.diags.append(Diag(b.line, "PII_COLUMN_PUBLISHED", f"table shows personal data columns {pii}; "
                                 "drop them or aggregate before publishing", "warning", b.id))
        return out
    return _chart(b, s, r, names, rows, out, diag, nb, results)


def _chart(b: Block, s: dict, r: dict, names: list, rows: list, out: dict, diag, nb: Notebook, results: dict) -> dict:
    """Validate a chart spec against components.json and emit labels, numeric series and Python-formatted displays."""
    def bad(code, msg):
        out.update(diag(BlockError(code, msg)))
        return out

    ctype, variant = s.get("type", "bar"), s.get("variant")
    if ctype in REGISTRY["aliases"]:
        ctype, variant = REGISTRY["aliases"][ctype][0], variant or REGISTRY["aliases"][ctype][1]
    reg = REGISTRY["chart"].get(ctype)
    if not reg:
        return bad("BAD_SPEC", f"chart type {ctype!r}; use {', '.join(REGISTRY['chart'])} (`databook components`)")
    variant = variant or next(iter(reg["variants"]))
    if variant not in reg["variants"]:
        return bad("BAD_SPEC", f"{ctype} variant {variant!r}; use {', '.join(reg['variants'])}")
    f = s.get("format")
    if f is not None and f not in FORMATS:
        return bad("BAD_SPEC", f"unknown format {f!r}; use {', '.join(FORMATS)}")
    x, ys = s.get("x"), s.get("y")
    ys = [ys] if isinstance(ys, (str, dict)) else ys
    if not isinstance(ys, list) or not ys:
        return bad("CHART_COLUMN_MISSING", f"chart needs `y:` column(s) of {s['data']} (has {', '.join(names)})")
    entries = []                                          # [{cols, mark, label}]; combo: y items are {col, mark, label?}
    for y in ys:
        if ctype == "combo":
            if not isinstance(y, dict) or y.get("mark") not in reg["marks"]:
                return bad("BAD_SPEC", f"combo y items need {{col, mark}} with mark one of {', '.join(reg['marks'])}; got {y!r}")
            cols = y.get("col")
            cols = cols if y["mark"] == "band" else [cols]
            if not (isinstance(cols, list) and len(cols) == (2 if y["mark"] == "band" else 1)
                    and all(isinstance(c, str) for c in cols)):
                return bad("BAD_SPEC", f"combo {y['mark']} needs col: {'[low, high]' if y['mark'] == 'band' else '<column>'}")
            entries.append({"cols": cols, "mark": y["mark"], "label": str(y.get("label") or " – ".join(cols))})
        elif isinstance(y, str):
            entries.append({"cols": [y], "mark": None, "label": y})
        else:
            return bad("BAD_SPEC", f"{ctype} y must be column name(s); per-series marks need type: combo")
    ys = [c for e in entries for c in e["cols"]]
    missing = [c for c in ys + ([] if ctype == "radial" else [x]) if c not in names]
    if missing:
        return bad("CHART_COLUMN_MISSING", f"chart columns {[m if m else 'x' for m in missing]} not in {s['data']} "
                                           f"(has {', '.join(names)})")
    if len(entries) > 1 and (reg["y"] == "1" or variant == "label"):
        return bad("BAD_SPEC", f"{ctype} {variant} takes one y column, got {ys}")
    if variant == "expanded" and len(entries) < 2:
        return bad("BAD_SPEC", "area expanded needs 2+ y columns (one column is always 100%)")
    series = []
    for e in entries:
        cur = {"name": e["label"], **({"mark": e["mark"]} if e["mark"] else {})}
        for k, y in zip(("values", "values2"), e["cols"]):
            raw = [row[names.index(y)] for row in rows]
            vals = [as_number(v) for v in raw]
            bad_i = next((i for i, (v, n) in enumerate(zip(raw, vals)) if v is not None and n is None), None)
            if bad_i is not None:
                return bad("CHART_NOT_NUMERIC", f"y column {y!r} has non-numeric value {raw[bad_i]!r} (row {bad_i + 1})")
            if reg["y"] == "1" and any(v is None or v < 0 for v in vals):
                i = next(i for i, v in enumerate(vals) if v is None or v < 0)
                return bad("CHART_NEGATIVE", f"{ctype} needs non-negative values; {y!r} row {i + 1} is {fmt(raw[i])}")
            cur[k], cur["raw" if k == "values" else "raw2"] = vals, raw
        disp = lambda v: fmt(v, f) if f else fmt_cell(v)
        if e["mark"] == "band":
            lo_hi = list(zip(cur["values"], cur["values2"]))
            i = next((i for i, (lo, hi) in enumerate(lo_hi) if lo is not None and hi is not None and lo > hi), None)
            if i is not None:
                return bad("CHART_BAND_ORDER", f"band {e['cols']} row {i + 1}: low {cur['raw'][i]} > high {cur['raw2'][i]}")
            cur["display"] = [f"{disp(a)} – {disp(z)}" for a, z in zip(cur["raw"], cur.pop("raw2"))]
        else:
            cur["display"] = [disp(v) for v in cur["raw"]]
        series.append(cur)
    if not isinstance(s.get("zero", True), bool):
        return bad("BAD_SPEC", f"zero must be true or false, got {s['zero']!r}")
    out.update({"data": s["data"], "type": ctype, "variant": variant, "title": s.get("title") or b.title,
                "description": s.get("description"), "x": x, "y": ys, "format": f, "zero": s.get("zero", True)})
    if ctype == "radial":
        if r["rowCount"] != 1:
            return bad("CHART_NEEDS_ONE_ROW", f"radial needs a 1-row block; {s['data']} has {r['rowCount']} rows")
        try:
            mx = as_number(_ref_value(s["max"], results)[0]) if isinstance(s.get("max"), str) else as_number(s.get("max", 1))
        except BlockError as e:
            return bad(e.code, str(e))
        if mx is None or mx <= 0:
            return bad("BAD_SPEC", f"radial max must be a positive number, got {s.get('max')!r}")
        if series[0]["values"][0] > mx:
            nb.diags.append(Diag(b.line, "CHART_ABOVE_MAX", f"radial value {series[0]['display'][0]} exceeds max; "
                                 "the ring is drawn full", "warning", b.id))
        out["max"] = mx
    else:
        labels = [fmt_cell(row[names.index(x)]) for row in rows]
        dup = sorted({v for v in labels if labels.count(v) > 1})
        if dup:
            return bad("CHART_DUPLICATE_X", f"x values repeat {dup[:5]}; aggregate in {s['data']} (GROUP BY {x}) "
                                            "so each x appears once")
        out["labels"] = labels
    if ctype in ("pie", "funnel"):
        sr = series[0]
        try:
            total = sum(sr["raw"])
        except TypeError:
            total = sum(sr["values"])
        if not total:
            return bad("CHART_NEGATIVE", f"{ctype} values of {ys[0]!r} sum to 0; nothing to draw")
        out["total"] = fmt(total, f) if f else fmt_cell(total)
        if ctype == "funnel":
            first = sr["values"][0]
            out["share"] = [fmt(v / first, "pct") if first else "—" for v in sr["values"]]
    for sr in series:
        del sr["raw"]
    out["series"] = series
    if r["truncated"]:
        nb.diags.append(Diag(b.line, "CHART_TRUNCATED", f"chart uses the first {ROW_CAP} of {r['rowCount']} rows",
                             "warning", b.id))
    return out


def _check_prose(b: Block, nb: Notebook) -> None:
    for n, line in enumerate(b.body.split("\n")):
        clean = re.sub(r"`[^`]*`", "", INTERP.sub("", line))
        for m in _LITERAL.finditer(clean):
            tok = m[1].strip()
            if re.fullmatch(r"(19|20)\d\d", tok):
                continue                                   # years are labels, not figures
            hard = any(ch in tok for ch in "%₹$€£,")
            nb.diags.append(Diag(b.line + n, "LITERAL_NUMBER_IN_PROSE",
                                 f"{tok!r} is typed into the text; compute it in a block and write "
                                 f"{{{{block.column}}}} so it can't go stale", "error" if hard else "warning", b.id))
        for m in re.finditer(r"\{\{.*?\}\}", re.sub(r"`[^`]*`", "", line)):
            if not INTERP.fullmatch(m[0]):                 # e.g. {{t[2].n}}: not a ref, would render as raw text
                nb.diags.append(Diag(b.line + n, "BAD_REF", f"{m[0]!r} is not a reference; use {{{{block.column | fmt}}}} "
                                     "on a 1-row block (pick the row in SQL, not with [n])", "error", b.id))
