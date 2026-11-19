# 스키마 표준 대조와 수정안 (제안)

상태: **제안. 사용자 확인 전에는 스키마를 바꾸지 않습니다.** 작성 2026-11-19.

사용자 요청: 스키마를 최대한 표준 규약에 맞추고, 이것을 앞으로의 기준으로 삼아 점진적으로 올린다. 그래서 현재 스키마(버전 1.0.0, [schema-design.md](schema-design.md))를 공개 표준 원문과 다시 대조했습니다.

## 1. 대조한 표준

"표준"과 "널리 쓰이는 도구의 형식"은 구분했습니다. 뒤쪽은 표준이 아닙니다.

| 종류 | 이름 | 확인 방법 | 단계 |
| --- | --- | --- | --- |
| 표준 | OTLP 트레이스·로그 메시지 정의 (`opentelemetry-proto`의 `trace.proto`, `logs.proto`) | 원문 | Stable |
| 표준 | OTLP JSON 인코딩 (`opentelemetry-proto` `docs/specification.md`) | 원문 | Stable |
| 표준 | OTLP File Exporter (JSON Lines 파일 형식, `opentelemetry-specification`) | 원문 | Development |
| 표준 | OTel GenAI 시맨틱 규약 (span, `gen_ai.evaluation.result` 이벤트, 메시지 JSON 스키마) | 원문, 커밋 76e0c19 | Development |
| 표준 | OTel `error.type` 속성 | GenAI 규약 문서 안의 인용 | Stable |
| 표준 | W3C Trace Context (traceId 32자리, spanId 16자리) | 플랫폼 계약의 패턴으로 간접 확인 | W3C 권고 |
| 표준 | MLCommons Croissant 1.1 (데이터셋 메타데이터, JSON-LD) | 원문 앞부분은 직접, 뒷부분은 요약으로 확인 | 2026-01-29 공개 |
| 표준 | JSON Schema 2020-12, SemVer 2.0.0, RFC 3339(시간), RFC 8785(JSON 정규화) | 원문을 이번에 다시 읽지 않음. 널리 알려진 내용에 의존 | 확정 표준 |
| 내부 계약 | 플랫폼 계약 0.2.0 | 원문 | 사용자 소유 |
| 도구 형식 | Inspect AI 평가 로그 (`EvalLog` 등) | 문서 일부만 확인. 표본·점수의 세부 필드는 확인하지 못함 | 표준 아님 |

## 2. 현재 스키마가 표준과 어긋나는 곳

가장 큰 어긋남은 span입니다. **이름만 OTel이고 형식은 OTel이 아닙니다.**

| 기록 | 지금 | 표준 | 어긋남 |
| --- | --- | --- | --- |
| span | 한 줄에 span 하나. `startTime`(RFC 3339 문자열), `attributes`는 `{이름: 값}` 객체, `status`는 `ok`/`error` 문자열, `errorCode` 키 | OTLP JSON: 한 줄이 `TracesData`(`resourceSpans` → `scopeSpans` → `spans`). `startTimeUnixNano`(문자열 숫자), `attributes`는 `[{key, value: {stringValue…}}]` 배열, `status.code`는 정수, `kind`도 정수. 오류 분류는 `error.type` 속성 | 큼. 지금 파일은 OTel 도구(수집기, 뷰어)가 읽지 못함 |
| fieldScore | 자체 기록 | OTel `gen_ai.evaluation.result` 이벤트: `gen_ai.evaluation.name`(필수), `gen_ai.evaluation.score.value`, `gen_ai.evaluation.score.label`, `gen_ai.evaluation.explanation`. 평가 대상 span에 붙임. OTLP에서는 `eventName`이 있는 LogRecord | 큼. 같은 개념의 표준 이벤트가 있는데 쓰지 않음 |
| modelCall | 자체 기록. 토큰을 `usage`와 `attributes` 두 곳에 나눠 적음 | OTel: 모델 호출 1회 = 추론 span 1개, 토큰은 그 span의 `gen_ai.usage.*`. 비용(USD) 속성은 규약에 없음 | 중간. 같은 숫자가 span과 장부 두 곳에 있게 됨 |
| rawPayload | `content`가 자유 문자열 | OTel 메시지 JSON 스키마(`gen-ai-input-messages.json`, `gen-ai-output-messages.json`): `role`과 `parts[]`(TextPart, BlobPart, UriPart 등) | 중간. 입력·출력 메시지에 정해진 구조가 있음 |
| item | 자체 기록 | 항목 1건의 표준은 없음. 데이터셋 수준은 Croissant: `version`(SemVer 권고), 파일 `sha256`, `RecordSet`/`Field`, 분할(`cr:Split`) | 작음. 항목은 그대로 두고 데이터셋 설명 파일이 빠져 있음 |
| conditionManifest | 자체 기록 | 실험 설정의 표준은 없음. OTel에서는 실행 주체를 resource 속성(`service.name`, `service.version`)과 `gen_ai.agent.*`로 적음 | 작음. 해시 계산 규칙만 RFC 8785로 명시하면 됨 |
| evaluation, knowledgeDocument | 플랫폼 계약 파일 그대로 | 플랫폼 계약 | 없음 |
| 스키마 파일 자체 | `$schema`만 있음 | JSON Schema: `$id`로 스키마를 식별 | 작음 |

## 3. 수정안 (스키마 2.0.0)

