# llm-lookahead-guard

<p align="center"><img src="https://raw.githubusercontent.com/dongjushin-ai/llm-lookahead-guard/main/docs/assets/demo.gif" alt="Terminal demo: check a leaky log (errors), mask it, check again (passes), then the masked-vs-raw A/B gap" width="760"></p>

**A linter for LLM backtests: finds look-ahead (temporal contamination) leaks in the prompts you sent and the answers you got back. Offline, zero dependencies, CI-ready.**

[![CI](https://github.com/dongjushin-ai/llm-lookahead-guard/actions/workflows/ci.yml/badge.svg)](https://github.com/dongjushin-ai/llm-lookahead-guard/actions/workflows/ci.yml)
![python](https://img.shields.io/badge/python-3.9%2B-blue)
![deps](https://img.shields.io/badge/dependencies-0-brightgreen)
![license](https://img.shields.io/badge/license-MIT-green)

[한국어 README](README.ko.md)

## Why

You backtest an LLM trading agent on 2023 data with `gpt-4o`. Its training data runs to late 2023, so it has already *read* how 2023 ended. Your prompt says:

```text
Date: 2023-03-01. Ticker: NVDA. Last close 232.10, RSI 58.
Note: NVDA closed at 305.40 on 2023-05-26 after earnings.
Decide BUY or SELL for the next 20 trading days.
```

That prompt leaks in three ways: the model's training data covers the whole outcome window, the date and ticker tell the model exactly what to recall, and one line states a price from *after* the decision date (it slipped in from a news feed). The backtest looks brilliant, and none of the result is skill.

`lookahead-guard` reads your logs and tells you, record by record:

```text
demo_log.jsonl:1 [leaky-future-price]  as_of=2023-03-01  model=gpt-4o-2024-08-06 (cutoff 2023-10-31)  exposure=full
  ERROR LAG001 exposure-full  [record]
        gpt-4o was trained on data to about 2023-10-31, after this decision (2023-03-01) and its whole
        outcome window (to 2023-03-21); the prompt also shows dates/assets/events, so the model can look up what happened
  ERROR LAG101 future-dated-fact  [prompt]
        states something about '2023-05-26', which is after the decision date 2023-03-01
        > ... RSI 58. Note: NVDA closed at 305.40 on 2023-05-26 after earnings. Decide BUY or SELL for ...
  WARN  LAG201 absolute-date-visible  [prompt]
  WARN  LAG202 asset-identifier-visible  [prompt]
```

## 30-second quickstart

```bash
pip install git+https://github.com/dongjushin-ai/llm-lookahead-guard
lookahead-guard demo                      # built-in synthetic log, no setup
lookahead-guard check my_backtest.jsonl   # your own log
```

A log is JSONL, one LLM decision per line. Field names are matched loosely, so most existing logs work as they are:

```json
{"id": "r1", "as_of": "2023-03-01", "model": "gpt-4o", "horizon_days": 20,
 "prompt": "...", "response": "..."}
```

`messages` lists in OpenAI / Anthropic / LangChain form work too (assistant turns are read as the response). For a plain-text prompt, pass the date: `lookahead-guard check prompt.txt --as-of 2023-03-01 --model gpt-4o`.

## What it checks

| Rule | Severity | Fires when |
|---|---|---|
| `LAG001` exposure-full | error / warning | the model's training cutoff is after the decision date **and** the whole outcome window. Error if the prompt also shows dates/tickers/events; warning if the prompt looks masked |
| `LAG002` exposure-partial | warning | the cutoff falls inside the outcome window |
| `LAG003` model-cutoff-unknown | warning | no cutoff known for the model (it never guesses from a similar name) |
| `LAG101` future-dated-fact | error | the prompt states what happened on a date after `as_of` ("closed at ... on 2023-05-26") |
| `LAG102` future-date-unclear | warning | a later date with no clear "expected/scheduled" wording |
| `LAG103` future-date-scheduled | info | a later date framed as scheduled ("earnings are due Oct 30"): usually fine |
| `LAG104` anachronistic-event | error | names an event that had not happened yet (e.g. "SVB collapse" in a 2022 prompt) |
| `LAG105` hindsight-language | warning | "would later", "in hindsight", "went on to" ... |
| `LAG201` absolute-date-visible | warning if exposed, else info | absolute dates let an exposed model locate the period |
| `LAG202` asset-identifier-visible | warning if exposed, else info | tickers, cashtags, `NASDAQ: XYZ`, company names, your own `--entity` names |
| `LAG203` era-event-visible | warning if exposed, else info | named events that date the prompt (COVID-19, ChatGPT, ...) |
| `LAG301` response-cites-future | error | the **model's answer** states something that happened after `as_of`: a sign of recall |
| `LAG302` response-hindsight | warning | hindsight wording in the answer |

The bundled model table (`lookahead-guard cutoffs`) covers 49 OpenAI, Anthropic, Google and Meta model families, from `gpt-3.5-turbo` and `llama-2` to `gpt-6-luna` and `claude-opus-5-5`. Every entry records the vendor page it was checked against (`source`), the vendor's own wording (`stated`), the check date (`checked`, last 2026-10-18) and whether an official page confirmed it (`verified`); `lookahead-guard cutoffs MODEL` prints the source. Add your own with `--cutoffs my_cutoffs.json` (`{"my-finetune-v3": "2024-03"}`) or force one with `--cutoff 2024-06`. A newer model version is never matched to an older entry: `claude-opus-5-6` is reported as unknown, not given the `claude-opus-5` date.

## Use it in CI

```yaml
- run: pip install git+https://github.com/dongjushin-ai/llm-lookahead-guard
- run: lookahead-guard check logs/*.jsonl --format github --fail-on error
```

`--format github` puts findings inline on the pull request. `--format json` is for scripts. The exit code is 1 when a finding at or above `--fail-on` exists.

## Fix it: masking

```bash
lookahead-guard mask examples/prompt.txt --as-of 2023-03-01 --mapping map.json
lookahead-guard mask my_backtest.jsonl > my_backtest.masked.jsonl
```

```text
before: Today is March 1, 2023. AAPL closed at 147.92. Q4 2022 revenue fell 5%. Results are due on May 4, 2023.
after:  Today is D+0. ASSET_1 closed at 147.92. Q-1 revenue fell 5%. Results are due on D+64.
```

Dates become offsets from the decision date (`D-5`, `M-1`, `Q+1`, `Y-2`), assets become `ASSET_n` (ticker and company name share one alias), and named events become `EVENT_n`. Aliases stay stable across a whole log, and `unmask()` puts asset names back into answers.

## Measure it: masked vs raw A/B

If the score drops a lot once the prompt is masked, the model was remembering, not reasoning. `run_ab` works with any `prompt -> decision` callable and makes no network calls itself:

```python
from lookahead_guard import load_records, run_ab

records = load_records(["my_backtest.jsonl"])
result = run_ab(records, outcomes, decide=my_model, score=lambda d, o: float(d == o))
print(result.summary())   # n=200  raw=1.000  masked=0.570  gap=+0.430 (95% CI +0.361 to +0.499)
```

That line is the output of `python examples/ab_demo.py`, which uses a *fake* model that memorized synthetic outcomes. `examples/ab_anthropic.py` runs the same comparison against a real model on your data, and only if you have an API key.

## Python API

```python
from datetime import date
from lookahead_guard import Checker, Record, mask_text

result = Checker().check(Record(as_of=date(2023, 3, 1), model="gpt-4o",
                                prompt="NVDA closed at 305.40 on 2023-05-26."))
result.exposure.status          # "full"
[f.rule for f in result.findings]  # ["LAG001", "LAG101", "LAG202"]
```

## How it differs from existing tools

| | Looks at | Needs an API / runs the model | Model-cutoff check | Masking |
|---|---|---|---|---|
| **llm-lookahead-guard** | the prompt and response text in your logs, from any framework | no | yes, per record, against the outcome window | yes, plus A/B |
| [Look-Ahead-Bench](https://github.com/benstaf/lookaheadbench) | a model, on a fixed benchmark | yes | indirectly (alpha decay) | no |
| [Peek](https://github.com/OnePunchMonk/peek) | dataframes and ML pipelines | no | no | no |
| [leakguard-mcp](https://github.com/doazvjettu/leakguard-mcp) | Python source code (`shift(-1)`, ...) | no | no | no |
| [TraderHarness](https://github.com/HephaestLab/TraderHarness) | runs inside its own harness | yes | no | yes, built in |
| [agent-backtest-lab](https://github.com/bettyguo/agent-backtest-lab) | strategy statistics and data access | optional | no | no |
| [Shapley-DCLR / TimeSPEC](https://arxiv.org/abs/2602.17234) | claims in the model's reasoning | yes (re-runs and search) | no | retrieval filter |
| [DatedGPT](https://arxiv.org/abs/2603.11838) | replaces the model with time-bounded ones | n/a | by construction | n/a |

They work well together. Use a point-in-time harness to run new experiments safely, a statistics tool to judge the result, and this linter for every log you already have or plan to publish. A full comparison is in [docs/landscape.md](docs/landscape.md) (Korean).

## Limitations

- **Heuristics, not proof.** The rules are regexes and word lists. They miss leaks phrased in unusual ways and sometimes flag harmless text. A clean report does not mean the backtest is clean.
- **Masking lowers re-identification risk; it does not remove it.** A distinctive price path or a famous number can still tell an exposed model what period it is in. That is why a masked but exposed record stays a warning.
- **Masking does not fix a future fact.** `mask` turns "closed at 305.40 on 2023-05-26" into "closed at 305.40 on D+86" and leaves the number alone, because numbers are the model's input and hiding one would not hide the leak. `check` reads `D+n`/`M+n`/`Q+n`/`Y+n` as dates after `as_of`, so the masked line is still `LAG101`; delete such lines. Past offsets (`D-5`) pass.
- **Cutoffs are vendor-reported.** Effective cutoffs can differ ([Dated Data, arXiv 2403.12958](https://arxiv.org/abs/2403.12958)). Use `--margin-days` to be conservative, and please send a PR when a value is wrong.
- **Two entries are not verified** (`verified: false`, shown as `NO` in `lookahead-guard cutoffs`): `claude-3-sonnet` (the Claude 3 model card could not be read on 2026-10-18) and `claude-opus-4-1` (its system card gives no cutoff and the retired model page is gone; the value is carried over from Claude Opus 4). `claude-3-haiku` is confirmed on Google Cloud's official Claude page rather than Anthropic's own.
- **Where vendor pages disagree, the later date wins**, because a later cutoff can only add warnings. `gpt-4` uses OpenAI's current Dec 2023 (older docs said Sep 2021 for the 0314/0613 snapshots); `claude-sonnet-4-6` uses the model page's Jan 2026 training-data cutoff (the help center says Aug 2025).
- **Not covered yet:** Gemini 3.x and Gemini 4 (Google's model pages give no knowledge cutoff), `gpt-5.4-mini` and other variants without their own vendor page, and open-weight models other than Llama.
- English text and US-market identifiers only for now.
- It checks text, not data pipelines. Pair it with a data-level tool for features and splits.

## Contributing

The most useful contributions are corrections and additions to `src/lookahead_guard/data/model_cutoffs.json` (cite the vendor page), new dated events in `lexicon.py`, and real-world false positives or false negatives as issues.

## License and disclaimer

MIT. This is a research and testing tool. It gives no investment advice and places no trades.
