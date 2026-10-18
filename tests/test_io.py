import json
from datetime import date

from lookahead_guard.io import load_records, record_from_dict


def test_aliases_and_defaults():
    r = record_from_dict({"et_date": "2026-10-12", "input": "hi", "model_name": "gpt-4o", "horizon": "10", "run_id": 7})
    assert r.as_of == date(2026, 10, 12) and r.prompt == "hi" and r.model == "gpt-4o"
    assert r.horizon_days == 10 and r.id == "7"


def test_messages_split_into_prompt_and_response():
    r = record_from_dict({
        "as_of": "2023-01-17",
        "messages": [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": [{"type": "text", "text": "question"}]},
            {"role": "assistant", "content": "answer"},
        ],
    })
    assert r.prompt == "sys\n\nquestion" and r.response == "answer"


def test_langchain_style_types():
    r = record_from_dict({"date": "2023-01-17", "prompt": [{"type": "human", "content": "q"}, {"type": "ai", "content": "a"}]})
    assert r.prompt == "q" and r.response == "a"


def test_timestamp_and_bad_date():
    assert record_from_dict({"ts": "2024-10-12T20:00:00Z", "prompt": "x"}).as_of == date(2024, 10, 12)
    assert record_from_dict({"as_of": "soon", "prompt": "x"}).as_of is None


def test_load_jsonl_json_and_text(tmp_path):
    jl = tmp_path / "log.jsonl"
    jl.write_text("\n".join(json.dumps({"as_of": "2024-01-0%d" % i, "prompt": "p"}) for i in (1, 2)) + "\n\n")
    js = tmp_path / "one.json"
    js.write_text(json.dumps([{"as_of": "2024-01-01", "prompt": "a"}, {"as_of": "2024-01-02", "prompt": "b"}]))
    txt = tmp_path / "p.txt"
    txt.write_text("plain prompt")
    recs = load_records([str(jl), str(js), str(txt)], as_of="2024-03-01", model="gpt-4o")
    assert len(recs) == 5
    assert [r.line for r in recs[:2]] == [1, 2]
    assert recs[-1].prompt == "plain prompt" and recs[-1].as_of == date(2024, 3, 1) and recs[-1].model == "gpt-4o"
