"""Run history (.databook/history/, last KEEP runs) and a per-block diff between two runs.

Compute blocks are keyed by id, charts/tables by their anchor (core/anchors.py). KPI cards and prose values are keyed
one level finer than a block: KPIs by label, prose values by their {{ref}}.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path

KEEP = 20
_REF_SPAN = re.compile(r'data-ref="([^"]+)">([^<]*)<')


def _h(v) -> str:
    return hashlib.sha256(json.dumps(v, sort_keys=True, default=str).encode()).hexdigest()[:12]


def summarize(doc: dict) -> dict:
    """{key: {field: comparable value}} — what a reviewer of agent changes cares about."""
    out: dict[str, dict] = {}

    def put(key: str, entry: dict):
        k, n = key, 2
        while k in out:                                    # same title/data twice → stable suffixes in doc order
            k, n = f"{key}#{n}", n + 1
        out[k] = entry

    for b in doc["blocks"]:
        kind = b["kind"]
        if kind in ("sql", "python", "sheet"):
            cols = [f"{c['name']} {c['type']}" for c in b.get("columns", [])]
            e = {"code": b.get("code"), "status": b.get("status"), "columns": cols, "rows": b.get("rowCount")}
            if b.get("rowCount") == 1 and b.get("display"):
                e["values"] = {c["name"]: v for c, v in zip(b["columns"], b["display"][0])}
            elif b.get("display") is not None:
                e["data"] = b.get("rowsHash") or _h(b["display"])   # whole result, any row order (older runs: shown rows)
            put(b["id"], e)
        elif kind == "md":
            for ref, val in _REF_SPAN.findall(b.get("text", "")):
                put(f"{{{{{ref}}}}}", {"value": val})
        elif kind == "kpi":
            for it in b.get("items", []):
                put(f"kpi {it['label']}", {"value": it.get("value"), "delta": it.get("deltaText")})
        else:
            e = {"error": b.get("error"), "type": b.get("type"), "variant": b.get("variant"),
                 "x": b.get("x"), "y": b.get("y"), "columns": b.get("columns"),
                 "data": _h([s.get("display") for s in b.get("series", [])] or b.get("display"))}
            put(b.get("anchor") or f"{kind} {b.get('title') or b.get('data') or b['id']}", e)
    return out


def save(dir_: Path, doc: dict) -> None:
    """Store this run; an identical-input rerun (same notebook + data hashes) replaces the newest entry."""
    dir_.mkdir(parents=True, exist_ok=True)
    runs = sorted(dir_.glob("*.json"))
    snap = {k: doc[k] for k in ("notebookHash", "dataHash", "ranAt")} | {"blocks": summarize(doc)}
    if runs:
        last = json.loads(runs[-1].read_text())
        if (last["notebookHash"], last["dataHash"]) == (snap["notebookHash"], snap["dataHash"]):
            runs[-1].unlink()
            runs = runs[:-1]
    tmp = dir_ / f".{time.time_ns()}.tmp"
    tmp.write_text(json.dumps(snap, default=str))
    tmp.replace(dir_ / f"{time.time_ns():020d}.json")
    for old in sorted(dir_.glob("*.json"))[:-KEEP]:
        old.unlink()


def latest_pair(dir_: Path) -> tuple[dict, dict] | None:
    """(base, latest): the newest run and the newest earlier run whose notebook or data differ."""
    runs = [json.loads(f.read_text()) for f in sorted(dir_.glob("*.json"))] if dir_.is_dir() else []
    if len(runs) < 2:
        return None
    return runs[-2], runs[-1]          # save() collapses identical-input reruns, so the previous entry differs


def diff(base: dict, new: dict) -> list[dict]:
    """[{key, change: + - ~ !, details: [...]}] in the new run's order, removals last. `!` = status got worse."""
    a, b = base["blocks"], new["blocks"]
    out = []
    for k, e in b.items():
        if k not in a:
            out.append({"key": k, "change": "+", "details": []})
            continue
        old = a[k]
        det = []
        for f in dict.fromkeys([*old, *e]):
            x, y = old.get(f), e.get(f)
            if x == y:
                continue
            if f == "values" and isinstance(x, dict) and isinstance(y, dict):
                det += [f"{c}: {_show(x.get(c))} → {_show(y.get(c))}" for c in dict.fromkeys([*x, *y]) if x.get(c) != y.get(c)]
            elif f == "code":
                det.append("code edited")
            elif f == "data":
                det.append("rows changed")
            else:
                det.append(f"{f}: {_show(x)} → {_show(y)}")
        if det:
            worse = old.get("status") == "ok" and e.get("status") in ("error", "skipped") or \
                    (not old.get("error") and e.get("error"))
            out.append({"key": k, "change": "!" if worse else "~", "details": det})
    out += [{"key": k, "change": "-", "details": []} for k in a if k not in b]
    return out


def _show(v) -> str:
    if v is None:
        return "∅"
    s = ", ".join(map(str, v)) if isinstance(v, list) else str(v)
    return s if len(s) <= 60 else s[:57] + "…"
