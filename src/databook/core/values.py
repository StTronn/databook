"""Exact JSON serialization of DuckDB values and display formatting (one implementation for md, kpi, table)."""
from __future__ import annotations

import math
from datetime import date, datetime, time
from decimal import Decimal

SAFE_INT = 2**53


def to_json(v):
    """DuckDB value → JSON-safe value without losing precision."""
    if v is None or isinstance(v, (bool, str)):
        return v
    if isinstance(v, int):
        return v if -SAFE_INT < v < SAFE_INT else str(v)
    if isinstance(v, Decimal):
        return str(v)                                      # exact; viewer formats from the string
    if isinstance(v, float):
        return v if math.isfinite(v) else None
    if isinstance(v, (datetime, date, time)):
        return v.isoformat()
    return str(v)


def as_number(v) -> float | None:
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float, Decimal)):
        return float(v)
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _group_indian(n: int) -> str:
    s = str(abs(n))
    head, tail = s[:-3], s[-3:]
    parts = []
    while len(head) > 2:
        parts.insert(0, head[-2:])
        head = head[:-2]
    if head:
        parts.insert(0, head)
    return ("-" if n < 0 else "") + ",".join(parts + [tail]) if parts else ("-" if n < 0 else "") + tail


def _dec(v) -> Decimal | None:
    if v is None or isinstance(v, bool):
        return None
    try:
        return Decimal(str(v))
    except Exception:
        return None


FORMATS = ("int", "num", "pct", "inr", "inr_short", "usd", "usd_short", "gbp", "gbp_short", "date", "text")
_SHORT = ((Decimal(10**9), "B"), (Decimal(10**6), "M"), (Decimal(10**3), "K"))


def fmt(v, kind: str | None = None, dtype: str = "") -> str:
    if v is None:
        return "—"
    kind = kind or _default(v, dtype)
    if kind == "text":
        return str(v)
    if kind == "date":
        return v.strftime("%d %b %Y") if isinstance(v, (datetime, date)) else str(v)[:10]
    d = _dec(v)
    if d is None or not d.is_finite():
        return str(v)
    if kind == "int":
        return f"{int(d.quantize(Decimal(1))):,}"
    if kind == "num":
        return f"{d.quantize(Decimal('0.01')):,}"
    if kind == "pct":
        return f"{(d * 100).quantize(Decimal('0.1'))}%"
    if kind == "inr":
        r = int(d.quantize(Decimal(1)))
        return ("-₹" if r < 0 else "₹") + _group_indian(abs(r))
    if kind == "inr_short":
        a, sign = abs(d), "-" if d < 0 else ""
        for size, unit in ((Decimal(10**7), "Cr"), (Decimal(10**5), "L"), (Decimal(10**3), "K")):
            if a >= size:
                return f"{sign}₹{(a / size).quantize(Decimal('0.01'))}{unit}"
        return f"{sign}₹{int(a.quantize(Decimal(1)))}"
    if kind in ("usd", "gbp"):
        return ("-" if d < 0 else "") + ("$" if kind == "usd" else "£") + f"{abs(d).quantize(Decimal('0.01')):,}"
    if kind in ("usd_short", "gbp_short"):
        a, sign, cur = abs(d), "-" if d < 0 else "", "$" if kind == "usd_short" else "£"
        for size, unit in _SHORT:
            if (a / size).quantize(Decimal("0.01")) >= 1:      # compare after rounding: 999,999.996 → £1.00M, not £1000.00K
                return f"{sign}{cur}{(a / size).quantize(Decimal('0.01'))}{unit}"
        return f"{sign}{cur}{int(a.quantize(Decimal(1)))}"
    raise ValueError(f"unknown format {kind!r}; use one of {', '.join(FORMATS)}")


def _default(v, dtype: str) -> str:
    if isinstance(v, bool):
        return "text"
    if isinstance(v, int):
        return "int"
    if isinstance(v, (Decimal, float)):
        return "num"
    if isinstance(v, datetime):
        return "text"
    return "text"


def fmt_cell(v, dtype: str = "") -> str:
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%d %H:%M")
    if isinstance(v, Decimal):
        return f"{v:,}"
    if isinstance(v, float):
        return f"{v:,.4g}" if abs(v) < 1 else f"{v:,.2f}"
    if isinstance(v, int) and not isinstance(v, bool):
        return f"{v:,}"
    return fmt(v, "text")
