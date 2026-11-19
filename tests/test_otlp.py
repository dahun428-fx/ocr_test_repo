"""OTLP JSON 도우미 (ocr_harness.otlp). 형식의 근거는 opentelemetry-proto의 JSON 인코딩 규칙입니다."""
from ocr_harness import otlp


def test_values_are_encoded_as_otlp_any_value():
    # 정수는 64비트라 JSON에서 문자열로 적습니다 (proto3 JSON 규칙). bool은 int보다 먼저 가려야 합니다.
    assert otlp.any_value("가") == {"stringValue": "가"}
    assert otlp.any_value(True) == {"boolValue": True}
    assert otlp.any_value(7) == {"intValue": "7"}
    assert otlp.any_value(0.5) == {"doubleValue": 0.5}
    assert otlp.any_value(["a", 1]) == {"arrayValue": {"values": [{"stringValue": "a"}, {"intValue": "1"}]}}
    assert otlp.any_value({"id": "x"}) == {"kvlistValue": {"values": [{"key": "id", "value": {"stringValue": "x"}}]}}


def test_none_cannot_be_an_attribute_value():
    # OTLP에는 "값 없음"을 적는 자리가 없습니다. 모르는 값은 속성을 아예 빼야 합니다.
    try:
        otlp.any_value(None)
    except TypeError:
        return
    raise AssertionError("TypeError가 나야 합니다")


def test_attributes_round_trip():
    original = {"a": "x", "b": 2, "c": [{"id": "d", "score": 0.5, "ok": False}]}
    assert otlp.plain_attributes(otlp.key_values(original)) == original


def test_span_has_the_exact_otlp_json_shape():
    span = otlp.span("0" * 31 + "1", "0" * 15 + "2", "ocr", "10", "20", {"ocr.cache.hit": True},
                     parent_span_id="0" * 15 + "3")
    assert span == {
        "traceId": "0" * 31 + "1",
        "spanId": "0" * 15 + "2",
        "parentSpanId": "0" * 15 + "3",
        "name": "ocr",
        "kind": 1,                       # SPAN_KIND_INTERNAL. OTLP JSON에서 enum은 정수로만 적습니다.
        "startTimeUnixNano": "10",
        "endTimeUnixNano": "20",
        "attributes": [{"key": "ocr.cache.hit", "value": {"boolValue": True}}],
        "status": {"code": 1},           # STATUS_CODE_OK
    }


def test_error_span_sets_status_and_error_type():
    span = otlp.span("0" * 31 + "1", "0" * 15 + "2", "ocr", "10", "20", {}, error_type="UPSTREAM_TIMEOUT")
    assert span["status"] == {"code": 2}  # STATUS_CODE_ERROR
    assert otlp.plain_attributes(span["attributes"]) == {"error.type": "UPSTREAM_TIMEOUT"}
    assert "parentSpanId" not in span     # 루트 span은 부모가 없습니다.


def test_traces_data_wraps_spans_with_resource_and_scope():
    data = otlp.traces_data("run-0001", "0.1.0", [{"name": "x"}])
    resource = otlp.plain_attributes(data["resourceSpans"][0]["resource"]["attributes"])
    assert resource == {
        "service.name": "ocr-harness",
        "service.version": "0.1.0",
        "ocr.run.id": "run-0001",
        "ocr.schema.version": "2.0.0",
    }
    assert data["resourceSpans"][0]["scopeSpans"][0]["spans"] == [{"name": "x"}]


def test_evaluation_event_uses_the_otel_event_name():
    event = otlp.evaluation_event("0" * 31 + "1", "0" * 15 + "2", "30", {"gen_ai.evaluation.name": "em"})
    assert event["eventName"] == "gen_ai.evaluation.result"
    assert event["timeUnixNano"] == "30"
    assert (event["traceId"], event["spanId"]) == ("0" * 31 + "1", "0" * 15 + "2")


def test_unix_nano_from_rfc3339():
    assert otlp.unix_nano("1970-01-01T00:00:01Z") == "1000000000"
    assert otlp.unix_nano("1970-01-01T09:00:01.5+09:00") == "1500000000"


def test_flatten_gives_one_plain_row_per_span():
    one = otlp.span("0" * 31 + "1", "0" * 15 + "2", "ocr", "10", "20", {"ocr.cache.hit": True})
    rows = otlp.flatten_spans(otlp.traces_data("run-0001", "0.1.0", [one]))
    assert rows == [{
        "traceId": "0" * 31 + "1", "spanId": "0" * 15 + "2", "parentSpanId": None, "name": "ocr",
        "startTimeUnixNano": "10", "endTimeUnixNano": "20", "statusCode": 1,
        "attributes": {"ocr.cache.hit": True},
        "resource": {"service.name": "ocr-harness", "service.version": "0.1.0",
                     "ocr.run.id": "run-0001", "ocr.schema.version": "2.0.0"},
    }]


def test_schema_version_is_the_same_everywhere():
    # 버전 상수가 세 곳(schema.py, otlp.py, 스키마 파일)에 있어서 어긋나지 않게 묶어 둡니다.
    from ocr_harness import schema
    assert otlp.SCHEMA_VERSION == schema.SCHEMA_VERSION
    assert schema.bundle()["schemas"]["item"]["properties"]["schemaVersion"]["const"] == schema.SCHEMA_VERSION
