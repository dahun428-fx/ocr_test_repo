"""기록 7종 검증 테스트 (스키마 2.0.0). 정답이 알려진 합성 기록만 씁니다.

설계와 근거: docs/schema-design.md, docs/schema-standards-review.md
"""
import hashlib
import json
from importlib import resources

import pytest

from ocr_harness import otlp
from ocr_harness.schema import KINDS, SCHEMA_VERSION, SchemaError, bundle, validate

import samples

SCHEMAS = resources.files("ocr_harness") / "schemas"
# 없어도 되는 최상위 키. 나머지는 하나라도 빠지면 거부되어야 합니다.
OPTIONAL = {
    "item": {"queries", "tags"},
    "conditionManifest": {"knowledgeIndexVersion"},
}


def set_attribute(record, key, value):
    """OTLP 속성 배열에서 key의 값을 바꾸거나 새로 넣습니다."""
    record["attributes"] = [kv for kv in record["attributes"] if kv["key"] != key]
    record["attributes"].append({"key": key, "value": otlp.any_value(value)})


def drop_attribute(record, key):
    record["attributes"] = [kv for kv in record["attributes"] if kv["key"] != key]


def test_all_kinds_are_defined():
    assert set(KINDS) == set(samples.ALL)


@pytest.mark.parametrize("kind", sorted(samples.ALL))
def test_valid_record_passes(kind):
    validate(kind, samples.ALL[kind]())


@pytest.mark.parametrize("kind", sorted(samples.ALL))
def test_each_required_key_is_enforced(kind):
    record = samples.ALL[kind]()
    for key in set(record) - OPTIONAL.get(kind, set()):
        broken = {k: v for k, v in record.items() if k != key}
        with pytest.raises(SchemaError):
            validate(kind, broken)


@pytest.mark.parametrize("kind", sorted(samples.ALL))
def test_undefined_top_level_key_is_rejected(kind):
    record = samples.ALL[kind]()
    record["writer_num"] = "x"   # 원본 라벨에서 촬영자 정보를 담는 키
    with pytest.raises(SchemaError):
        validate(kind, record)


def test_unknown_kind_is_rejected():
    with pytest.raises(KeyError):
        validate("nope", {})


# 스키마 파일 자체 ----------------------------------------------------------

OWN_KINDS = ["item", "conditionManifest", "tracesData", "logsData", "rawPayload"]


@pytest.mark.parametrize("kind", OWN_KINDS)
def test_own_schema_has_id_dialect_and_korean_description(kind):
    schema = bundle()["schemas"][kind]
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["$id"].endswith(f"/schemas/{SCHEMA_VERSION}/{schema['$id'].rsplit('/', 1)[1]}")
    assert schema["description"]


@pytest.mark.parametrize("kind", ["item", "conditionManifest", "rawPayload"])
def test_every_top_level_key_is_described(kind):
    # 스키마 파일만 읽어도 각 키의 뜻을 알 수 있어야 합니다.
    for key, definition in bundle()["schemas"][kind]["properties"].items():
        assert definition.get("description"), f"{kind}.{key}에 설명이 없습니다"


# 플랫폼 형식 규칙 (id, semver, 해시) -----------------------------------------

@pytest.mark.parametrize("kind,key,bad", [
    ("item", "itemId", "sha256:" + "a" * 64),      # id 패턴
    ("item", "productId", "Prod_1"),
    ("item", "datasetVersion", "eval-v1"),          # semver
    ("item", "imageDigest", "a" * 64),              # sha256: 접두사
    ("conditionManifest", "version", "c1-v1"),
    ("rawPayload", "traceId", "tr-0001"),           # 16진수 32자리
    ("rawPayload", "spanId", "0123"),
])
def test_platform_format_rules(kind, key, bad):
    record = samples.ALL[kind]()
    record[key] = bad
    with pytest.raises(SchemaError):
        validate(kind, record)


@pytest.mark.parametrize("kind", ["item", "conditionManifest", "rawPayload"])
def test_schema_version_is_pinned(kind):
    record = samples.ALL[kind]()
    record["schemaVersion"] = "9.9.9"
    with pytest.raises(SchemaError):
        validate(kind, record)


# 가져온 파일은 고치지 않습니다 -----------------------------------------------

