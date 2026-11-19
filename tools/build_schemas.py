"""스키마 JSON 파일을 만드는 스크립트. 스키마의 원본은 이 파일입니다.

추적(traces-data)과 평가 이벤트(logs-data) 스키마는 속성 이름마다 값의 종류를 정하느라
JSON이 길어서 손으로 고치기 어렵습니다. 그래서 여기서 표로 정의하고 JSON으로 풀어 씁니다.

    python tools/build_schemas.py            # 스키마 파일을 다시 씁니다
    python tools/build_schemas.py --release  # released/<버전>.json 스냅샷도 씁니다 (새 버전을 낼 때만)

테스트(tests/test_build_schemas.py)가 이 스크립트의 결과와 저장소의 JSON 파일이 같은지 검사합니다.
스키마를 바꾸는 절차는 docs/schema-design.md 10절을 보세요.
"""
import json
import pathlib
import sys

OUT = pathlib.Path(__file__).resolve().parent.parent / "src" / "ocr_harness" / "schemas"
# 버전과 규약 커밋은 패키지(schema.py)에 한 번만 적고 여기서 가져다 씁니다.
sys.path.insert(0, str(OUT.parent.parent))
from ocr_harness.schema import SCHEMA_VERSION, SEMCONV_COMMIT, bundle  # noqa: E402

# 여러 스키마에서 같이 쓰는 값 목록. 한 곳에서만 정의해 서로 어긋나지 않게 합니다.
AUTH_ROUTES = ["subscription_oauth", "api_key", "fake"]
QUERY_TYPES = ["A", "B", "C"]
BASE = f"https://github.com/dahun428-fx/ocr_test_repo/schemas/{SCHEMA_VERSION}/"
OTEL = f"https://raw.githubusercontent.com/open-telemetry/semantic-conventions-genai/{SEMCONV_COMMIT}/model/gen-ai/"
ID_P, SEMVER_P, DIGEST_P = "^[a-z][a-z0-9.-]{1,63}$", "^[0-9]+\\.[0-9]+\\.[0-9]+$", "^sha256:[a-f0-9]{64}$"
TRACE_P, SPAN_P = "^(?!0{32})[a-f0-9]{32}$", "^(?!0{16})[a-f0-9]{16}$"
REF_P, NANO_P = "^raw://sha256:[a-f0-9]{64}$", "^[0-9]+$"
CODES = ["UNAUTHENTICATED", "FORBIDDEN", "VALIDATION_ERROR", "NOT_FOUND", "CONFLICT", "NOT_IMPLEMENTED",
         "UPSTREAM_UNAVAILABLE", "UPSTREAM_TIMEOUT", "UPSTREAM_ERROR", "RATE_LIMITED"]

def d(schema, text): return {**schema, "description": text}
def pid(text): return d({"type": "string", "pattern": ID_P}, text)
def semver(text): return d({"type": "string", "pattern": SEMVER_P}, text)
def digest(text): return d({"type": "string", "pattern": DIGEST_P}, text)
def obj(props, optional=(), **extra):
    return {"type": "object", "properties": props, "required": [k for k in props if k not in optional],
            "additionalProperties": False, **extra}
def record(file, kind, text, props, optional=(), **extra):
    head = {"schemaVersion": d({"const": SCHEMA_VERSION}, "이 기록이 따르는 스키마 묶음의 버전."),
            "recordType": d({"const": kind}, "기록 종류. JSONL 한 파일에 여러 종류가 섞여도 구분할 수 있게 합니다.")}
    return {"$schema": "https://json-schema.org/draft/2020-12/schema", "$id": BASE + file, "title": kind,
            "description": text, **obj({**head, **props}, optional, **extra)}

