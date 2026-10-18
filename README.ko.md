# llm-lookahead-guard

<p align="center"><img src="https://raw.githubusercontent.com/dongjushin-ai/llm-lookahead-guard/main/docs/assets/demo.gif" alt="터미널 데모: 누수 로그 check(error) → mask → 다시 check(통과) → 마스킹 전후 A/B 차이" width="760"></p>

**LLM 백테스트용 린터: 모델에 보낸 프롬프트와 받은 답에서 미래 정보 누수(look-ahead, temporal contamination)를 찾아냅니다. 오프라인, 의존성 0개, CI에 바로 붙습니다.**

[English README](README.md)

## 왜 필요한가

`gpt-4o`로 2023년 데이터를 백테스트한다고 해 봅시다. 이 모델은 2023년 말까지의 데이터로 학습했으니 2023년이 어떻게 끝났는지 이미 **읽은** 상태입니다. 그런데 프롬프트가 이렇다면:

```text
Date: 2023-03-01. Ticker: NVDA. Last close 232.10, RSI 58.
Note: NVDA closed at 305.40 on 2023-05-26 after earnings.
Decide BUY or SELL for the next 20 trading days.
```

세 군데서 샙니다. ① 모델 학습 데이터가 결과 구간 전체를 덮고, ② 날짜와 티커가 "무엇을 떠올리면 되는지"를 알려 주고, ③ 뉴스 피드에서 결정일 **이후** 가격이 한 줄 섞여 들어왔습니다. 백테스트 성적은 훌륭하게 나오지만, 그건 실력이 아닙니다.

`lookahead-guard`는 로그를 읽고 기록마다 이렇게 알려 줍니다:

```text
demo_log.jsonl:1 [leaky-future-price]  as_of=2023-03-01  model=gpt-4o-2024-08-06 (cutoff 2023-10-31)  exposure=full
  ERROR LAG001 exposure-full      학습 기준일이 결정일과 결과 구간 전체보다 뒤 + 프롬프트에 날짜·티커 노출
  ERROR LAG101 future-dated-fact  결정일 이후 날짜(2023-05-26)의 사실을 서술
  WARN  LAG201 absolute-date-visible
  WARN  LAG202 asset-identifier-visible
```

## 30초 빠른 시작

```bash
pip install git+https://github.com/dongjushin-ai/llm-lookahead-guard
lookahead-guard demo                      # 내장 가상 로그로 바로 체험
lookahead-guard check my_backtest.jsonl   # 내 로그 점검
```

로그는 JSONL, 한 줄에 LLM 판단 하나입니다. 필드 이름은 느슨하게 맞추므로(`as_of`/`date`/`et_date`/`timestamp`, `prompt`/`input`/`messages`, `response`/`output` ...) 기존 로그를 거의 그대로 넣을 수 있습니다.

```json
{"id": "r1", "as_of": "2023-03-01", "model": "gpt-4o", "horizon_days": 20, "prompt": "...", "response": "..."}
```

OpenAI·Anthropic·LangChain 형식의 `messages` 목록도 됩니다(assistant 턴은 응답으로 읽음). 텍스트 프롬프트 파일은 날짜를 함께 주세요: `lookahead-guard check prompt.txt --as-of 2023-03-01 --model gpt-4o`.

## 무엇을 점검하나

| 규칙 | 심각도 | 언제 |
|---|---|---|
| `LAG001` exposure-full | error / warning | 모델 학습 기준일이 결정일과 결과 구간 **전체**보다 뒤. 프롬프트에 날짜·티커·사건이 보이면 error, 마스킹돼 있으면 warning |
| `LAG002` exposure-partial | warning | 기준일이 결과 구간 중간에 걸침 |
| `LAG003` model-cutoff-unknown | warning | 모델 기준일을 모름 (비슷한 이름으로 추측하지 않음) |
| `LAG101` future-dated-fact | error | 결정일 이후 날짜에 일어난 일을 서술 ("closed at ... on 2023-05-26") |
| `LAG102` future-date-unclear | warning | 이후 날짜인데 "예정/전망" 표현이 없음 |
| `LAG103` future-date-scheduled | info | 예정된 일정으로 표현된 이후 날짜 ("earnings are due Oct 30") — 보통 정상 |
| `LAG104` anachronistic-event | error | 아직 일어나지 않은 사건 이름 (예: 2022년 프롬프트에 "SVB collapse") |
| `LAG105` hindsight-language | warning | "would later", "in hindsight", "went on to" 같은 사후 서술 |
| `LAG201` absolute-date-visible | 노출 시 warning, 아니면 info | 절대 날짜가 보여 시기를 특정할 수 있음 |
| `LAG202` asset-identifier-visible | 노출 시 warning, 아니면 info | 티커, `$TSLA`, `NASDAQ: XYZ`, 회사명, `--entity`로 준 이름 |
| `LAG203` era-event-visible | 노출 시 warning, 아니면 info | 시기를 알려 주는 사건명 (COVID-19, ChatGPT 등) |
| `LAG301` response-cites-future | error | **모델의 답**이 결정일 이후 사실을 서술 — 회상의 흔적 |
| `LAG302` response-hindsight | warning | 답에 사후 서술 |