VENDORED = {
    "platform/0.2.0/evaluation.schema.json": "ac96592ce7e597d60a43596368c4fa563939632d4bb300f310cdb549e78eb802",
    "platform/0.2.0/retrieval.schema.json": "eab2e9096d0394f9e4a2a93297a70b6496d781f8375e6572c8aea75d1eecb527",
    "otel-genai/76e0c19e7fe1/gen-ai-input-messages.json": "a9f0788ddeaa8853106d4ac353aa09d96abd7002da74673e2b63ea16efa53cdc",
    "otel-genai/76e0c19e7fe1/gen-ai-output-messages.json": "01daaafa9d7fd06e1f532ee4f50e4b9d3b4f9b9145d195018dbd6273006bfad7",
}


@pytest.mark.parametrize("name", sorted(VENDORED))
def test_vendored_files_are_unmodified_copies(name):
    data = SCHEMAS.joinpath(name).read_bytes()
    assert hashlib.sha256(data).hexdigest() == VENDORED[name]


def test_evaluation_takes_no_extra_field_beyond_platform_contract():
    record = samples.evaluation()
    record["confidenceInterval"] = [0.5, 0.7]
    with pytest.raises(SchemaError):
        validate("evaluation", record)


def test_knowledge_document_classification_follows_platform_enum():
    record = samples.knowledge_document()
    record["classification"] = "secret"
    with pytest.raises(SchemaError):
        validate("knowledgeDocument", record)


# item --------------------------------------------------------------------

def test_item_rejects_pii_inside_image_block():
    record = samples.item()
    record["image"]["age"] = 30
    with pytest.raises(SchemaError):
        validate("item", record)


def test_item_split_must_be_dev_or_test():
    record = samples.item()
    record["split"] = "train"
    with pytest.raises(SchemaError):
        validate("item", record)


@pytest.mark.parametrize("block", ["fields", "queries"])
def test_item_query_type_must_be_a_b_or_c(block):
    record = samples.item()
    record[block][0]["queryType"] = "D"
    with pytest.raises(SchemaError):
        validate("item", record)


# conditionManifest -------------------------------------------------------

def test_manifest_component_may_be_absent_as_null_but_not_missing():
    record = samples.condition_manifest()
    record["components"]["retrieval"] = None
    validate("conditionManifest", record)
    del record["components"]["retrieval"]
    with pytest.raises(SchemaError):
        validate("conditionManifest", record)


def test_manifest_condition_id_is_not_a_closed_list():
    record = samples.condition_manifest()
    record["conditionId"] = "c7-history"
    validate("conditionManifest", record)


# tracesData: OTLP 구조 ----------------------------------------------------

@pytest.mark.parametrize("name", sorted(samples.SPAN_KINDS))
def test_every_span_kind_passes(name):
    validate("tracesData", samples.traces(name))


@pytest.mark.parametrize("key", ["traceId", "spanId", "name", "kind", "startTimeUnixNano", "endTimeUnixNano",
                                 "attributes", "status"])
def test_span_requires_the_otlp_fields(key):
    data = samples.traces()
    del samples.the_span(data)[key]
    with pytest.raises(SchemaError):
        validate("tracesData", data)


@pytest.mark.parametrize("key,bad", [
    ("traceId", "tr-0001"),
    ("traceId", "0" * 32),                # 전부 0인 id는 W3C Trace Context에서 무효입니다.
    ("spanId", "0123"),
    ("startTimeUnixNano", "2026-11-19T10:00:00+09:00"),   # RFC 3339가 아니라 유닉스 나노초
    ("kind", "SPAN_KIND_INTERNAL"),       # OTLP JSON에서 enum 이름 문자열은 금지
    ("status", "ok"),
    ("name", "something"),                # 정해진 span 종류만
])
def test_span_rejects_non_otlp_values(key, bad):
    data = samples.traces()
    samples.the_span(data)[key] = bad
    with pytest.raises(SchemaError):
        validate("tracesData", data)


def test_span_attributes_must_be_an_otlp_key_value_list():
    data = samples.traces()
    samples.the_span(data)["attributes"] = {"ocr.outcome": "ok"}   # 객체로 쓰면 OTLP가 아닙니다.
    with pytest.raises(SchemaError):
        validate("tracesData", data)