QTYPE = {"enum": QUERY_TYPES}
QTEXT = "질의 유형. A: 포장에만 있는 값, B: 공개 근거로 교정할 수 있는 값, C: 둘 다 필요한 값. (이 연구의 자체 정의)"
EVID = pid("근거가 되는 knowledgeDocument의 documentId. 채점과 분석에만 쓰고 모델 입력에는 넣지 않습니다.")
schemas = {}
schemas["item.schema.json"] = record("item.schema.json", "item",
    "평가 항목 1건(이미지 1장). 항목 1건의 형식에는 공통 표준이 없어 자체 정의입니다. 형식 규칙(id, semver, 해시)은 플랫폼 계약 0.2.0을 따릅니다. 정의하지 않은 키는 거부하므로 촬영자 개인정보가 들어올 수 없습니다.", {
    "itemId": pid("항목 id. `img-` + 이미지 해시 앞 32자 (ocr_harness.ids.item_id)."),
    "imageDigest": digest("이미지 파일 내용의 SHA-256."),
    "datasetVersion": semver("이 항목이 속한 평가셋 버전 (SemVer). 동결한 버전은 바꾸지 않습니다."),
    "sourceFormat": pid("원본 라벨 형식의 이름. 형식마다 수집 어댑터를 따로 둡니다."),
    "domain": pid("데이터 영역 (예: medicine-packaging)."),
    "productId": pid("제품 id. 분할과 통계(신뢰구간, 검정)의 군집 단위입니다."),
    "split": d({"enum": ["dev", "test"]}, "개발용 또는 평가용. 같은 제품은 한쪽에만 들어갑니다."),
    "image": d(obj({"width": d({"type": "integer", "minimum": 1}, "가로 픽셀."),
                    "height": d({"type": "integer", "minimum": 1}, "세로 픽셀.")}), "이미지 크기. 그 밖의 촬영 정보는 받지 않습니다."),
    "classification": d({"enum": ["public", "internal", "confidential", "restricted"]}, "데이터 분류 (플랫폼 계약의 분류 4종). 이용약관 확인 결과를 여기에 적습니다."),
    "fields": d({"type": "array", "items": obj({
        "fieldId": pid("필드 이름 (예: product-name, expiry)."), "queryType": d(QTYPE, QTEXT),
        "gold": d({"type": "string"}, "정답 값. 항상 포장에 인쇄된 글자입니다."), "evidenceDocumentId": EVID},
        optional=("evidenceDocumentId",))}, "필드 추출 과제의 정답 목록."),
    "queries": d({"type": "array", "items": obj({
        "queryId": pid("질의 id."), "queryType": d(QTYPE, QTEXT),
        "question": d({"type": "string", "minLength": 1}, "질문."), "answer": d({"type": "string"}, "정답."),
        "evidenceDocumentId": EVID}, optional=("evidenceDocumentId",))}, "질의응답 과제의 질문과 정답 목록."),
    "tags": d({"type": "array", "items": {"type": "string", "pattern": ID_P}}, "분석용 표시 (예: 촬영 조건)."),
}, optional=("queries", "tags"))

