"""Deterministic masking of dates, asset identifiers and named events.

Masking is the usual mitigation for look-ahead bias in LLM backtests: the
model should reason from the numbers, not from remembering what happened
to AAPL after 2024-10-12. Dates become offsets from the decision date
(``D-5``, ``M-1``, ``Q+1``, ``Y-2``), assets become ``ASSET_1``... and named
events become ``EVENT_1``....

Masking lowers re-identification risk; it does not remove it. Distinctive
price paths and numbers can still identify a period.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Sequence, Tuple

from .dates import find_dates
from .detect import find_assets, find_events


@dataclass
class MaskResult:
    text: str
    mapping: Dict[str, str] = field(default_factory=dict)  # alias -> original

    def unmask(self, text: str) -> str:
        return unmask(text, self.mapping)


def _offset(prefix: str, n: int) -> str:
    return f"{prefix}{'+' if n >= 0 else '-'}{abs(n)}"


def _date_alias(mention, as_of: date) -> str:
    if mention.granularity == "day":
        return _offset("D", (mention.earliest - as_of).days)
    if mention.granularity == "month":
        months = (mention.earliest.year - as_of.year) * 12 + (mention.earliest.month - as_of.month)
        return _offset("M", months)
    if mention.granularity == "quarter":
        q_m = (mention.earliest.month - 1) // 3
        q_a = (as_of.month - 1) // 3
        return _offset("Q", (mention.earliest.year - as_of.year) * 4 + (q_m - q_a))
    return _offset("Y", mention.earliest.year - as_of.year)


class Masker:
    """Keeps alias numbering stable across many texts (e.g. a whole log)."""

    def __init__(self, entities: Sequence[str] = ()) -> None:
        self.entities = list(entities)
        self.asset_alias: Dict[str, str] = {}
        self.event_alias: Dict[str, str] = {}
        self.mapping: Dict[str, str] = {}

    def _asset(self, key: str, original: str) -> str:
        if key not in self.asset_alias:
            self.asset_alias[key] = f"ASSET_{len(self.asset_alias) + 1}"
            self.mapping[self.asset_alias[key]] = key
        return self.asset_alias[key]

    def _event(self, name: str) -> str:
        if name not in self.event_alias:
            self.event_alias[name] = f"EVENT_{len(self.event_alias) + 1}"
            self.mapping[self.event_alias[name]] = name
        return self.event_alias[name]

    def mask(self, text: str, as_of: date, entities: Sequence[str] = ()) -> MaskResult:
        spans: List[Tuple[int, int, str]] = []

        def free(start, end):
            return not any(start < e and end > s for s, e, _ in spans)

        for ev in find_events(text):
            if free(ev.start, ev.end):
                spans.append((ev.start, ev.end, self._event(ev.key)))
        for a in find_assets(text, list(self.entities) + list(entities)):
            if free(a.start, a.end):
                alias = self._asset(a.key, a.text)
                if a.kind == "cashtag":
                    alias = "$" + alias
                spans.append((a.start, a.end, alias))
        for d in find_dates(text, as_of):
            if not d.relative and free(d.start, d.end):
                alias = _date_alias(d, as_of)
                self.mapping.setdefault(alias, d.text)
                spans.append((d.start, d.end, alias))

        out = text
        for start, end, alias in sorted(spans, key=lambda s: s[0], reverse=True):
            out = out[:start] + alias + out[end:]
        return MaskResult(out, dict(self.mapping))


def mask_text(text: str, as_of: date, entities: Sequence[str] = ()) -> MaskResult:
    """Mask one text. Use :class:`Masker` to share aliases across texts."""
    return Masker(entities).mask(text, as_of)


def unmask(text: str, mapping: Dict[str, str]) -> str:
    """Put asset and event names back into a model answer (dates stay relative)."""
    for alias in sorted(mapping, key=len, reverse=True):
        if alias.startswith(("ASSET_", "EVENT_")):
            text = text.replace(alias, mapping[alias])
    return text
