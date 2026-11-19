# 스키마 설계안 v2 (제안)

상태: **제안. 사용자 확인 전에는 코드를 바꾸지 않습니다.** 작성 2026-11-19.

M0에서 만든 스키마 4종(v1)은 근거 대조 없이 이름을 정한 곳이 많았습니다. 이 문서는 (1) 근거를 원문으로 확인하고, (2) 나중에 [aiagent_platform_core_system_architecture](https://github.com/dahun428-fx/aiagent_platform_core_system_architecture)(이하 플랫폼)에 그대로 넣을 수 있는 구조로 다시 잡은 설계안입니다.

## 1. 확인한 근거

| 근거 | 확인한 원문 | 여기서 가져오는 것 |
| --- | --- | --- |
| 플랫폼 계약 | `contracts/*.schema.json` 0.2.0 (커밋 d3d0a9d) | 평가 결과, 검색 문서, 모델 결과·사용량, 오류 코드, id·버전·해시 형식 |
| 플랫폼 문서 | `docs/observability.md`, `evaluation.md`, `guardrails.md`, `memory.md`, `versioning.md` | 추적 전파, 속성 이름 규칙, 원문 기록 금지, 검사 모드, 계약 동결 방식 |
| OpenTelemetry GenAI 시맨틱 규약 | [semantic-conventions-genai](https://github.com/open-telemetry/semantic-conventions-genai) main, 커밋 76e0c19 (Development 단계) | span 이름, `gen_ai.*` 속성 이름 |
| W3C Trace Context | 플랫폼 계약의 `traceparent`, `traceId` 패턴 | traceId 32자리, spanId 16자리 16진수 |
| 선행 연구 실행 기록 | `E:\ocr-local-benchmark\research\runs\*\predictions.jsonl`의 `sdk.usage`, `sdk.model_usage`, `total_cost_usd_reported` | 주·보조 모델 분리, 캐시 토큰, SDK 보고 비용 |
| 선행 문헌 | OHRBench (arXiv 2412.02592), Adding Error Bars to Evals (arXiv 2411.00640) | 단계별(OCR·검색·생성) 기록 분리, 채점 기록에 군집 단위(제품) 포함 |

아직 원문으로 대조하지 못한 것: 선행 연구 `predictions.jsonl`의 전체 키 목록. 구현 전에 PC에서 다시 읽어 6.5절 표를 확정합니다.

## 2. 플랫폼 계약에서 확인한 형식 규칙

v1은 이 규칙들과 어긋납니다.

| 규칙 | 플랫폼 원문 | v1 상태 |
| --- | --- | --- |
| 키 이름 | camelCase (`datasetVersion`, `traceId`, `documentId`) | snake_case |
| 식별자 | `^[a-z][a-z0-9.-]{1,63}$` | `sha256:…`를 id로 씀 (형식 위반) |
| 버전 | `^[0-9]+\.[0-9]+\.[0-9]+$` (semver) | 자유 문자열 (`eval-v1`, `c1-v1`) |
| 해시 | `^sha256:[a-f0-9]{64}$`, 이름은 `…Digest` | 형식은 같고 이름이 다름 |
| 추적 | `traceId` 32자리 16진수, `traceparent` | 자유 문자열 (`tr-0001`) |
| 오류 코드 | `problem.code` 10종 | 3종만 |
| 사용량 | `usage.inputTokens`, `usage.outputTokens` | `gen_ai.usage.*`만 |
| 닫힌 스키마 | `additionalProperties: false` | 같음. 단 trace의 단계 안쪽은 열려 있음 |
| 원문 | 프롬프트·출력·검색 원문은 추적에 기록 금지. 평가 목적은 별도 승인과 보존 정책 | OCR 글자와 모델 원출력을 trace 안에 넣음 |
| 속성 이름 | span 이름·속성은 OTel GenAI 규약. 플랫폼 고유 속성은 `platform.` 접두사 | 섞여 있음. `cache_creation`은 규약에 없는 이름 |
| 계약 동결 | `contracts/released/<버전>.json` 스냅샷과 현재 계약이 같은지 테스트로 검사 | 없음 |

## 3. 설계 원칙

1. **플랫폼 계약이 있는 기록은 그 계약을 그대로 만족합니다.** 필드를 더하지 않습니다. 평가 결과와 검색 문서가 여기에 해당합니다.
2. **플랫폼 계약이 없는 기록은 봉투(envelope)와 속성으로 나눕니다.** 봉투 키는 플랫폼과 같은 camelCase와 형식 규칙을 씁니다. 측정값은 `attributes` 안에 넣고 이름은 OTel `gen_ai.*`, 플랫폼 개념은 `platform.*`, 이 연구 고유는 `ocr.*` 접두사를 씁니다.
3. **원문은 추적 기록에 넣지 않습니다.** 추적에는 해시와 참조만 두고, 원문은 저장소 밖의 내용 주소 저장소에 둡니다. OTel의 `gen_ai.input.messages_ref`, `gen_ai.output.messages_ref`와 같은 방식입니다. 플랫폼의 "평가 목적 원문 기록은 별도 승인·보존 정책" 조항에 맞습니다.
4. **조건은 불변 선언(manifest)이고 해시로 묶습니다.** 플랫폼의 `agentVersion` + `manifestDigest`에 그대로 대응합니다.
5. **스키마를 버전으로 동결합니다.** 플랫폼과 같은 방식으로 `schemas/released/<버전>.json` 스냅샷을 두고, 현재 스키마와 다르면 테스트가 실패합니다.
6. **고정 값으로 채우는 자리는 표시해 둡니다.** 테넌트, 정책 버전처럼 연구에서 쓰지 않는 플랫폼 필수 값은 상수로 채우고, 플랫폼에 넣을 때 실제 값으로 바꿉니다.

## 4. 기록 종류 (v1 4종 → v2 8종)

```
데이터        item ──────────────┐
지식베이스    knowledgeDocument  │   (플랫폼 retrieval 문서 형식)
조건 선언     conditionManifest ─┤   (불변, digest)
                                 ▼
실행          span  (OTel span 형식, 실행 1회 = trace 1개 = span 여러 개)
                ├─ rawPayload   (원문. 저장소 밖, 해시로 참조)
                └─ modelCall    (비용 장부. 호출 1회 = 1줄)
채점          fieldScore        (필드·질의 1건)
                └─ evaluation   (조건 × 지표 집계. 플랫폼 evaluation 계약 그대로)
```

| v2 기록 | v1에서 | 바뀌는 이유 |
| --- | --- | --- |
| item | item | id·버전 형식, 질의 추가 |
| knowledgeDocument | 없음 | 플랫폼 `retrieval.schema.json`의 문서 형식을 그대로 씀 |
| conditionManifest | 없음 (문자열 `condition_version`만) | 조건을 해시로 고정해야 `manifestDigest`를 채울 수 있음 |
| span | trace.steps | 단계를 OTel span으로. 단계 추가(M8 이력 등)에 스키마 변경이 필요 없음 |
| rawPayload | trace 안의 원문 | 원문 기록 금지 규칙. 공개 저장소 규칙과도 맞음 |
| modelCall | cost_ledger | 이름과 형식 정리, 플랫폼 `usage`·`routeDecisionId` 대응 |
| fieldScore | eval_record | 필드 외에 질의·이미지 단위 채점도 받음, 군집 단위(제품) 포함 |
| evaluation | 없음 | 플랫폼 계약 그대로. EDD 관문의 통과·실패 기록 |

## 5. 공통 봉투

플랫폼 계약이 없는 기록(item, conditionManifest, span, rawPayload, modelCall, fieldScore)은 아래 키를 공통으로 가집니다.

| 키 | 형식 | 근거 |
| --- | --- | --- |
| `schemaVersion` | semver | 플랫폼 versioning. v1에 없던 것 |
| `recordType` | 기록 종류 이름 (상수) | JSONL 한 파일에 섞여도 구분 |
| `runId` | 플랫폼 id 패턴 | 실행 묶음 |
| `traceId` | 32자리 16진수 | W3C, 플랫폼 `evaluation.traceId` (item·conditionManifest 제외) |

## 6. 기록별 정의

필수는 ●, 선택은 ○입니다.

### 6.1 item

| 키 | 필수 | 형식 | 근거·비고 |
| --- | --- | --- | --- |
| `itemId` | ● | 플랫폼 id 패턴. `img-` + 이미지 해시 앞 32자 | v1은 해시 전체를 id로 써서 패턴 위반 |
| `imageDigest` | ● | `sha256:…` | 플랫폼 `…Digest` 이름 규칙 |
| `datasetVersion` | ● | semver | 플랫폼 evaluation. `eval-v1` → `1.0.0` |
| `sourceFormat`, `domain` | ● | 문자열 | 증분 데이터 규칙 (형식 어댑터) |
| `productId` | ● | 플랫폼 id 패턴 | 통계 군집 단위 (Adding Error Bars) |
| `split` | ● | `dev` / `test` | CLAUDE.md 규칙 5 |
| `image` | ● | `width`, `height` | |
| `classification` | ● | `public` / `internal` / `confidential` / `restricted` | 플랫폼 데이터 분류. 이용약관 확인 결과를 여기에 기록 |
| `fields[]` | ● | `fieldId`, `queryType`(A/B/C), `gold`, `evidenceDocumentId`○ | 설계 v3. gold는 인쇄된 값 |
| `queries[]` | ○ | `queryId`, `queryType`, `question`, `answer`, `evidenceDocumentId`○ | v1에 없던 것. 주 과제의 질의응답 |

촬영자 개인정보 키는 정의하지 않으므로 들어올 수 없습니다 (닫힌 스키마).

### 6.2 knowledgeDocument

플랫폼 `retrieval.schema.json`의 `documents[]` 항목과 **같은 스키마**입니다. 추가 필드가 없습니다.

| 키 | 값 | 비고 |
| --- | --- | --- |
| `documentId` | 플랫폼 id 패턴 | 식약처 품목기준코드에서 만듦 |
| `content` | 문서 본문 | 저장소 밖에 저장 |
| `citation` | 출처 URL과 받은 날짜 | |
| `classification` | `public` | 공개 근거 자료만 색인 (CLAUDE.md 규칙 3) |
| `tenantId` | `ocr-research` (고정) | 원칙 6 |
| `allowedPrincipals` | `["ocr-research"]` (고정) | 플랫폼 id 패턴의 문자열 배열. 원칙 6 |

색인 목록(문서 id, 내용 해시, 색인 버전)은 conditionManifest가 참조합니다.

### 6.3 conditionManifest

조건 하나의 불변 선언입니다. 이 파일의 해시가 `manifestDigest`입니다.

| 키 | 필수 | 형식 | 플랫폼 대응 |
| --- | --- | --- | --- |
| `conditionId` | ● | `c0`~`c4`, `ck` 등. 닫힌 목록이 아님 | Manifest `metadata.id` |
| `version` | ● | semver | `agentVersion` |
| `model` | ● | 요청 모델 id, 인증 경로 | `gen_ai.request.model` |
| `components` | ● | ocr, retrieval, context, history, postprocess 각각의 구현 id와 버전, 또는 `null`(없음) | Manifest `capabilities` |
| `promptTemplateDigest` | ● | `sha256:…` | `gen_ai.prompt.name`, `gen_ai.prompt.version` |
| `knowledgeIndexVersion` | ○ | semver | 플랫폼 `knowledgeId` |
| `sdk` | ● | SDK·CLI 버전 | 연구 계획 §10 (버전 고정) |
| `policyVersion` | ● | semver. 연구에서는 `0.0.0` 고정 | 플랫폼 evaluation 필수 값 (원칙 6) |
| `semconvCommit` | ● | OTel 규약 커밋 | 플랫폼 observability "규격 버전을 고정하고 기록" |

플랫폼의 정식 Agent Manifest(`agent.platform/v1alpha1`)는 identity, governance, deployment까지 요구하므로 지금은 만들지 않습니다. 넣을 때 이 선언에서 변환합니다.

### 6.4 span

실행 1회(항목 × 조건 × 반복)가 trace 하나이고, 단계마다 span 한 줄입니다.

| 키 | 필수 | 형식 | 근거 |
| --- | --- | --- | --- |
| `traceId`, `spanId`, `parentSpanId`○ | ● | 32 / 16 / 16자리 16진수 | W3C Trace Context |
| `name` | ● | 아래 표 | OTel span 이름 규칙 |
| `startTime`, `endTime` | ● | RFC 3339 | OTel |
| `status` | ● | `ok` / `error` | OTel span status |
| `errorCode` | ○ | 플랫폼 `problem.code` 10종 | status가 error이면 필수 |
| `attributes` | ● | 아래 표의 이름만 허용 | 원칙 2 |

span 종류와 속성:

| span `name` | 언제 | 주요 속성 |
| --- | --- | --- |
| `invoke_agent ocr-harness` (루트) | 실행 1회 | `gen_ai.agent.name`, `gen_ai.agent.version`, `ocr.item.id`, `ocr.condition.id`, `ocr.manifest.digest`, `ocr.dataset.version`, `ocr.repeat`, `platform.idempotency_key`, `ocr.outcome`(ok / refused / empty / error) |
| `ocr` | OCR 실행 또는 캐시 읽기 | `ocr.engine.name`, `ocr.engine.version`, `ocr.output.digest`, `ocr.output.ref`, `ocr.cache.hit` |
| `retrieval {data_source}` | 검색 | `gen_ai.operation.name`=`retrieval`, `gen_ai.data_source.id`, `gen_ai.retrieval.top_k`, `gen_ai.retrieval.documents`(id, score, 여기에 rank·selected 추가), `ocr.retrieval.query.digest`, `ocr.retrieval.query.ref` |
| `context` | 컨텍스트 구성 | `ocr.context.template.digest`, `ocr.context.order`(문서 id 순서), `ocr.context.tokens.*`(지시문, OCR, 문서, 이력, 이미지) |
| `history` | 이력 선별 (M8) | `ocr.history.candidates`, `ocr.history.excluded`(턴 id와 사유) |
| `chat {model}` | 모델 호출 | `gen_ai.operation.name`=`chat`, `gen_ai.provider.name`, `gen_ai.request.model`, `gen_ai.response.model`, `gen_ai.input.messages_ref`, `gen_ai.output.messages_ref`, `ocr.prompt.digest`, `ocr.model_call.ids` |
| `postprocess` | 후처리 | `platform.guardrail.mode`(`check_only` / `enforce`), `ocr.postprocess.kind`(`deterministic` / `requery`), `ocr.postprocess.rules`(규칙 id와 결과), `ocr.output.before.digest`, `ocr.output.after.digest` |

- 검색 질의 원문은 OTel에 `gen_ai.retrieval.query.text`가 있지만, OCR 글자가 들어가므로 원칙 3에 따라 해시와 참조만 둡니다.
- 후처리의 "검사만" 모드는 플랫폼 guardrails의 검사 모드 구분과 같은 개념입니다.
- 단계가 늘어도 span 종류만 추가하면 됩니다.

### 6.5 modelCall (비용 장부)

모델 호출 1회가 1줄입니다. 재시도와 보조 모델 호출도 각각 1줄입니다.

| 키 | 필수 | 형식 | 근거 |
| --- | --- | --- | --- |
| `modelCallId` | ● | 플랫폼 id 패턴 | |
| `traceId`, `spanId` | ● | | 어느 `chat` span의 호출인지 |
| `itemId`, `conditionId`, `at` | ● | | v1에 없어 항목·시간별 비용을 바로 볼 수 없었음 |
| `attempt` | ● | 0 이상 | 재시도 비용 |
| `modelRole` | ● | `main` / `auxiliary` | 선행 연구: 호출마다 보조 Haiku 사용 |
| `authRoute` | ● | `subscription_oauth` / `api_key` / `fake` | CLAUDE.md 실행 환경 |
| `provider` | ● | `external` / `self-hosted` | 플랫폼 `model-result.provider` |
| `routeDecisionId` | ● | 플랫폼 id 패턴 | 플랫폼 `model-result.routeDecisionId`. 모델 경로 한 곳을 지났다는 기록 |
| `usage.inputTokens`, `usage.outputTokens` | ● | 0 이상 정수 | 플랫폼 `model-result.usage` 그대로 |
| `attributes` | ● | `gen_ai.request.model`, `gen_ai.response.model`, `gen_ai.usage.cache_read.input_tokens`, `gen_ai.usage.cache_write.input_tokens`, `gen_ai.usage.image.input_tokens`○, `ocr.usage.hidden_context_tokens`(SDK 입력 합계 − 하네스가 센 합계) | OTel. v1의 `cache_creation`은 규약에 없는 이름이라 `cache_write`로 고침 |
| `cost` | ● | `sdkReportedUsd`, `computedUsd`, `priceTableVersion` | 선행 연구 `total_cost_usd_reported`. 구독에서는 청구액이 아닌 환산값 |
| `errorCode` | ● | 플랫폼 `problem.code` 또는 `null` | |
| `durationMs` | ● | | |

### 6.6 rawPayload

원문 저장 기록입니다. **저장소에 올리지 않고** 사용자 PC의 `E:\ocr-harness-data`에만 둡니다.

| 키 | 필수 | 형식 |
| --- | --- | --- |
| `digest` | ● | `sha256:…` (내용 주소) |
| `kind` | ● | `ocr_output` / `retrieval_query` / `input_messages` / `output_messages` / `postprocess_output` |
| `content` | ● | 원문 |
| `traceId`, `spanId` | ● | |
| `retention` | ● | 보존 기한 또는 `study` |

### 6.7 fieldScore

채점 1건입니다.

| 키 | 필수 | 형식 | 근거 |
| --- | --- | --- | --- |
| `scoreId` | ● | 플랫폼 id 패턴 | |
| `traceId`, `itemId`, `productId` | ● | | productId는 제품 단위 CI·검정용 |
| `target` | ● | `{kind: field, fieldId}` / `{kind: query, queryId}` / `{kind: item}` | v1은 필드만 가능했음 |
| `queryType` | ○ | A / B / C | |
| `ocrMisread` | ○ | 불리언 | 주 지표의 분모 표시 |
| `metric` | ● | 문자열 | 플랫폼 `metric`, OTel `gen_ai.evaluation.name` |
| `score` | ● | 숫자 | 플랫폼 `score`, OTel `gen_ai.evaluation.score.value`. v1의 `value`를 고침 |
| `stage` | ● | `before_postprocess` / `after_postprocess` | 설계 v3 |
| `datasetVersion`, `agentVersion`, `manifestDigest`, `scorerVersion` | ● | semver, semver, 해시, semver | 플랫폼 evaluation과 같은 이름 |

### 6.8 evaluation

플랫폼 `evaluation.schema.json`을 **그대로** 씁니다. 추가 필드가 없습니다. 조건 × 지표의 집계 한 줄이고, EDD 관문의 판정 기록입니다.

| 키 | 이 연구에서 채우는 값 |
| --- | --- |
| `evaluationId` | 실행 묶음·조건·지표로 만든 id |
| `datasetVersion` | 평가셋 버전 |
| `agentVersion`, `manifestDigest` | conditionManifest의 버전과 해시 |
| `policyVersion` | `0.0.0` 고정 (원칙 6) |
| `metric`, `score` | 지표 이름, 집계 점수 |
| `threshold`, `passed` | 관문 기준과 통과 여부 |
| `traceId` | 집계 작업의 trace |

신뢰구간, 표본 수, p값은 이 계약에 자리가 없습니다. 별도 통계 리포트에 두고 `evaluationId`로 연결합니다. 플랫폼 계약에 통계 필드를 더하는 것은 플랫폼 쪽 ADR 대상이라 여기서 정하지 않습니다.

## 7. 플랫폼에 넣는 경로

| 이 저장소 | 플랫폼 | 필요한 작업 |
| --- | --- | --- |
| evaluation | Evaluation (`evaluation.schema.json`) | 없음. 그대로 등록 |
| knowledgeDocument | Knowledge (`retrieval.schema.json`) | tenantId, allowedPrincipals를 실제 값으로 |
| span | Observability (OTel exporter) | JSONL → OTLP 변환. 이름은 이미 규약 |
| modelCall | Agent Gateway 모델 경로의 비용 귀속 | `usage`, `routeDecisionId`가 이미 같은 이름 |
| conditionManifest | Agent Manifest + Tuning | identity·governance·deployment를 채워 변환 |
| postprocess의 검사 모드 | Guardrails 집행 지점 ① | 규칙을 검사 서비스 adapter로 |
| history span | Memory (단기) | Memory 규칙 적용 (비신뢰 데이터 취급) |
| rawPayload | 평가 목적 원문 기록 (TBD-12) | 승인·보존 정책 확정 후 |
| errorCode | `problem.code` | 없음 |

가져오지 않는 것은 그대로입니다: Identity, Credential Broker, 사람 승인, 테넌트 구분.

## 8. v1에서 바꾸는 것 요약

1. 키 이름을 camelCase로, id·버전·해시·traceId를 플랫폼 형식으로.
2. trace 한 덩어리를 OTel span 여러 줄로.
3. 원문을 추적 기록에서 빼고 rawPayload로.
4. 조건을 conditionManifest로 선언하고 해시로 묶음.
5. 채점을 fieldScore(건별)와 evaluation(집계, 플랫폼 계약)으로 나눔.
6. knowledgeDocument 추가 (플랫폼 계약).
7. 오류 코드를 플랫폼 10종으로.
8. `cache_creation` → `cache_write`, `value` → `score`.
9. 모든 기록에 `schemaVersion`, 스냅샷 동결 테스트.
10. item에 질의와 데이터 분류 추가.

## 9. 사용자가 정할 것

| 결정 | 권고 | 이유 |
| --- | --- | --- |
| 봉투는 camelCase, 측정값은 `attributes` 안의 OTel 이름으로 나누는 방식 | 채택 | 플랫폼 계약과 OTel 규약을 둘 다 만족하는 유일한 방법. v1의 "필드 이름을 OTel에 맞춘다"는 CLAUDE.md 문구는 고쳐야 함 |
| 버전을 semver로 (`eval-v1` → `1.0.0`) | 채택 | 플랫폼 evaluation 계약의 필수 형식 |
| trace를 span 여러 줄로 | 채택 | 플랫폼 observability가 요구(MUST). 대시보드에서는 traceId로 묶어 읽음 |
| 플랫폼 계약 버전 고정 | 0.2.0 | 현재 released 최신 |
| 통계 값(CI, p값)의 자리 | 별도 리포트 | 플랫폼 계약 변경은 플랫폼 ADR 대상 |