component = lambda text: d({"oneOf": [{"type": "null"}, obj({"id": pid("구현 id."), "version": semver("구현 버전.")})]}, text + " 쓰지 않으면 null (키는 생략할 수 없습니다).")
schemas["condition-manifest.schema.json"] = record("condition-manifest.schema.json", "conditionManifest",
    "실험 조건 하나의 불변 선언. 실험 설정에는 공통 표준이 없어 구조는 자체 정의입니다. 이 기록을 RFC 8785로 정규화한 JSON의 SHA-256이 manifestDigest입니다 (ocr_harness.ids.manifest_digest).", {
    "conditionId": pid("조건 id (c0~c4, ck 등). 닫힌 목록이 아닙니다."),
    "version": semver("조건 선언의 버전. 플랫폼 evaluation 계약의 agentVersion에 들어갑니다."),
    "model": d(obj({"requestModel": d({"type": "string", "minLength": 1}, "요청할 모델 id (OTel gen_ai.request.model과 같은 값)."),
                    "authRoute": d({"enum": AUTH_ROUTES}, "인증 경로. 구독, API 키, 가짜 모델의 결과를 섞지 않기 위해 적습니다.")}), "모델 설정."),
    "components": d(obj({"ocr": component("OCR 엔진."), "retrieval": component("검색."), "context": component("컨텍스트 구성."),
                         "history": component("이력 선별."), "postprocess": component("출력 후처리.")}), "하네스 단계별 구현."),
    "promptTemplateDigest": digest("프롬프트 틀의 SHA-256."),
    "knowledgeIndexVersion": semver("검색 색인의 버전. 검색을 쓰지 않으면 생략합니다."),
    "sdk": d(obj({"name": d({"type": "string", "minLength": 1}, "SDK 이름."), "version": semver("SDK 버전."), "cliVersion": semver("CLI 버전.")}), "모델 호출에 쓰는 SDK. 버전에 따라 숨은 컨텍스트가 달라져 고정합니다."),
    "policyVersion": semver("플랫폼 evaluation 계약의 필수 값. 이 연구에서는 0.0.0으로 고정합니다."),
    "platformContractVersion": d({"const": "0.2.0"}, "가져온 플랫폼 계약의 버전."),
    "semconvCommit": d({"type": "string", "pattern": "^[a-f0-9]{7,40}$"}, "속성 이름의 근거로 삼은 OTel GenAI 시맨틱 규약의 커밋."),
}, optional=("knowledgeIndexVersion",))

# OTLP AnyValue 조각 -------------------------------------------------------
def S(text, **rule): return d(obj({"stringValue": {"type": "string", **rule}}), text)
def I(text, negative=False):
    return d(obj({"intValue": {"oneOf": [{"type": "string", "pattern": "^-?[0-9]+$" if negative else "^[0-9]+$"},
                                         {"type": "integer", **({} if negative else {"minimum": 0})}]}}), text)
def B(text): return d(obj({"boolValue": {"type": "boolean"}}), text)
def F(text, **rule): return d(obj({"doubleValue": {"type": "number", **rule}}), text)
def SA(text, **rule): return d(obj({"arrayValue": obj({"values": {"type": "array", "items": obj({"stringValue": {"type": "string", **rule}})}})}), text)
def KA(text, spec, required):
    return d(obj({"arrayValue": obj({"values": {"type": "array", "items": obj({"kvlistValue": obj({"values": key_values(spec, required)})})}})}), text)

def has(key): return {"contains": {"type": "object", "properties": {"key": {"const": key}}, "required": ["key"]}}
def key_values(spec, required=()):
    """OTLP 속성 배열([{key, value}]). 이름은 spec에 있는 것만, 값의 종류는 이름마다 정해져 있습니다."""
    out = {"type": "array", "items": {
        "type": "object", "properties": {"key": {"enum": list(spec)}, "value": {"type": "object"}},
        "required": ["key", "value"], "additionalProperties": False,
        "allOf": [{"if": {"properties": {"key": {"const": k}}, "required": ["key"]}, "then": {"properties": {"value": v}}} for k, v in spec.items()]}}
    if required:
        out["allOf"] = [has(k) for k in required]
    return out

idp, sv, dg = {"pattern": ID_P}, {"pattern": SEMVER_P}, {"pattern": DIGEST_P}
RESOURCE = {
    "service.name": S("서비스 이름 (OTel resource 규약). 항상 ocr-harness.", const="ocr-harness"),
    "service.version": S("이 저장소 패키지의 버전 (OTel resource 규약).", **sv),
    "ocr.run.id": S("실행 묶음 id.", **idp),
    "ocr.schema.version": S("이 파일이 따르는 스키마 묶음의 버전.", const=SCHEMA_VERSION),
}
resource = d(obj({"attributes": key_values(RESOURCE, list(RESOURCE))}), "이 줄의 기록을 만든 주체 (OTLP Resource).")
scope = d(obj({"name": {"type": "string"}, "version": {"type": "string"}}, optional=("name", "version")), "기록을 만든 코드 (OTLP InstrumentationScope).")
nano = lambda text: d({"type": "string", "pattern": NANO_P}, text + " 유닉스 나노초를 문자열로 적습니다 (OTLP JSON 규칙).")

