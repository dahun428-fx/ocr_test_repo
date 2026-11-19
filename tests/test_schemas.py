"""스키마 4종 검증 테스트. 정답이 알려진 합성 레코드만 씁니다."""
import pytest

from ocr_harness.schema import SchemaError, validate

import samples


@pytest.mark.parametrize("kind", sorted(samples.ALL))
def test_valid_record_passes(kind):
    validate(kind, samples.ALL[kind]())


@pytest.mark.parametrize("kind", sorted(samples.ALL))
def test_each_required_key_is_enforced(kind):
    record = samples.ALL[kind]()
    for key in list(record):
        if kind == "trace" and key == "steps":
            continue
        broken = {k: v for k, v in record.items() if k != key}
        with pytest.raises(SchemaError):
            validate(kind, broken)


def test_unknown_kind_is_rejected():
    with pytest.raises(KeyError):
        validate("nope", {})


@pytest.mark.parametrize("pii_key", ["writer_num", "age", "gender"])
def test_item_rejects_annotator_pii_keys(pii_key):
    record = samples.item()
    record[pii_key] = "x"
    with pytest.raises(SchemaError):
        validate("item", record)


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


def test_item_query_type_must_be_a_b_or_c():
    record = samples.item()
    record["fields"][0]["query_type"] = "D"
    with pytest.raises(SchemaError):
        validate("item", record)


def test_trace_failed_run_requires_known_error_code():
    record = samples.trace()
    record["status"] = "error"
    record["error"] = {"code": "SOMETHING_ELSE", "message": "x"}
    with pytest.raises(SchemaError):
        validate("trace", record)
    record["error"]["code"] = "RATE_LIMITED"
    validate("trace", record)


def test_trace_error_status_without_error_block_is_rejected():
    record = samples.trace()
    record["status"] = "error"
    with pytest.raises(SchemaError):
        validate("trace", record)


def test_trace_condition_must_be_declared():
    record = samples.trace()
    record["condition"] = "C9"
    with pytest.raises(SchemaError):
        validate("trace", record)


def test_eval_record_stage_separates_before_and_after_postprocess():
    record = samples.eval_record()
    record["stage"] = "before_postprocess"
    validate("eval_record", record)
    record["stage"] = "sometime"
    with pytest.raises(SchemaError):
        validate("eval_record", record)


def test_cost_ledger_rejects_negative_tokens():
    record = samples.cost_ledger()
    record["gen_ai.usage.input_tokens"] = -1
    with pytest.raises(SchemaError):
        validate("cost_ledger", record)


def test_cost_ledger_separates_main_and_auxiliary_model():
    record = samples.cost_ledger()
    record["model_role"] = "auxiliary"
    validate("cost_ledger", record)
    record["model_role"] = "other"
    with pytest.raises(SchemaError):
        validate("cost_ledger", record)


def test_cost_ledger_auth_route_is_recorded():
    record = samples.cost_ledger()
    for route in ("api_key", "fake"):
        record["auth_route"] = route
        validate("cost_ledger", record)
    record["auth_route"] = "unknown"
    with pytest.raises(SchemaError):
        validate("cost_ledger", record)
