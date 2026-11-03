"""notebook.md → blocks, references between them, and execution order."""
from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field

import duckdb
import yaml

COMPUTE = ("sql", "python", "sheet")
DISPLAY = ("kpi", "chart", "table")
_FENCE = re.compile(r'^```([A-Za-z]+)(?:[ \t]+([A-Za-z_][A-Za-z0-9_]*))?(?:[ \t]+"([^"]*)")?[ \t]*$')
_ANY_FENCE = re.compile(r"^(```+|~~~+)")
INTERP = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)\s*(?:\|\s*([a-z_]+)\s*)?\}\}")
REF = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)$")


@dataclass
class Diag:
    line: int
    code: str
    message: str
    severity: str = "error"
    block: str | None = None

    def __str__(self):
        return f"{'✗' if self.severity == 'error' else '⚠'} notebook.md:{self.line} {self.code} {self.message}"


@dataclass
class Block:
    kind: str
    id: str
    body: str
    line: int                              # 1-based line of the opening fence (md: first line)
    spec: object = None                    # parsed YAML for display/sheet blocks
    deps: set[str] = field(default_factory=set)
    title: str | None = None              # ```sql id "Title"
    reads: set[str] = field(default_factory=set)   # imported tables read
    uses: set[str] = field(default_factory=set)    # named outputs of python blocks read (`model__summary`)
    auto: bool = False                     # id numbered by position (md_3, chart_2), not written by the author


@dataclass
class Notebook:
    meta: dict
    blocks: list[Block]
    diags: list[Diag]

    def get(self, bid: str) -> Block | None:
        return next((b for b in self.blocks if b.id == bid), None)


def parse(text: str) -> Notebook:
    lines, diags, blocks, meta = text.split("\n"), [], [], {}
    i = 0
    if lines and lines[0].strip() == "---":
        end = next((j for j in range(1, len(lines)) if lines[j].strip() == "---"), None)
        if end is None:
            diags.append(Diag(1, "BAD_FRONTMATTER", "frontmatter opened with --- but never closed"))
        else:
            try:
                meta = yaml.safe_load("\n".join(lines[1:end])) or {}
            except yaml.YAMLError as e:
                diags.append(Diag(1, "BAD_FRONTMATTER", str(e).split("\n")[0]))
            i = end + 1
    md, md_start, auto = [], i + 1, {}

    def flush():
        nonlocal md
        if "".join(md).strip():
            blocks.append(Block("md", f"md_{len(blocks) + 1}", "\n".join(md), md_start, auto=True))
        md = []

    while i < len(lines):
        m = _FENCE.match(lines[i])
        if m and m[1] in COMPUTE + DISPLAY:
            kind, bid, title, start = m[1], m[2], m[3], i + 1
            end = next((j for j in range(i + 1, len(lines)) if lines[j].strip() == "```"), None)
            if end is None:
                diags.append(Diag(start, "UNCLOSED_FENCE", f"```{kind} block is never closed"))
                break
            flush()
            numbered = not bid
            if numbered:
                if kind in COMPUTE:
                    diags.append(Diag(start, "MISSING_ID", f"```{kind} needs an id, e.g. ```{kind} my_block"))
                auto[kind] = auto.get(kind, 0) + 1
                bid = f"{kind}_{auto[kind]}"
            blocks.append(Block(kind, bid, "\n".join(lines[i + 1:end]), start, title=(title or "").strip() or None,
                                auto=numbered))
            i, md_start = end + 1, end + 2
            continue
        if (k := re.match(r"^```([A-Za-z]+)", lines[i])) and k[1] in COMPUTE + DISPLAY:
            diags.append(Diag(i + 1, "BAD_FENCE", f'cannot read {lines[i].strip()!r}; write ```{k[1]} <id> "Optional title"'))
        if f := _ANY_FENCE.match(lines[i]):          # other fenced code in prose: copy verbatim
            j = next((j for j in range(i + 1, len(lines)) if lines[j].strip() == f[1]), len(lines) - 1)   # only a bare fence closes
            md += lines[i:j + 1]
            i = j + 1
            continue
        md.append(lines[i])
        i += 1
    flush()
    seen: dict[str, int] = {}
    for b in blocks:
        if b.id in seen:
            diags.append(Diag(b.line, "DUPLICATE_ID", f"id {b.id!r} already used on line {seen[b.id]}", block=b.id))
        seen.setdefault(b.id, b.line)
        if b.kind in DISPLAY + ("sheet",):
            try:
                b.spec = yaml.safe_load(b.body)
            except yaml.YAMLError as e:
                diags.append(Diag(b.line, "BAD_SPEC", str(e).split("\n")[0], block=b.id))
    return Notebook(meta, blocks, diags)