DOC = {"id": S("문서 id (knowledgeDocument.documentId).", **idp), "score": F("검색 점수."),
       "rank": I("순위 (1부터)."), "selected": B("컨텍스트에 실제로 넣었는지.")}
SPAN_ATTRS = {
    "error.type": S("오류 분류 (OTel error.type). 값은 플랫폼 계약의 problem.code 10종.", enum=CODES),
    "gen_ai.operation.name": S("작업 종류 (OTel).", enum=["invoke_agent", "retrieval", "chat"]),
    "gen_ai.agent.name": S("에이전트 이름 (OTel)."), "gen_ai.agent.version": S("조건 선언의 버전 (OTel).", **sv),
    "gen_ai.provider.name": S("모델 제공자 (OTel)."),
    "gen_ai.request.model": S("요청한 모델 id (OTel).", minLength=1),
    "gen_ai.response.model": S("실제로 응답한 모델 id (OTel)."),
    "gen_ai.response.finish_reasons": SA("종료 사유 (OTel)."),
    "gen_ai.usage.input_tokens": I("입력 토큰 수 (OTel)."), "gen_ai.usage.output_tokens": I("출력 토큰 수 (OTel)."),
    "gen_ai.usage.cache_read.input_tokens": I("캐시에서 읽은 입력 토큰 수 (OTel)."),
    "gen_ai.usage.cache_write.input_tokens": I("캐시에 쓴 입력 토큰 수 (OTel)."),
    "gen_ai.usage.reasoning.output_tokens": I("추론에 쓴 출력 토큰 수 (OTel)."),
    "gen_ai.input.messages_ref": S("입력 메시지 원문의 참조 (OTel). 원문은 rawPayload에 둡니다.", pattern=REF_P),
    "gen_ai.output.messages_ref": S("출력 메시지 원문의 참조 (OTel).", pattern=REF_P),
    "gen_ai.system_instructions_ref": S("시스템 지시문 원문의 참조 (OTel).", pattern=REF_P),
    "gen_ai.data_source.id": S("검색 대상 자료원 id (OTel).", **idp),
    "gen_ai.retrieval.top_k": I("요청한 검색 결과 수 (OTel)."),
    "gen_ai.retrieval.documents": KA("검색된 문서 목록 (OTel). id와 score는 규약, rank와 selected는 자체 추가.", DOC, ["id", "score"]),
    "platform.idempotency_key": S("같은 실행을 두 번 기록하지 않기 위한 키 (플랫폼 개념).", **idp),
    "platform.guardrail.mode": S("후처리를 검사만 할지 적용까지 할지 (플랫폼 guardrails의 구분).", enum=["check_only", "enforce"]),
    "platform.model.provider": S("모델 위치 (플랫폼 model-result.provider).", enum=["external", "self-hosted"]),
    "platform.route_decision.id": S("모델 경로 결정 id (플랫폼 model-result.routeDecisionId). 모든 호출이 모델 경로 한 곳을 지났다는 기록.", **idp),
    "ocr.item.id": S("항목 id.", **idp), "ocr.condition.id": S("조건 id.", **idp),
    "ocr.manifest.digest": S("조건 선언의 해시.", **dg), "ocr.dataset.version": S("평가셋 버전.", **sv),
    "ocr.repeat": I("반복 번호 (0부터)."),
    "ocr.outcome": S("실행 결과. 거절과 빈 출력도 숨기지 않고 적습니다.", enum=["ok", "refused", "empty", "error"]),
    "ocr.engine.name": S("OCR 엔진 이름.", minLength=1), "ocr.engine.version": S("OCR 엔진 버전.", minLength=1),
    "ocr.output.digest": S("OCR 출력의 해시.", **dg), "ocr.output.ref": S("OCR 출력 원문의 참조.", pattern=REF_P),
    "ocr.cache.hit": B("OCR 캐시에서 읽었는지."),
    "ocr.retrieval.query.digest": S("검색 질의의 해시. 질의에는 OCR 글자가 들어가므로 원문은 적지 않습니다.", **dg),
    "ocr.retrieval.query.ref": S("검색 질의 원문의 참조.", pattern=REF_P),
    "ocr.context.template.digest": S("컨텍스트 틀의 해시.", **dg),
    "ocr.context.order": SA("컨텍스트에 넣은 순서 (구획 이름 또는 문서 id).", **idp),
    **{f"ocr.context.tokens.{k}": I(f"컨텍스트 중 {t} 부분의 토큰 수.") for k, t in
       [("instruction", "지시문"), ("ocr", "OCR 글자"), ("documents", "검색 문서"), ("history", "이력"), ("image", "이미지")]},
    "ocr.history.candidates": SA("이력 후보 턴 id.", **idp),
    "ocr.history.excluded": KA("제외한 턴과 사유.", {"id": S("턴 id.", **idp), "reason": S("제외 사유.", **idp)}, ["id", "reason"]),
    "ocr.prompt.digest": S("모델에 보낸 최종 프롬프트의 해시.", **dg),
    "ocr.model.role": S("주 모델인지, SDK가 따로 부른 보조 모델인지.", enum=["main", "auxiliary"]),
    "ocr.model.auth_route": S("인증 경로.", enum=AUTH_ROUTES),
    "ocr.model.attempt": I("재시도 번호 (0부터). 재시도마다 span을 따로 남깁니다."),
    "ocr.usage.hidden_context_tokens": I("SDK가 보고한 입력 합계에서 하네스가 센 합계를 뺀 값 (SDK가 붙인 숨은 컨텍스트).", negative=True),
    "ocr.cost.sdk_reported_usd": F("SDK가 보고한 비용(USD). 구독에서는 청구액이 아닌 환산값. 모르면 속성을 뺍니다.", minimum=0),
    "ocr.cost.computed_usd": F("가격표로 직접 계산한 비용(USD). 모르면 속성을 뺍니다.", minimum=0),
    "ocr.cost.price_table.version": S("계산에 쓴 가격표의 버전.", minLength=1),
    "ocr.cost.basis": S("비용 산정 기준 (SDK가 보고한 값)."),
    "ocr.sdk.num_turns": I("SDK가 보고한 턴 수."), "ocr.sdk.duration_api_ms": I("SDK가 보고한 API 소요 시간(ms)."),
    "ocr.postprocess.kind": S("후처리 종류.", enum=["deterministic", "requery"]),
    "ocr.postprocess.rules": KA("적용한 규칙과 결과.", {"id": S("규칙 id.", **idp), "result": S("결과.", enum=["unchanged", "changed", "flagged"])}, ["id", "result"]),
    "ocr.output.before.digest": S("후처리 전 출력의 해시.", **dg), "ocr.output.after.digest": S("후처리 후 출력의 해시.", **dg),
}
REQUIRED = {
    "invoke_agent": ["gen_ai.operation.name", "gen_ai.agent.name", "gen_ai.agent.version", "ocr.item.id", "ocr.condition.id",
                     "ocr.manifest.digest", "ocr.dataset.version", "ocr.repeat", "platform.idempotency_key", "ocr.outcome"],
    "ocr": ["ocr.engine.name", "ocr.engine.version", "ocr.output.digest", "ocr.cache.hit"],
    "retrieval": ["gen_ai.operation.name", "gen_ai.data_source.id", "gen_ai.retrieval.top_k", "gen_ai.retrieval.documents",
                  "ocr.retrieval.query.digest"],
    "context": ["ocr.context.template.digest", "ocr.context.order"] + [f"ocr.context.tokens.{k}" for k in ("instruction", "ocr", "documents", "history", "image")],
    "history": ["ocr.history.candidates", "ocr.history.excluded"],
    "chat": ["gen_ai.operation.name", "gen_ai.provider.name", "gen_ai.request.model", "gen_ai.usage.input_tokens",
             "gen_ai.usage.output_tokens", "gen_ai.usage.cache_read.input_tokens", "gen_ai.usage.cache_write.input_tokens",
             "ocr.prompt.digest", "ocr.model.role", "ocr.model.auth_route", "ocr.model.attempt", "platform.model.provider",
             "platform.route_decision.id", "ocr.usage.hidden_context_tokens", "ocr.cost.price_table.version"],
    "postprocess": ["platform.guardrail.mode", "ocr.postprocess.kind", "ocr.postprocess.rules",
                    "ocr.output.before.digest", "ocr.output.after.digest"],
}
rules = [{"if": {"properties": {"name": {"pattern": f"^{kind}( |$)"}}, "required": ["name"]},
          "then": {"properties": {"attributes": {"allOf": [has(k) for k in keys]}}}} for kind, keys in REQUIRED.items()]
