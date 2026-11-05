"""Viewer ↔ coding-agent bridge: requests from the viewer's Agent panel, handled by the user's OPEN agent session.

Flow: the viewer posts a request (text + attached blocks) → `create()` snapshots the notebook and its current results →
the listening session picks it up (`databook inbox --wait` in Claude Code, a pi extension, or `codex queue` via
`deliver()`) → the agent works, reporting with `databook reply <id> --step/--text` → `finish()` reruns the notebook
and diffs it against the snapshot (what changed) → the viewer can `undo()` while the file is still what the agent left.

State lives in .databook/agent/: requests/<id>.json (one file per request, written atomically under the project lock)
and listener.json (which agent/session listens, last heartbeat). Nothing here talks to an LLM.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

from databook import history
from databook.core import anchors
from databook.project import Project, ProjectError

MAX_TEXT = 8000
LISTEN_FRESH_S = 15          # heartbeat older than this → listener gone
BUSY_FRESH_S = 1800          # a claimed request this recent → the session is (probably) working on it


def _dir(p: Project) -> Path:
    return p.dir / "agent"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(json.dumps(data, indent=1, default=str))
    tmp.replace(path)


def _sha(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def _req_path(p: Project, rid: str) -> Path:
    if not rid or not all(c.isalnum() or c == "-" for c in rid):
        raise ProjectError(f"bad request id {rid!r}")
    return _dir(p) / "requests" / f"{rid}.json"


def load(p: Project, rid: str) -> dict:
    f = _req_path(p, rid)
    if not f.exists():
        raise ProjectError(f"no request {rid}")
    return json.loads(f.read_text())


def _save(p: Project, r: dict) -> None:
    _write(_req_path(p, r["id"]), r)


def _last_run(p: Project, nb: str) -> dict:
    rp = p.nb(nb).results_path
    doc = (json.loads(rp.read_text()) if rp.exists() else None) or {"blocks": []}
    anchors.assign(doc["blocks"])
    return doc


def _context(p: Project, nb: str, ref, doc: dict) -> dict:
    """Viewer context {blockId, quote} → what the agent needs: label, file:line, current values, quote."""
    out = {"quote": (str(ref.get("quote") or "")[:500] or None)}
    b = next((b for b in doc["blocks"] if b["id"] == ref.get("blockId")), None)
    if b:
        out.update(blockId=b["id"], anchor=b["anchor"], kind=b["kind"], line=b["line"], brief=anchors.brief(b),
                   label=ref.get("label") or b.get("title") or b["anchor"])
    else:
        out["label"] = str(ref.get("label") or "selection")
    return out


def create(p: Project, notebook: str, text: str, contexts: list) -> dict:
    """Viewer → new pending request. Snapshots the notebook file and the summary of its last run (for diff/undo)."""
    ref = p.nb(notebook)
    text = str(text).strip()
    if not text or len(text) > MAX_TEXT:
        raise ProjectError(f"request must be 1–{MAX_TEXT} characters")
    doc = _last_run(p, ref.key)
    rid = f"{int(time.time() * 1000):x}-{secrets.token_hex(2)}"
    snap = _dir(p) / "snapshots" / rid
    snap.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ref.path, snap / "notebook.md")
    r = {"id": rid, "notebook": ref.key, "path": ref.path.relative_to(p.root).as_posix(), "text": text,
         "contexts": [_context(p, ref.key, c, doc) for c in (contexts or [])[:20] if isinstance(c, dict)],
         "status": "pending", "created": _now(), "events": [], "answer": None, "changes": [], "error": None,
         "before": history.summarize(doc) if doc["blocks"] else {}, "before_sha": _sha(ref.path),
         "after_sha": None, "undone": False}
    with p.lock():
        _save(p, r)
    deliver(p, r)
    return r


def prompt(r: dict) -> str:
    """What the agent session receives for a request."""
    lines = [f"[databook] Request {r['id']} from the viewer, notebook {r['path']}:", "", r["text"], ""]
    if r["contexts"]:
        lines.append("Attached:")
        for c in r["contexts"]:
            where = f" (block {c['blockId']}, {r['path']}:{c['line']}) — {c['brief']}" if c.get("blockId") else ""
            lines.append(f"- @{c['label']}{where}" + (f'\n  selected text: "{c["quote"]}"' if c.get("quote") else ""))
        lines.append("")
    lines += [
        "Handle it with the databook skill: if it is a question, answer WITHOUT editing files; if it asks for a change, "
        f"edit {r['path']} (and models/ if needed) and run `databook check` until it passes.",
        f'Report progress:  databook reply {r["id"]} --step "<what you are doing>"',
        f'Finish:           databook reply {r["id"]} --done --text "<answer or summary, markdown; cite blocks as @id>"',
        "Then run `databook inbox --wait` again (in the background) to keep listening.",
    ]
    return "\n".join(lines)


# ── listener (which session is connected) ─────────────────────────────────────────────────────────────────────────

def beat(p: Project, agent: str, session: str | None = None, state: str = "listening", rid: str | None = None) -> None:
    _write(_dir(p) / "listener.json", {"agent": agent, "session": session, "state": state, "request": rid,
                                       "pid": os.getpid(), "at": time.time()})


def listener(p: Project) -> dict:
    f = _dir(p) / "listener.json"
    if not f.exists():
        return {"state": "offline"}
    d = json.loads(f.read_text())
    age = time.time() - d.get("at", 0)
    if d.get("state") == "busy" and age < BUSY_FRESH_S:
        return d
    if d.get("state") == "listening" and (age < LISTEN_FRESH_S or d.get("agent") in ("pi", "codex") and age < BUSY_FRESH_S):
        return d          # pi/codex push-style listeners beat less often than the blocking `inbox --wait`
    return {**d, "state": "offline"}


def claim(p: Project, agent: str, session: str | None = None) -> dict | None:
    """Oldest pending request → claimed by this session (None if nothing is pending)."""
    with p.lock():
        files = sorted((_dir(p) / "requests").glob("*.json")) if (_dir(p) / "requests").is_dir() else []
        for f in files:
            r = json.loads(f.read_text())
            if r["status"] == "pending":
                r.update(status="claimed", claimed=_now(), agent=agent)
                _save(p, r)
                beat(p, agent, session, "busy", r["id"])
                return r
    return None


# ── replies from the agent ────────────────────────────────────────────────────────────────────────────────────────

def _check_open(r: dict) -> None:
    if r["status"] == "stopped":
        raise ProjectError(f"request {r['id']} was stopped by the user; stop working on it")
    if r["status"] in ("done", "failed"):
        raise ProjectError(f"request {r['id']} is already {r['status']}")


def step(p: Project, rid: str, text: str) -> dict:
    with p.lock():
        r = load(p, rid)
        _check_open(r)
        r["events"].append({"t": "step", "text": str(text)[:500], "at": _now()})
        if r["status"] == "pending":
            r["status"] = "claimed"
        _save(p, r)
    return r


def _changes(before: dict, doc: dict) -> list[dict]:
    """history.diff keys → blocks of the new run (for highlight + scroll), with the diff details as text."""
    after = history.summarize(doc) if doc["blocks"] else {}
    out = []
    for c in history.diff({"blocks": before}, {"blocks": after}):
        m = re.fullmatch(r"(.*?)(?:#(\d+))?", c["key"])        # history numbers repeated keys "<key>#2", "<key>#3"
        key, nth = m[1], int(m[2] or 1)
        b = next((b for b in doc["blocks"] if b["id"] == key or b["anchor"] == c["key"]), None)
        if b is None and key.startswith("kpi "):
            kpis = [b for b in doc["blocks"] if b["kind"] == "kpi" and any(i["label"] == key[4:] for i in b.get("items", []))]
            b = kpis[nth - 1] if len(kpis) >= nth else None
        if b is None and key.startswith("{{"):
            ref = key.strip("{}")
            b = next((b for b in doc["blocks"] if b["kind"] == "md" and f'data-ref="{ref}"' in b.get("text", "")), None)
        detail = {"+": "added", "-": "removed"}.get(c["change"]) or "; ".join(c["details"]) or "changed"
        # name what changed, not its container: a KPI card by its label, a prose number by its ref
        label = key[4:] if key.startswith("kpi ") else key if key.startswith("{{") else \
            (b.get("title") or b["anchor"]) if b else c["key"]
        out.append({"key": c["key"], "change": c["change"], "blockId": b["id"] if b else None, "label": label, "detail": detail})
    return out


def finish(p: Project, rid: str, text: str | None, error: str | None = None) -> dict:
    """Agent done: rerun the notebook, diff against the snapshot, record the answer; session goes back to listening."""
    from databook.run import run_notebook
    r = load(p, rid)
    _check_open(r)
    ref = p.nb(r["notebook"])
    changed = _sha(ref.path) != r["before_sha"]
    doc = run_notebook(p, r["notebook"]) if changed else _last_run(p, r["notebook"])
    anchors.assign(doc["blocks"])
    with p.lock():
        r = load(p, rid)
        _check_open(r)
        r["answer"] = (str(text)[:MAX_TEXT] if text else None)
        r["error"] = error
        r["changes"] = _changes(r["before"], doc) if changed else []
        r["after_sha"] = _sha(ref.path)
        r["check_ok"] = doc.get("ok", True) if changed else None
        r["status"] = "failed" if error else "done"
        r["finished"] = _now()
        _save(p, r)
        lst = _dir(p) / "listener.json"
        if lst.exists():
            d = json.loads(lst.read_text())
            if d.get("request") == rid:
                beat(p, d.get("agent", "agent"), d.get("session"), "listening")
    return r


def stop(p: Project, rid: str) -> dict:
    with p.lock():
        r = load(p, rid)
        if r["status"] in ("pending", "claimed"):
            r["status"] = "stopped"
            r["finished"] = _now()
            _save(p, r)
    return r


def undo(p: Project, rid: str) -> dict:
    """Restore the notebook as it was before the request — only if the file is still exactly what the agent left."""
    with p.lock():
        r = load(p, rid)
        if r["status"] not in ("done", "failed", "stopped"):
            raise ProjectError("the agent is still working on this request")
        if r["undone"]:
            raise ProjectError("already undone")
        ref = p.nb(r["notebook"])
        cur = _sha(ref.path)
        if cur == r["before_sha"]:
            raise ProjectError("nothing to undo: the notebook is unchanged")
        if r["after_sha"] is not None and cur != r["after_sha"]:
            raise ProjectError("the notebook changed after the agent's edit; undo it by hand to keep those changes")
        shutil.copy2(_dir(p) / "snapshots" / rid / "notebook.md", ref.path)
        r["undone"] = True
        _save(p, r)
    return r


def thread(p: Project, notebook: str) -> dict:
    """Viewer: listener state + this notebook's requests, oldest first (internal snapshot fields left out)."""
    key = p.nb(notebook).key
    d = _dir(p) / "requests"
    reqs = []
    for f in sorted(d.glob("*.json")) if d.is_dir() else []:
        r = json.loads(f.read_text())
        if r["notebook"] == key:
            reqs.append({k: v for k, v in r.items() if k not in ("before", "before_sha", "after_sha")})
    return {"listener": listener(p), "requests": reqs}


