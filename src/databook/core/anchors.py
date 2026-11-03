"""Stable identity of a rendered block (what comments, run diffs and the viewer point at) and a snapshot of its content.

Compute blocks, and display blocks with an author-written id (```chart monthly), are anchored by id. Auto-id blocks
(md_7, chart_2: numbered by position, so they shift when a block is inserted above) are anchored by meaning: KPIs by
their first label, charts/tables by title or data block, prose by its first line. Meaning-based anchors contain a
space, so they never equal an id; repeats get " #2", " #3" in document order.
"""
from __future__ import annotations

import hashlib
import json
import re

from databook.core.notebook import COMPUTE

_REF_SPAN = re.compile(r'<span class="tb-ref[^"]*" data-ref="([^"]+)">[^<]*</span>')
_TAG = re.compile(r"<[^>]+>")
_AUTO_ID = re.compile(r"^(md|kpi|chart|table)_\d+$")     # results written before blocks carried `auto`
_NOT_CONTENT = ("id", "line", "deps", "reads", "usedBy", "anchor", "auto", "rows")   # position/links, or covered by rowsHash


def _key(b: dict) -> str:
    kind = b["kind"]
    if kind in COMPUTE or not b.get("auto", kind == "md" or bool(_AUTO_ID.match(b["id"]))):
        return b["id"]
    if kind == "md":                                   # refs, not their values: a new number must not move the anchor
        text = _REF_SPAN.sub(r"{{\1}}", b.get("text", ""))
        return "md " + next((" ".join(ln.split())[:80] for ln in text.split("\n") if ln.strip()), "")
    if kind == "kpi":
        items = b.get("items") or []
        return "kpi " + (items[0]["label"] if items else "")
    return f"{kind} {b.get('title') or b.get('data') or ''}"


def assign(blocks: list[dict]) -> None:
    """Set block["anchor"] on every block of one run, unique within it."""
    used: set[str] = set()
    for b in blocks:
        k, a, n = _key(b), _key(b), 2
        while a in used:
            a, n = f"{k} #{n}", n + 1
        used.add(a)
        b["anchor"] = a


def fingerprint(b: dict) -> str:
    """Hash of what the block shows (code, values, text, errors), not where it sits."""
    body = {k: v for k, v in b.items() if k not in _NOT_CONTENT}
    return hashlib.sha256(json.dumps(body, sort_keys=True, default=str).encode()).hexdigest()[:16]


def brief(b: dict) -> str:
    """One line a reviewer recognises: the KPI values, the sentence, a 1-row result, or the row count."""
    if b.get("error"):
        s = b["error"]
    elif b["kind"] == "md":
        s = _TAG.sub("", b.get("text", ""))
    elif b["kind"] == "kpi":
        s = "; ".join(f"{i['label']} {i.get('value', '')}" for i in b.get("items") or [])
    elif b.get("rowCount") == 1 and b.get("display") and b.get("columns"):
        s = ", ".join(f"{c['name'] if isinstance(c, dict) else c} {v}" for c, v in zip(b["columns"], b["display"][0]))
    else:
        s = f"{b.get('rowCount', len(b.get('labels') or []))} rows"
    s = " ".join(str(s).split())
    return s if len(s) <= 160 else s[:157] + "…"