rules.append({"if": {"properties": {"status": {"properties": {"code": {"const": 2}}, "required": ["code"]}}, "required": ["status"]},
              "then": {"properties": {"attributes": has("error.type")}}})
OPT_SPAN = ("parentSpanId", "traceState", "flags", "droppedAttributesCount", "events", "droppedEventsCount", "links", "droppedLinksCount")
span = obj({
    "traceId": d({"type": "string", "pattern": TRACE_P}, "추적 id. 16진수 32자리, 전부 0은 무효 (W3C Trace Context). 실행 1회(항목 × 조건 × 반복)가 추적 하나입니다."),
    "spanId": d({"type": "string", "pattern": SPAN_P}, "span id. 16진수 16자리."),
    "parentSpanId": d({"type": "string", "pattern": SPAN_P}, "부모 span id. 루트 span에는 없습니다."),
    "name": d({"type": "string", "pattern": "^(invoke_agent|ocr|retrieval|context|history|chat|postprocess)( [^ ]+)?$"},
              "span 이름. `{작업} {대상}` 꼴 (OTel GenAI 규약). invoke_agent, retrieval, chat은 규약의 작업 이름이고 ocr, context, history, postprocess는 자체 정의입니다."),
    "kind": d({"enum": [1, 2, 3, 4, 5]}, "span 종류. OTLP JSON에서는 정수로만 적습니다 (1 INTERNAL, 3 CLIENT)."),
    "startTimeUnixNano": nano("시작 시각."), "endTimeUnixNano": nano("끝 시각."),
    "attributes": d(key_values(SPAN_ATTRS), "속성. 이름은 목록에 있는 것만 받습니다. 원문이 들어가는 이름(gen_ai.input.messages 등)과 규약에 없는 이름은 목록에 없어 거부됩니다."),
    "status": d(obj({"code": {"enum": [0, 1, 2]}, "message": {"type": "string"}}, optional=("message",)), "상태 (0 UNSET, 1 OK, 2 ERROR). ERROR이면 error.type 속성이 있어야 합니다."),
    "traceState": {"type": "string"}, "flags": {"type": "integer"}, "droppedAttributesCount": {"type": "integer"},
    "events": {"type": "array"}, "droppedEventsCount": {"type": "integer"}, "links": {"type": "array"}, "droppedLinksCount": {"type": "integer"},
}, optional=OPT_SPAN, allOf=rules)
schemas["traces-data.schema.json"] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema", "$id": BASE + "traces-data.schema.json", "title": "tracesData",
    "description": "추적 파일의 한 줄. OTLP File Exporter 형식(JSON Lines, 한 줄이 TracesData)이고 OTLP JSON 인코딩을 따릅니다. 단계 1개가 span 1개, 모델 호출 1회가 chat span 1개입니다. 토큰과 비용은 chat span에만 적고 비용 장부는 거기서 뽑습니다. 원문은 넣지 않고 해시와 참조만 둡니다.",
    **obj({"resourceSpans": {"type": "array", "minItems": 1, "items": obj({
        "resource": resource,
        "scopeSpans": {"type": "array", "minItems": 1, "items": obj({"scope": scope, "spans": {"type": "array", "items": span}, "schemaUrl": {"type": "string"}}, optional=("scope", "schemaUrl"))},
        "schemaUrl": {"type": "string"}}, optional=("schemaUrl",))}})}