내장 모델 기준일 표(`lookahead-guard cutoffs`)는 OpenAI·Anthropic·Google·Meta 49개 계열(`gpt-3.5-turbo`, `llama-2`부터 `gpt-6-luna`, `claude-opus-5-5`까지)의 벤더 공개값입니다. 항목마다 확인한 벤더 문서(`source`), 벤더 원문 표현(`stated`), 확인 날짜(`checked`, 최근 2026-10-18), 공식 문서로 확인됐는지(`verified`)를 남겨 두었고, `lookahead-guard cutoffs 모델명`으로 출처를 볼 수 있습니다. `--cutoffs my_cutoffs.json`(`{"my-finetune-v3": "2024-03"}`)으로 추가하거나 `--cutoff 2024-06`으로 강제할 수 있습니다. 더 새 버전은 옛 항목에 매칭하지 않습니다(`claude-opus-5-6`은 `claude-opus-5` 날짜를 물려받지 않고 "모름"으로 보고).

## CI에서 쓰기

```yaml
- run: pip install git+https://github.com/dongjushin-ai/llm-lookahead-guard
- run: lookahead-guard check logs/*.jsonl --format github --fail-on error
```

`--format github`은 PR 화면에 바로 주석을 달고, `--format json`은 스크립트용입니다. `--fail-on` 이상 등급이 있으면 종료 코드 1.

## 고치기: 마스킹

```bash
lookahead-guard mask examples/prompt.txt --as-of 2023-03-01 --mapping map.json
lookahead-guard mask my_backtest.jsonl > my_backtest.masked.jsonl
```

```text
전: Today is March 1, 2023. AAPL closed at 147.92. Q4 2022 revenue fell 5%. Results are due on May 4, 2023.
후: Today is D+0. ASSET_1 closed at 147.92. Q-1 revenue fell 5%. Results are due on D+64.
```

날짜는 결정일 기준 오프셋(`D-5`, `M-1`, `Q+1`, `Y-2`), 자산은 `ASSET_n`(티커와 회사명은 같은 별칭), 사건은 `EVENT_n`. 로그 전체에서 별칭이 고정되고, `unmask()`로 답의 자산명을 되돌릴 수 있습니다.

## 재 보기: 마스킹 vs 원본 A/B

마스킹하자 점수가 크게 떨어진다면 모델은 추론이 아니라 기억을 하고 있었던 겁니다. `run_ab`는 `프롬프트 -> 판단` 함수면 무엇이든 받고, 자체적으로 네트워크를 쓰지 않습니다.

```text
$ python examples/ab_demo.py      # 가짜 "암기 모델" + 가상 데이터
n=200  raw=1.000  masked=0.570  gap=+0.430 (95% CI +0.361 to +0.499)
```

`examples/ab_anthropic.py`는 같은 비교를 실제 모델과 내 데이터로 돌립니다. API 키가 있을 때만 동작합니다.

## 기존 도구와의 차이

