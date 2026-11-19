"""OpenTelemetry SDK로 기록을 쓰고 읽는 부분 (ocr_harness.otlp).

기록을 만드는 일은 SDK와 공식 JSON 인코더가 합니다. 여기서는 (1) 그 결과가 OTLP 파일 형식이고
우리 스키마를 통과하는지, (2) 우리가 덧붙인 얇은 코드(파일 쓰기, 오류 표시, 읽기)가 맞는지만 봅니다.
"""
import json

from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import SimpleLogRecordProcessor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor

from ocr_harness import otlp, schema

import samples


def test_span_exporter_writes_otlp_json_lines_that_pass_the_schema(tmp_path):
    path = tmp_path / "traces.jsonl"
    provider = TracerProvider(resource=otlp.resource("run-0001", "0.1.0"))
    provider.add_span_processor(SimpleSpanProcessor(otlp.JsonLinesSpanExporter(path)))
    tracer = provider.get_tracer(otlp.SCOPE_NAME, "0.1.0")
    with tracer.start_as_current_span("invoke_agent ocr-harness", attributes=samples.root_attributes()) as root:
        otlp.finish(root)
        with tracer.start_as_current_span("ocr", attributes=samples.ocr_attributes()) as child:
            otlp.finish(child)
    lines = path.read_text("utf-8").splitlines()
    assert len(lines) == 2                       # 끝난 span마다 한 줄 (OTLP File Exporter: 한 줄이 TracesData)
    for line in lines:
        schema.validate("tracesData", json.loads(line))
    child, root = (otlp.flatten_spans(json.loads(line))[0] for line in lines)
    assert child["parentSpanId"] == root["spanId"] and child["traceId"] == root["traceId"]
    assert root["parentSpanId"] is None


def test_ids_are_hex_not_base64():
    # OTLP JSON 규칙: traceId와 spanId는 16진수 문자열. 일반 protobuf JSON 변환은 base64를 내므로 따로 확인합니다.
    span = samples.the_span(samples.traces())
    assert len(span["traceId"]) == 32 and len(span["spanId"]) == 16
    int(span["traceId"], 16), int(span["spanId"], 16)


def test_finish_marks_errors_with_status_and_error_type():
    span = samples.the_span(samples.traces("ocr", error_type="UPSTREAM_TIMEOUT"))
    assert span["status"]["code"] == 2           # STATUS_CODE_ERROR
    assert otlp.plain_attributes(span["attributes"])["error.type"] == "UPSTREAM_TIMEOUT"
    assert samples.the_span(samples.traces("ocr"))["status"]["code"] == 1   # STATUS_CODE_OK


def test_resource_carries_run_id_and_schema_version():
    resource = samples.traces()["resourceSpans"][0]["resource"]["attributes"]
    assert otlp.plain_attributes(resource) == {
        "service.name": "ocr-harness",
        "service.version": "0.1.0",
        "ocr.run.id": "run-0001",
        "ocr.schema.version": schema.SCHEMA_VERSION,
    }


def test_log_exporter_writes_evaluation_events_that_pass_the_schema(tmp_path):
    path = tmp_path / "logs.jsonl"
    provider = LoggerProvider(resource=otlp.resource("run-0001", "0.1.0"))
    provider.add_log_record_processor(SimpleLogRecordProcessor(otlp.JsonLinesLogExporter(path)))
    chat = samples.run_spans([("invoke_agent ocr-harness", samples.root_attributes(), None),
                              ("chat fake-model", samples.chat_attributes(), None)])[0]
    attributes = samples.score_attributes() | {"gen_ai.evaluation.score.value": 1}   # 정수로 넘겨도
    otlp.emit_evaluation(provider.get_logger(otlp.SCOPE_NAME, "0.1.0"), chat.get_span_context(), attributes)
    line = json.loads(path.read_text("utf-8"))
    schema.validate("logsData", line)
    event = samples.the_event(line)
    assert event["eventName"] == "gen_ai.evaluation.result"
    assert event["spanId"] == format(chat.get_span_context().span_id, "016x")      # 채점한 span에 붙습니다.
    assert otlp.plain_attributes(event["attributes"])["gen_ai.evaluation.score.value"] == 1.0   # 실수로 적힙니다.


def test_plain_attributes_reads_back_structured_values():
    span = samples.the_span(samples.traces("retrieval mfds"))
    assert otlp.plain_attributes(span["attributes"]) == samples.retrieval_attributes()


def test_flatten_gives_one_plain_row_per_span():
    (row,) = otlp.flatten_spans(samples.traces("ocr"))
    assert row["name"] == "ocr" and row["statusCode"] == 1
    assert row["attributes"] == samples.ocr_attributes()
    assert row["resource"]["ocr.run.id"] == "run-0001"
    assert int(row["endTimeUnixNano"]) >= int(row["startTimeUnixNano"])
