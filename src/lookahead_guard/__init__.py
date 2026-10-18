"""llm-lookahead-guard: lint LLM backtest prompts and logs for look-ahead leakage."""

from .ab import ABResult, run_ab
from .cutoffs import CutoffTable, ModelCutoff, normalize_model_id
from .dates import find_dates, parse_date
from .io import load_records, record_from_dict
from .mask import Masker, MaskResult, mask_text, unmask
from .rules import RULES, Checker, Finding, Record, RecordResult, check_record

__version__ = "0.1.0"

__all__ = [
    "ABResult",
    "Checker",
    "CutoffTable",
    "Finding",
    "MaskResult",
    "Masker",
    "ModelCutoff",
    "RULES",
    "Record",
    "RecordResult",
    "check_record",
    "find_dates",
    "load_records",
    "mask_text",
    "normalize_model_id",
    "parse_date",
    "record_from_dict",
    "run_ab",
    "unmask",
]
