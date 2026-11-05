"""`databook setup` / `doctor`: wire the agent skill into every coding agent on this machine and report what is wired.

The skill is COPIED (not symlinked): under the npm launcher the package lives in uv's cache, whose paths change on
upgrade or cache pruning, so a symlink would dangle. A copy carries a marker file; setup only replaces directories it
created (marker present) or old `databook skill install` symlinks, never a user's own `databook` skill directory.
Skill locations (checked against each agent's docs): Claude Code ~/.claude/skills, Codex ~/.codex/skills,
pi ~/.pi/agent/skills, OpenCode ~/.config/opencode/skills; ~/.agents/skills (Agent Skills standard; read by pi and
OpenCode) is always written. pi also gets the viewer-bridge extension (integrations/pi/databook.ts) copied to
~/.pi/agent/extensions/databook.ts; the copy's first line is its marker, a file without it is the user's and is left alone.
"""
from __future__ import annotations

import os
import shutil
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

SKILL = Path(__file__).parent / "skill"
MARKER = ".databook-skill"
PI_EXT = Path(__file__).parent / "integrations" / "pi" / "databook.ts"
PI_EXT_DIR = "~/.pi/agent/extensions"
EXT_MARK = "// databook setup v"           # first line of our copy of the pi extension
# Before the rename the tool was "trace" + "book": its skill dir and marker. setup removes those copies (marker or
# symlink only) so agents don't load two skills, one of them pointing at a command that no longer exists.
LEGACY = ("trace" + "book", ".trace" + "book-skill")
# (agent, skills dir, detected when any of these exists or the binary is on PATH; None = always)
AGENTS = [
    ("Claude Code", "~/.claude/skills", ["~/.claude"], "claude"),
    ("Codex", "~/.codex/skills", ["~/.codex"], "codex"),
    ("pi", "~/.pi/agent/skills", ["~/.pi"], "pi"),
    ("OpenCode", "~/.config/opencode/skills", ["~/.config/opencode"], "opencode"),
    ("Agent Skills (shared)", "~/.agents/skills", None, None),
]


def tb_version() -> str:
    try:
        return version("databook")
    except PackageNotFoundError:
        return "0+unknown"


def _home(p: str) -> Path:
    return Path(os.path.expanduser(p))


def detected(paths: list[str] | None, binary: str | None) -> bool:
    return paths is None or any(_home(p).exists() for p in paths) or bool(binary and shutil.which(binary))


def state(target: Path) -> str:
    """missing | ours (copy with marker, or an old setup symlink) | foreign (a directory we didn't create)."""
    if target.is_symlink():
        return "ours"
    if not target.exists():
        return "missing"
    return "ours" if (target / MARKER).exists() else "foreign"


def install(target: Path) -> str:
    """Copy the packaged skill to `target` (…/databook). Returns what happened; never touches a foreign dir."""
    st = state(target)
    if st == "foreign":
        return "skipped: a databook skill you created is there (remove it to let setup manage it)"
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(f".{target.name}.tmp")
    shutil.rmtree(tmp, ignore_errors=True)
    shutil.copytree(SKILL, tmp, ignore=shutil.ignore_patterns("__pycache__"))
    (tmp / MARKER).write_text(tb_version() + "\n")
    if target.is_symlink():
        target.unlink()
    elif target.exists():
        shutil.rmtree(target)
    tmp.rename(target)                         # swap in place: a reader never sees a half-copied skill
    return "updated" if st == "ours" else "installed"


def ext_state(target: Path) -> tuple[str, str]:
    """(missing | ours | foreign, version) for the pi extension file. A symlink is the user's (e.g. a dev checkout)."""
    if not target.exists() and not target.is_symlink():
        return "missing", ""
    if target.is_symlink() or not target.is_file():
        return "foreign", ""
    with target.open(errors="replace") as f:
        first = f.readline()
    return ("ours", (first[len(EXT_MARK):].split() or [""])[0]) if first.startswith(EXT_MARK) else ("foreign", "")


def install_ext(target: Path) -> str:
    st, _ = ext_state(target)
    if st == "foreign":
        return "skipped: a databook.ts you created is there (remove it to let setup manage it)"
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(f".{target.name}.tmp")    # dotfile + atomic replace: pi never loads a half-written copy
    tmp.write_text(f"{EXT_MARK}{tb_version()} (managed by `databook setup`; delete this line to keep your edits)\n"
                   + PI_EXT.read_text())
    tmp.replace(target)
    return "updated" if st == "ours" else "installed"


def setup(only: list[str] | None = None) -> list[tuple[str, Path, str]]:
    """[(agent, skill dir, result)] for detected agents (or the named ones, detected or not)."""
    out = []
    for name, base, paths, binary in AGENTS:
        if only is not None and not any(name.lower().startswith(o.lower()) for o in only):
            continue
        target = _home(base) / "databook"
        old = _home(base) / LEGACY[0]
        if old.is_symlink() or (old / LEGACY[1]).exists():
            old.unlink() if old.is_symlink() else shutil.rmtree(old)
        if only is None and not detected(paths, binary):
            out.append((name, target, "not found, skipped"))
            continue
        out.append((name, target, install(target)))
        if name == "pi":
            ext = _home(PI_EXT_DIR) / "databook.ts"
            out.append(("pi extension", ext, install_ext(ext)))
    return out


def doctor() -> list[tuple[str, str]]:
    """[(check, result)]: versions, viewer bundle, and each agent's skill state."""
    import duckdb
    rows = [("databook", tb_version()), ("duckdb", duckdb.__version__),
            ("viewer bundle", "ok" if (Path(__file__).parent / "viewer" / "index.html").is_file() else "MISSING")]
    for name, base, paths, binary in AGENTS:
        t = _home(base) / "databook"
        st = state(t)
        ver = (t / MARKER).read_text().strip() if st == "ours" and (t / MARKER).exists() else ""
        agent = "agent found" if detected(paths, binary) else "agent not found"
        skill = {"missing": "no skill", "foreign": "your own skill dir", "ours": f"skill {ver or 'linked'}"}[st]
        stale = " (outdated: run `databook setup`)" if ver and ver != tb_version() else ""
        rows.append((name, f"{agent}, {skill}{stale} — {t}"))
        if name == "pi":
            e = _home(PI_EXT_DIR) / "databook.ts"
            st, ver = ext_state(e)
            stale = " (outdated: run `databook setup`)" if ver and ver != tb_version() else ""
            rows.append(("pi extension", {"missing": "not installed", "foreign": "your own file",
                                          "ours": f"extension {ver}{stale}"}[st] + f" — {e}"))
    return rows
