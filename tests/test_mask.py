from datetime import date

from lookahead_guard.mask import Masker, mask_text, unmask

AS_OF = date(2024, 10, 14)


def test_dates_become_offsets():
    out = mask_text("On 2024-10-09 and Oct 14, 2024; September 2024; Q4 2024; Q2 2024; FY2025; 2023.", AS_OF).text
    assert out == "On D-5 and D+0; M-1; Q+0; Q-2; Y+1; Y-1."


def test_assets_and_events_aliases_are_stable():
    m = Masker(entities=["ACMR"])
    a = m.mask("AAPL and ACMR fell after the CrowdStrike outage. AAPL again.", AS_OF)
    b = m.mask("ACMR then AAPL.", AS_OF)
    assert a.text == "ASSET_1 and ASSET_2 fell after the EVENT_1. ASSET_1 again."
    assert b.text == "ASSET_2 then ASSET_1."
    assert a.mapping["ASSET_1"] == "AAPL"


def test_company_name_and_ticker_share_an_alias():
    out = mask_text("Apple (AAPL) and $AAPL", AS_OF).text
    assert out == "ASSET_1 (ASSET_1) and $ASSET_1"


def test_unmask_restores_assets_not_dates():
    res = mask_text("Buy TSLA before 2024-10-20.", AS_OF)
    assert res.text == "Buy ASSET_1 before D+6."
    assert unmask("ASSET_1 looks strong into D+6", res.mapping) == "TSLA looks strong into D+6"
    assert res.unmask("ASSET_1") == "TSLA"


def test_plain_text_untouched():
    text = "Momentum 0.71, RSI 55, volume 1.2x. Decide BUY or SELL."
    assert mask_text(text, AS_OF).text == text
