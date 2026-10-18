"""Optional: masked-vs-raw A/B on YOUR historical records with a real model.

Runs only if the ``anthropic`` package is installed and ANTHROPIC_API_KEY is
set. Nothing in the test suite or CI calls this file.

Input: a JSONL file where each line has ``as_of``, ``prompt`` and
``outcome`` ("UP" or "DOWN"), e.g. built from your own backtest.

    pip install anthropic
    export ANTHROPIC_API_KEY=...
    python examples/ab_anthropic.py my_records.jsonl --model <model-id> --limit 50

API calls cost money; start with a small --limit.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from lookahead_guard import record_from_dict, run_ab

SYSTEM = "You are a trading assistant. Reply with exactly one word: UP or DOWN."


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--model", required=True)
    ap.add_argument("--limit", type=int, default=20)
    args = ap.parse_args()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY is not set; skipping (this example is optional).")
        return 0
    try:
        import anthropic
    except ImportError:
        print("pip install anthropic to run this example.")
        return 0

    client = anthropic.Anthropic()
    rows = [json.loads(line) for line in open(args.path, encoding="utf-8") if line.strip()][: args.limit]
    records = [record_from_dict(r) for r in rows]
    outcomes = [str(r["outcome"]).upper() for r in rows]

    def decide(prompt: str) -> str:
        msg = client.messages.create(model=args.model, max_tokens=5, system=SYSTEM,
                                     messages=[{"role": "user", "content": prompt}])
        text = "".join(getattr(b, "text", "") for b in msg.content).upper()
        return "UP" if "UP" in text else "DOWN"

    result = run_ab(records, outcomes, decide, lambda d, o: 1.0 if d == o else 0.0)
    print(result.summary())
    return 0


if __name__ == "__main__":
    sys.exit(main())
