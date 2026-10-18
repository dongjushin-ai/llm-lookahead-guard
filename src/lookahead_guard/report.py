"""Render check results as text, JSON or GitHub Actions annotations."""

from __future__ import annotations

import json
from collections import Counter
from typing import List, Sequence

from .rules import SEVERITY_RANK, RecordResult


def summarize(results: Sequence[RecordResult]) -> dict:
    exposure = Counter(r.exposure.status for r in results)
    severities = Counter(f.severity for r in results for f in r.findings)
    rules = Counter(f.rule for r in results for f in r.findings)
    worst = Counter(r.max_severity or "clean" for r in results)
    return {
        "records": len(results),
        "records_by_worst_severity": dict(worst),
        "exposure": dict(exposure),
        "findings_by_severity": dict(severities),
        "findings_by_rule": dict(sorted(rules.items())),
    }


def _filter(results, min_severity):
    floor = SEVERITY_RANK[min_severity]
    return [[f for f in r.findings if SEVERITY_RANK[f.severity] >= floor] for r in results]


def _location(r: RecordResult) -> str:
    rec = r.record
    loc = rec.source or "<input>"
    if rec.line:
        loc += f":{rec.line}"
    if rec.id:
        loc += f" [{rec.id}]"
    return loc


_LABEL = {"error": "ERROR", "warning": "WARN ", "info": "info "}


def render_text(results: Sequence[RecordResult], min_severity: str = "info", color: bool = False) -> str:
    def paint(s, code):
        return f"\033[{code}m{s}\033[0m" if color else s

    colors = {"error": "31;1", "warning": "33", "info": "36"}
    lines: List[str] = []
    for r, findings in zip(results, _filter(results, min_severity)):
        rec = r.record
        cut = r.exposure.cutoff.cutoff.isoformat() if r.exposure.cutoff else "?"
        head = (f"{_location(r)}  as_of={rec.as_of.isoformat() if rec.as_of else '?'}  "
                f"model={rec.model or '-'} (cutoff {cut})  exposure={r.exposure.status}")
        lines.append(paint(head, "1"))
        if not findings:
            lines.append("  " + paint("clean", "32"))
        for f in findings:
            lines.append(f"  {paint(_LABEL[f.severity], colors[f.severity])} {f.rule} {f.name}  [{f.where}]")
            lines.append(f"        {f.message}")
            if f.excerpt:
                lines.append(f"        > {f.excerpt}")
        lines.append("")
    s = summarize(results)
    worst = s["records_by_worst_severity"]
    lines.append(
        f"{s['records']} record(s): {worst.get('error', 0)} with errors, {worst.get('warning', 0)} with warnings, "
        f"{worst.get('clean', 0) + worst.get('info', 0)} clean or info-only.  "
        f"Exposure: " + ", ".join(f"{k}={v}" for k, v in sorted(s["exposure"].items()))
    )
    return "\n".join(lines)


def render_json(results: Sequence[RecordResult], min_severity: str = "info") -> str:
    payload = []
    for r, findings in zip(results, _filter(results, min_severity)):
        d = r.to_dict()
        d["findings"] = [f.to_dict() for f in findings]
        payload.append(d)
    return json.dumps({"summary": summarize(results), "records": payload}, indent=2, ensure_ascii=False)


def render_github(results: Sequence[RecordResult], min_severity: str = "warning") -> str:
    """GitHub Actions workflow commands: shows findings inline on the PR diff."""
    level = {"error": "error", "warning": "warning", "info": "notice"}
    lines = []
    for r, findings in zip(results, _filter(results, min_severity)):
        rec = r.record
        for f in findings:
            props = [f"title={f.rule} {f.name}"]
            if rec.source:
                props.insert(0, f"file={rec.source}")
            if rec.line:
                props.insert(1, f"line={rec.line}")
            msg = f.message.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
            lines.append(f"::{level[f.severity]} {','.join(props)}::{msg}")
    return "\n".join(lines)