EVENT_ATTRS = {
    "gen_ai.evaluation.name": S("지표 이름 (OTel).", minLength=1),
    "gen_ai.evaluation.score.value": F("점수 (OTel)."),
    "gen_ai.evaluation.score.label": S("점수의 뜻을 읽기 쉽게 적은 표시 (OTel). 예: correct, incorrect."),
    "error.type": S("채점 자체가 실패했을 때의 오류 분류 (OTel).", enum=CODES),
    "ocr.score.id": S("채점 기록 id.", **idp), "ocr.item.id": S("항목 id.", **idp),
    "ocr.product.id": S("제품 id. 제품 단위 신뢰구간과 검정에 씁니다.", **idp),
    "ocr.condition.id": S("조건 id.", **idp), "ocr.condition.version": S("조건 선언의 버전 (플랫폼 agentVersion).", **sv),
    "ocr.manifest.digest": S("조건 선언의 해시 (플랫폼 manifestDigest).", **dg),
    "ocr.dataset.version": S("평가셋 버전 (플랫폼 datasetVersion).", **sv), "ocr.scorer.version": S("채점기 버전.", **sv),
    "ocr.target.kind": S("채점 대상의 종류: 필드, 질의, 이미지 전체.", enum=["field", "query", "item"]),
    "ocr.target.id": S("대상 필드 id 또는 질의 id. 이미지 전체 채점에는 없습니다.", **idp),
    "ocr.query.type": S(QTEXT, enum=QUERY_TYPES),
    "ocr.ocr_misread": B("OCR이 이 필드를 잘못 읽었는지. 주 지표의 분모 표시입니다."),
    "ocr.score.stage": S("후처리 전 출력을 채점했는지, 후 출력을 채점했는지.", enum=["before_postprocess", "after_postprocess"]),
}
EVENT_REQ = ["gen_ai.evaluation.name", "gen_ai.evaluation.score.value", "ocr.score.id", "ocr.item.id", "ocr.product.id",
             "ocr.condition.id", "ocr.condition.version", "ocr.manifest.digest", "ocr.dataset.version", "ocr.scorer.version",
             "ocr.target.kind", "ocr.score.stage"]
