"""Load backtest records from JSONL / JSON / plain-text files.

A JSONL record is one LLM decision. Field names are matched loosely so that
existing logs can be checked without converting them:

=================  ===========================================================
meaning            accepted keys (first found wins)
=================  ===========================================================
decision date      as_of, asof, decision_date, date, et_date, timestamp, ts
prompt text        prompt, input, messages (OpenAI/Anthropic/LangChain style)
model answer       response, output, completion, answer (or assistant messages)
model id           model, model_name, llm
outcome window     horizon_days, horizon
identifiers        entities (list of extra strings to treat as asset names)
record id          id, record_id, run_id
=================  ===========================================================
"""

from __future__ import annotations

import json
import os
from typing import Any, Iterable, Iterator, List, Optional, Tuple

from .dates import parse_date
from .rules import Record

_AS_OF = ("as_of", "asof", "decision_date", "date", "et_date", "timestamp", "ts")
_PROMPT = ("prompt", "input", "user_prompt", "query")
_RESPONSE = ("response", "output", "completion", "answer")
_MODEL = ("model", "model_name", "llm")
_HORIZON = ("horizon_days", "horizon")
_ID = ("id", "record_id", "run_id")


def _first(d: dict, keys: Iterable[str]) -> Any:
    for k in keys:
        if k in d and d[k] not in (None, ""):
            return d[k]
    return None


def _content_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):  # [{"type": "text", "text": "..."}]
        parts = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict):
                parts.append(str(part.get("text") or part.get("content") or ""))
        return "\n".join(p for p in parts if p)
    if isinstance(content, dict):
        return str(content.get("text") or content.get("content") or "")
    return str(content)


def _split_messages(messages: list) -> Tuple[str, str]:
    prompt_parts, response_parts = [], []
    for msg in messages:
        if not isinstance(msg, dict):
            prompt_parts.append(str(msg))
            continue
        role = str(msg.get("role") or msg.get("type") or "user").lower()
        text = _content_text(msg.get("content"))
        if role in ("assistant", "ai", "model"):
            response_parts.append(text)
        else:
            prompt_parts.append(text)
    return "\n\n".join(p for p in prompt_parts if p), "\n\n".join(r for r in response_parts if r)


def record_from_dict(d: dict, source: Optional[str] = None, line: Optional[int] = None) -> Record:
    raw_as_of = _first(d, _AS_OF)
    as_of = None
    if raw_as_of is not None:
        try:
            as_of = parse_date(str(raw_as_of))
        except ValueError:
            as_of = None
    prompt = _first(d, _PROMPT)
    response = _first(d, _RESPONSE)
    if isinstance(prompt, list):
        prompt, msg_response = _split_messages(prompt)
        response = response or msg_response
    if prompt is None and isinstance(d.get("messages"), list):
        prompt, msg_response = _split_messages(d["messages"])
        response = response or msg_response
    horizon = _first(d, _HORIZON)
    entities = d.get("entities") or []
    if isinstance(entities, str):
        entities = [entities]
    rid = _first(d, _ID)
    return Record(
        as_of=as_of,
        prompt=_content_text(prompt),
        model=_first(d, _MODEL),
        response=_content_text(response),
        horizon_days=int(horizon) if horizon is not None else None,
        entities=[str(e) for e in entities],
        id=str(rid) if rid is not None else None,
        source=source,
        line=line,
    )


def iter_records(path: str, as_of: Optional[str] = None, model: Optional[str] = None) -> Iterator[Record]:
    """Yield records from a file.

    ``.jsonl`` -> one record per line; ``.json`` -> an object or a list of
    objects; anything else -> the whole file is one prompt (``as_of``
    required).
    """
    ext = os.path.splitext(path)[1].lower()
    with open(path, encoding="utf-8") as fh:
        if ext == ".jsonl":
            for n, line in enumerate(fh, 1):
                line = line.strip()
                if not line or line.startswith("//"):
                    continue
                yield record_from_dict(json.loads(line), path, n)
            return
        if ext == ".json":
            data = json.load(fh)
            items = data if isinstance(data, list) else [data]
            for item in items:
                yield record_from_dict(item, path, None if len(items) > 1 else 1)
            return
        text = fh.read()
    yield Record(
        as_of=parse_date(as_of) if as_of else None,
        prompt=text,
        model=model,
        id=os.path.basename(path),
        source=path,
        line=1,
    )


def load_records(paths: Iterable[str], as_of: Optional[str] = None, model: Optional[str] = None) -> List[Record]:
    out: List[Record] = []
    for p in paths:
        out.extend(iter_records(p, as_of=as_of, model=model))
    return out
