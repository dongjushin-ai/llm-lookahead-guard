from datetime import date

import pytest

from lookahead_guard import Checker, Record
from lookahead_guard.mask import mask_text


@pytest.fixture(scope="module")
def checker():
    return Checker(entities=["ACMR", "Acme Robotics"])


def rules(result, severity=None):
    return {f.rule for f in result.findings if severity is None or f.severity == severity}


def test_missing_as_of_is_an_error(checker):
    r = checker.check(Record(as_of=None, prompt="hello"))
    assert rules(r) == {"LAG000"}


@pytest.mark.parametrize("as_of,horizon,status", [
    (date(2023, 3, 1), 20, "full"),       # gpt-4o cutoff 2023-10-31
    (date(2023, 10, 25), 20, "partial"),  # window crosses the cutoff
    (date(2023, 11, 1), 20, "none"),      # after the cutoff
])
def test_exposure_status(checker, as_of, horizon, status):
    r = checker.check(Record(as_of=as_of, prompt="Momentum 0.4.", model="gpt-4o", horizon_days=horizon))
    assert r.exposure.status == status
    expected = {"full": {"LAG001"}, "partial": {"LAG002"}, "none": set()}[status]
    assert rules(r) & {"LAG001", "LAG002"} == expected


def test_full_exposure_is_error_only_when_identifiers_visible(checker):
    masked = checker.check(Record(as_of=date(2023, 3, 1), prompt="ASSET_1 closed at 101 on D-1.", model="gpt-4o"))
    raw = checker.check(Record(as_of=date(2023, 3, 1), prompt="AAPL closed at 101 on 2023-02-28.", model="gpt-4o"))
    assert [f.severity for f in masked.findings if f.rule == "LAG001"] == ["warning"]
    assert [f.severity for f in raw.findings if f.rule == "LAG001"] == ["error"]


def test_margin_days_extends_exposure():
    rec = Record(as_of=date(2023, 11, 10), prompt="x", model="gpt-4o")
    assert Checker().check(rec).exposure.status == "none"
    assert Checker(margin_days=30).check(rec).exposure.status == "full"


def test_cutoff_override_and_unknown_model():
    rec = Record(as_of=date(2024, 5, 2), prompt="x", model="my-finetune-v3")
    assert rules(Checker().check(rec)) == {"LAG003"}
    assert Checker(cutoff_override=date(2024, 12, 31)).check(rec).exposure.status == "full"
    assert "LAG003" in rules(Checker().check(Record(as_of=date(2024, 5, 2), prompt="x")))


def test_future_dated_fact(checker):
    r = checker.check(Record(as_of=date(2023, 3, 1), prompt="NVDA closed at 305.40 on 2023-05-26.", model="gpt-4o"))
    assert "LAG101" in rules(r, "error")


def test_may_the_month_is_not_a_forward_cue(checker):
    r = checker.check(Record(as_of=date(2023, 3, 1), prompt="The stock jumped 20% on May 25, 2023.", model="gpt-4o"))
    assert "LAG101" in rules(r, "error")


@pytest.mark.parametrize("text", [
    "Earnings are scheduled for 2024-10-30.",
    "Results are expected on Oct 30.",
    "The Fed will meet on November 7, 2024.",
])
def test_scheduled_future_dates_are_info(checker, text):
    r = checker.check(Record(as_of=date(2024, 10, 14), prompt=text, model="gpt-4o"))
    assert "LAG103" in rules(r, "info")
    assert "LAG101" not in rules(r)


def test_unclear_future_date_is_warning(checker):
    r = checker.check(Record(as_of=date(2024, 10, 14), prompt="Key date: 2024-11-05.", model="gpt-4o"))
    assert "LAG102" in rules(r, "warning")


def test_future_year_guidance_is_not_flagged_but_realized_year_is(checker):
    ok = checker.check(Record(as_of=date(2024, 10, 14), prompt="FY2025 guidance calls for 8% growth.", model="gpt-4o"))
    assert not rules(ok) & {"LAG101", "LAG102"}
    bad = checker.check(Record(as_of=date(2024, 10, 14), prompt="Revenue fell 10% in 2025.", model="gpt-4o"))
    assert "LAG101" in rules(bad)


def test_anachronistic_event(checker):
    r = checker.check(Record(as_of=date(2022, 10, 3), prompt="Risk similar to the SVB collapse.", model="gpt-4o"))
    assert "LAG104" in rules(r, "error")
    later = checker.check(Record(as_of=date(2023, 6, 1), prompt="Risk similar to the SVB collapse.", model="gpt-4o"))
    assert "LAG104" not in rules(later)
    assert "LAG203" in rules(later, "warning")


def test_hindsight_language(checker):
    r = checker.check(Record(as_of=date(2024, 2, 12), prompt="The stock, which would later double, is cheap."))
    assert "LAG105" in rules(r)


def test_identity_findings_are_info_when_not_exposed(checker):
    r = checker.check(Record(as_of=date(2024, 2, 12), prompt="ACMR on 2024-02-09 closed at 10.", model="gpt-4o"))
    assert r.exposure.status == "none"
    assert {"LAG201", "LAG202"} <= rules(r, "info")


def test_asset_detection_kinds(checker):
    text = "Apple, $TSLA, NASDAQ: ACMR and Acme Robotics; not MA20 or the IT team."
    r = checker.check(Record(as_of=date(2023, 3, 1), prompt=text, model="gpt-4o"))
    msg = next(f.message for f in r.findings if f.rule == "LAG202")
    for key in ("AAPL", "TSLA", "ACMR", "Acme Robotics"):
        assert key in msg


def test_response_recall(checker):
    r = checker.check(Record(as_of=date(2023, 1, 17), prompt="BUY or SELL?", model="claude-3-opus",
                             response="BUY. It rose 18% by March 2023 once the merger was approved."))
    assert "LAG301" in rules(r, "error")
    fine = checker.check(Record(as_of=date(2023, 1, 17), prompt="BUY or SELL?", model="claude-3-opus",
                                response="BUY. I expect it could rise by March 2023."))
    assert "LAG301" not in rules(fine)


def test_response_event_and_hindsight(checker):
    r = checker.check(Record(as_of=date(2022, 6, 1), prompt="?", model="gpt-4o",
                             response="In hindsight, ChatGPT changed everything."))
    assert {"LAG301", "LAG302"} <= rules(r)


def test_masked_prompt_has_no_identity_or_future_findings(checker):
    as_of = date(2023, 3, 1)
    raw = "Date: 2023-03-01. AAPL fell 3% in February 2023 after the COVID wave; Q4 2022 EPS beat."
    masked = mask_text(raw, as_of).text
    r = checker.check(Record(as_of=as_of, prompt=masked, model="gpt-4o"))
    assert not rules(r) & {"LAG101", "LAG102", "LAG104", "LAG201", "LAG202", "LAG203"}
    assert [f.severity for f in r.findings if f.rule == "LAG001"] == ["warning"]


def test_findings_sorted_by_severity(checker):
    r = checker.check(Record(as_of=date(2023, 3, 1), prompt="AAPL closed at 305 on 2023-05-26.", model="gpt-4o"))
    sev = [f.severity for f in r.findings]
    order = {"error": 0, "warning": 1, "info": 2}
    assert sev == sorted(sev, key=order.__getitem__)
