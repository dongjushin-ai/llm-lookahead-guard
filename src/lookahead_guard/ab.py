"""Masked-vs-raw A/B harness.

Run the same decision function on the raw prompt and on the masked prompt,
score both against the realized outcome, and report the gap. A model whose
score drops a lot once dates and tickers are masked was, at least partly,
remembering rather than reasoning.

The harness is model agnostic: ``decide`` is any callable ``prompt -> decision``
(an API client, a local model, a stub). Nothing here calls a network.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Callable, List, Optional, Sequence

from .mask import Masker
from .rules import Record


@dataclass
class ABRow:
    id: Optional[str]
    raw_score: float
    masked_score: float


@dataclass
class ABResult:
    n: int
    raw_mean: float
    masked_mean: float
    gap: float  # raw - masked
    gap_ci95: tuple
    rows: List[ABRow] = field(default_factory=list)

    def summary(self) -> str:
        lo, hi = self.gap_ci95
        return (f"n={self.n}  raw={self.raw_mean:.3f}  masked={self.masked_mean:.3f}  "
                f"gap={self.gap:+.3f} (95% CI {lo:+.3f} to {hi:+.3f})")


def run_ab(
    records: Sequence[Record],
    outcomes: Sequence[Any],
    decide: Callable[[str], Any],
    score: Callable[[Any, Any], float],
    entities: Sequence[str] = (),
) -> ABResult:
    """Score ``decide`` on raw and masked prompts.

    ``score(decision, outcome)`` returns a number, e.g. 1.0 for a correct
    direction call and 0.0 otherwise. The 95% interval is a normal
    approximation on paired differences; treat small samples with care.
    """
    if len(records) != len(outcomes):
        raise ValueError("records and outcomes must have the same length")
    masker = Masker(entities)
    rows: List[ABRow] = []
    for rec, outcome in zip(records, outcomes):
        if rec.as_of is None:
            raise ValueError(f"record {rec.id!r} has no as_of")
        masked = masker.mask(rec.prompt, rec.as_of, rec.entities).text
        rows.append(ABRow(rec.id, float(score(decide(rec.prompt), outcome)), float(score(decide(masked), outcome))))
    n = len(rows)
    if n == 0:
        return ABResult(0, float("nan"), float("nan"), float("nan"), (float("nan"), float("nan")))
    raw = sum(r.raw_score for r in rows) / n
    msk = sum(r.masked_score for r in rows) / n
    diffs = [r.raw_score - r.masked_score for r in rows]
    gap = raw - msk
    if n > 1:
        var = sum((d - gap) ** 2 for d in diffs) / (n - 1)
        half = 1.96 * math.sqrt(var / n)
    else:
        half = float("inf")
    return ABResult(n, raw, msk, gap, (gap - half, gap + half), rows)