| # | 바꾸는 것 | 내용 | 얻는 것 | 치르는 값 |
| --- | --- | --- | --- | --- |
| 1 | span을 OTLP JSON으로 | 추적 파일은 OTLP File Exporter 형식 그대로 씁니다. 한 줄이 `TracesData`입니다. `runId`, 스키마 버전은 resource 속성으로, `errorCode`는 `error.type` 속성으로 옮깁니다 (값은 플랫폼 오류 코드 10종 유지) | 변환 없이 OTel 수집기와 뷰어에 넣을 수 있음. 플랫폼 Observability에 그대로 연결 | 사람이 읽기 어려워짐. 그래서 읽고 쓰는 도우미 함수와 대시보드용 평탄화 함수를 둠. 검증은 "OTLP 구조 검사 + 속성 이름·필수 검사" 두 단계가 됨 |
| 2 | fieldScore를 OTel 평가 이벤트로 | `gen_ai.evaluation.result` 이벤트(OTLP 로그 파일)로 적고, 평가한 `chat` span의 traceId·spanId를 답니다. 제품 id, 대상 필드, 단계 같은 연구 고유 값은 `ocr.*` 속성으로 둡니다 | 표준 이벤트. 추적과 같은 도구로 조회 | 위와 같음 |
| 3 | modelCall을 추론 span으로 통합 | 모델 호출 1회마다 `chat` span을 하나씩 만듭니다 (재시도, 보조 모델 포함). 토큰은 `gen_ai.usage.*`, 비용은 표준에 없으므로 `ocr.cost.*`로 그 span에 적습니다. 비용 장부는 span에서 뽑아내는 집계 결과가 됩니다 | 같은 숫자를 한 곳에만 적음. 장부와 추적이 어긋날 수 없음 | "장부 파일"이 원본이 아니라 파생물이 됨. 플랫폼 `model-result.usage` 형식은 집계 단계에서 맞춤 |
| 4 | rawPayload의 메시지를 OTel 메시지 스키마로 | `input_messages`, `output_messages`의 `content`를 OTel JSON 스키마 구조로 적고 그 스키마로 검증합니다 | 원문 저장도 표준 구조 | OCR 출력과 검색 질의는 표준이 없어 지금처럼 둠 |
| 5 | 데이터셋 설명 파일 추가 | 평가셋 버전마다 Croissant 1.1 `croissant.json`을 만듭니다 (이름, 버전, 라이선스, 파일 해시, RecordSet, 분할). item 기록의 키는 그 RecordSet의 Field로 선언합니다 | 데이터셋 버전 동결이 표준 형식으로 남음 | 라이선스와 출처를 채우려면 데이터 이용약관 확인이 필요 (이미 대기 중인 항목) |
| 6 | 해시 계산 규칙 명시 | `manifestDigest`는 RFC 8785 정규화 JSON의 SHA-256으로 정의합니다 | 다른 언어로 구현해도 같은 해시 | 숫자 표기까지 RFC와 같은지 테스트 추가 |
| 7 | 스키마에 `$id`와 한글 `description` | 모든 스키마에 식별자와 키별 한글 설명을 넣습니다 | 스키마 파일만 읽어도 뜻을 알 수 있음 | 없음 |

바꾸지 않는 것: evaluation, knowledgeDocument (플랫폼 계약), item의 키 구성, conditionManifest의 키 구성, 속성 접두사 규칙(`gen_ai.*`, `platform.*`, `ocr.*`).

## 4. 표준이 없어서 자체 정의로 남는 것

이 부분은 표준을 찾지 못했습니다. 자체 정의임을 문서와 스키마에 표시합니다.

- A/B/C 질의 유형, OCR 오인식 표시, 후처리 전·후 단계: 이 연구의 설계입니다.
- 비용(USD) 속성: OTel GenAI 규약에 없습니다.
- 조건 선언(conditionManifest)의 구조: 실험 설정의 공통 표준이 없습니다.
- 항목 1건의 형식: 도구마다 다릅니다. Inspect AI는 표본에 input, target을 둔다고 문서에 나오지만 세부 필드는 확인하지 못했고, 표준도 아닙니다.
- OTel GenAI 규약은 Development 단계라 이름이 바뀔 수 있습니다. 커밋을 고정하고, 올릴 때마다 차이를 대조합니다.

## 5. 버전 처리

1.0.0은 PR #2에만 있고 이 형식으로 만든 실행 기록이 없습니다. 수정안을 채택하면 2.0.0으로 올리고 `released/2.0.0.json`을 추가합니다. 1.0.0 스냅샷은 기록으로 남깁니다.

## 6. 사용자가 정할 것

| 결정 | 권고 | 이유 |
| --- | --- | --- |
| 1번 (span을 OTLP JSON으로) | 채택 | 표준에 맞춘다는 목표에서 가장 큰 차이. 읽기 불편은 도우미로 해결 |
| 2번 (채점을 OTel 평가 이벤트로) | 채택 | 같은 개념의 표준이 있음 |
| 3번 (modelCall을 span으로 통합) | 채택 | 한 곳에만 기록. 다만 "장부가 파생물"이 되는 점은 사용자 판단 필요 |
| 4번 (메시지 구조) | 채택 | 비용이 작음 |
| 5번 (Croissant) | 채택하되 M1b에서 | 수집기를 만들 때 함께 만드는 것이 자연스러움 |
| 6번, 7번 | 채택 | 비용이 거의 없음 |