def test_span_accepts_standard_optional_otlp_fields():
    data = samples.traces()
    samples.the_span(data).update({"traceState": "", "flags": 1, "droppedAttributesCount": 0, "events": [], "links": []})
    validate("tracesData", data)


def test_integer_attribute_may_be_a_json_number_or_a_string():
    # proto3 JSON 규칙: 64비트 정수는 문자열로 쓰지만, 읽을 때는 숫자도 받아야 합니다.
    data = samples.traces()
    span = samples.the_span(data)
    drop_attribute(span, "ocr.repeat")
    span["attributes"].append({"key": "ocr.repeat", "value": {"intValue": 0}})
    validate("tracesData", data)


@pytest.mark.parametrize("key", ["service.name", "service.version", "ocr.run.id", "ocr.schema.version"])
def test_resource_requires_run_and_version_attributes(key):
    data = samples.traces()
    drop_attribute(data["resourceSpans"][0]["resource"], key)
    with pytest.raises(SchemaError):
        validate("tracesData", data)


def test_resource_schema_version_is_pinned():
    data = samples.traces()
    set_attribute(data["resourceSpans"][0]["resource"], "ocr.schema.version", "9.9.9")
    with pytest.raises(SchemaError):
        validate("tracesData", data)


# tracesData: 속성 규칙 ----------------------------------------------------

def test_error_status_requires_error_type_with_platform_code():
    data = samples.traces("ocr")
    span = samples.the_span(data)
    span["status"] = {"code": 2}
    with pytest.raises(SchemaError):
        validate("tracesData", data)
    set_attribute(span, "error.type", "SOMETHING_ELSE")
    with pytest.raises(SchemaError):
        validate("tracesData", data)
    for code in ("RATE_LIMITED", "UPSTREAM_TIMEOUT", "UPSTREAM_ERROR", "UPSTREAM_UNAVAILABLE", "VALIDATION_ERROR"):
        set_attribute(span, "error.type", code)
        validate("tracesData", data)


@pytest.mark.parametrize("raw_attribute", [
    "gen_ai.input.messages",
    "gen_ai.output.messages",
    "gen_ai.system_instructions",
    "gen_ai.retrieval.query.text",
    "ocr.output.text",
])
def test_span_rejects_raw_text_attributes(raw_attribute):
    data = samples.traces("chat fake-model")
    set_attribute(samples.the_span(data), raw_attribute, "원문")
    with pytest.raises(SchemaError):
        validate("tracesData", data)


def test_span_rejects_names_outside_the_list():
    for name in ("engine", "gen_ai.usage.cache_creation.input_tokens"):   # 뒤쪽은 OTel 규약에 없는 이름
        data = samples.traces("chat fake-model")
        set_attribute(samples.the_span(data), name, 1)
        with pytest.raises(SchemaError):
            validate("tracesData", data)


@pytest.mark.parametrize("key,bad", [
    ("gen_ai.usage.input_tokens", "많음"),       # 정수 자리에 문자열
    ("gen_ai.usage.input_tokens", -1),
    ("ocr.prompt.digest", "abc"),
    ("ocr.model.role", "other"),
    ("ocr.model.auth_route", "unknown"),
    ("platform.model.provider", "cloud"),
    ("platform.route_decision.id", "Route 1"),
    ("ocr.cost.computed_usd", "0.004"),          # 실수 자리에 문자열
])
def test_chat_attribute_values_are_typed(key, bad):
    data = samples.traces("chat fake-model")
    set_attribute(samples.the_span(data), key, bad)
    with pytest.raises(SchemaError):
        validate("tracesData", data)


REQUIRED_ATTRIBUTES = [
    ("invoke_agent ocr-harness", "ocr.item.id"),
    ("invoke_agent ocr-harness", "ocr.manifest.digest"),
    ("invoke_agent ocr-harness", "platform.idempotency_key"),
    ("invoke_agent ocr-harness", "ocr.outcome"),
    ("ocr", "ocr.output.digest"),
    ("retrieval mfds", "gen_ai.retrieval.documents"),
    ("context", "ocr.context.order"),
    ("chat fake-model", "gen_ai.request.model"),
    ("chat fake-model", "gen_ai.usage.input_tokens"),
    ("chat fake-model", "gen_ai.usage.output_tokens"),
    ("chat fake-model", "gen_ai.usage.cache_read.input_tokens"),
    ("chat fake-model", "gen_ai.usage.cache_write.input_tokens"),
    ("chat fake-model", "ocr.model.role"),
    ("chat fake-model", "ocr.model.auth_route"),
    ("chat fake-model", "platform.route_decision.id"),
    ("chat fake-model", "ocr.cost.price_table.version"),
    ("postprocess", "platform.guardrail.mode"),
    ("postprocess", "ocr.output.after.digest"),
]


