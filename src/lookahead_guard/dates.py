"""Find date mentions in free text and resolve them to date ranges.

Every mention is resolved to an ``[earliest, latest]`` interval, so a
coarse mention such as ``"2025"`` or ``"Q3 2024"`` can still be compared
with a decision date: a mention is *in the future* of ``as_of`` when even
its earliest possible day is after ``as_of``.

The extractor is deliberately conservative and dependency free. It is a
heuristic, not a full temporal parser.
"""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import date, timedelta
from typing import List, Optional, Tuple

_MONTHS = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}

_MON = (
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?|"
    r"Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?"
)
_YEAR = r"(?:19|20)\d{2}"
_ORD = r"(?:st|nd|rd|th)?"


@dataclass(frozen=True)
class DateMention:
    """A date-like span in a text, resolved to the interval it can mean."""

    text: str
    start: int
    end: int
    earliest: date
    latest: date
    granularity: str  # "day" | "month" | "quarter" | "year"
    inferred_year: bool = False
    relative: bool = False  # a masked offset such as "D+86" (see mask.py)

    def is_after(self, as_of: date) -> bool:
        return self.earliest > as_of


def _month_num(token: str) -> int:
    return _MONTHS[token.lower().rstrip(".")]


def _last_day(year: int, month: int) -> date:
    return date(year, month, calendar.monthrange(year, month)[1])


def _safe_day(year: int, month: int, day: int) -> Optional[date]:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _two_digit_year(token: str) -> int:
    token = token.lstrip("'")
    year = int(token)
    return year if year >= 100 else 2000 + year


def _infer_year(month: int, day: int, as_of: date) -> Optional[date]:
    """Pick the year that puts month/day closest to ``as_of``."""
    best = None
    for year in (as_of.year - 1, as_of.year, as_of.year + 1):
        candidate = _safe_day(year, month, day)
        if candidate is None:
            continue
        if best is None or abs((candidate - as_of).days) < abs((best - as_of).days):
            best = candidate
    return best


# Resolvers take (match, as_of) and return (earliest, latest, granularity,
# inferred_year) or None to reject the match.


