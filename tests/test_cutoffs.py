import json
import re
from datetime import date
from importlib import resources

import pytest

from lookahead_guard.cutoffs import CutoffTable, normalize_model_id


@pytest.fixture(scope="module")
def table():
    return CutoffTable.bundled()


@pytest.mark.parametrize("raw,norm", [
    ("openai/gpt-4o-2024-08-06", "gpt-4o-2024-08-06"),
    ("us.anthropic.claude-3-5-sonnet-20240620-v1:0", "claude-3-5-sonnet-20240620"),
    ("meta-llama/Meta-Llama-3.1-8B-Instruct", "meta-llama-3.1-8b-instruct"),
    ("claude-sonnet-4@20250514", "claude-sonnet-4"),
    ("llama3.1:70b", "llama3.1-70b"),
])
def test_normalize(raw, norm):
    assert normalize_model_id(raw) == norm


@pytest.mark.parametrize("model,expected_id,cutoff", [
    ("gpt-4o", "gpt-4o", date(2023, 10, 31)),
    ("gpt-4o-2024-08-06", "gpt-4o", date(2023, 10, 31)),
    ("gpt-4o-mini-2024-07-18", "gpt-4o-mini", date(2023, 10, 31)),
    ("gpt-4-0613", "gpt-4", date(2023, 12, 31)),
    ("gpt-5-nano-2025-08-07", "gpt-5-mini", date(2024, 5, 31)),
    ("gpt-5.2-chat-latest", "gpt-5.2", date(2025, 8, 31)),
    ("gpt-6-luna", "gpt-6-luna", date(2026, 5, 18)),
    ("claude-opus-4-1-20250805", "claude-opus-4-1", date(2025, 3, 31)),
    ("claude-sonnet-4-6", "claude-sonnet-4-6", date(2026, 1, 31)),
    ("claude-opus-5", "claude-opus-5", date(2026, 5, 31)),
    ("claude-opus-5-5", "claude-opus-5-5", date(2026, 6, 30)),
    ("meta-llama/Llama-4-Scout-17B-16E-Instruct", "llama-4", date(2024, 8, 31)),
    ("gpt-4.1-mini", "gpt-4.1", date(2024, 6, 30)),
    ("claude-3-5-sonnet-20241022", "claude-3-5-sonnet", date(2024, 4, 30)),
    ("claude-sonnet-4-5-20250929", "claude-sonnet-4-5", date(2025, 7, 31)),
    ("claude-sonnet-4-20250514", "claude-sonnet-4", date(2025, 3, 31)),
    ("meta-llama/Meta-Llama-3.1-405B-Instruct", "llama-3.1", date(2023, 12, 31)),
    ("meta.llama3-1-8b-instruct-v1:0", "llama-3.1", date(2023, 12, 31)),
    ("gemini-2.5-pro", "gemini-2.5", date(2025, 1, 31)),
])
def test_lookup(table, model, expected_id, cutoff):
    mc = table.lookup(model)
    assert mc is not None and mc.id == expected_id and mc.cutoff == cutoff


@pytest.mark.parametrize("model", ["claude-sonnet-9-9", "claude-opus-5-6", "gpt-5.4-mini", "gpt-4o-ultra", "my-finetune", "", None, "gpt-6"])
def test_unknown_or_newer_versions_are_not_guessed(table, model):
    # A newer version must never silently inherit an older (earlier) cutoff.
    assert table.lookup(model) is None


def test_user_entries_override(table):
    t = CutoffTable.bundled()
    t.load_dict({"gpt-4o": "2024-06", "my-finetune-v3": "2024-03"})
    assert t.lookup("gpt-4o").cutoff == date(2024, 6, 30)
    assert t.lookup("my-finetune-v3").cutoff == date(2024, 3, 31)
    # bundled table untouched
    assert table.lookup("gpt-4o").cutoff == date(2023, 10, 31)


def test_every_bundled_entry_is_reachable_by_its_id(table):
    for mc in table.entries():
        assert table.lookup(mc.id) is not None, mc.id


def _raw_entries():
    raw = resources.files("lookahead_guard").joinpath("data/model_cutoffs.json").read_text("utf-8")
    return json.loads(raw)["models"]


def test_every_bundled_entry_cites_a_source():
    for entry in _raw_entries():
        assert isinstance(entry.get("verified"), bool), entry["id"]
        assert entry.get("source", "").startswith("https://"), entry["id"]
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", entry.get("checked", "")), entry["id"]
        if entry["verified"]:
            assert entry.get("stated"), f"{entry['id']}: verified entries quote the vendor wording"
        else:
            assert entry.get("note"), f"{entry['id']}: unverified entries explain why"


def test_ids_are_unique_and_source_fields_load(table):
    ids = [e["id"] for e in _raw_entries()]
    assert len(ids) == len(set(ids))
    mc = table.lookup("gpt-5")
    assert mc.verified and mc.source.startswith("https://developers.openai.com/") and mc.checked == "2026-10-18"
    assert table.lookup("claude-3-sonnet-20240229").verified is False
