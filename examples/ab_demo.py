"""Masked-vs-raw A/B demo with a *fake* model that memorized outcomes.

No API key, no network, fully synthetic: tickers are fictional and the
"market" is random numbers. The fake model answers correctly whenever it
can recognise the asset and the date (it "remembers" the future), and
otherwise falls back to a coin-flip-quality momentum rule. The A/B harness
shows how much of its accuracy disappears once the prompt is masked.

    python examples/ab_demo.py
"""

from __future__ import annotations

import random
import re
from datetime import date, timedelta

from lookahead_guard import Record, run_ab

TICKERS = ["ACMR", "BLZN", "CRVX", "DYNQ", "ELMO"]  # fictional
rng = random.Random(7)

records, outcomes, memory = [], [], {}
start = date(2022, 1, 3)
for i in range(200):
    ticker = rng.choice(TICKERS)
    as_of = start + timedelta(days=7 * i)
    momentum = rng.uniform(-1, 1)
    # The "true" next-month direction is only weakly related to momentum.
    went_up = rng.random() < 0.5 + 0.1 * momentum
    outcome = "UP" if went_up else "DOWN"
    prompt = (f"Date: {as_of.isoformat()}. Ticker: {ticker}. 20-day momentum score {momentum:+.2f}. "
              "Will the stock be higher in 21 trading days? Answer UP or DOWN.")
    records.append(Record(as_of=as_of, prompt=prompt, entities=TICKERS, id=f"r{i}"))
    outcomes.append(outcome)
    memory[(ticker, as_of.isoformat())] = outcome  # what the fake model "read" during training


def fake_memorizing_model(prompt: str) -> str:
    m = re.search(r"Date: (\d{4}-\d{2}-\d{2})\. Ticker: ([A-Z]+)\.", prompt)
    if m and (m.group(2), m.group(1)) in memory:
        return memory[(m.group(2), m.group(1))]  # recall, not reasoning
    score = float(re.search(r"momentum score ([+-]\d\.\d+)", prompt).group(1))
    return "UP" if score > 0 else "DOWN"


def hit(decision: str, outcome: str) -> float:
    return 1.0 if decision == outcome else 0.0


if __name__ == "__main__":
    result = run_ab(records, outcomes, fake_memorizing_model, hit, entities=TICKERS)
    print("Direction accuracy, raw prompt vs masked prompt (synthetic data):")
    print(" ", result.summary())
    print("\nExample masked prompt:")
    from lookahead_guard import mask_text

    print(" ", mask_text(records[0].prompt, records[0].as_of, TICKERS).text)
