"""Source packs: optional plugins that recognize a vendor's files and type them exactly.

A pack is any object registered under the `databook.packs` entry-point group with:
  name: str
  kinds: dict[kind, Kind]          # fingerprint columns, JSON entity, table name, column types, key
  timezone: str | None             # suggested project TZ for naive local timestamps
  skill_ref / templates: Path | None
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable
from importlib.metadata import entry_points
from pathlib import Path

MATCH, HINT = 0.8, 0.5


@dataclass
class Kind:
    table: str
    fingerprint: frozenset[str]
    columns: dict[str, str]                         # column → converter name (exports, major units)
    entity: str | None = None                       # JSON items' `entity` value (API / CLI output)
    json_columns: dict[str, str] = field(default_factory=dict)  # overrides for JSON (minor units, unix)
    key: tuple[str, ...] = ("id",)                   # () = no dedup (line items, events, ad rows)
    prepare: Callable | None = None                 # (RawTable) → None: drop footer rows, null tokens, renames


@dataclass
class Match:
    pack: object
    kind: str
    score: float

    @property
    def label(self) -> str:
        return f"{self.pack.name}.{self.kind}"

    @property
    def spec(self) -> Kind:
        return self.pack.kinds[self.kind]


class DetectError(Exception):
    pass


_PACKS: dict[str, object] | None = None


def packs() -> dict[str, object]:
    global _PACKS
    if _PACKS is None:
        _PACKS = {ep.name: ep.load() for ep in entry_points(group="databook.packs")}
    return _PACKS


def detect(headers: list[str], entity: str | None, forced: str | None) -> tuple[Match | None, str | None]:
    """→ (match, hint). Raises DetectError on unknown --as or a tie between packs."""
    if forced:
        pname, _, kind = forced.partition(".")
        p = packs().get(pname)
        if not p or kind not in p.kinds:
            known = ", ".join(f"{n}.{k}" for n, q in packs().items() for k in q.kinds)
            raise DetectError(f"unknown source {forced!r}; known: {known}")
        return Match(p, kind, 1.0), None
    cols, scored = set(headers), []
    for p in packs().values():
        for kind, k in p.kinds.items():
            if entity and k.entity == entity:
                scored.append(Match(p, kind, 1.0))
            elif k.fingerprint:
                scored.append(Match(p, kind, len(k.fingerprint & cols) / len(k.fingerprint)))
    scored.sort(key=lambda m: -m.score)
    if not scored or scored[0].score < HINT:
        return None, None
    best = scored[0]
    if best.score < MATCH:
        return None, f"looks like {best.label} ({best.score:.2f}); pass --as {best.label} to use it"
    ties = [m.label for m in scored if m.score == best.score]
    if len(ties) > 1:
        raise DetectError(f"ambiguous source: matches {', '.join(ties)} equally; pass --as <pack.kind>")
    return best, None


def templates() -> dict[str, Path]:
    out = {}
    for p in packs().values():
        if getattr(p, "templates", None):
            out.update({d.name: d for d in Path(p.templates).iterdir() if d.is_dir()})
    return out
