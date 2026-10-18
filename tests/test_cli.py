import json

from lookahead_guard.cli import main

LEAKY = {"id": "a", "as_of": "2023-03-01", "model": "gpt-4o", "prompt": "NVDA closed at 305 on 2023-05-26."}
CLEAN = {"id": "b", "as_of": "2024-02-01", "model": "gpt-4o", "prompt": "Momentum 0.4. BUY or SELL?"}


def write(tmp_path, *rows):
    p = tmp_path / "log.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in rows))
    return str(p)


def test_exit_codes(tmp_path, capsys):
    assert main(["check", write(tmp_path, LEAKY)]) == 1
    assert main(["check", write(tmp_path, CLEAN)]) == 0
    assert main(["check", write(tmp_path, LEAKY), "--fail-on", "never"]) == 0
    assert main(["check", str(tmp_path / "missing.jsonl")]) == 2


def test_json_output(tmp_path, capsys):
    main(["check", write(tmp_path, LEAKY, CLEAN), "--format", "json"])
    data = json.loads(capsys.readouterr().out)
    assert data["summary"]["records"] == 2
    assert data["records"][0]["exposure"]["status"] == "full"
    assert any(f["rule"] == "LAG101" for f in data["records"][0]["findings"])


def test_github_annotations(tmp_path, capsys):
    path = write(tmp_path, LEAKY)
    main(["check", path, "--format", "github"])
    out = capsys.readouterr().out
    assert f"::error file={path},line=1,title=LAG101 future-dated-fact::" in out


def test_min_severity_hides_lower(tmp_path, capsys):
    main(["check", write(tmp_path, LEAKY), "--min-severity", "error", "--format", "json"])
    data = json.loads(capsys.readouterr().out)
    assert {f["severity"] for f in data["records"][0]["findings"]} == {"error"}


def test_text_file_needs_as_of(tmp_path, capsys):
    p = tmp_path / "p.txt"
    p.write_text("AAPL closed at 305 on 2023-05-26.")
    assert main(["check", str(p), "--model", "gpt-4o"]) == 1  # LAG000 error
    assert main(["check", str(p), "--model", "gpt-4o", "--as-of", "2023-06-01"]) == 1  # exposure + identifiers


def test_cutoff_flags(tmp_path, capsys):
    row = dict(CLEAN, model="my-finetune-v3")
    path = write(tmp_path, row)
    assert main(["check", path, "--fail-on", "warning"]) == 1  # unknown model -> LAG003 warning
    cut = tmp_path / "c.json"
    cut.write_text(json.dumps({"my-finetune-v3": "2023-06"}))
    assert main(["check", path, "--cutoffs", str(cut), "--fail-on", "warning"]) == 0


def test_mask_command(tmp_path, capsys):
    p = tmp_path / "p.txt"
    p.write_text("AAPL on 2023-02-28")
    mapping = tmp_path / "m.json"
    assert main(["mask", str(p), "--as-of", "2023-03-01", "--mapping", str(mapping)]) == 0
    assert capsys.readouterr().out.strip() == "ASSET_1 on D-1"
    assert json.loads(mapping.read_text())["ASSET_1"] == "AAPL"
    jl = write(tmp_path, LEAKY)
    assert main(["mask", jl]) == 0
    row = json.loads(capsys.readouterr().out.strip())
    assert row["prompt"] == "ASSET_1 closed at 305 on D+86." and row["masked"] is True


def test_cutoffs_rules_demo(capsys):
    assert main(["cutoffs"]) == 0
    assert "gpt-4o" in capsys.readouterr().out
    assert main(["cutoffs", "claude-3-5-sonnet-20241022"]) == 0
    assert "2024-04-30" in capsys.readouterr().out
    assert main(["cutoffs", "nope-model"]) == 1
    assert main(["rules"]) == 0
    assert "LAG301" in capsys.readouterr().out
    assert main(["demo"]) == 0
    out = capsys.readouterr().out
    assert "LAG101" in out and "LAG301" in out and "LAG104" in out
    assert main([]) == 2