def _ref_names(b: Block) -> list[str]:
    """Names a non-SQL/Python block reads (before resolving against known tables/blocks)."""
    s = b.spec
    if b.kind == "md":
        return [m[1] for m in INTERP.finditer(b.body)]
    if b.kind == "kpi" and isinstance(s, list):
        return [r.split(".")[0] for it in s if isinstance(it, dict) for k in ("value", "compare")
                if isinstance(r := it.get(k), str)]
    if b.kind in ("chart", "table") and isinstance(s, dict) and isinstance(s.get("data"), str):
        return [s["data"]] + ([s["max"].split(".")[0]] if isinstance(s.get("max"), str) and REF.match(s["max"]) else [])
    if b.kind == "sheet" and isinstance(s, dict) and isinstance(s.get("inputs"), dict):
        return [v.split(".")[0] for v in s["inputs"].values() if isinstance(v, str) and REF.match(v)]
    return []


def name_parts(name: str) -> list[str]:
    """`shop.sales."My T"` → ['shop', 'sales', 'My T'] (dots inside quotes are part of the name)."""
    return [p.strip('"') for p in re.findall(r'"(?:[^"]|"")*"|[^.]+', name)]


def resolve(nb: Notebook, tables: set[str], sources: frozenset[str] = frozenset()) -> list[Block]:
    """Fill block.deps; add REF/CYCLE diagnostics; return blocks in execution order (cycles excluded).
    `sources`: lower-case names of attached databases; SQL may read `<source>.<schema>.<table>`."""
    ids = {b.id for b in nb.blocks}
    lower = {t.lower(): t for t in tables} | {i.lower(): i for i in ids}
    py = {b.id.lower(): b.id for b in nb.blocks if b.kind == "python"}

    def owner(n: str) -> str | None:
        """`model__summary` → `model` when `model` is a python block (named output of a multi-output block)."""
        head, sep, tail = n.partition("__")
        return py.get(head.lower()) if sep and tail and n.lower() not in lower else None
    for b in nb.blocks:
        if b.id in tables:
            nb.diags.append(Diag(b.line, "DUPLICATE_ID", f"block id {b.id!r} shadows an imported table", block=b.id))
        if b.kind == "sql":
            try:
                names = list(duckdb.get_table_names(b.body))
                qualified = [name_parts(q.split(" AS ")[0]) for q in duckdb.get_table_names(b.body, qualified=True)]
            except Exception as e:
                nb.diags.append(Diag(b.line, "SQL_ERROR", str(e).split("\n")[0], block=b.id))
                continue
            external = [q for q in qualified if len(q) > 1 and q[0].lower() in sources]
            if bad := sorted(".".join(q) for q in qualified if len(q) > 1 and q not in external and q[0].lower() != "main"):
                nb.diags.append(Diag(b.line, "CROSS_NOTEBOOK_REF", f"{b.id} reads {', '.join(bad)}; a notebook can "
                                     "only read imported tables, its own blocks and sources (`databook source list`)",
                                     block=b.id))
                continue
            b.reads |= {".".join(q) for q in external}    # source tables: read through DuckDB, never a block dep
            local = {q[-1].lower() for q in qualified if q not in external}
            names = [n for n in names if n.lower() in local]
        elif b.kind == "python":
            try:
                tree = ast.parse("def __tb__():\n" + "\n".join("    " + ln for ln in b.body.split("\n")))
            except SyntaxError as e:
                nb.diags.append(Diag(b.line + (e.lineno or 1) - 1, "PY_ERROR", f"SyntaxError: {e.msg}", block=b.id))
                continue
            names = [n.id for n in ast.walk(tree)
                     if isinstance(n, ast.Name) and (n.id.lower() in lower or owner(n.id)) and n.id != b.id]
        else:
            names = _ref_names(b)
        for n in names:
            if o := owner(n):
                b.deps.add(o)                     # output existence is checked when the block runs
                b.uses.add(n)
            elif n.lower() not in lower:
                nb.diags.append(Diag(b.line, "REF_UNKNOWN", f"{b.id} reads {n!r}, which is neither an imported "
                                     f"table nor a block (tables: {', '.join(sorted(tables)) or 'none'})", block=b.id))
            elif lower[n.lower()] in ids:
                b.deps.add(lower[n.lower()])
            else:
                b.reads.add(lower[n.lower()])
    # Kahn's algorithm over block → block dependencies, document order as tie-break.
    firsts = [b for b in nb.blocks if nb.get(b.id) is b]   # later duplicates never run (DUPLICATE_ID)
    pending = {b.id: set(b.deps) for b in firsts}
    order: list[Block] = []
    while True:
        ready = [b for b in firsts if b.id in pending and not pending[b.id]]
        if not ready:
            break
        for b in ready:
            order.append(b)
            del pending[b.id]
        for d in pending.values():
            d -= {b.id for b in ready}
    if pending:
        cyc = ", ".join(sorted(pending))
        for bid in pending:
            nb.diags.append(Diag(nb.get(bid).line, "CYCLE", f"blocks depend on each other in a loop: {cyc}", block=bid))
    return order