@pytest.mark.parametrize("name,key", REQUIRED_ATTRIBUTES)
def test_span_kind_requires_its_attributes(name, key):
    data = samples.traces(name)
    drop_attribute(samples.the_span(data), key)
    with pytest.raises(SchemaError):
        validate("tracesData", data)


def test_chat_cost_may_be_left_out_when_unknown():
    data = samples.traces("chat fake-model")
    drop_attribute(samples.the_span(data), "ocr.cost.sdk_reported_usd")
    drop_attribute(samples.the_span(data), "ocr.cost.computed_usd")
    validate("tracesData", data)


def test_chat_accepts_sdk_reported_extras_seen_in_prior_runs():
    data = samples.traces("chat fake-model")
    for key, value in {
        "gen_ai.response.model": "fake-model-1",
        "gen_ai.response.finish_reasons": ["stop"],
        "gen_ai.usage.reasoning.output_tokens": 0,
        "ocr.sdk.num_turns": 1,
        "ocr.sdk.duration_api_ms": 800,
        "ocr.cost.basis": "api_list_price",
    }.items():
        set_attribute(samples.the_span(data), key, value)
    validate("tracesData", data)


def test_root_span_outcome_keeps_refusals_and_empty_outputs_visible():
    data = samples.traces()
    for outcome in ("ok", "refused", "empty", "error"):
        set_attribute(samples.the_span(data), "ocr.outcome", outcome)
        validate("tracesData", data)
    set_attribute(samples.the_span(data), "ocr.outcome", "skipped")
    with pytest.raises(SchemaError):
        validate("tracesData", data)


def test_postprocess_mode_is_check_only_or_enforce():
    data = samples.traces("postprocess")
    set_attribute(samples.the_span(data), "platform.guardrail.mode", "enforce")
    validate("tracesData", data)
    set_attribute(samples.the_span(data), "platform.guardrail.mode", "apply")
    with pytest.raises(SchemaError):
        validate("tracesData", data)


def test_retrieved_documents_are_structured():
    data = samples.traces("retrieval mfds")
    set_attribute(samples.the_span(data), "gen_ai.retrieval.documents", ["mfds-0001"])   # id만 있는 문자열 배열은 거부
    with pytest.raises(SchemaError):
        validate("tracesData", data)


# logsData: OTel 평가 이벤트 -------------------------------------------------

def test_event_name_must_be_the_otel_evaluation_event():
    data = samples.logs()
    samples.the_event(data)["eventName"] = "score"
    with pytest.raises(SchemaError):
        validate("logsData", data)


@pytest.mark.parametrize("key", ["timeUnixNano", "eventName", "traceId", "spanId", "attributes"])
def test_event_requires_the_otlp_fields(key):
    data = samples.logs()
    del samples.the_event(data)[key]
    with pytest.raises(SchemaError):
        validate("logsData", data)


@pytest.mark.parametrize("key", [
    "gen_ai.evaluation.name", "gen_ai.evaluation.score.value", "ocr.score.id", "ocr.item.id", "ocr.product.id",
    "ocr.condition.id", "ocr.condition.version", "ocr.manifest.digest", "ocr.dataset.version", "ocr.scorer.version",
    "ocr.target.kind", "ocr.score.stage",
])
def test_event_requires_its_attributes(key):
    data = samples.logs()
    drop_attribute(samples.the_event(data), key)
    with pytest.raises(SchemaError):
        validate("logsData", data)


@pytest.mark.parametrize("key", ["gen_ai.evaluation.score.label", "ocr.query.type", "ocr.ocr_misread"])
def test_event_optional_attributes(key):
    data = samples.logs()
    drop_attribute(samples.the_event(data), key)
    validate("logsData", data)


