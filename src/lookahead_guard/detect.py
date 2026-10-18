"""Detectors for asset identifiers and named events in text."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence

from .lexicon import AMBIGUOUS_TICKERS, ASSETS, EVENTS, Event


@dataclass(frozen=True)
class Span:
    text: str
    start: int
    end: int
    key: str  # canonical identity, e.g. the ticker for both "AAPL" and "Apple"
    kind: str  # "ticker" | "cashtag" | "company" | "entity" | "event"
    event: Optional[Event] = None


def _ticker_regex() -> re.Pattern:
    tickers = sorted((t for t in ASSETS if t not in AMBIGUOUS_TICKERS), key=len, reverse=True)
    alt = "|".join(re.escape(t) for t in tickers)
    return re.compile(rf"(?<![A-Za-z0-9$.])(?:{alt})(?![A-Za-z0-9]|\.[A-Z])")


_TICKER_RE = _ticker_regex()
_CASHTAG_RE = re.compile(r"\$([A-Z]{1,5}(?:\.[A-Z])?)(?![A-Za-z0-9])")
_EXCHANGE_RE = re.compile(r"\b(?:NASDAQ|NYSE|NYSEARCA|NYSE American|AMEX|KRX|TSE|LSE)\s*:\s*([A-Z0-9.]{1,8})\b")

_NAME_TO_KEY = {}
for _ticker, _names in ASSETS.items():
    for _name in _names:
        _NAME_TO_KEY.setdefault(_name, _ticker)
_NAME_RE = re.compile(
    r"(?<![A-Za-z0-9])(?:"
    + "|".join(re.escape(n) for n in sorted(_NAME_TO_KEY, key=len, reverse=True))
    + r")(?:'s)?(?![A-Za-z0-9])"
)


def _overlaps(span, taken) -> bool:
    return any(span[0] < e and span[1] > s for s, e in taken)


def find_assets(text: str, entities: Sequence[str] = ()) -> List[Span]:
    """Find tickers, cashtags, exchange-prefixed symbols, company names and
    user-supplied entity strings."""
    out: List[Span] = []
    taken: List[tuple] = []

    def add(start, end, key, kind):
        if _overlaps((start, end), taken):
            return
        taken.append((start, end))
        out.append(Span(text[start:end], start, end, key, kind))

    for ent in sorted(set(e for e in entities if e), key=len, reverse=True):
        for m in re.finditer(rf"(?<![A-Za-z0-9]){re.escape(ent)}(?![A-Za-z0-9])", text):
            add(m.start(), m.end(), ent, "entity")
    for m in _EXCHANGE_RE.finditer(text):
        add(m.start(), m.end(), m.group(1), "ticker")
    for m in _CASHTAG_RE.finditer(text):
        add(m.start(), m.end(), m.group(1), "cashtag")
    for m in _TICKER_RE.finditer(text):
        add(m.start(), m.end(), m.group(0), "ticker")
    for m in _NAME_RE.finditer(text):
        name = m.group(0)
        if name.endswith("'s"):
            name = name[:-2]
        add(m.start(), m.end(), _NAME_TO_KEY.get(name, name.upper()), "company")
    out.sort(key=lambda s: s.start)
    return out


def find_events(text: str, events: Iterable[Event] = EVENTS) -> List[Span]:
    out: List[Span] = []
    for ev in events:
        for m in ev.pattern.finditer(text):
            out.append(Span(m.group(0), m.start(), m.end(), ev.name, "event", ev))
    out.sort(key=lambda s: s.start)
    return out


_SENT_END = re.compile(r"(?<=[.!?;])\s+|\n+")


def sentence_around(text: str, start: int, end: int) -> tuple:
    """Return (sentence_start, sentence_end) of the sentence containing a span."""
    s_start, s_end = 0, len(text)
    for m in _SENT_END.finditer(text):
        if m.end() <= start:
            s_start = m.end()
        elif m.start() >= end:
            s_end = m.start()
            break
    return s_start, s_end
