"""File readers → RawTable (header row located, names normalized, untyped values)."""
from __future__ import annotations

import csv
import io
import json
import re
import sqlite3
import warnings
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

import openpyxl


@dataclass
class RawTable:
    source: str                  # "data/payments.xlsx" or "data/payments.xlsx#Sheet2"
    headers: list[str]           # normalized snake_case, unique
    original: list[str]          # header text as found
    rows: list[list]             # python values (str/int/float/bool/datetime/None)
    entity: str | None = None    # Razorpay-style JSON `entity` of items, if any
    minor_units: bool = False    # True for API/CLI JSON (amounts in paise)
    table: str | None = None     # source table name (SQLite) → DuckDB table name
    warnings: list[str] = field(default_factory=list)


# Print-layout elements are irrelevant to data and are where real exports carry invalid XML
# (Razorpay subscriptions export: <pageMargins left=""> crashes openpyxl).
_PRINT_TAGS = re.compile(rb"<(pageMargins|pageSetup|printOptions|headerFooter)\b[^>]*?(?:/>|>.*?</\1>)", re.S)
_NUM_FORMULA = re.compile(r"^=\+?(-?\d+(?:\.\d+)?)$")


def sanitize_xlsx(data: bytes) -> tuple[bytes, int]:
    zin = zipfile.ZipFile(io.BytesIO(data))
    out, removed = io.BytesIO(), 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout:
        for info in zin.infolist():
            b = zin.read(info.filename)
            if info.filename.startswith("xl/worksheets/") and info.filename.endswith(".xml"):
                b, n = _PRINT_TAGS.subn(b"", b)
                removed += n
            zout.writestr(info, b)
    return out.getvalue(), removed


def snake(name: str) -> str:
    s = re.sub(r"[^0-9a-zA-Z]+", "_", str(name).strip()).strip("_").lower()
    return ("c_" + s) if s[:1].isdigit() else s


def _blank(v) -> bool:
    return v is None or (isinstance(v, str) and v.strip() == "")


def _locate(grid: list[list], source: str) -> RawTable | None:
    """Find the header row (first mostly-text row ≥2 cells wide), trim empty edges and rows."""
    rows = [list(r) for r in grid]
    filled = [sum(not _blank(v) for v in r) for r in rows]
    if not any(filled):
        return None
    width = max(filled[:20])
    hdr = next((i for i, r in enumerate(rows[:20])
                if filled[i] >= 2 and filled[i] >= 0.5 * width
                and all(isinstance(v, str) for v in r if not _blank(v))),
               next(i for i, n in enumerate(filled) if n))
    body = [r for r in rows[hdr + 1:] if any(not _blank(v) for v in r)]
    ncols = max(len(r) for r in [rows[hdr], *body])
    head = rows[hdr] + [None] * (ncols - len(rows[hdr]))
    body = [r + [None] * (ncols - len(r)) for r in body]
    keep = [j for j in range(ncols) if not _blank(head[j]) or any(not _blank(r[j]) for r in body)]
    t = RawTable(source, [], [], [[r[j] for j in keep] for r in body])
    seen: dict[str, int] = {}
    for j in keep:
        orig = "" if _blank(head[j]) else str(head[j]).strip()
        name = snake(orig) or f"col_{j + 1}"
        if not orig:
            t.warnings.append(f"column {j + 1} has data but no header; named {name}")
        if name in seen:
            seen[name] += 1
            t.warnings.append(f"duplicate header {orig!r}; renamed to {name}_{seen[name]}")
            name = f"{name}_{seen[name]}"
        else:
            seen[name] = 1
        t.headers.append(name)
        t.original.append(orig)
    if hdr:
        t.warnings.append(f"header found on row {hdr + 1}")
    return t


