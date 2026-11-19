"""스키마 8종 검증 테스트 (설계: docs/schema-design.md). 정답이 알려진 합성 레코드만 씁니다."""
import hashlib
import json
from importlib import resources

import pytest

from ocr_harness.schema import KINDS, SchemaError, bundle, validate

import samples

SCHEMAS = resources.files("ocr_harness") / "schemas"
OPTIONAL = {
    "item": {"queries", "tags"},
    "conditionManifest": {"knowledgeIndexVersion"},
    "span": {"parentSpanId", "errorCode"},
    "fieldScore": {"queryType", "ocrMisread"},
}


def test_all_eight_kinds_are_defined():
    assert set(KINDS) == set(samples.ALL)


@pytest.mark.parametrize("kind", sorted(samples.ALL))
def test_valid_record_passes(kind):
    validate(kind, samples.ALL[kind]())


@pytest.mark.parametrize("make", samples.SPANS, ids=lambda f: f.__name__)
def test_every_span_kind_passes(make):
    validate("span", make())


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
    record["writer_num"] = "x"
    with pytest.raises(SchemaError):
        validate(kind, record)


def test_unknown_kind_is_rejected():
    with pytest.raises(KeyError):
        validate("nope", {})


# 플랫폼 형식 규칙 ---------------------------------------------------------

@pytest.mark.parametrize("kind,key,bad", [
    ("item", "itemId", "sha256:" + "a" * 64),      # id 패턴
    ("item", "productId", "Prod_1"),
    ("item", "datasetVersion", "eval-v1"),          # semver
    ("item", "imageDigest", "a" * 64),              # sha256: 접두사
    ("conditionManifest", "version", "c1-v1"),
    ("span", "traceId", "tr-0001"),                 # 32자리 16진수
    ("span", "spanId", "0123"),
    ("modelCall", "routeDecisionId", "Route 1"),
    ("fieldScore", "manifestDigest", "abc"),
    ("fieldScore", "agentVersion", "v1"),
])
def test_platform_format_rules(kind, key, bad):
    record = samples.ALL[kind]()
    record[key] = bad
    with pytest.raises(SchemaError):
        validate(kind, record)


@pytest.mark.parametrize("kind", ["item", "conditionManifest", "span", "rawPayload", "modelCall", "fieldScore"])
def test_schema_version_is_pinned(kind):
    record = samples.ALL[kind]()
    record["schemaVersion"] = "9.9.9"
    with pytest.raises(SchemaError):
        validate(kind, record)


# 플랫폼 계약 그대로 --------------------------------------------------------

PLATFORM_DIGESTS = {
    "evaluation.schema.json": "ac96592ce7e597d60a43596368c4fa563939632d4bb300f310cdb549e78eb802",
    "retrieval.schema.json": "eab2e9096d0394f9e4a2a93297a70b6496d781f8375e6572c8aea75d1eecb527",
}


@pytest.mark.parametrize("name", sorted(PLATFORM_DIGESTS))
def test_platform_contract_files_are_unmodified_copies(name):
    data = (SCHEMAS / "platform" / "0.2.0" / name).read_bytes()
    assert hashlib.sha256(data).hexdigest() == PLATFORM_DIGESTS[name]


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


# span --------------------------------------------------------------------

def test_span_error_requires_platform_problem_code():
    record = samples.span_chat()
    record["status"] = "error"
    with pytest.raises(SchemaError):
        validate("span", record)
    record["errorCode"] = "SOMETHING_ELSE"
    with pytest.raises(SchemaError):
        validate("span", record)
    for code in ("RATE_LIMITED", "UPSTREAM_TIMEOUT", "UPSTREAM_ERROR", "UPSTREAM_UNAVAILABLE", "VALIDATION_ERROR"):
        record["errorCode"] = code
        validate("span", record)


def test_span_name_must_be_a_known_kind():
    record = samples.span_ocr()
    record["name"] = "something"
    with pytest.raises(SchemaError):
        validate("span", record)


@pytest.mark.parametrize("raw_attribute", [
    "gen_ai.input.messages",
    "gen_ai.output.messages",
    "gen_ai.system_instructions",
    "gen_ai.retrieval.query.text",
    "ocr.output.text",
])
def test_span_rejects_raw_text_attributes(raw_attribute):
    record = samples.span_chat()
    record["attributes"][raw_attribute] = "원문"
    with pytest.raises(SchemaError):
        validate("span", record)


def test_span_attribute_names_need_a_known_prefix():
    record = samples.span_ocr()
    record["attributes"]["engine"] = "x"
    with pytest.raises(SchemaError):
        validate("span", record)


def test_span_rejects_cache_creation_name_not_in_otel_convention():
    record = samples.span_chat()
    record["attributes"]["gen_ai.usage.cache_creation.input_tokens"] = 1
    with pytest.raises(SchemaError):
        validate("span", record)


