"""Column converters + conservative generic type inference.

Every converter maps a raw value to a canonical *string* (or None) that DuckDB then CASTs to the
declared type. Converters raise ValueError rather than guess; inference falls back to VARCHAR.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

_INT = re.compile(r"^[+-]?\d+$")
_PLAIN = re.compile(r"^-?\d+(\.\d+)?$")
_WEST = re.compile(r"^-?\d{1,3}(,\d{3})+(\.\d+)?$")           # 1,234,567.89
_INDIAN = re.compile(r"^-?\d{1,2}(,\d{2})*,\d{3}(\.\d+)?$")   # 12,34,567.89
_EURO = re.compile(r"^-?\d{1,3}(\.\d{3})+,\d+$")              # 1.234,56  (ambiguous → never parsed)
_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}(?:[ T]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?)?(?:Z|[+-]\d{2}:?\d{2})?$")
_SLASH = re.compile(r"^(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})(?:[ T](\d{1,2}):(\d{2})(?::(\d{2}))?)?$")
_CURRENCY = "₹$€£"
EXCEL_EPOCH = datetime(1899, 12, 30)
# ISO 4217 minor-unit exponents that differ from 2 (Razorpay/Stripe-style integer amounts).
_EXP = {**dict.fromkeys("BIF CLP DJF GNF ISK JPY KMF KRW PYG RWF UGX VND VUV XAF XOF XPF".split(), 0),
        **dict.fromkeys("BHD IQD JOD KWD LYD OMR TND".split(), 3)}


class Ambiguous(Exception):
    """Inference refuses to pick; carries a diagnostic code + fix hint."""
    def __init__(self, code: str, msg: str):
        super().__init__(msg)
        self.code = code


@dataclass
class Ctx:
    tz: ZoneInfo
    minor_units: bool = False
    row: dict = field(default_factory=dict)


def _num_str(v) -> str:
    if isinstance(v, bool):
        raise ValueError("boolean is not a number")
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        if v != v or v in (float("inf"), float("-inf")):
            raise ValueError("non-finite number")
        return repr(v)                                   # shortest round-trip repr: 0.99 not 0.98999…
    if isinstance(v, Decimal):
        return str(v)
    s = str(v).strip()
    if s[:1] in _CURRENCY:
        s = s[1:].strip()
    if _WEST.match(s) or _INDIAN.match(s):
        s = s.replace(",", "")
    if not _PLAIN.match(s.lstrip("+")):
        raise ValueError(f"not a number: {v!r}")
    return s.lstrip("+")


def to_decimal(v) -> Decimal:
    try:
        d = Decimal(_num_str(v))
    except InvalidOperation as e:
        raise ValueError(f"not a number: {v!r}") from e
    if "E" in str(d):
        d = Decimal(format(d, "f"))
    return d


def scale_of(v) -> int:
    e = to_decimal(v).as_tuple().exponent
    return -e if e < 0 else 0


def conv_text(v, ctx):
    if isinstance(v, float) and v.is_integer() and abs(v) < 2**53:
        return str(int(v))        # Excel stores ids/phones typed as numbers as floats: 9.19e11 → "919900990099"
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    return str(v)


def conv_int(v, ctx):
    if isinstance(v, float):
        if not v.is_integer():
            raise ValueError(f"not an integer: {v!r}")
        return str(int(v))
    s = _num_str(v)
    if not _INT.match(s):
        raise ValueError(f"not an integer: {v!r}")
    if not -2**63 <= int(s) < 2**63:
        raise ValueError(f"integer out of BIGINT range: {v!r}")
    return s


def make_decimal(scale: int):
    q = Decimal(1).scaleb(-scale)

    def conv(v, ctx):
        d = to_decimal(v)
        r = d.quantize(q)
        if r != d:
            raise ValueError(f"{v!r} has more than {scale} decimal places")
        return str(r)
    return conv


def conv_money_minor(v, ctx):
    """Integer minor units (paise) → major units, exponent from the row's currency."""
    cur = str(ctx.row.get("currency") or "INR").upper()
    exp = _EXP.get(cur, 2)
    if exp > 2:
        raise ValueError(f"currency {cur} has {exp} decimal places; DECIMAL(18,2) money cannot hold it exactly")
    d = to_decimal(conv_int(v, ctx)).scaleb(-exp)
    return str(d.quantize(Decimal("0.01")))


def conv_money(v, ctx):
    return conv_money_minor(v, ctx) if ctx.minor_units else make_decimal(2)(v, ctx)


_TRUE, _FALSE = {"true", "t", "yes", "y", "1", "1.0"}, {"false", "f", "no", "n", "0", "0.0"}


def conv_bool(v, ctx):
    if isinstance(v, bool):
        return "true" if v else "false"
    s = str(v).strip().lower()
    if s in _TRUE:
        return "true"
    if s in _FALSE:
        return "false"
    raise ValueError(f"not a boolean: {v!r}")


def _parse_dt(v, order: str | None) -> tuple[datetime, bool]:
    """→ (datetime, has_time). order ∈ {'dmy','mdy',None}; None accepts ISO only."""
    if isinstance(v, datetime):
        return v, True
    if isinstance(v, date):
        return datetime(v.year, v.month, v.day), False
    s = str(v).strip()
    if _ISO.match(s):
        return datetime.fromisoformat(s.replace("Z", "+00:00")), len(s) > 10
    m = _SLASH.match(s)
    if m and order:
        a, b, y = int(m[1]), int(m[2]), int(m[3])
        d, mo = (a, b) if order == "dmy" else (b, a)
        return datetime(y, mo, d, int(m[4] or 0), int(m[5] or 0), int(m[6] or 0)), m[4] is not None
    raise ValueError(f"not a recognized date/time: {v!r}")