| | 무엇을 보나 | API·모델 실행 필요 | 모델 기준일 점검 | 마스킹 |
|---|---|---|---|---|
| **llm-lookahead-guard** | 어떤 프레임워크든 로그 속 프롬프트·응답 텍스트 | 없음 | 기록마다, 결과 구간 기준 | 있음 + A/B |
| [Look-Ahead-Bench](https://github.com/benstaf/lookaheadbench) | 고정 벤치마크 위의 모델 | 필요 | 간접 (alpha decay) | 없음 |
| [Peek](https://github.com/OnePunchMonk/peek) | 데이터프레임·ML 파이프라인 | 없음 | 없음 | 없음 |
| [leakguard-mcp](https://github.com/doazvjettu/leakguard-mcp) | 파이썬 소스 코드 | 없음 | 없음 | 없음 |
| [TraderHarness](https://github.com/HephaestLab/TraderHarness) | 자체 하네스 안에서 실행 | 필요 | 없음 | 내장 |
| [agent-backtest-lab](https://github.com/bettyguo/agent-backtest-lab) | 전략 통계·데이터 접근 | 선택 | 없음 | 없음 |
| [Shapley-DCLR / TimeSPEC](https://arxiv.org/abs/2602.17234) | 모델 근거 속 주장 | 필요 (재실행·검색) | 없음 | 검색 필터 |
| [DatedGPT](https://arxiv.org/abs/2603.11838) | 시점 제한 모델로 교체 | 해당 없음 | 구조적으로 해결 | 해당 없음 |

서로 보완 관계입니다. 새 실험은 시점 정합 하네스로 안전하게 돌리고, 결과는 통계 도구로 판단하고, 이미 가진 로그나 공개할 로그는 이 린터로 점검하세요. 자세한 비교는 [docs/landscape.md](docs/landscape.md).

## 한계

- **증명이 아니라 휴리스틱입니다.** 정규식과 단어 목록이라 특이한 표현은 놓치고 무해한 문장을 잡기도 합니다. 깨끗한 리포트가 깨끗한 백테스트를 뜻하지는 않습니다.
- **마스킹은 재식별 위험을 줄일 뿐 없애지 못합니다.** 독특한 가격 경로나 유명한 숫자로도 시기를 알아챌 수 있습니다. 그래서 마스킹됐지만 노출된 기록은 warning으로 남깁니다.
- **마스킹은 미래 사실을 고치지 못합니다.** `mask`는 "closed at 305.40 on 2023-05-26"을 "closed at 305.40 on D+86"으로 바꾸고 숫자는 그대로 둡니다. 숫자는 모델의 입력이고, 가려도 누수는 남기 때문입니다. `check`는 `D+n`/`M+n`/`Q+n`/`Y+n`을 결정일 이후 날짜로 읽어 마스킹된 문장도 `LAG101`로 잡으니 그런 문장은 지우세요. 과거 오프셋(`D-5`)은 통과합니다.
- **기준일은 벤더 공개값입니다.** 실효 기준일은 다를 수 있습니다([Dated Data, arXiv 2403.12958](https://arxiv.org/abs/2403.12958)). `--margin-days`로 보수적으로 잡고, 틀린 값은 PR로 알려 주세요.
- **확인 못 한 항목이 2개 있습니다** (`verified: false`, `lookahead-guard cutoffs`에서 `NO`로 표시): `claude-3-sonnet`(2026-10-18에 Claude 3 모델 카드를 읽지 못함), `claude-opus-4-1`(시스템 카드에 기준일이 없고 은퇴한 모델 페이지는 사라짐, Claude Opus 4 값을 이어 씀). `claude-3-haiku`는 Anthropic이 아닌 Google Cloud 공식 Claude 페이지로 확인했습니다.
- **벤더 문서끼리 다르면 더 늦은 날짜를 씁니다.** 기준일이 늦을수록 경고가 늘어날 뿐 줄지 않기 때문입니다. `gpt-4`는 OpenAI 현재 문서의 2023년 12월(예전 문서는 0314/0613 스냅샷을 2021년 9월로 표기), `claude-sonnet-4-6`은 모델 페이지의 학습 데이터 기준일 2026년 1월(고객센터 글은 2025년 8월)을 씁니다.
- **아직 없는 모델:** Gemini 3.x·Gemini 4(구글 모델 페이지에 기준일이 없음), `gpt-5.4-mini`처럼 별도 벤더 페이지가 없는 변형, Llama 외 오픈 웨이트 모델.
- 지금은 영어 텍스트와 미국 시장 식별자만 다룹니다.
- 텍스트를 점검하지, 데이터 파이프라인을 점검하지 않습니다. 피처·분할 누수는 데이터 수준 도구와 함께 쓰세요.

## 기여

가장 반가운 기여는 `src/lookahead_guard/data/model_cutoffs.json` 수정·추가(벤더 문서 출처 포함), `lexicon.py`의 날짜 있는 사건 추가, 실제 사례의 거짓 양성/음성 이슈입니다.

## 라이선스와 고지

MIT. 연구·검증용 도구이며 투자 조언을 하지 않고 주문을 내지 않습니다.
