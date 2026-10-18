# 경쟁 지형 (2026-10-18 직접 확인)

> 조사 방법: 각 저장소·논문 페이지를 직접 열어 README/초록 기준으로 정리. 스타 수는 확인 시점 값.
> "안 하는 것"은 페이지에 해당 기능이 **언급되지 않음**을 뜻하며, 숨은 기능이 있을 수 있음.

## 한눈에 보기

| 도구 | 형태 | 무엇을 하나 | 입력 | 키·네트워크 | 안 하는 것 (우리와 겹치지 않는 부분) |
|---|---|---|---|---|---|
| [Look-Ahead-Bench](https://github.com/benstaf/lookaheadbench) (arXiv 2601.13770), ★8 | 벤치마크 (+웹 UI) | 모델별 alpha decay 측정: 2021년(학습 내) vs 2024년(학습 밖) 구간, AAPL 등 5종목, AI Hedge Fund 프레임워크로 실행 | 정해진 시나리오 | 모델 실행 필요 | **내 백테스트 로그**를 점검하지 않음. 모델 단위 평가이지 기록 단위 진단이 아님. 라이선스 미표기 |
| [Peek](https://github.com/OnePunchMonk/peek), ★0, MIT | 파이썬 라이브러리+CLI | 시계열 ML 파이프라인 누수 감사: target leak, 피처 인과성(잘라서 재계산), split 겹침, shuffle 순열 검정 | 데이터프레임·피처 함수 | 불필요 | **LLM 텍스트**(프롬프트·응답)와 **모델 학습 기준일**을 다루지 않음 |
| AgentQuant (Peek의 출발점) | LLM 전략 연구 에이전트 | Peek README에 따르면 중심 이동 창·워밍업 부족 누수를 직접 겪고 Peek을 분리 | - | - | PR 자체는 이번 조사에서 직접 확인하지 못함. 성격은 Peek과 같은 "데이터 파이프라인" 쪽 |
| [Shapley-DCLR / TimeSPEC](https://arxiv.org/abs/2602.17234) (arXiv 2602.17234) | 논문+익명 코드 | 모델 근거를 원자 주장으로 쪼개 시점 분류, Shapley로 "결정을 움직인 주장 중 미래 정보 비율" 계산. TimeSPEC은 날짜 필터 검색+주장 감사+재생성 | 모델 근거, 기준일, 재실행 권한, 검색 API | **필요** (LLM 재실행, Perplexity·Gemini 검증) | 오프라인·저비용·CI용이 아님. 정적 점검 없음. 저자도 비용을 한계로 명시 |
| [DatedGPT](https://arxiv.org/abs/2603.11838) (arXiv 2603.11838) | 논문+웹 데모 | 연도별 컷오프(2013~2024) 1.3B 모델 12개를 새로 학습, 미래 정보 없는 모델 제공. "lookahead premium" 26.4bp 측정 | - | - | 기존 모델·기존 백테스트를 점검하지 않음(모델을 **바꾸는** 해법). 코드 링크 없음 |
| [TraderHarness](https://github.com/HephaestLab/TraderHarness), ★14, Apache-2.0 | 백테스트 하네스 | 시뮬레이션 시계로 데이터 차단, 날짜→`D+0`·회사→중립 ID 이중 마스킹, 요청 지문 기반 재현, 직렬화 출력 audit | 자체 하네스 안의 실행 | 모델 실행 필요 | **가장 가까운 경쟁자.** 단, 마스킹이 하네스 내부 기능이고 다른 프레임워크 로그를 점검하는 독립 린터로 쓰는 방법은 안내되지 않음. 모델 기준일 표 없음 |
| [agent-backtest-lab](https://github.com/bettyguo/agent-backtest-lab), Apache-2.0 | 통계 감사 하네스 | as-of 이후 데이터 거부 방화벽, 조정주가 거부, 퍼지 CV, PBO·DSR·Reality Check, TradingAgents·FinGPT 어댑터 | 전략·에이전트 | 선택 | 프롬프트 텍스트 점검, 모델 기준일, 마스킹 A/B 없음 (페이지 기준) |
| [traceguard](https://github.com/lizhuojunx86/traceguard), ★2, Apache-2.0 | 계측·트레이싱 | 피처/모델/참조 데이터 타임스탬프 검증, 모델 **출시일** 레지스트리로 미출시 모델 사용 차단, 프롬프트 버전 고정 | 파이프라인 코드 | 선택 | 프롬프트 **내용** 스캔 없음. 출시일은 보지만 **학습 기준일 대비 결과 구간 노출**은 판정하지 않음 |
| [NoAlpha](https://github.com/flysheep-ai/NoAlpha), ★3, MIT | 연구 플랫폼 | 시점 정합 라벨, 앞으로만 쌓는 LLM 피처 저장소, 누수 공격 테스트 | 자체 파이프라인 | 필요 | 로그 텍스트 점검·기준일 표·마스킹 없음 |
| [leakguard-mcp](https://github.com/doazvjettu/leakguard-mcp), ★0, MIT | 정적 분석기(MCP) | 파이썬 **코드**의 `shift(-n)`, 중심 rolling, 전역 스케일링 등 10개 규칙 | .py 소스 | 불필요 | 프롬프트·응답 텍스트는 분석하지 않음 (명시) |
| [Profit Mirage / FactFin](https://arxiv.org/abs/2510.07920) (arXiv 2510.07920) | 논문 | 반사실 교란(가격·팩터·뉴스)으로 암기 의존도 측정, FinLake-Bench | 전략·데이터 | 필요 | 코드 링크 확인 못함. 텍스트 정적 점검 아님 |
| llm-knowledge-cutoff-dates (HaoooWang) | 목록(awesome 리스트) | 모델별 지식 기준일 모음 | - | - | 아무것도 점검하지 않음. 우리 표의 교차검증 출처로 쓸 수 있음 |
| [Dated Data](https://arxiv.org/abs/2403.12958) (arXiv 2403.12958) | 논문 | 공개 기준일과 **실효** 기준일이 다를 수 있음을 보임 | - | - | 도구 아님. 우리 `--margin-days` 근거 |

## 고른 빈틈

**"이미 돌린 백테스트의 로그 텍스트를, 키 없이·의존성 없이·어떤 프레임워크든, CI에서 30초 안에 점검하는 린터"** 가 없다.

1. **입력 단위가 다르다.** 기존 도구는 데이터프레임(Peek), 파이썬 코드(leakguard), 자체 하네스 실행(TraderHarness, agent-backtest-lab), 모델 자체(Look-Ahead-Bench, DatedGPT)를 본다. LLM에 **실제로 보낸 문자열과 받은 답**을 JSONL로 받아 기록 단위로 판정하는 도구는 확인되지 않았다.
2. **모델 기준일 × 결정일 × 결과 구간** 을 묶어 "이 기록은 결과 전체가 학습 데이터 안에 있다"를 판정하는 기능이 없다. traceguard는 출시일만, 목록 저장소는 표만 있다.
3. **노출 여부에 따라 식별자 경고의 심각도를 바꾸는** 규칙(노출된 모델 + 날짜·티커 노출 = error, 마스킹됨 = warning)은 어디에도 없다.
4. **모델 응답에서 회상 흔적**(결정일 이후 사건을 과거형으로 서술)을 정규식만으로 잡는 저비용 점검. Shapley-DCLR은 정교하지만 API 비용이 크고, 우리는 그 앞단의 무료 1차 필터 역할.

TraderHarness와는 **경쟁보다 보완**: 그쪽은 "처음부터 안전하게 돌리는 하네스", 우리는 "이미 있는 로그·다른 프레임워크(TradingAgents, LangChain, 자작 봇)용 린터". TraderHarness 출력에도 돌릴 수 있다.

## 정직한 한계

- 정규식·사전 기반 휴리스틱이라 거짓 양성/음성이 있다. 정밀도는 아직 측정 전(스프린트 2 목표).
- 마스킹해도 가격 경로·숫자로 시기를 재식별할 수 있다(TraderHarness도 같은 단서를 단다). 그래서 마스킹된 노출 기록은 error가 아니라 warning으로 남긴다.
- 기준일 표는 벤더 공개값이며 실효 기준일과 다를 수 있다.
