from datetime import date, timedelta

import pytest

from lookahead_guard import Record, run_ab


def test_memorizing_model_shows_a_gap():
    records, outcomes = [], []
    for i in range(30):
        d = date(2022, 1, 3) + timedelta(days=i)
        records.append(Record(as_of=d, prompt=f"On {d.isoformat()} TSLA? UP or DOWN", id=str(i)))
        outcomes.append("UP" if i % 3 else "DOWN")
    truth = {r.prompt: o for r, o in zip(records, outcomes)}

    def decide(prompt):
        return truth.get(prompt, "UP")  # knows the answer only for raw prompts

    res = run_ab(records, outcomes, decide, lambda a, b: float(a == b))
    assert res.raw_mean == 1.0
    assert res.masked_mean == pytest.approx(20 / 30)
    assert res.gap_ci95[0] > 0
    assert "gap=+0.333" in res.summary()


def test_no_gap_for_a_model_that_ignores_identifiers():
    recs = [Record(as_of=date(2022, 1, 3), prompt="AAPL momentum +0.5")] * 5
    res = run_ab(recs, ["UP"] * 5, lambda p: "UP", lambda a, b: float(a == b))
    assert res.gap == 0.0


def test_length_mismatch_raises():
    with pytest.raises(ValueError):
        run_ab([Record(as_of=date(2022, 1, 3), prompt="x")], [], lambda p: p, lambda a, b: 0.0)
