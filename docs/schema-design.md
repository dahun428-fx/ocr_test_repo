# 스키마 설계 (스키마 2.0.0)

상태: **확정, 구현 완료.** 2026-11-19에 사용자가 두 번 결정했습니다. (1) 플랫폼 계약에 맞춘 v2 권고 5건 채택(1.0.0), (2) 표준 형식에 맞추는 수정안 7건 전부 채택(2.0.0). 1.0.0은 실행 기록을 만든 적이 없어 스냅샷을 두지 않습니다.

목표는 두 가지입니다. 공개 표준이 있는 곳은 그 형식을 그대로 쓰고, [aiagent_platform_core_system_architecture](https://github.com/dahun428-fx/aiagent_platform_core_system_architecture)(이하 플랫폼)에 바꾸지 않고 넣을 수 있게 합니다.

## 1. 근거

| 근거 | 확인한 원문 | 여기서 쓰는 곳 |
| --- | --- | --- |
| OTLP 메시지 정의 | `opentelemetry-proto`의 `trace.proto`, `logs.proto` | 추적과 평가 이벤트의 키 구성 |
| OTLP JSON 인코딩 | `opentelemetry-proto` `docs/specification.md` | id는 16진수 문자열, enum은 정수, 64비트 정수는 문자열 |
| OTLP File Exporter | `opentelemetry-specification` `protocol/file-exporter.md` (Development 단계) | JSONL 파일, 한 줄이 `TracesData` 또는 `LogsData`, 한 파일에 한 종류 |
| OTel GenAI 시맨틱 규약 | [semantic-conventions-genai](https://github.com/open-telemetry/semantic-conventions-genai) 커밋 76e0c19 (Development 단계) | span 이름, `gen_ai.*` 속성, `gen_ai.evaluation.result` 이벤트, 메시지 JSON 스키마 |
| OTel `error.type` | GenAI 규약 문서의 인용 (Stable) | 오류 분류 속성 |
| W3C Trace Context | 플랫폼 계약의 패턴 | traceId 32자리, spanId 16자리, 전부 0은 무효 |
| RFC 8785 (JSON 정규화) | 구현체 `rfc8785` 패키지와 테스트로 확인 | 해시 계산 |
| JSON Schema 2020-12, SemVer 2.0.0 | 원문을 이번에 다시 읽지 않음 | 스키마 파일, 버전 표기 |
| 플랫폼 계약 0.2.0 | `contracts/*.schema.json` (커밋 d3d0a9d) | evaluation, knowledgeDocument, id·버전·해시 형식, 오류 코드 10종 |
| 선행 연구 실행 기록 | `E:\ocr-local-benchmark`의 `predictions.jsonl` 키 | 주·보조 모델 분리, 캐시 토큰, SDK 보고 비용 |
| MLCommons Croissant 1.1 | 명세 앞부분 원문 | 데이터셋 설명 파일 (M1b에서 추가) |

## 2. 원칙

1. **표준 형식이 있으면 그대로 씁니다.** 추적과 평가 이벤트는 OTLP JSON입니다. OTel 도구가 변환 없이 읽습니다.
2. **플랫폼 계약이 있으면 그 파일을 그대로 씁니다.** evaluation과 knowledgeDocument는 사본이고 필드를 더하지 않습니다.
3. **속성 이름은 접두사로 출처를 드러냅니다.** `gen_ai.*`, `error.type`, `service.*`는 OTel 규약, `platform.*`는 플랫폼 개념, `ocr.*`는 이 연구의 자체 정의입니다.
4. **한 사실은 한 곳에만 적습니다.** 토큰과 비용은 chat span에만 있고, 비용 장부는 거기서 뽑는 집계입니다.
5. **원문은 추적에 넣지 않습니다.** 해시와 참조만 두고 원문은 저장소 밖 rawPayload에 둡니다. 속성 이름이 닫힌 목록이라 원문이 들어가는 이름은 스키마가 거부합니다.
6. **조건은 불변 선언이고 해시로 묶습니다.** 해시는 RFC 8785 정규화 JSON의 SHA-256입니다.
7. **스키마를 버전으로 동결합니다.** `schemas/released/<버전>.json` 스냅샷과 현재 스키마가 다르면 테스트가 실패합니다.
8. **가져온 파일은 고치지 않습니다.** 플랫폼 계약과 OTel 메시지 스키마 사본은 테스트가 파일 해시를 대조합니다.

## 3. 기록 종류

```
데이터        item ──────────────┐            자체 정의 (표준 없음)
지식베이스    knowledgeDocument  │            플랫폼 계약 그대로
조건 선언     conditionManifest ─┤            자체 정의 (표준 없음)
                                 ▼
실행          tracesData   추적 파일 한 줄    OTLP JSON. 단계 = span, 모델 호출 = chat span
                └─ rawPayload   원문          자체 봉투 + OTel 메시지 스키마. 저장소 밖
채점          logsData     평가 이벤트 한 줄  OTLP JSON. 채점 1건 = gen_ai.evaluation.result
                └─ evaluation   집계          플랫폼 계약 그대로
파생          비용 장부                        chat span에서 뽑음 (ocr_harness.ledger). 저장 형식 아님
```

| 종류 | 형식의 출처 | 파일 |
| --- | --- | --- |
| item | 자체 정의. id·버전·해시 형식은 플랫폼 | `item.schema.json` |
| knowledgeDocument | 플랫폼 `retrieval.schema.json`의 문서 형식 | `platform/0.2.0/` |
| conditionManifest | 자체 정의 | `condition-manifest.schema.json` |
| tracesData | OTLP `TracesData` + 속성 규칙 | `traces-data.schema.json` |
| logsData | OTLP `LogsData` + 속성 규칙 | `logs-data.schema.json` |
| rawPayload | 자체 봉투. 메시지는 OTel 메시지 스키마 | `raw-payload.schema.json`, `otel-genai/76e0c19e7fe1/` |
| evaluation | 플랫폼 `evaluation.schema.json` | `platform/0.2.0/` |

키와 속성 하나하나의 뜻은 스키마 파일의 `description`에 한글로 적혀 있습니다. 아래는 구조와 이유만 적습니다.

## 4. item, conditionManifest

둘 다 `schemaVersion`(상수 `2.0.0`)과 `recordType`을 가집니다.

**item** (평가 항목 1건): `itemId`(`img-` + 이미지 해시 앞 32자), `imageDigest`, `datasetVersion`(SemVer), `sourceFormat`, `domain`, `productId`(분할과 통계의 군집 단위), `split`(dev/test), `image{width,height}`, `classification`(플랫폼 분류 4종), `fields[]`(`fieldId`, `queryType` A/B/C, `gold`, `evidenceDocumentId`○), `queries[]`○, `tags[]`○. 정의하지 않은 키는 거부하므로 촬영자 개인정보가 들어올 수 없습니다.

**conditionManifest** (조건 하나의 불변 선언): `conditionId`(닫힌 목록 아님), `version`(플랫폼 `agentVersion`), `model{requestModel, authRoute}`, `components{ocr, retrieval, context, history, postprocess}`(각각 `{id, version}` 또는 `null`), `promptTemplateDigest`, `knowledgeIndexVersion`○, `sdk{name, version, cliVersion}`, `policyVersion`(`0.0.0` 고정), `platformContractVersion`(`0.2.0`), `semconvCommit`. 이 기록의 RFC 8785 해시가 `manifestDigest`입니다.

## 5. tracesData (추적)

파일 한 줄이 OTLP `TracesData`입니다. 보통 실행 1회(항목 × 조건 × 반복)의 span 전부를 한 줄에 담습니다.

```json
{"resourceSpans":[{
  "resource":{"attributes":[{"key":"service.name","value":{"stringValue":"ocr-harness"}}, …]},
  "scopeSpans":[{"scope":{"name":"ocr_harness","version":"0.1.0"},
    "spans":[{"traceId":"…32자리","spanId":"…16자리","parentSpanId":"…","name":"chat claude-sonnet",
              "kind":1,"startTimeUnixNano":"1795050000000000000","endTimeUnixNano":"1795050001000000000",
              "attributes":[{"key":"gen_ai.usage.input_tokens","value":{"intValue":"250"}}, …],
              "status":{"code":1}}]}]}]}
```

- resource 속성(필수): `service.name`(`ocr-harness`), `service.version`, `ocr.run.id`, `ocr.schema.version`.
- 시간은 유닉스 나노초 문자열, `kind`와 `status.code`는 정수, 속성은 `[{key, value}]` 배열입니다. 모두 OTLP JSON 규칙입니다.
- `status.code`가 2(ERROR)이면 `error.type` 속성이 있어야 하고, 값은 플랫폼 오류 코드 10종입니다.
- 속성 값에 "없음"은 적을 수 없습니다. 모르는 값은 속성을 뺍니다.

span 종류 (`name`의 첫 단어)와 필수 속성:

| span | 언제 | 필수 속성 |
| --- | --- | --- |
| `invoke_agent ocr-harness` | 실행 1회 (루트) | `gen_ai.operation.name`, `gen_ai.agent.name`, `gen_ai.agent.version`, `ocr.item.id`, `ocr.condition.id`, `ocr.manifest.digest`, `ocr.dataset.version`, `ocr.repeat`, `platform.idempotency_key`, `ocr.outcome`(ok/refused/empty/error) |
| `ocr` | OCR 실행 또는 캐시 읽기 | `ocr.engine.name`, `ocr.engine.version`, `ocr.output.digest`, `ocr.cache.hit` |
| `retrieval {자료원}` | 검색 | `gen_ai.operation.name`, `gen_ai.data_source.id`, `gen_ai.retrieval.top_k`, `gen_ai.retrieval.documents`(id, score + rank, selected), `ocr.retrieval.query.digest` |
| `context` | 컨텍스트 구성 | `ocr.context.template.digest`, `ocr.context.order`, `ocr.context.tokens.{instruction,ocr,documents,history,image}` |
| `history` | 이력 선별 (M8) | `ocr.history.candidates`, `ocr.history.excluded` |
| `chat {모델}` | **모델 호출 1회** (재시도, 보조 모델도 각각) | `gen_ai.operation.name`, `gen_ai.provider.name`, `gen_ai.request.model`, `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`, `gen_ai.usage.cache_read.input_tokens`, `gen_ai.usage.cache_write.input_tokens`, `ocr.prompt.digest`, `ocr.model.role`(main/auxiliary), `ocr.model.auth_route`, `ocr.model.attempt`, `platform.model.provider`, `platform.route_decision.id`, `ocr.usage.hidden_context_tokens`, `ocr.cost.price_table.version` |
| `postprocess` | 후처리 | `platform.guardrail.mode`(check_only/enforce), `ocr.postprocess.kind`, `ocr.postprocess.rules`, `ocr.output.before.digest`, `ocr.output.after.digest` |

chat span의 선택 속성: `gen_ai.system_instructions_ref`, `gen_ai.response.model`, `gen_ai.response.finish_reasons`, `gen_ai.usage.reasoning.output_tokens`, `gen_ai.input.messages_ref`, `gen_ai.output.messages_ref`, `ocr.cost.sdk_reported_usd`, `ocr.cost.computed_usd`, `ocr.cost.basis`, `ocr.sdk.num_turns`, `ocr.sdk.duration_api_ms`. 그 밖의 선택 속성은 원문 참조인 `ocr.output.ref`(ocr span)와 `ocr.retrieval.query.ref`(retrieval span)입니다.

`history` span은 M8에서 쓸 자리만 정의했습니다. SDK로 만든 기록이 스키마를 통과하는지 확인한 것은 나머지 6종입니다.

선행 연구 기록과의 대응: SDK 결과 1건의 `sdk.model_usage`에는 모델별 항목이 있습니다(주 모델과 보조 Haiku). 모델 하나당 chat span 하나로 풀어 적고 `ocr.model.role`로 구분합니다. `cacheCreationInputTokens`는 `gen_ai.usage.cache_write.input_tokens`, `costUSD`는 `ocr.cost.sdk_reported_usd`, `costBasis`는 `ocr.cost.basis`가 됩니다. 실패한 호출도 span을 남기고 토큰을 0으로 적습니다.

**비용 장부**는 저장 형식이 아니라 `ocr_harness.ledger.model_calls()`가 chat span에서 뽑는 행입니다. 행의 키는 플랫폼 `model-result`와 같은 이름(`usage.inputTokens`, `usage.outputTokens`, `provider`, `routeDecisionId`)입니다.

## 6. logsData (평가 이벤트)

파일 한 줄이 OTLP `LogsData`이고, 채점 1건이 `eventName`이 `gen_ai.evaluation.result`인 LogRecord 하나입니다. `traceId`와 `spanId`는 채점한 출력을 만든 span을 가리킵니다 (규약: 평가 대상 span에 붙임).

| 속성 | 필수 | 출처 |
| --- | --- | --- |
| `gen_ai.evaluation.name`, `gen_ai.evaluation.score.value` | ● | OTel |
| `gen_ai.evaluation.score.label` | ○ | OTel |
| `ocr.score.id`, `ocr.item.id`, `ocr.product.id` | ● | 자체. `ocr.product.id`는 제품 단위 신뢰구간·검정용 |
| `ocr.condition.id`, `ocr.condition.version`, `ocr.manifest.digest`, `ocr.dataset.version`, `ocr.scorer.version` | ● | 자체. 플랫폼 evaluation의 `agentVersion`, `manifestDigest`, `datasetVersion`에 대응 |
| `ocr.target.kind`(field/query/item), `ocr.target.id`(field·query일 때 필수) | ● | 자체 |
| `ocr.query.type`(A/B/C), `ocr.ocr_misread` | ○ | 자체. 주 지표의 분모 표시 |
| `ocr.score.stage`(before_postprocess/after_postprocess) | ● | 자체 |

채점 자체가 실패하면 `error.type`(플랫폼 오류 코드)을 적습니다. OTel의 `gen_ai.evaluation.explanation`(자유 글)은 정답이나 원문이 섞일 수 있어 받지 않습니다.

## 7. rawPayload, evaluation, knowledgeDocument

**rawPayload**: `schemaVersion`, `recordType`, `runId`, `traceId`, `spanId`, `digest`, `kind`, `content`, `retention`. `kind`가 `input_messages`, `output_messages`이면 `content`는 OTel 메시지 JSON 스키마(메시지마다 `role`과 `parts[]`)를 따르고, `ocr_output`, `retrieval_query`, `postprocess_output`이면 글자열입니다. `digest`는 글자열이면 UTF-8 바이트의, 구조가 있으면 RFC 8785 정규화 JSON의 SHA-256입니다. 저장소에 올리지 않습니다.

**evaluation**: 플랫폼 계약 그대로 (`evaluationId`, `datasetVersion`, `agentVersion`, `manifestDigest`, `policyVersion`, `metric`, `score`, `threshold`, `passed`, `traceId`). 조건 × 지표의 집계 한 줄이고 EDD 관문의 판정 기록입니다. 신뢰구간, 표본 수, p값은 이 계약에 자리가 없어 별도 통계 리포트에 두고 `evaluationId`로 연결합니다.

**knowledgeDocument**: 플랫폼 계약 그대로 (`documentId`, `content`, `citation`(URI), `classification`, `tenantId`, `allowedPrincipals`). 연구에서는 `tenantId`를 `ocr-research`, `allowedPrincipals`를 `["ocr-research"]`로 고정합니다.

## 8. 표준이 없어 자체 정의인 것

- A/B/C 질의 유형, OCR 오인식 표시, 후처리 전·후 단계: 이 연구의 설계입니다.
- 비용(USD) 속성 `ocr.cost.*`: OTel GenAI 규약에 비용 속성이 없습니다.
- `ocr`, `context`, `history`, `postprocess` span: 규약에 해당 작업 이름이 없습니다.
- item과 conditionManifest의 구조: 공통 표준이 없습니다.
- OTel GenAI 규약과 OTLP File Exporter는 Development 단계라 바뀔 수 있습니다. 커밋을 고정했고, 올릴 때마다 차이를 대조합니다.

## 9. 플랫폼에 넣는 경로

| 이 저장소 | 플랫폼 | 필요한 작업 |
| --- | --- | --- |
| evaluation | Evaluation | 없음 |
| knowledgeDocument | Knowledge | `tenantId`, `allowedPrincipals`를 실제 값으로 |
| tracesData, logsData | Observability | 없음. OTLP 파일을 수집기에 그대로 넣음 |
| 비용 장부 행 | Agent Gateway 모델 경로의 비용 귀속 | 없음. 같은 이름 |
| conditionManifest | Agent Manifest + Tuning | identity, governance, deployment를 채워 변환 |
| postprocess의 검사 모드 | Guardrails 집행 지점 | 규칙을 검사 서비스 adapter로 |
| rawPayload | 평가 목적 원문 기록 (플랫폼 TBD-12) | 승인·보존 정책 확정 후 |

## 10. 구현 위치와 바꾸는 절차

| 무엇 | 어디 |
| --- | --- |
| 스키마의 원본 (표로 정의) | `tools/build_schemas.py` |
| 만들어진 스키마 JSON | `src/ocr_harness/schemas/*.schema.json` |
| 가져온 사본 (고치지 않음) | `schemas/platform/0.2.0/`, `schemas/otel-genai/76e0c19e7fe1/` |
| 동결 스냅샷 | `schemas/released/2.0.0.json` |
| 검증 | `ocr_harness.schema.validate(kind, record)` |
| 추적·평가 이벤트 쓰기 | OpenTelemetry SDK + 공식 JSON 인코더. `ocr_harness.otlp`는 파일 내보내기(`JsonLinesSpanExporter`, `JsonLinesLogExporter`)와 `resource`, `finish`, `emit_evaluation`만 더함 |
| 추적 읽기 | `ocr_harness.otlp`의 `plain_attributes`, `flatten_spans` |
| 비용 장부 집계 | `ocr_harness.ledger.model_calls` |
| id와 해시 | `ocr_harness.ids` |

스키마를 바꾸는 절차:

1. 실패하는 테스트를 먼저 씁니다.
2. `tools/build_schemas.py`의 표를 고치고, `schema.py`의 `SCHEMA_VERSION`을 올립니다 (상수는 이 한 곳에만 있고 `otlp.py`와 스크립트가 가져다 씁니다). 속성을 더하기만 하면 minor, 뜻이나 형식을 바꾸면 major입니다.
3. `python tools/build_schemas.py --release`로 스키마 파일과 새 스냅샷을 씁니다.
4. `docs/HISTORY.md`에 이유를 적습니다.

스냅샷과 현재 스키마가 다르거나, JSON 파일을 손으로 고쳐 스크립트 결과와 다르면 테스트가 실패합니다.

## 11. 알려진 한계

- 기록은 OpenTelemetry Python SDK(`opentelemetry-sdk` 1.45.2)와 공식 JSON 인코더(`opentelemetry-exporter-otlp-json-common` 0.66b2)로 만듭니다. 인코더와 SDK의 로그 API는 아직 베타라 버전을 고정했습니다. 올릴 때는 "SDK가 만든 기록이 스키마를 통과한다"는 테스트가 차이를 잡습니다.
- Python SDK에는 OTLP JSON 파일 내보내기가 없어 그 부분(약 20줄)만 직접 썼습니다.

- 속성 배열 안에서 같은 이름이 두 번 나오는 것은 스키마로 막지 못합니다 (OTLP는 이름이 겹치지 않아야 한다고 정합니다). SDK가 속성을 이름별로 하나만 가지므로 실제로는 생기지 않습니다.
- `citation`의 URI 형식은 JSON Schema의 `format`이라 검증기가 강제하지 않습니다.
- Croissant 데이터셋 설명 파일은 아직 없습니다. M1b에서 수집기와 함께 만듭니다.