def make_timestamp(order: str | None = None, local_tz: bool = False):
    """Naive values: TIMESTAMP, or (local_tz) interpreted in the project TZ → TIMESTAMPTZ."""
    def conv(v, ctx):
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            if not 20000 < v < 80000:
                raise ValueError(f"number {v!r} is not a plausible Excel date serial")
            v = EXCEL_EPOCH + timedelta(days=float(v))
        dt, _ = _parse_dt(v, order)
        if local_tz:
            dt = dt.replace(tzinfo=ctx.tz) if dt.tzinfo is None else dt
            return dt.isoformat(sep=" ")
        if dt.tzinfo is not None:
            raise ValueError(f"{v!r} has a UTC offset in a timestamp-without-zone column")
        return dt.isoformat(sep=" ")
    return conv


def conv_unix(v, ctx):
    return datetime.fromtimestamp(int(conv_int(v, ctx)), timezone.utc).isoformat(sep=" ")


def conv_json(v, ctx):
    if isinstance(v, (dict, list)):
        return json.dumps(v)
    return str(v)


# Named converters usable from packs and `--types col=<name>` overrides: name → (duckdb type, fn)
NAMED = {
    "text": ("VARCHAR", conv_text),
    "int": ("BIGINT", conv_int),
    "bool": ("BOOLEAN", conv_bool),
    "money": ("DECIMAL(18,2)", conv_money),
    "json": ("VARCHAR", conv_json),
    "timestamp": ("TIMESTAMP", make_timestamp()),
    "date:dmy": ("TIMESTAMP", make_timestamp("dmy")),
    "date:mdy": ("TIMESTAMP", make_timestamp("mdy")),
    "local:dmy": ("TIMESTAMPTZ", make_timestamp("dmy", local_tz=True)),
    "unix": ("TIMESTAMPTZ", conv_unix),
}


def named(name: str):
    if name in NAMED:
        return NAMED[name]
    if m := re.fullmatch(r"decimal(?::(\d+))?", name):
        s = int(m[1] or 2)
        return f"DECIMAL({18 if s <= 6 else 38},{s})", make_decimal(s)
    raise ValueError(f"unknown type {name!r}; use one of: {', '.join(NAMED)}, decimal:<scale>")


def infer(values: list) -> tuple[str, str]:
    """Pick (converter name, reason). Raises Ambiguous when a choice would be a guess."""
    vals = [v for v in values if not (v is None or (isinstance(v, str) and not v.strip()))]
    if not vals:
        return "text", "all empty"
    strs = [v.strip() for v in vals if isinstance(v, str)]
    for s in strs:
        if s[:1] in "=@+" or (s.isdigit() and ((len(s) > 1 and s[0] == "0") or len(s) > 15)):
            return "text", f"identifier-like or formula-like text, e.g. {s!r}"
        if _EURO.match(s):
            raise Ambiguous("AMBIGUOUS_NUMBER", f"{s!r} could be 1.234,56 (decimal comma) or a version/id; "
                                                "pass --types <col>=text or clean the file")
    if all(isinstance(v, bool) for v in vals) or (strs and len(strs) == len(vals)
                                                     and all(s.lower() in ("true", "false") for s in strs)):
        return "bool", "booleans"
    if all(isinstance(v, (int, float, str)) and not isinstance(v, bool) for v in vals):
        try:
            for v in vals:
                conv_int(v, None)
            return "int", "integers"
        except ValueError:
            pass
        try:
            s = max(scale_of(v) for v in vals)
            return (f"decimal:{s}", "exact decimals") if s <= 6 else ("double", "floating point")
        except ValueError:
            pass
    if any(isinstance(v, (datetime, date)) for v in vals) or any(_ISO.match(s) or _SLASH.match(s) for s in strs):
        slash = [m for s in strs if (m := _SLASH.match(s))]
        order = None
        if slash:
            dmy = any(int(m[1]) > 12 for m in slash)
            mdy = any(int(m[2]) > 12 for m in slash)
            if dmy and mdy:
                return "text", "mixed day-first and month-first dates"
            if not (dmy or mdy):
                raise Ambiguous("AMBIGUOUS_DATE", f"dates like {slash[0][0]!r} could be day-first or month-first; "
                                                  "pass --types <col>=date:dmy or date:mdy")
            order = "dmy" if dmy else "mdy"
        try:
            tz = {_parse_dt(v, order)[0].tzinfo is not None for v in vals}
        except ValueError:
            return "text", "mixed dates and text"
        if tz == {True}:
            return "tz_timestamp", "timestamps with UTC offsets"
        if tz == {False}:
            return ("date:" + order) if order else "timestamp", "timestamps"
        return "text", "mixed timestamps with and without UTC offsets"
    kinds = sorted({type(v).__name__ for v in vals})
    return "text", "text" if kinds == ["str"] else f"mixed value types ({', '.join(kinds)})"


def resolve(name: str):
    if name == "double":
        return "DOUBLE", lambda v, ctx: _num_str(v)
    if name == "tz_timestamp":
        return "TIMESTAMPTZ", lambda v, ctx: _parse_dt(v, None)[0].isoformat(sep=" ")
    return named(name)
