"""Review comments on notebook blocks: left in the viewer (`tracebook dev`), read and resolved by the agent via the CLI.

Stored in .tracebook/comments.json; every read-modify-write holds the project lock (the dev server and CLI are
separate processes).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from tracebook.core import anchors
from tracebook.project import Project, ProjectError

MAX_TEXT = 4000


def _path(p: Project):
    return p.dir / "comments.json"


def _load(p: Project) -> dict:
    f = _path(p)
    return json.loads(f.read_text()) if f.exists() else {"next": 1, "items": []}


def _save(p: Project, data: dict) -> None:
    tmp = _path(p).with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=1))
    tmp.replace(_path(p))


def _last_run(p: Project, notebook: str) -> dict:
    """The notebook's last results doc with anchors set ({"blocks": []} if the notebook or its results are gone)."""
    rp = p.nb(notebook).results_path if notebook in p.notebooks() else None
    doc = (json.loads(rp.read_text()) if rp and rp.exists() else None) or {"blocks": []}
    anchors.assign(doc["blocks"])                  # same function the run used; also covers results from older versions
    return doc


def _find(blocks: list[dict], anchor: str | None, block: str) -> dict | None:
    """By anchor; comments from before anchors existed carry none and are matched by block id."""
    return next((b for b in blocks if (b["anchor"] == anchor if anchor else b["id"] == block)), None)


def _state(c: dict, blocks: list[dict]) -> dict:
    """attached | outdated (block found, content changed since the comment; `now` = what it shows today) |
    orphan (block gone: the agent should resolve with a note). A comment never moves to another block."""
    b = _find(blocks, c.get("anchor"), c["block"])
    if b is None:
        return {"state": "orphan", "orphan": True}
    changed = bool(c.get("seen")) and anchors.fingerprint(b) != c["seen"]["hash"]
    return {"block": b["id"], "line": b["line"], "orphan": False, "state": "outdated" if changed else "attached",
            **({"now": anchors.brief(b)} if changed else {})}


def items(p: Project, notebook: str | None = None, include_resolved: bool = False) -> list[dict]:
    """Comments resolved against the notebook's last run: current block id and line, plus `state` (see _state)."""
    out, runs = [], {}
    for c in _load(p)["items"]:
        if (notebook is not None and c["notebook"] != notebook) or (not include_resolved and c["status"] != "open"):
            continue
        if c["notebook"] not in runs:
            runs[c["notebook"]] = _last_run(p, c["notebook"])["blocks"]
        out.append({**c, **_state(c, runs[c["notebook"]])})
    return out


def add(p: Project, notebook: str, block: str, text: str, anchor: str | None = None) -> dict:
    """Attach a comment to a block of the notebook's last run, by anchor when the viewer sends one (an id can point
    at a different block once the notebook re-ran), else by id. Stores a snapshot of what the block showed."""
    ref = p.nb(notebook)
    text = str(text).strip()
    if not text or len(text) > MAX_TEXT:
        raise ProjectError(f"comment must be 1–{MAX_TEXT} characters")
    doc = _last_run(p, ref.key)
    b = _find(doc["blocks"], anchor, block)
    if not b:
        raise ProjectError(f"no block {anchor or block!r} in {ref.key} (as of its last run)")
    seen = {"ranAt": doc.get("ranAt"), "dataHash": doc.get("dataHash"), "hash": anchors.fingerprint(b),
            "brief": anchors.brief(b)}
    with p.lock():
        data = _load(p)
        c = {"id": data["next"], "notebook": ref.key, "path": ref.path.relative_to(p.root).as_posix(), "block": b["id"],
             "anchor": b["anchor"], "line": b["line"], "text": text, "status": "open", "created": _now(),
             "resolution": None, "resolved": None, "seen": seen}
        data["next"] += 1
        data["items"].append(c)
        _save(p, data)
    return c


def resolve(p: Project, cid: int, note: str | None = None) -> dict:
    with p.lock():
        data = _load(p)
        c = next((c for c in data["items"] if c["id"] == cid), None)
        if not c:
            raise ProjectError(f"no comment #{cid}")
        if c["status"] == "resolved":
            raise ProjectError(f"comment #{cid} is already resolved")
        c.update(status="resolved", resolution=(note or "").strip()[:MAX_TEXT] or None, resolved=_now())
        _save(p, data)
    return c


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