def _read_xlsx(path: Path, label: str) -> list[RawTable]:
    data, removed = sanitize_xlsx(path.read_bytes())
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # "no default style" etc. from generated exports
        wf = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=False)
        wv = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    out = []
    for sf, sv in zip(wf.worksheets, wv.worksheets):
        grid, evaluated, unevaluated = [], 0, 0
        for rf, rv in zip(sf.iter_rows(values_only=True), sv.iter_rows(values_only=True)):
            row = []
            for f, v in zip(rf, rv):
                if isinstance(f, str) and f.startswith("="):
                    if v is not None:
                        f = v                                 # cached value = what Excel displays
                    elif m := _NUM_FORMULA.match(f):
                        f, evaluated = (float(m[1]) if "." in m[1] else int(m[1])), evaluated + 1
                    else:
                        unevaluated += 1                      # keep formula text, never evaluate
                row.append(f)
            grid.append(row)
        src = label if len(wf.worksheets) == 1 else f"{label}#{sf.title}"
        if t := _locate(grid, src):
            if removed:
                t.warnings.append(f"ignored {removed} print-layout XML element(s) (page setup; not data)")
            if evaluated:
                t.warnings.append(f"{evaluated} literal-number formula cell(s) without cached value evaluated")
            if unevaluated:
                t.warnings.append(f"{unevaluated} formula cell(s) without cached value kept as formula text")
            out.append(t)
    return out


def _read_csv(path: Path, label: str) -> list[RawTable]:
    text = path.read_text(encoding="utf-8-sig")
    try:
        dialect = csv.Sniffer().sniff(text[:65536], delimiters=",\t;|")
    except csv.Error:
        dialect = csv.excel_tab if path.suffix.lower() == ".tsv" else csv.excel
    grid = [[None if c == "" else c for c in r] for r in csv.reader(io.StringIO(text), dialect)]
    t = _locate(grid, label)
    return [t] if t else []


def _read_json(path: Path, label: str) -> list[RawTable]:
    doc = json.loads(path.read_text(encoding="utf-8-sig"))
    if isinstance(doc, dict) and isinstance(doc.get("items"), list):
        items = doc["items"]
    elif isinstance(doc, list):
        items = [i for d in doc for i in (d["items"] if isinstance(d, dict) and "items" in d else [d])]
    else:
        items = [doc]
    if not items:
        return []
    if not all(isinstance(i, dict) for i in items):
        raise ValueError(f"{label}: expected a list of objects")
    keys: dict[str, None] = {}
    for i in items:
        keys.update(dict.fromkeys(i))
    entities = {i.get("entity") for i in items}
    t = RawTable(label, [snake(k) for k in keys], list(keys), [], minor_units=True,
                 entity=entities.pop() if len(entities) == 1 else None)
    for i in items:
        t.rows.append([json.dumps(v) if isinstance(v, (dict, list)) else v for v in (i.get(k) for k in keys)])
    return [t]


def _read_sqlite(path: Path, label: str) -> list[RawTable]:
    """Every table as-is (header = column names, no header-row search); values typed later like any other source."""
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        out = []
        for (name,) in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' "
                                   "ORDER BY name").fetchall():
            cur = con.execute(f'SELECT * FROM "{name.replace(chr(34), chr(34) * 2)}"')
            cols = [d[0] for d in cur.description]
            t = RawTable(f"{label}#{name}", [], cols, [], table=snake(name))
            blobs = 0
            for r in cur:
                row = []
                for v in r:
                    if isinstance(v, bytes):
                        v, blobs = v.hex(), blobs + 1
                    row.append(v)
                t.rows.append(row)
            seen: dict[str, int] = {}
            for j, c in enumerate(cols):
                n = snake(c) or f"col_{j + 1}"
                if n in seen:
                    seen[n] += 1
                    t.warnings.append(f"duplicate column {c!r}; renamed to {n}_{seen[n]}")
                    n = f"{n}_{seen[n]}"
                else:
                    seen[n] = 1
                t.headers.append(n)
            if blobs:
                t.warnings.append(f"{blobs} BLOB value(s) imported as hex text")
            out.append(t)
        return out
    finally:
        con.close()


def read_file(path: Path, label: str) -> list[RawTable]:
    ext = path.suffix.lower()
    if ext in (".xlsx", ".xlsm"):
        return _read_xlsx(path, label)
    if ext in (".csv", ".tsv", ".txt"):
        return _read_csv(path, label)
    if ext == ".json":
        return _read_json(path, label)
    if ext in (".sqlite", ".sqlite3", ".db"):
        return _read_sqlite(path, label)
    raise ValueError(f"{label}: unsupported file type {ext!r} "
                     "(supported: .xlsx .xlsm .csv .tsv .json .parquet .sqlite .db)")