named = lambda values: {"contains": {"type": "object", "properties": {"key": {"const": "ocr.target.kind"}, "value": {"properties": {"stringValue": {"enum": values}}}}, "required": ["key"]}}
event_attrs = key_values(EVENT_ATTRS, EVENT_REQ)
event_attrs["allOf"] += [{"if": named(["field", "query"]), "then": has("ocr.target.id")}]
OPT_EVENT = ("observedTimeUnixNano", "severityNumber", "severityText", "body", "droppedAttributesCount", "flags")
event = obj({
    "timeUnixNano": nano("채점한 시각."), "eventName": d({"const": "gen_ai.evaluation.result"}, "이벤트 이름. OTel GenAI 규약의 평가 결과 이벤트로 고정합니다."),
    "traceId": d({"type": "string", "pattern": TRACE_P}, "채점한 실행의 추적 id."),
    "spanId": d({"type": "string", "pattern": SPAN_P}, "채점한 출력을 만든 span의 id (규약: 평가 대상 span에 붙입니다)."),
    "attributes": d(event_attrs, "속성. 자유 글(gen_ai.evaluation.explanation)은 정답이나 원문이 섞일 수 있어 받지 않습니다."),
    "observedTimeUnixNano": {"type": "string", "pattern": NANO_P}, "severityNumber": {"type": "integer"}, "severityText": {"type": "string"},
    "body": {"type": "object"}, "droppedAttributesCount": {"type": "integer"}, "flags": {"type": "integer"},
}, optional=OPT_EVENT)
schemas["logs-data.schema.json"] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema", "$id": BASE + "logs-data.schema.json", "title": "logsData",
    "description": "평가 이벤트 파일의 한 줄. OTLP File Exporter 형식(한 줄이 LogsData)입니다. 채점 1건이 OTel GenAI 규약의 gen_ai.evaluation.result 이벤트 1개입니다. 조건 × 지표의 집계는 플랫폼 evaluation 기록에 따로 적습니다.",
    **obj({"resourceLogs": {"type": "array", "minItems": 1, "items": obj({
        "resource": resource,
        "scopeLogs": {"type": "array", "minItems": 1, "items": obj({"scope": scope, "logRecords": {"type": "array", "items": event}, "schemaUrl": {"type": "string"}}, optional=("scope", "schemaUrl"))},
        "schemaUrl": {"type": "string"}}, optional=("schemaUrl",))}})}

