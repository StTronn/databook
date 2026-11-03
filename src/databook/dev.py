"""`databook dev` (live preview server) and `databook export` (self-contained HTML)."""
from __future__ import annotations

import json
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from databook.core.values import to_json
from databook.project import Project

VIEWER = Path(__file__).parent / "viewer" / "index.html"
_SLOT = "/*__TB_DATA__*/null"
_THEME_SLOT = "/*__TB_THEME__*/"


def theme_css(root: Path) -> str:
    """Optional project theme.css (shadcn CSS variables) layered over the built-in theme."""
    f = root / "theme.css"
    return f.read_text().replace("</", "<\\/") if f.is_file() else ""     # no </style> breakout


def export_html(doc: dict, out: Path, root: Path) -> None:
    data = json.dumps(doc, default=to_json).replace("</", "<\\/")   # no </script> breakout from data
    html = VIEWER.read_text()
    if html.count(_SLOT) != 1 or html.count(_THEME_SLOT) != 1:
        raise RuntimeError("viewer template must contain the data and theme slots exactly once")
    out.parent.mkdir(parents=True, exist_ok=True)
    head, tail = (x.replace(_SLOT, data) for x in html.split(_THEME_SLOT))   # fill template slots only, never
    out.write_text(head + theme_css(root) + tail)                          # slot-like text inside data/theme


def _inputs(p: Project) -> tuple[dict[str, float], dict[str, float], tuple]:
    """mtimes: (per notebook, shared inputs that affect every notebook, (theme.css, comments) → refetch only)."""
    mt = lambda f: f.stat().st_mtime if f.exists() else None
    notes = {k: mt(f) for k, f in p.notebooks().items()}
    shared = {str(f): mt(f) for f in [p.dir / "import.json", p.dir / "config.json", p.dir / "sources.json",
                                      *p.root.glob("models/**/*.xlsx")]}
    return notes, shared, (mt(p.root / "theme.css"), mt(p.dir / "comments.json"))


def serve(p: Project, port: int, open_browser: bool) -> None:
    from databook import comments, workspace
    from databook.packs import templates
    from databook.project import ProjectError
    from databook.run import run_notebook
    # error: workspace-wide (e.g. an unreadable notebook name); errors: run crashes per notebook key, so the
    # viewer only shows a notebook's own failure. Rule/diagnostic errors live in each notebook's results instead.
    state = {"version": 0, "error": None, "errors": {}}
    runs = threading.Lock()                       # one rerun at a time inside this process

    def rerun(keys) -> None:
        with runs:
            errors = dict(state["errors"])
            for k in keys:
                try:
                    doc = run_notebook(p, k)
                    errors.pop(k, None)
                    errs = sum(d["severity"] == "error" for d in doc["diagnostics"])
                    print(f"[{time.strftime('%H:%M:%S')}] {k}: {'ok' if doc['ok'] else f'{errs} error(s)'}", flush=True)
                except Exception as e:            # keep serving the last good results
                    errors[k] = f"{type(e).__name__}: {e}"
                    print(f"[{time.strftime('%H:%M:%S')}] {k}: {errors[k]}", flush=True)
            state["errors"], state["error"] = errors, None
            state["version"] += 1

    def watch():
        seen = None
        while True:
            try:
                now = _inputs(p)
            except ProjectError as e:             # e.g. a notebook file with an unsupported name
                if state["error"] != str(e):
                    state["error"], state["version"] = str(e), state["version"] + 1
                time.sleep(0.5)
                continue
            if seen is None or now[1] != seen[1]:
                rerun(list(now[0]))
            else:
                changed = [k for k, m in now[0].items() if seen[0].get(k) != m]
                if changed:
                    rerun(changed)
                elif now[2] != seen[2] or now[0].keys() != seen[0].keys():
                    state["errors"] = {k: v for k, v in state["errors"].items() if k in now[0]}
                    state["version"] += 1         # theme/comments edited or notebook deleted: viewer refetches
            seen = now
            time.sleep(0.5)

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, body: bytes, ctype: str, code: int = 200):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, data, code: int = 200):
            self._send(json.dumps(data, default=to_json).encode(), "application/json", code)

        def _local(self) -> bool:
            # DNS-rebinding guard: a page on another site must not read data previews through this server.
            host = (self.headers.get("Host") or "").rsplit(":", 1)[0]
            if host in ("127.0.0.1", "localhost"):
                return True
            self._json({"error": "forbidden host"}, 403)
            return False

        def do_GET(self):
            if not self._local():
                return
            u = urlparse(self.path)
            q = {k: v[-1] for k, v in parse_qs(u.query).items()}
            try:
                if u.path == "/results.json":
                    f = p.nb(q.get("nb")).results_path
                    return self._send(f.read_bytes() if f.exists() else b"null", "application/json")
                if u.path == "/version":
                    return self._json(state)
                if u.path == "/theme.css":
                    return self._send(theme_css(p.root).encode(), "text/css; charset=utf-8")
                if u.path == "/api/workspace":
                    return self._json(workspace.info(p))
                if u.path == "/api/schema":
                    return self._json(workspace.schema(p))
                if u.path == "/api/comments":
                    return self._json({"comments": comments.items(p, q.get("nb"), include_resolved=True)})
                if u.path == "/api/preview":
                    return self._json(workspace.preview(p, q.get("table", ""), int(q.get("limit", workspace.PREVIEW_ROWS))))
                if u.path in ("/", "/index.html"):
                    return self._send(VIEWER.read_bytes(), "text/html; charset=utf-8")
            except (ProjectError, ValueError) as e:
                return self._json({"error": str(e)}, 400)
            self.send_error(404)

        def do_POST(self):
            if not self._local():
                return
            origin = self.headers.get("Origin")
            if (self.headers.get("Content-Type") or "").split(";")[0] != "application/json" or (
                    origin and urlparse(origin).hostname not in ("127.0.0.1", "localhost")):
                return self._json({"error": "JSON requests from this page only"}, 403)   # blocks cross-site forms
            path = urlparse(self.path).path
            if path not in ("/api/notebooks", "/api/comments", "/api/comments/resolve"):
                return self.send_error(404)
            try:
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
                if path == "/api/comments":
                    return self._json(comments.add(p, str(body.get("notebook", "")), str(body.get("block", "")),
                                                   str(body.get("text", "")), str(body.get("anchor") or "") or None))
                if path == "/api/comments/resolve":
                    return self._json(comments.resolve(p, int(body.get("id")), body.get("note")))
                name, tpl_name = str(body.get("name", "")), body.get("template")
                tpl = templates().get(tpl_name) if tpl_name else None
                if tpl_name and not tpl:
                    raise ProjectError(f"unknown template {tpl_name!r}")
                with runs:                        # don't create while a rerun is mid-flight
                    created, skipped = workspace.new_notebook(p, name, tpl)
                key = created[0].removeprefix("notebooks/").removesuffix(".md")
                rerun([key])
                return self._json({"key": key, "created": created, "skipped": skipped})
            except (ProjectError, ValueError, TypeError) as e:
                return self._json({"error": str(e)}, 400)

    threading.Thread(target=watch, daemon=True).start()
    for port_try in range(port, port + 20):
        try:
            srv = ThreadingHTTPServer(("127.0.0.1", port_try), H)
            break
        except OSError:
            continue
    else:
        raise OSError(f"no free port in {port}..{port + 19}")
    url = f"http://127.0.0.1:{srv.server_address[1]}/"
    print(f"databook dev: {url}  (watching notebooks/, models/, imports; Ctrl+C to stop)", flush=True)
    if open_browser:
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
