"""tracebook CLI. Output is compact text for agents; --json for machines. Exit 1 = diagnostics/errors."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from tracebook.core.values import fmt_cell, to_json
import duckdb

from tracebook import workspace
from tracebook.project import (NB_DIR, RESERVED_SOURCES, SOURCE_NAME, SOURCE_TYPES, SYSTEM_SCHEMAS, Project,
                               ProjectError)
from tracebook.workspace import new_notebook

PKG = Path(__file__).parent


def _out(args, data, text: str) -> None:
    print(json.dumps(data, default=to_json, indent=1) if args.json else text)


def _table(headers: list[str], rows: list[list[str]], numeric: list[bool] | None = None) -> str:
    w = [max([len(h), *(len(r[i]) for r in rows)]) for i, h in enumerate(headers)]
    num = numeric or [False] * len(headers)
    line = lambda r: "  ".join(c.rjust(w[i]) if num[i] else c.ljust(w[i]) for i, c in enumerate(r)).rstrip()
    return "\n".join([line(headers), line(["─" * x for x in w]), *map(line, rows)])


def cmd_init(args):
    from tracebook.packs import packs, templates
    root = Path(args.dir).resolve()
    if (root / ".tracebook").exists():
        raise ProjectError(f"{root} is already a tracebook project")
    tpl = None
    if args.template:
        tpl = templates().get(args.template)
        if not tpl:
            raise ProjectError(f"unknown template {args.template!r}; available: {', '.join(templates()) or 'none'}")
    tz = args.tz or next((p.timezone for p in packs().values() if tpl and tpl.is_relative_to(p.templates)), None) or "UTC"
    try:
        ZoneInfo(tz)
    except (ZoneInfoNotFoundError, ValueError):
        raise ProjectError(f"unknown time zone {tz!r} (use an IANA name like Asia/Kolkata)")
    (root / "data").mkdir(parents=True, exist_ok=True)
    p = Project(root)
    p.dir.mkdir()
    p.save_config({"timezone": tz})
    created, _ = new_notebook(p, args.template or "untitled", tpl, args.demo) if not p.notebooks() else ([], [])
    _out(args, {"root": str(root), "timezone": tz, "created": created},
         f"initialized {root} (timezone {tz})\n  created: {', '.join(created) or '-'}\n"
         f"next: tracebook import data/*  →  tracebook schema  →  edit {created[0] if created else 'the notebook'}"
         "  →  tracebook check")


def cmd_new(args):
    from tracebook.packs import templates
    p = Project.find()
    tpl = templates().get(args.template) if args.template else None
    if args.template and not tpl:
        raise ProjectError(f"unknown template {args.template!r}; available: {', '.join(templates()) or 'none'}")
    created, skipped = new_notebook(p, args.name.removesuffix(".md").removeprefix(f"{NB_DIR}/"), tpl)
    _out(args, {"created": created, "skipped": skipped}, f"created: {', '.join(created)}"
         + (f"\nkept existing: {', '.join(skipped)}" if skipped else ""))


def cmd_import(args):
    from tracebook.ingest.load import import_files
    p = Project.find()
    overrides = {}
    for t in args.types or []:
        for pair in t.split(","):
            col, _, typ = pair.partition("=")
            if not typ:
                raise ProjectError(f"--types expects col=type, got {pair!r}")
            overrides[col.strip()] = typ.strip()
    paths = [Path(x) for x in args.files]
    missing = [str(x) for x in paths if not x.is_file()]
    if missing:
        raise ProjectError(f"file(s) not found: {', '.join(missing)}")
    rep = import_files(p, paths, args.as_, overrides, args.name)
    lines = [f"imported {len(rep.tables)} table(s) (timezone {p.config['timezone']})"]
    if rep.tables:
        lines.append(_table(["table", "source", "rows", "cols", "files"],
                            [[t["table"], t["source"], f"{t['rows']:,}", str(len(t["columns"])),
                              ", ".join(f["path"] for f in t["files"])] for t in rep.tables],
                            [False, False, True, True, False]))
    lines += ["warnings:" if rep.warnings else "warnings: (none)", *("  ⚠ " + w for w in rep.warnings)]
    lines += ["errors:" if rep.errors else "errors: (none)", *("  ✗ " + e for e in rep.errors)]
    _out(args, vars(rep), "\n".join(lines))
    return 1 if rep.errors else 0


def cmd_schema(args):
    p = Project.find()
    m = p.manifest["tables"]
    if args.table:
        m = {k: v for k, v in m.items() if k in args.table}
        if not m:
            raise ProjectError(f"no imported table named {', '.join(args.table)}")
    lines = []
    for name, t in sorted(m.items()):
        lines.append(f"{name}  ({t['source']}, {t['rows']:,} rows, from {', '.join(f['path'] for f in t['files'])})")
        lines += [f"  {c['name']:<24} {c['type']:<14} {c.get('source', '')}" for c in t["columns"]]
    nbs = p.notebooks()
    rp = p.nb(args.nb).results_path if args.nb or len(nbs) == 1 else None
    res = json.loads(rp.read_text()) if rp and rp.exists() else {"blocks": []}
    blk = [b for b in res["blocks"] if b.get("columns") and b["kind"] in ("sql", "python", "sheet")]
    if blk and not args.table:
        lines.append("block outputs (from last check):")
        lines += [f"  {b['id']:<20} {b['rowCount']:,} rows  [{', '.join(c['name'] for c in b['columns'])}]" for b in blk]
    src = workspace.source_tables(p) if not args.table else {}
    for name, s in src.items():
        lines.append(f"source {name} ({s['type']}, read-only; query as {name}.<schema>.<table>)"
                     + (f"  ⚠ unavailable: {s['error']}" if s.get("error") else ""))
        for t in s.get("tables", []):
            lines.append(f"  {t['name']}")
            lines += [f"    {c['name']:<22} {c['type']}" for c in t["columns"]]
        if s.get("more"):
            lines.append(f"  … {s['more']} more table(s); `tracebook query` information_schema to see them")
    _out(args, {"tables": m, "sources": src},
         "\n".join(lines) or "(no tables imported; run `tracebook import <files>` or `tracebook source add`)")


def cmd_source(args):
    p = Project.find()
    srcs = p.sources
    if args.action == "list":
        _out(args, {"sources": srcs}, "\n".join(f"{n}  {s['type']}  " + (f"${s['env']}" if s.get("env") else s["path"])
                                                for n, s in srcs.items()) or "no sources; `tracebook source add`")
        return 0
    if not args.name:
        raise ProjectError(f"usage: tracebook source {args.action} <name> …")
    if args.action == "remove":
        if srcs.pop(args.name, None) is None:
            raise ProjectError(f"no source {args.name!r}")
        p.save_sources(srcs)
        print(f"removed source {args.name}")
        return 0
    if not SOURCE_NAME.match(args.name) or args.name in RESERVED_SOURCES or args.name.startswith("nb_"):
        raise ProjectError(f"source name {args.name!r}: use lower-case letters, digits and _ (not main, data, "
                           "memory, system, temp or nb_…)")
    if args.name in srcs:
        raise ProjectError(f"source {args.name!r} exists; `tracebook source remove {args.name}` first")
    if args.type not in SOURCE_TYPES:
        raise ProjectError(f"--type must be one of {', '.join(SOURCE_TYPES)}")
    if bool(args.env) == bool(args.path) or (args.path and args.type in ("postgres", "mysql")):
        raise ProjectError("give --env VAR (a URL or path held in an environment variable; required for postgres/mysql) "
                           "or --path FILE (sqlite/duckdb files)")
    s = {"type": args.type, **({"env": args.env} if args.env else {"path": args.path})}
    con = duckdb.connect()                # test it before saving
    try:
        p.attach(con, args.name, s)
        n = con.execute("SELECT count(*) FROM duckdb_tables() WHERE database_name = ? AND schema_name NOT IN "
                        "(SELECT unnest(?))", [args.name, list(SYSTEM_SCHEMAS)]).fetchone()[0]
    except ProjectError:
        raise
    except Exception as e:
        raise ProjectError(f"cannot attach {args.name}: " +
                           p.redact(f"{type(e).__name__}: {str(e).splitlines()[0]}", {args.name: s})) from None
    finally:
        con.close()
    p.save_sources({**srcs, args.name: s})
    print(f"added source {args.name} ({args.type}, {n} table(s)); read-only. `tracebook schema` lists its tables")


def cmd_query(args):
    p = Project.find()
    nbs = p.notebooks()                  # bare block names resolve in the chosen (or only) notebook, then `main`
    schema = p.nb(args.nb).schema if args.nb or len(nbs) == 1 else None
    with p.lock():                       # wait for a running check/dev rerun: DuckDB refuses readers while it writes
        con = p.connect(read_only=True, schema=schema)
        try:
            for name, err in p.attach_sources(con).items():
                print(f"⚠ source {name} unavailable: {err}", file=sys.stderr)
            try:
                cur = con.execute(args.sql)
                cols = [d[0] for d in cur.description or []]
                rows = cur.fetchmany(args.n + 1)
            except Exception as e:       # one line, secrets redacted
                print(f"✗ {type(e).__name__}: {p.redact(str(e).splitlines()[0] if str(e) else '')}", file=sys.stderr)
                return 1
        finally:
            con.close()
    more = len(rows) > args.n
    rows = rows[: args.n]
    text = _table(cols, [[fmt_cell(v) for v in r] for r in rows]) if cols else "(no result)"
    text += f"\n({len(rows)} row(s){', more not shown; raise -n' if more else ''})" if cols else ""
    _out(args, {"columns": cols, "rows": rows, "more": more}, text)


def _summary(doc: dict) -> list[str]:
    lines = []
    for b in doc["blocks"]:
        if b["kind"] == "md":
            continue
        st = b.get("status", "error" if b.get("error") else "ok")
        if b["kind"] in ("sql", "python", "sheet"):
            shape = f"{b['rowCount']:,} row(s) [{', '.join(c['name'] for c in b['columns'])}]" if "columns" in b else b.get("error", "")
        elif b["kind"] == "kpi":
            shape = " · ".join(f"{i['label']}={i['value']}" for i in b.get("items", []))
        else:
            shape = b.get("error") or f"{b.get('type', '')} data={b.get('data')}".strip()
        deps = f" ← {', '.join(b['deps'])}" if b.get("deps") else ""
        lines.append(f"@{b['id']:<16} {b['kind']:<7} {st:<7} {shape}{deps}")
    return lines


def _diags(doc: dict) -> list[str]:
    ds = doc["diagnostics"]
    if not ds:
        return ["diagnostics: (none)"]
    path = doc.get("path", "notebook.md")
    return ["diagnostics:", *(f"  {'✗' if d['severity'] == 'error' else '⚠'} {path}:{d['line']} {d['code']} {d['message']}"
                              for d in ds)]


def cmd_check(args):
    from tracebook.run import run_notebook
    p = Project.find()
    keys = [p.nb(args.nb).key] if args.nb else list(p.notebooks())
    if not keys:
        raise ProjectError("no notebooks yet; run `tracebook new <name>`")
    docs, text = {}, []
    for k in keys:
        doc = docs[k] = run_notebook(p, k)
        errs = sum(d["severity"] == "error" for d in doc["diagnostics"])
        warns = len(doc["diagnostics"]) - errs
        n = len([b for b in doc["blocks"] if b["kind"] != "md"])
        head = f"{'✓' if doc['ok'] else '✗'} {n} block(s), {errs} error(s), {warns} warning(s)"
        text += [*([f"── {p.nb(k).path.relative_to(p.root)}"] if len(keys) > 1 else []), head,
                 *(_summary(doc) if args.cmd == "snapshot" else []), *_diags(doc)]
    view = {k: d if args.full else {"ok": d["ok"], "diagnostics": d["diagnostics"]} for k, d in docs.items()}
    _out(args, view[keys[0]] if len(keys) == 1 else {"notebooks": view}, "\n".join(text))
    return 0 if all(d["ok"] for d in docs.values()) else 1


def cmd_diff(args):
    from tracebook import history
    pair = history.latest_pair(Project.find().nb(args.nb).history_dir)
    if not pair:
        _out(args, {"changes": None}, "no earlier run with a different notebook or data; run `tracebook check` after a change")
        return 0
    base, new = pair
    ch = history.diff(base, new)
    text = [f"{base['ranAt']} → {new['ranAt']}: {len(ch)} change(s)  (+ added  - removed  ~ changed  ! now failing)",
            *(f"{c['change']} {c['key']}" + (f"  {'; '.join(c['details'])}" if c["details"] else "") for c in ch)]
    _out(args, {"base": base["ranAt"], "new": new["ranAt"], "changes": ch}, "\n".join(text))


def cmd_comments(args):
    from tracebook import comments
    p = Project.find()
    if args.action == "resolve":
        if args.id is None:
            raise ProjectError("usage: tracebook comments resolve <id> [--note '<what you changed>']")
        c = comments.resolve(p, args.id, args.note)
        _out(args, c, f"resolved #{c['id']} on @{c['block']} ({c['path']}:{c['line']})")
        return 0
    cs = comments.items(p, p.nb(args.nb).key if args.nb else None, include_resolved=args.all)
    text = [f"#{c['id']} [{c['status']}] @{c['block']} ({c['path']}:{c['line']}): {c['text']}"
            + ("\n    ⚠ block no longer exists; resolve with a note" if c["orphan"] and c["status"] == "open" else "")
            + (f"\n    ⚠ changed since this comment: was “{c['seen']['brief']}”, now “{c['now']}”"
               if c["state"] == "outdated" and c["status"] == "open" else "")
            + (f"\n    → {c['resolution']}" if c["resolution"] else "") for c in cs]
    _out(args, {"comments": cs}, "\n".join(text) or "no open comments")


def cmd_dev(args):
    from tracebook.dev import serve
    serve(Project.find(), args.port, args.open)


def cmd_export(args):
    from tracebook.dev import export_html
    from tracebook.run import run_notebook
    p = Project.find()
    doc = run_notebook(p, args.nb)
    if not doc["ok"] and not args.force:
        print("\n".join(["✗ export refused: fix errors first (or pass --force)", *_diags(doc)]))
        return 1
    if args.block:                           # one compute block's full result as CSV (answer files, hand-offs)
        from tracebook.run import _fq, _load_df
        b = next((b for b in doc["blocks"] if b["id"] == args.block), None)
        if not b or "columns" not in b:
            raise ProjectError(f"no computed block {args.block!r} in {doc['notebook']}")
        if not args.out:
            raise ProjectError("export --block needs an output path, e.g. answer.csv")
        with p.lock():
            con = p.connect(read_only=True)
            try:
                df = _load_df(con, _fq(p.nb(args.nb).schema, args.block))
            finally:
                con.close()
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(out, index=False)
        _out(args, {"path": str(out), "rows": len(df)}, f"wrote {out} ({len(df):,} rows, columns: {', '.join(df.columns)})")
        return 0
    single = len(p.notebooks()) == 1
    out = Path(args.out or (p.root / "dist" / ("index.html" if single else f"{doc['notebook']}.html")))
    export_html(doc, out, p.root)
    pii = [d for d in doc["diagnostics"] if d["code"] == "PII_COLUMN_PUBLISHED"]
    _out(args, {"path": str(out)}, f"wrote {out} ({out.stat().st_size // 1024} KB, block results only, no raw tables)"
         + ("".join(f"\n  ⚠ {d['message']}" for d in pii)))


def cmd_sheet(args):
    from tracebook.engine.sheet import SheetError, diff, inspect
    for f in [args.file, *([args.diff] if args.diff else [])]:
        if not Path(f).is_file():
            raise ProjectError(f"file not found: {f}")
    try:
        if args.diff:
            d = diff(Path(args.diff), Path(args.file))
            text = [f"{args.diff} → {args.file}: {len(d['changes'])} cell change(s)",
                    *([f"sheets added: {', '.join(d['sheets_added'])}"] if d["sheets_added"] else []),
                    *([f"sheets removed: {', '.join(d['sheets_removed'])}"] if d["sheets_removed"] else [])]
            if d["changes"]:
                text.append(_table(["cell", "old", "new"], [[c["cell"], fmt_cell(c["old"]), fmt_cell(c["new"])]
                                                             for c in d["changes"]]))
            text += ["warnings:" if d["warnings"] else "warnings: (none)", *("  ⚠ " + w for w in d["warnings"])]
            _out(args, d, "\n".join(text))
            return 0
        d = inspect(Path(args.file), args.range, args.n)
    except SheetError as e:
        print(f"✗ {e.code} {e}", file=sys.stderr)
        return 1
    text = [f"{args.file} (recalculated on a temp copy; source untouched)",
            *(f"  {sh['name']}  {sh['dims']}  {sh['formulas']} formula(s)" for sh in d["sheets"]),
            _table(["cell", "formula", "value"], [[f"{c['sheet']}!{c['a']}", c["f"] or "", fmt_cell(c["v"])]
                                                  for c in d["cells"]])]
    if d["truncated"]:
        text.append(f"(first {args.n} cells; narrow with --range Sheet!A1:D20 or raise -n)")
    text += ["errors:" if d["errors"] else "errors: (none)", *(f"  ✗ {e['code']} {e['message']}" for e in d["errors"])]
    _out(args, d, "\n".join(text))
    return 1 if d["errors"] else 0


def cmd_components(args):
    reg = json.loads((PKG / "components.json").read_text())
    charts = {k: v for k, v in reg["chart"].items() if not args.type or k in args.type}
    if not charts:
        raise ProjectError(f"unknown chart type {', '.join(args.type)}; types: {', '.join(reg['chart'])}")
    lines = ["chart block fields: " + "; ".join(f"{k} = {v}" for k, v in reg["fields"].items())]
    for name, c in charts.items():
        lines += [f"\n{name}  (y: {c['y']} column{'s' if c['y'] != '1' else ''}) — {c['summary']}",
                  *(f"  variant {v:<11} {d}" for v, d in c["variants"].items()),
                  *(f"  {k}: {d}" for k, d in c.get("options", {}).items()), f"  e.g. {c['example']}"]
    _out(args, {**reg, "chart": charts}, "\n".join(lines))


def cmd_skill(args):
    src = PKG / "skill"
    if args.action == "path":
        print(src)
        return 0
    if args.action == "guide":
        from tracebook.packs import packs
        pk = packs().get(args.name or "")
        if not pk or not getattr(pk, "skill_ref", None):
            raise ProjectError(f"no guide for pack {args.name!r}; packs: {', '.join(packs())}")
        print(Path(pk.skill_ref).read_text())
        return 0
    target = Path(args.target).expanduser() / "tracebook"
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_symlink() or target.exists():
        if not target.is_symlink():
            raise ProjectError(f"{target} exists and is not a symlink; remove it first")
        target.unlink()
    target.symlink_to(src, target_is_directory=True)
    print(f"linked {target} → {src}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="tracebook", description=__doc__)
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("init", help="create a project")
    s.add_argument("dir")
    s.add_argument("--template")
    s.add_argument("--tz", help="IANA time zone for local timestamps and date buckets")
    s.add_argument("--demo", action="store_true", help="also write synthetic example data (templates that support it)")
    s.set_defaults(fn=cmd_init)
    s = sub.add_parser("import", help="load files into the project database")
    s.add_argument("files", nargs="+")
    s.add_argument("--as", dest="as_", help="force a source, e.g. razorpay.payments")
    s.add_argument("--types", action="append", help="col=type[,col=type]  (text,int,bool,money,decimal:N,json,"
                                                     "timestamp,date:dmy,date:mdy,local:dmy,unix)")
    s.add_argument("--name", help="table name (default: from source pack or file name)")
    s.set_defaults(fn=cmd_import)
    s = sub.add_parser("schema", help="tables, columns, types")
    s.add_argument("table", nargs="*")
    s.add_argument("--nb", help="notebook whose block outputs to list (default: the only one)")
    s.set_defaults(fn=cmd_schema)
    s = sub.add_parser("query", help="run a read-only SQL query")
    s.add_argument("sql")
    s.add_argument("-n", type=int, default=20)
    s.add_argument("--nb", help="notebook whose blocks are queryable by bare name (default: the only one)")
    s.set_defaults(fn=cmd_query)
    for name, hlp in (("check", "run all blocks and validate"), ("snapshot", "run + list blocks with status and shape")):
        s = sub.add_parser(name, help=hlp)
        s.add_argument("--full", action="store_true", help="with --json: include full results")
        s.add_argument("--nb", help="one notebook (default: all)")
        s.set_defaults(fn=cmd_check)
    s = sub.add_parser("new", help="create a notebook: notebooks/<name>.md (folders allowed: growth/cohorts)")
    s.add_argument("name")
    s.add_argument("--template")
    s.set_defaults(fn=cmd_new)
    s = sub.add_parser("source", help="read-only databases notebooks can query: add/list/remove")
    s.add_argument("action", choices=["add", "list", "remove"])
    s.add_argument("name", nargs="?")
    s.add_argument("--type", choices=sorted(SOURCE_TYPES))
    s.add_argument("--env", help="environment variable holding the URL (postgres://…, mysql DSN) or file path")
    s.add_argument("--path", help="sqlite/duckdb file (relative to the workspace)")
    s.set_defaults(fn=cmd_source)
    s = sub.add_parser("diff", help="per-block changes between the last two runs with different notebook/data")
    s.add_argument("--nb", help="notebook (default: the only one)")
    s.set_defaults(fn=cmd_diff)
    s = sub.add_parser("comments", help="review comments left in the viewer; `comments resolve <id> --note …`")
    s.add_argument("action", nargs="?", choices=["resolve"])
    s.add_argument("id", nargs="?", type=int)
    s.add_argument("--note", help="what you changed (shown to the reviewer)")
    s.add_argument("--nb", help="only this notebook")
    s.add_argument("--all", action="store_true", help="include resolved")
    s.set_defaults(fn=cmd_comments)
    s = sub.add_parser("dev", help="live preview in the browser")
    s.add_argument("--port", type=int, default=4321)
    s.add_argument("--open", action="store_true")
    s.set_defaults(fn=cmd_dev)
    s = sub.add_parser("export", help="write a self-contained HTML report, or with --block one block's result as CSV")
    s.add_argument("out", nargs="?")
    s.add_argument("--block", help="compute block id: write its full result to OUT as CSV")
    s.add_argument("--force", action="store_true")
    s.add_argument("--nb", help="notebook (default: the only one)")
    s.set_defaults(fn=cmd_export)
    s = sub.add_parser("sheet", help="inspect/recalc an .xlsx model and list formula errors, or --diff against an older copy")
    s.add_argument("file")
    s.add_argument("--range", help="only cells in Sheet!A1:D20")
    s.add_argument("--diff", metavar="OLD", help="show cell changes from OLD to file (warns on removed formulas)")
    s.add_argument("-n", type=int, default=500)
    s.set_defaults(fn=cmd_sheet)
    s = sub.add_parser("components", help="chart types, variants and fields the viewer can render")
    s.add_argument("type", nargs="*")
    s.set_defaults(fn=cmd_components)
    s = sub.add_parser("skill", help="install the agent skill (Claude Code: ~/.claude/skills)")
    s.add_argument("action", choices=["install", "path", "guide"])
    s.add_argument("name", nargs="?", help="pack name for `guide`")
    s.add_argument("--target", default="~/.claude/skills")
    s.set_defaults(fn=cmd_skill)
    args = ap.parse_args(argv)
    try:
        return args.fn(args) or 0
    except ProjectError as e:
        print(f"✗ {e}", file=sys.stderr)
        return 2
    except Exception as e:  # surface engine errors (e.g. bad SQL in `query`) as one line, not a traceback
        if args.cmd == "query":
            print(f"✗ {type(e).__name__}: {str(e).splitlines()[0]}", file=sys.stderr)
            return 1
        raise


if __name__ == "__main__":
    sys.exit(main())