def test_event_targets_a_field_a_query_or_the_whole_item():
    for kind in ("field", "query"):
        data = samples.logs()
        set_attribute(samples.the_event(data), "ocr.target.kind", kind)
        validate("logsData", data)
        drop_attribute(samples.the_event(data), "ocr.target.id")      # 필드·질의는 대상 id가 있어야 합니다.
        with pytest.raises(SchemaError):
            validate("logsData", data)
    data = samples.logs()
    set_attribute(samples.the_event(data), "ocr.target.kind", "item")
    drop_attribute(samples.the_event(data), "ocr.target.id")          # 이미지 전체 채점은 대상 id가 없습니다.
    validate("logsData", data)
    set_attribute(samples.the_event(data), "ocr.target.kind", "page")
    with pytest.raises(SchemaError):
        validate("logsData", data)


def test_event_stage_separates_before_and_after_postprocess():
    data = samples.logs()
    set_attribute(samples.the_event(data), "ocr.score.stage", "before_postprocess")
    validate("logsData", data)
    set_attribute(samples.the_event(data), "ocr.score.stage", "sometime")
    with pytest.raises(SchemaError):
        validate("logsData", data)


def test_event_score_value_is_a_number_not_a_string():
    data = samples.logs()
    set_attribute(samples.the_event(data), "gen_ai.evaluation.score.value", "1.0")
    with pytest.raises(SchemaError):
        validate("logsData", data)


def test_event_rejects_free_text_explanation():
    # OTel에는 gen_ai.evaluation.explanation이 있지만, 정답이나 원문이 섞일 수 있어 받지 않습니다.
    data = samples.logs()
    set_attribute(samples.the_event(data), "gen_ai.evaluation.explanation", "정답은 합성정")
    with pytest.raises(SchemaError):
        validate("logsData", data)


# rawPayload ---------------------------------------------------------------

def test_raw_payload_kind_is_a_known_list():
    record = samples.raw_payload()
    record["kind"] = "anything"
    with pytest.raises(SchemaError):
        validate("rawPayload", record)


def test_raw_payload_messages_follow_the_otel_message_schema():
    record = samples.raw_payload()
    record["content"] = "글자만"                       # 메시지는 구조가 있어야 합니다.
    with pytest.raises(SchemaError):
        validate("rawPayload", record)
    record["content"] = [{"role": "assistant"}]       # parts가 없으면 OTel 메시지가 아닙니다.
    with pytest.raises(SchemaError):
        validate("rawPayload", record)
    record["kind"] = "input_messages"                 # 입력 메시지는 role과 parts만 필수
    record["content"] = [{"role": "user", "parts": [{"type": "text", "content": "x"}]}]
    validate("rawPayload", record)


@pytest.mark.parametrize("kind", ["ocr_output", "retrieval_query", "postprocess_output"])
def test_raw_payload_other_kinds_are_plain_text(kind):
    record = samples.raw_payload()
    record["kind"] = kind
    record["content"] = "글자"
    validate("rawPayload", record)
    record["content"] = [{"role": "user"}]
    with pytest.raises(SchemaError):
        validate("rawPayload", record)


# 동결 --------------------------------------------------------------------

def test_current_schemas_equal_the_released_snapshot():
    released = json.loads(SCHEMAS.joinpath("released", f"{SCHEMA_VERSION}.json").read_text("utf-8"))
    assert bundle() == released, "스키마를 바꿨다면 버전을 올리고 새 스냅샷을 추가한 뒤 HISTORY에 이유를 적으세요"


def test_previous_snapshot_is_kept_as_a_record():
    assert json.loads(SCHEMAS.joinpath("released", "1.0.0.json").read_text("utf-8"))["schemaVersion"] == "1.0.0"


# 오류 메시지 ---------------------------------------------------------------

def test_missing_attribute_error_names_the_attribute():
    # 속성 배열 전체를 쏟아내는 대신, 빠진 속성 이름을 알려 줘야 고칠 수 있습니다.
    data = samples.traces("chat fake-model")
    drop_attribute(samples.the_span(data), "ocr.model.role")
    with pytest.raises(SchemaError, match="필수 속성 없음: ocr.model.role"):
        validate("tracesData", data)