@pytest.mark.parametrize("make,key", [
    (samples.span_root, "ocr.manifest.digest"),
    (samples.span_root, "platform.idempotency_key"),
    (samples.span_root, "ocr.outcome"),
    (samples.span_ocr, "ocr.output.digest"),
    (samples.span_retrieval, "gen_ai.retrieval.documents"),
    (samples.span_context, "ocr.context.order"),
    (samples.span_chat, "gen_ai.request.model"),
    (samples.span_chat, "ocr.model_call.ids"),
    (samples.span_postprocess, "platform.guardrail.mode"),
    (samples.span_postprocess, "ocr.output.after.digest"),
])
def test_span_kind_requires_its_attributes(make, key):
    record = make()
    del record["attributes"][key]
    with pytest.raises(SchemaError):
        validate("span", record)


def test_root_span_outcome_keeps_refusals_and_empty_outputs_visible():
    record = samples.span_root()
    for outcome in ("ok", "refused", "empty", "error"):
        record["attributes"]["ocr.outcome"] = outcome
        validate("span", record)
    record["attributes"]["ocr.outcome"] = "skipped"
    with pytest.raises(SchemaError):
        validate("span", record)


def test_postprocess_mode_is_check_only_or_enforce():
    record = samples.span_postprocess()
    record["attributes"]["platform.guardrail.mode"] = "enforce"
    validate("span", record)
    record["attributes"]["platform.guardrail.mode"] = "apply"
    with pytest.raises(SchemaError):
        validate("span", record)


# modelCall ---------------------------------------------------------------

def test_model_call_rejects_negative_tokens():
    record = samples.model_call()
    record["usage"]["inputTokens"] = -1
    with pytest.raises(SchemaError):
        validate("modelCall", record)


def test_model_call_separates_main_and_auxiliary_model():
    record = samples.model_call()
    record["modelRole"] = "auxiliary"
    validate("modelCall", record)
    record["modelRole"] = "other"
    with pytest.raises(SchemaError):
        validate("modelCall", record)


def test_model_call_auth_route_is_recorded():
    record = samples.model_call()
    for route in ("subscription_oauth", "api_key", "fake"):
        record["authRoute"] = route
        validate("modelCall", record)
    record["authRoute"] = "unknown"
    with pytest.raises(SchemaError):
        validate("modelCall", record)


def test_model_call_uses_otel_cache_write_name():
    record = samples.model_call()
    record["attributes"]["gen_ai.usage.cache_creation.input_tokens"] = 1
    with pytest.raises(SchemaError):
        validate("modelCall", record)


def test_model_call_accepts_sdk_reported_extras_seen_in_prior_runs():
    record = samples.model_call()
    record["attributes"].update({
        "gen_ai.response.model": "fake-model-1",
        "gen_ai.response.finish_reasons": ["end_turn"],
        "gen_ai.usage.reasoning.output_tokens": 0,
        "gen_ai.usage.image.input_tokens": 0,
        "ocr.sdk.num_turns": 1,
        "ocr.sdk.duration_api_ms": 800,
    })
    record["cost"]["basis"] = "api_list_price"
    validate("modelCall", record)


def test_model_call_cost_may_be_unknown_but_must_be_present():
    record = samples.model_call()
    record["cost"]["sdkReportedUsd"] = None
    validate("modelCall", record)
    del record["cost"]["sdkReportedUsd"]
    with pytest.raises(SchemaError):
        validate("modelCall", record)


# rawPayload, fieldScore --------------------------------------------------

def test_raw_payload_kind_is_a_known_list():
    record = samples.raw_payload()
    record["kind"] = "anything"
    with pytest.raises(SchemaError):
        validate("rawPayload", record)


@pytest.mark.parametrize("target", [
    {"kind": "field", "fieldId": "expiry"},
    {"kind": "query", "queryId": "q-0001"},
    {"kind": "item"},
])
def test_field_score_targets_a_field_a_query_or_the_whole_item(target):
    record = samples.field_score()
    record["target"] = target
    validate("fieldScore", record)


@pytest.mark.parametrize("target", [{"kind": "field"}, {"kind": "query", "fieldId": "x"}, {"kind": "page"}])
def test_field_score_rejects_malformed_target(target):
    record = samples.field_score()
    record["target"] = target
    with pytest.raises(SchemaError):
        validate("fieldScore", record)


def test_field_score_stage_separates_before_and_after_postprocess():
    record = samples.field_score()
    record["stage"] = "before_postprocess"
    validate("fieldScore", record)
    record["stage"] = "sometime"
    with pytest.raises(SchemaError):
        validate("fieldScore", record)


# 동결 --------------------------------------------------------------------

def test_current_schemas_equal_the_released_snapshot():
    released = json.loads((SCHEMAS / "released" / "1.0.0.json").read_text("utf-8"))
    assert bundle() == released, "스키마를 바꿨다면 새 버전 스냅샷을 추가하고 HISTORY에 이유를 적으세요"