kind_is = lambda k: {"properties": {"kind": {"const": k}}, "required": ["kind"]}
schemas["raw-payload.schema.json"] = record("raw-payload.schema.json", "rawPayload",
    "원문 저장 기록. 추적에는 원문을 넣지 않으므로 여기에 두고 해시로 참조합니다. 저장소에 올리지 않고 사용자 PC에만 둡니다.", {
    "runId": pid("실행 묶음 id."),
    "traceId": d({"type": "string", "pattern": TRACE_P}, "이 원문이 나온 실행의 추적 id."),
    "spanId": d({"type": "string", "pattern": SPAN_P}, "이 원문이 나온 span의 id."),
    "digest": digest("content의 SHA-256 (ocr_harness.ids.content_digest). span은 `raw://` + 이 값으로 참조합니다."),
    "kind": d({"enum": ["ocr_output", "retrieval_query", "input_messages", "output_messages", "postprocess_output"]}, "원문의 종류."),
    "content": d({}, "원문. input_messages와 output_messages는 OTel GenAI 규약의 메시지 JSON 스키마 구조(role, parts)를 따르고, 나머지는 글자열입니다."),
    "retention": d({"oneOf": [{"const": "study"}, {"type": "string", "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}$"}]}, "보존 기한. 날짜(YYYY-MM-DD) 또는 연구 기간 동안(study)."),
}, allOf=[
    {"if": kind_is("input_messages"), "then": {"properties": {"content": {"$ref": OTEL + "gen-ai-input-messages.json"}}}},
    {"if": kind_is("output_messages"), "then": {"properties": {"content": {"$ref": OTEL + "gen-ai-output-messages.json"}}}},
    {"if": {"properties": {"kind": {"enum": ["ocr_output", "retrieval_query", "postprocess_output"]}}, "required": ["kind"]},
     "then": {"properties": {"content": {"type": "string"}}}},
])



def write(name: str, schema: dict) -> None:
    (OUT / name).write_text(json.dumps(schema, ensure_ascii=False, indent=2) + "\n", "utf-8")


if __name__ == "__main__":
    for file_name, built in schemas.items():
        write(file_name, built)
    if "--release" in sys.argv:
        # 패키지의 bundle()이 방금 쓴 파일을 읽어 스냅샷을 만듭니다.
        write(f"released/{SCHEMA_VERSION}.json", bundle())