def deliver(p: Project, r: dict) -> None:
    """Push pending requests to listeners that can't poll (Codex: `codex queue`, which runs the message as a user turn
    once the session is idle). Claude Code and pi pull themselves. Never raises: a failed push puts the request back to
    pending with a step saying why and marks the listener offline (a later `databook inbox` can still pick it up)."""
    lst = listener(p)
    if lst.get("agent") != "codex" or not lst.get("session") or lst["state"] not in ("listening", "busy"):
        return
    while (q := claim(p, "codex", lst["session"])):
        msg = prompt(q).rsplit("\n", 1)[0]          # drop the `inbox --wait` hint: Codex is pushed
        try:
            import subprocess
            out = subprocess.run(["codex", "queue", "--thread", lst["session"], "--message", msg],
                                 capture_output=True, text=True, timeout=20)
            err = None if out.returncode == 0 else (out.stderr or out.stdout).strip()[-300:] or f"exit {out.returncode}"
        except Exception as e:                       # codex missing, timeout, …
            err = f"{type(e).__name__}: {e}"[:300]
        if err is None:
            continue
        with p.lock():
            q = load(p, q["id"])
            if q["status"] == "claimed":
                q["status"] = "pending"
                q["events"].append({"t": "step", "text": f"could not reach the Codex session: {err}", "at": _now()})
                _save(p, q)
            beat(p, "codex", lst["session"], "unreachable")
        return
