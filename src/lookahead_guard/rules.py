"""The checker: turns one backtest record into a list of findings.

Rule families
-------------
LAG0xx  exposure    - does the model's training data overlap the decision
                      date and the outcome window?
LAG1xx  prompt      - does the text sent to the model contain information
                      from after the decision date?
LAG2xx  identity    - does the prompt let the model recognise *when* and
                      *what* it is looking at (dates, tickers, named events)?
                      Only matters when the model is exposed.
LAG3xx  response    - does the model's own answer cite things that happened
                      after the decision date (a sign of recall)?
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Dict, List, Optional, Sequence

from .cutoffs import CutoffTable, ModelCutoff
from .dates import DateMention, find_dates
from .detect import find_assets, find_events, sentence_around
from .lexicon import FORWARD_STRONG, FORWARD_WEAK, HINDSIGHT, REALIZED

SEVERITIES = ("info", "warning", "error")
SEVERITY_RANK = {s: i for i, s in enumerate(SEVERITIES)}

RULES: Dict[str, str] = {
    "LAG000": "record-invalid",
    "LAG001": "exposure-full",
    "LAG002": "exposure-partial",
    "LAG003": "model-cutoff-unknown",
    "LAG101": "future-dated-fact",
    "LAG102": "future-date-unclear",
    "LAG103": "future-date-scheduled",
    "LAG104": "anachronistic-event",
    "LAG105": "hindsight-language",
    "LAG201": "absolute-date-visible",
    "LAG202": "asset-identifier-visible",
    "LAG203": "era-event-visible",
    "LAG301": "response-cites-future",
    "LAG302": "response-hindsight",
}


@dataclass
class Record:
    """One LLM decision in a backtest."""

    as_of: Optional[date]
    prompt: str
    model: Optional[str] = None
    response: str = ""
    horizon_days: Optional[int] = None
    entities: List[str] = field(default_factory=list)
    id: Optional[str] = None
    source: Optional[str] = None
    line: Optional[int] = None


@dataclass
class Finding:
    rule: str
    severity: str
    message: str
    where: str = "record"  # "record" | "prompt" | "response"
    excerpt: str = ""
    start: Optional[int] = None
    end: Optional[int] = None

    @property
    def name(self) -> str:
        return RULES.get(self.rule, self.rule)

    def to_dict(self) -> dict:
        return {
            "rule": self.rule,
            "name": self.name,
            "severity": self.severity,
            "where": self.where,
            "message": self.message,
            "excerpt": self.excerpt,
            "start": self.start,
            "end": self.end,
        }


@dataclass
class Exposure:
    status: str  # "none" | "partial" | "full" | "unknown"
    cutoff: Optional[ModelCutoff] = None
    window_end: Optional[date] = None


@dataclass
class RecordResult:
    record: Record
    exposure: Exposure
    findings: List[Finding]

    @property
    def max_severity(self) -> Optional[str]:
        if not self.findings:
            return None
        return max((f.severity for f in self.findings), key=SEVERITY_RANK.__getitem__)

    def to_dict(self) -> dict:
        r = self.record
        return {
            "id": r.id,
            "source": r.source,
            "line": r.line,
            "as_of": r.as_of.isoformat() if r.as_of else None,
            "model": r.model,
            "horizon_days": r.horizon_days,
            "exposure": {
                "status": self.exposure.status,
                "model_cutoff": self.exposure.cutoff.cutoff.isoformat() if self.exposure.cutoff else None,
                "matched_model": self.exposure.cutoff.id if self.exposure.cutoff else None,
                "outcome_window_end": self.exposure.window_end.isoformat() if self.exposure.window_end else None,
            },
            "findings": [f.to_dict() for f in self.findings],
        }


def _excerpt(text: str, start: int, end: int, width: int = 40) -> str:
    a, b = max(0, start - width), min(len(text), end + width)
    snippet = text[a:b].replace("\n", " ")
    return ("..." if a > 0 else "") + snippet + ("..." if b < len(text) else "")


def classify_context(text: str, mention: DateMention, mentions: Sequence[DateMention]) -> str:
    """Classify the sentence around a date mention: realized / scheduled / unclear.

    Date spans themselves are blanked first so that "May" (the month) is not
    read as the modal verb "may".
    """
    s, e = sentence_around(text, mention.start, mention.end)
    chars = list(text[s:e])
    for m in mentions:
        if m.end <= s or m.start >= e:
            continue
        for i in range(max(m.start, s), min(m.end, e)):
            chars[i - s] = " "
    sentence = "".join(chars)
    if FORWARD_STRONG.search(sentence):
        return "scheduled"
    if REALIZED.search(sentence):
        return "realized"
    if FORWARD_WEAK.search(sentence):
        return "scheduled"
    return "unclear"


class Checker:
    """Run every rule over records.

    Parameters
    ----------
    cutoffs:
        Cutoff table; defaults to the bundled one.
    default_model, default_horizon_days:
        Used when a record does not say.
    cutoff_override:
        Treat every model as having this cutoff (``YYYY-MM[-DD]``).
    margin_days:
        Extra days added to every cutoff, to be conservative about
        vendor-reported dates.
    """

    def __init__(
        self,
        cutoffs: Optional[CutoffTable] = None,
        default_model: Optional[str] = None,
        default_horizon_days: Optional[int] = None,
        cutoff_override: Optional[date] = None,
        margin_days: int = 0,
        entities: Sequence[str] = (),
    ) -> None:
        self.cutoffs = cutoffs or CutoffTable.bundled()
        self.default_model = default_model
        self.default_horizon_days = default_horizon_days
        self.cutoff_override = cutoff_override
        self.margin_days = margin_days
        self.entities = list(entities)

    # -- exposure -------------------------------------------------------------
    def exposure(self, record: Record) -> Exposure:
        model = record.model or self.default_model
        horizon = record.horizon_days if record.horizon_days is not None else self.default_horizon_days
        horizon = 1 if horizon is None else max(0, int(horizon))
        if self.cutoff_override is not None:
            mc = ModelCutoff(id=model or "override", vendor="user", cutoff=self.cutoff_override, kind="user")
        else:
            mc = self.cutoffs.lookup(model)
        if record.as_of is None:
            return Exposure("unknown", mc)
        window_end = record.as_of + timedelta(days=horizon)
        if mc is None:
            return Exposure("unknown", None, window_end)
        cutoff = mc.cutoff + timedelta(days=self.margin_days)
        if record.as_of > cutoff:
            return Exposure("none", mc, window_end)
        if window_end <= cutoff:
            return Exposure("full", mc, window_end)
        return Exposure("partial", mc, window_end)

    # -- main -------------------------------------------------------------------
    def check(self, record: Record) -> RecordResult:
        findings: List[Finding] = []
        if record.as_of is None:
            findings.append(Finding("LAG000", "error", "record has no as_of / decision date; cannot check it"))
            return RecordResult(record, Exposure("unknown"), findings)

        as_of = record.as_of
        exp = self.exposure(record)
        exposed = exp.status != "none"
        entities = list(self.entities) + list(record.entities)
        prompt = record.prompt or ""

        # Prompt: future information and identifiers.
        p_dates = find_dates(prompt, as_of)
        p_events = find_events(prompt)
        p_assets = find_assets(prompt, entities)
        prompt_findings = self._future_findings(prompt, as_of, p_dates, p_events, where="prompt")
        identity = self._identity_findings(prompt, as_of, p_dates, p_events, p_assets, exposed)

        findings.extend(self._exposure_findings(record, exp, identity_visible=bool(identity)))
        findings.extend(prompt_findings)
        findings.extend(identity)

        # Response: evidence that the model recalled the future.
        if record.response:
            findings.extend(self._response_findings(record.response, as_of))

        findings.sort(key=lambda f: (-SEVERITY_RANK[f.severity], f.rule, f.start or 0))
        return RecordResult(record, exp, findings)

    def check_all(self, records: Sequence[Record]) -> List[RecordResult]:
        return [self.check(r) for r in records]

    # -- rule groups ------------------------------------------------------------
    def _exposure_findings(self, record: Record, exp: Exposure, identity_visible: bool) -> List[Finding]:
        model = record.model or self.default_model
        if exp.status == "unknown":
            if not model:
                return [Finding("LAG003", "warning", "no model given; pass --model or a 'model' field to check training-data exposure")]
            return [Finding("LAG003", "warning", f"no known cutoff for model {model!r}; pass --cutoff YYYY-MM or --cutoffs FILE")]
        if exp.status == "none":
            return []
        cut = exp.cutoff.cutoff.isoformat()
        if exp.status == "full":
            if identity_visible:
                return [Finding(
                    "LAG001", "error",
                    f"{exp.cutoff.id} was trained on data to about {cut}, after this decision "
                    f"({record.as_of.isoformat()}) and its whole outcome window (to {exp.window_end.isoformat()}); "
                    "the prompt also shows dates/assets/events, so the model can look up what happened",
                )]
            return [Finding(
                "LAG001", "warning",
                f"{exp.cutoff.id} was trained on data to about {cut}, covering the whole outcome window; "
                "no identifiers were found in the prompt, which lowers but does not remove the risk "
                "(price patterns and numbers can still identify the period)",
            )]
        return [Finding(
            "LAG002", "warning",
            f"{exp.cutoff.id} cutoff (~{cut}) falls inside the outcome window "
            f"({record.as_of.isoformat()} to {exp.window_end.isoformat()}); part of the outcome may be memorized",
        )]

    def _future_findings(self, text, as_of, dates, events, where) -> List[Finding]:
        out: List[Finding] = []
        for d in dates:
            if not d.is_after(as_of):
                continue
            ctx = classify_context(text, d, dates)
            if d.granularity == "year" and ctx != "realized":
                # "FY2025 guidance" in a 2024 prompt is normal.
                if ctx == "unclear":
                    out.append(Finding("LAG102", "warning",
                                       f"mentions {d.text!r}, after the decision date {as_of.isoformat()}; check it is a forecast, not an outcome",
                                       where, _excerpt(text, d.start, d.end), d.start, d.end))
                continue
            if ctx == "realized":
                out.append(Finding("LAG101", "error",
                                   f"states something about {d.text!r}, which is after the decision date {as_of.isoformat()}",
                                   where, _excerpt(text, d.start, d.end), d.start, d.end))
            elif ctx == "scheduled":
                out.append(Finding("LAG103", "info",
                                   f"refers to future date {d.text!r} as scheduled/expected; fine if it was known on {as_of.isoformat()}",
                                   where, _excerpt(text, d.start, d.end), d.start, d.end))
            else:
                out.append(Finding("LAG102", "warning",
                                   f"mentions {d.text!r}, after the decision date {as_of.isoformat()}; check it is not an outcome",
                                   where, _excerpt(text, d.start, d.end), d.start, d.end))
        for ev in events:
            if ev.event.first_known > as_of:
                out.append(Finding("LAG104", "error",
                                   f"names '{ev.event.name}', which only became known on {ev.event.first_known.isoformat()}",
                                   where, _excerpt(text, ev.start, ev.end), ev.start, ev.end))
        for m in HINDSIGHT.finditer(text):
            out.append(Finding("LAG105", "warning",
                               f"hindsight wording {m.group(0)!r} suggests the text was written after the fact",
                               where, _excerpt(text, m.start(), m.end()), m.start(), m.end()))
        return out

    def _identity_findings(self, text, as_of, dates, events, assets, exposed) -> List[Finding]:
        sev = "warning" if exposed else "info"
        out: List[Finding] = []
        past_dates = [d for d in dates if not d.is_after(as_of) and d.granularity in ("day", "month", "quarter")]
        years = [d for d in dates if not d.is_after(as_of) and d.granularity == "year"]
        shown = past_dates + years
        if shown:
            sample = ", ".join(sorted({d.text for d in shown})[:4])
            out.append(Finding("LAG201", sev,
                               f"{len(shown)} absolute date(s) visible ({sample}); mask them as offsets such as D-5",
                               "prompt", _excerpt(text, shown[0].start, shown[0].end), shown[0].start, shown[0].end))
        if assets:
            keys = sorted({a.key for a in assets})
            out.append(Finding("LAG202", sev,
                               f"asset identifiers visible ({', '.join(keys[:5])}{'...' if len(keys) > 5 else ''}); mask them as ASSET_1, ASSET_2",
                               "prompt", _excerpt(text, assets[0].start, assets[0].end), assets[0].start, assets[0].end))
        known_events = [e for e in events if e.event.first_known <= as_of]
        if known_events:
            names = sorted({e.event.name for e in known_events})
            out.append(Finding("LAG203", sev,
                               f"named event(s) date the prompt ({', '.join(names[:3])})",
                               "prompt", _excerpt(text, known_events[0].start, known_events[0].end),
                               known_events[0].start, known_events[0].end))
        return out

    def _response_findings(self, text, as_of) -> List[Finding]:
        out: List[Finding] = []
        dates = find_dates(text, as_of)
        for d in dates:
            if not d.is_after(as_of):
                continue
            ctx = classify_context(text, d, dates)
            if ctx == "realized":
                out.append(Finding("LAG301", "error",
                                   f"the model's answer states what happened on {d.text!r}, after the decision date {as_of.isoformat()} - likely recall",
                                   "response", _excerpt(text, d.start, d.end), d.start, d.end))
        for ev in find_events(text):
            if ev.event.first_known > as_of:
                out.append(Finding("LAG301", "error",
                                   f"the model's answer names '{ev.event.name}' ({ev.event.first_known.isoformat()}), after the decision date - likely recall",
                                   "response", _excerpt(text, ev.start, ev.end), ev.start, ev.end))
        for m in HINDSIGHT.finditer(text):
            out.append(Finding("LAG302", "warning",
                               f"hindsight wording {m.group(0)!r} in the model's answer",
                               "response", _excerpt(text, m.start(), m.end()), m.start(), m.end()))
        return out


def check_record(record: Record, **kwargs) -> RecordResult:
    """Convenience wrapper: ``check_record(Record(...), default_model="gpt-4o")``."""
    return Checker(**kwargs).check(record)


__all__ = ["Checker", "Exposure", "Finding", "Record", "RecordResult", "RULES", "SEVERITIES", "check_record", "classify_context"]

