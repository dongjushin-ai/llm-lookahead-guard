from datetime import date

import pytest

from lookahead_guard.dates import find_dates, parse_date

AS_OF = date(2024, 10, 14)


def spans(text, as_of=AS_OF):
    return [(d.text, d.granularity, d.earliest, d.latest) for d in find_dates(text, as_of)]


def test_iso_day():
    assert spans("closed on 2024-11-05.") == [("2024-11-05", "day", date(2024, 11, 5), date(2024, 11, 5))]


def test_month_name_day_year_and_day_month_year():
    out = spans("On Oct 30, 2024 and 5 November 2024 and March 3rd 2023")
    assert [o[0] for o in out] == ["Oct 30, 2024", "5 November 2024", "March 3rd 2023"]
    assert out[1][2] == date(2024, 11, 5)


def test_us_numeric():
    assert spans("filed 11/05/2024")[0][2] == date(2024, 11, 5)


def test_month_year_and_iso_month():
    out = spans("In September 2024 and in 2024-12 too")
    assert out[0][1:] == ("month", date(2024, 9, 1), date(2024, 9, 30))
    assert out[1][1:] == ("month", date(2024, 12, 1), date(2024, 12, 31))


def test_quarters():
    out = spans("Q3 2024, Q4'24, 1Q25 and Q2-2023")
    assert [o[2] for o in out] == [date(2024, 7, 1), date(2024, 10, 1), date(2025, 1, 1), date(2023, 4, 1)]
    assert all(o[1] == "quarter" for o in out)


def test_fiscal_and_bare_year():
    out = spans("FY2025 guidance; back in 2019 it was different")
    assert out[0][0] == "FY2025" and out[0][1] == "year"
    assert out[1][0] == "2019"


def test_prices_and_percentages_are_not_years():
    assert spans("Index at 2050.5, price $2024, up 2025% lol, level 2090") == []


def test_month_day_without_year_infers_nearest_year():
    out = find_dates("earnings on Oct 30", AS_OF)
    assert out[0].earliest == date(2024, 10, 30) and out[0].inferred_year
    out = find_dates("results on Jan 5", date(2024, 12, 20))
    assert out[0].earliest == date(2025, 1, 5)


def test_no_double_counting_inside_full_date():
    out = spans("2024-10-14")
    assert len(out) == 1


def test_parse_date_forms():
    assert parse_date("2024-10-12T20:00:00Z") == date(2024, 10, 12)
    assert parse_date("2023-10") == date(2023, 10, 31)
    assert parse_date("2024-02") == date(2024, 2, 29)
    assert parse_date("2021") == date(2021, 12, 31)
    with pytest.raises(ValueError):
        parse_date("last tuesday")