def _r_iso_day(m, as_of):
    d = _safe_day(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    return (d, d, "day", False) if d else None


def _r_mdy(m, as_of):
    d = _safe_day(int(m.group(3)), _month_num(m.group(1)), int(m.group(2)))
    return (d, d, "day", False) if d else None


def _r_dmy(m, as_of):
    d = _safe_day(int(m.group(3)), _month_num(m.group(2)), int(m.group(1)))
    return (d, d, "day", False) if d else None


def _r_us_numeric(m, as_of):
    d = _safe_day(int(m.group(3)), int(m.group(1)), int(m.group(2)))
    return (d, d, "day", False) if d else None


def _r_month_day_no_year(m, as_of):
    if as_of is None:
        return None
    d = _infer_year(_month_num(m.group(1)), int(m.group(2)), as_of)
    return (d, d, "day", True) if d else None


def _r_month_year(m, as_of):
    year, month = int(m.group(2)), _month_num(m.group(1))
    return (date(year, month, 1), _last_day(year, month), "month", False)


def _r_iso_month(m, as_of):
    year, month = int(m.group(1)), int(m.group(2))
    return (date(year, month, 1), _last_day(year, month), "month", False)


def _quarter(year: int, q: int):
    first = 3 * (q - 1) + 1
    return (date(year, first, 1), _last_day(year, first + 2), "quarter", False)


def _r_q_year(m, as_of):
    return _quarter(_two_digit_year(m.group(2)), int(m.group(1)))


def _r_nq_year(m, as_of):
    return _quarter(_two_digit_year(m.group(2)), int(m.group(1)))


def _r_fiscal(m, as_of):
    year = _two_digit_year(m.group(1))
    return (date(year, 1, 1), date(year, 12, 31), "year", False)


def _r_year(m, as_of):
    year = int(m.group(1))
    # A bare four-digit number far in the future is more likely a price or
    # an index level than a year.
    if as_of is not None and year > as_of.year + 5:
        return None
    return (date(year, 1, 1), date(year, 12, 31), "year", False)


def _r_relative(m, as_of):
    """Masked offsets (``D+86``, ``M-1``, ``Q+1``, ``Y-2``), the inverse of mask.py."""
    if as_of is None:
        return None
    unit, n = m.group(1), int(m.group(2))
    try:
        if unit == "D":
            d = as_of + timedelta(days=n)
            return (d, d, "day", False)
        if unit == "Y":
            y = as_of.year + n
            return (date(y, 1, 1), date(y, 12, 31), "year", False)
        months = n if unit == "M" else 3 * n
        start_month = as_of.month if unit == "M" else 3 * ((as_of.month - 1) // 3) + 1
        idx = as_of.year * 12 + start_month - 1 + months
        year, month = divmod(idx, 12)
        if unit == "M":
            return (date(year, month + 1, 1), _last_day(year, month + 1), "month", False)
        return _quarter(year, month // 3 + 1)
    except (ValueError, OverflowError):
        return None


# Order matters: earlier, more specific patterns claim their span first.
_PATTERNS = [
    (re.compile(rf"\b({_YEAR})[-/.](\d{{1,2}})[-/.](\d{{1,2}})\b"), _r_iso_day),
    (re.compile(rf"\b({_MON})\s+(\d{{1,2}}){_ORD},?\s+({_YEAR})\b"), _r_mdy),
    (re.compile(rf"\b(\d{{1,2}}){_ORD}\s+({_MON}),?\s+({_YEAR})\b"), _r_dmy),
    (re.compile(rf"\b(\d{{1,2}})/(\d{{1,2}})/({_YEAR})\b"), _r_us_numeric),
    (re.compile(rf"\b({_MON})\s+({_YEAR})\b"), _r_month_year),
    (re.compile(rf"\b({_MON})\s+(\d{{1,2}}){_ORD}\b(?!\s*(?:%|,?\s*\d))"), _r_month_day_no_year),
    (re.compile(rf"\b({_YEAR})-(0[1-9]|1[0-2])\b(?![-/]\d)"), _r_iso_month),
    (re.compile(r"\bQ([1-4])(?:\s+|\s*'|-|\s*FY)?((?:19|20)\d{2}|\d{2})\b"), _r_q_year),
    (re.compile(r"\b([1-4])Q((?:19|20)\d{2}|\d{2})\b"), _r_nq_year),
    (re.compile(r"\b(?:FY|fiscal(?:\s+year)?)\s?((?:19|20)\d{2}|'?\d{2})\b"), _r_fiscal),
    (re.compile(r"(?<![A-Za-z0-9_])([DMQY])([+-]\d{1,5})\b(?![.,]\d)"), _r_relative),
    (re.compile(rf"(?<![$\d.,])\b({_YEAR})\b(?![.,]\d)(?!\s*%)"), _r_year),
]


def find_dates(text: str, as_of: Optional[date] = None) -> List[DateMention]:
    """Return non-overlapping date mentions in ``text``, in text order.

    ``as_of`` is used to infer the year of mentions such as ``"Oct 30"`` and
    to ignore implausible far-future "years" (often prices).
    """
    claimed: List[Tuple[int, int]] = []
    found: List[DateMention] = []
    for pattern, resolver in _PATTERNS:
        for m in pattern.finditer(text):
            start, end = m.span()
            if any(start < c_end and end > c_start for c_start, c_end in claimed):
                continue
            resolved = resolver(m, as_of)
            if resolved is None:
                continue
            earliest, latest, granularity, inferred = resolved
            claimed.append((start, end))
            found.append(
                DateMention(m.group(0), start, end, earliest, latest, granularity, inferred,
                            relative=resolver is _r_relative)
            )
    found.sort(key=lambda d: d.start)
    return found


def parse_date(value: str) -> date:
    """Parse ``YYYY-MM-DD`` or ``YYYY-MM`` (end of month) or ``YYYY`` (end of year).

    Timestamps such as ``2024-10-12T20:00:00Z`` are accepted; only the date
    part is used.
    """
    value = str(value).strip()
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", value)
    if m:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = re.match(r"^(\d{4})-(\d{2})$", value)
    if m:
        return _last_day(int(m.group(1)), int(m.group(2)))
    m = re.match(r"^(\d{4})$", value)
    if m:
        return date(int(m.group(1)), 12, 31)
    raise ValueError(f"not a date: {value!r} (expected YYYY-MM-DD, YYYY-MM or YYYY)")


def add_days(d: date, days: int) -> date:
    return d + timedelta(days=days)
