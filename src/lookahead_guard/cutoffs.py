"""Model knowledge-cutoff table and lookup.

The bundled table lives in ``data/model_cutoffs.json``. Users can extend or
override it with their own JSON (``{"model-id": "YYYY-MM[-DD]"}`` or the
bundled format) or pass a cutoff directly.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date
from importlib import resources
from typing import Dict, List, Optional

from .dates import parse_date


@dataclass(frozen=True)
class ModelCutoff:
    id: str
    vendor: str
    cutoff: date  # last day the model may have seen
    kind: str  # "training" | "knowledge" | "user"
    note: str = ""


def normalize_model_id(model: str) -> str:
    """Lowercase and strip provider prefixes and deployment suffixes.

    ``"openai/gpt-4o-2024-08-06"`` -> ``"gpt-4o-2024-08-06"``,
    ``"us.anthropic.claude-3-5-sonnet-20240620-v1:0"`` ->
    ``"claude-3-5-sonnet-20240620"``,
    ``"meta-llama/Meta-Llama-3.1-8B-Instruct"`` -> ``"meta-llama-3.1-8b-instruct"``.
    """
    s = model.strip().lower()
    s = s.split("@", 1)[0]
    s = s.rsplit("/", 1)[-1]
    s = re.sub(r"^(us|eu|apac|global)\.", "", s)
    s = re.sub(r"^(anthropic|meta|openai|google|mistral|amazon)\.", "", s)
    s = s.replace("_", "-").replace(":", "-")
    s = re.sub(r"-v\d+(-\d+)?$", "", s)
    return s


class CutoffTable:
    def __init__(self) -> None:
        self._patterns: List[tuple] = []  # (compiled, ModelCutoff)
        self._exact: Dict[str, ModelCutoff] = {}

    @classmethod
    def bundled(cls) -> "CutoffTable":
        table = cls()
        raw = resources.files("lookahead_guard").joinpath("data/model_cutoffs.json").read_text("utf-8")
        table.load_dict(json.loads(raw))
        return table

    def load_dict(self, data: dict) -> None:
        if "models" in data:
            for entry in data["models"]:
                mc = ModelCutoff(
                    id=entry["id"],
                    vendor=entry.get("vendor", ""),
                    cutoff=parse_date(entry["cutoff"]),
                    kind=entry.get("kind", "knowledge"),
                    note=entry.get("note", ""),
                )
                for pat in entry.get("patterns", [re.escape(entry["id"])]):
                    self._patterns.append((re.compile(pat), mc))
                self._exact[normalize_model_id(entry["id"])] = mc
            return
        # Simple user format: {"my-model": "2024-06"}
        for model_id, value in data.items():
            if model_id.startswith("_"):
                continue
            self.add(model_id, value)

    def load_file(self, path: str) -> None:
        with open(path, encoding="utf-8") as fh:
            self.load_dict(json.load(fh))

    def add(self, model_id: str, cutoff: str, vendor: str = "user") -> None:
        mc = ModelCutoff(id=model_id, vendor=vendor, cutoff=parse_date(cutoff), kind="user")
        # User entries win over bundled ones.
        self._exact[normalize_model_id(model_id)] = mc
        self._patterns.insert(0, (re.compile(re.escape(normalize_model_id(model_id))), mc))

    def lookup(self, model: Optional[str]) -> Optional[ModelCutoff]:
        if not model:
            return None
        norm = normalize_model_id(model)
        if norm in self._exact and self._exact[norm].kind == "user":
            return self._exact[norm]
        for pattern, mc in self._patterns:
            if pattern.fullmatch(norm):
                return mc
        return self._exact.get(norm)

    def entries(self) -> List[ModelCutoff]:
        seen, out = set(), []
        for _, mc in self._patterns:
            if mc.id not in seen:
                seen.add(mc.id)
                out.append(mc)
        return out
