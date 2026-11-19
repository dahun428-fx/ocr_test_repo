"""OpenTelemetry로 추적과 평가 이벤트를 쓰고 읽습니다.

기록을 만드는 일은 직접 하지 않고 OpenTelemetry(Apache 2.0)의 것을 씁니다.
  - span과 로그 만들기: opentelemetry-sdk
  - OTLP JSON으로 바꾸기: opentelemetry-exporter-otlp-json-common (공식 인코더, 아직 베타)
  - 파일 형식: OTLP File Exporter (JSON Lines, 한 줄이 TracesData 또는 LogsData)

여기에는 SDK에 없는 얇은 부분만 둡니다.
  - 파일로 내보내기 (파이썬 SDK에는 OTLP JSON 파일 내보내기가 없습니다)
  - 이 연구의 규칙: resource 속성, 오류 표시, 평가 이벤트 이름
  - 읽기: OTLP JSON → 파이썬 값 (비용 장부와 대시보드에서 씁니다)

쓴 기록이 규칙에 맞는지는 ocr_harness.common.schema.validate("tracesData" | "logsData", 줄)로 검사합니다.
"""
import json
import time
from pathlib import Path

from opentelemetry import trace
from opentelemetry._logs import LogRecord
from opentelemetry.exporter.otlp.json.common._log_encoder import encode_logs as _encode_logs
from opentelemetry.exporter.otlp.json.common.trace_encoder import encode_spans as _encode_spans
from opentelemetry.sdk._logs.export import LogRecordExporter, LogRecordExportResult
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult
from opentelemetry.trace import Status, StatusCode

from ocr_harness.common.schema import SCHEMA_VERSION   # 버전 상수는 schema.py 한 곳에만 둡니다.

SERVICE_NAME = "ocr-harness"
SCOPE_NAME = "ocr_harness"                      # get_tracer / get_logger에 넘기는 이름
EVALUATION_EVENT = "gen_ai.evaluation.result"   # OTel GenAI 규약의 평가 결과 이벤트 이름


# 쓰기 ---------------------------------------------------------------------

def resource(run_id: str, service_version: str) -> Resource:
    """TracerProvider / LoggerProvider에 넘기는 resource. 실행 묶음 id와 스키마 버전이 줄마다 실립니다."""
    # Resource.create()는 SDK 정보(telemetry.sdk.*)를 자동으로 붙이므로 쓰지 않습니다. 우리 스키마는 네 가지만 받습니다.
    return Resource({
        "service.name": SERVICE_NAME,
        "service.version": service_version,
        "ocr.run.id": run_id,
        "ocr.schema.version": SCHEMA_VERSION,
    })


def finish(span, error_type: str | None = None) -> None:
    """span의 결과를 표시합니다. 오류면 상태를 ERROR로 하고 error.type(플랫폼 오류 코드)을 답니다."""
    if error_type is None:
        span.set_status(Status(StatusCode.OK))
    else:
        span.set_attribute("error.type", error_type)
        span.set_status(Status(StatusCode.ERROR))


def emit_evaluation(logger, span_context, attributes: dict) -> None:
    """채점 1건을 OTel 평가 이벤트로 내보냅니다. span_context는 채점한 출력을 만든 span입니다."""
    if "gen_ai.evaluation.score.value" in attributes:
        # 점수는 규약에서 실수(double)입니다. 1처럼 정수로 넘어와도 실수로 적습니다.
        attributes = {**attributes, "gen_ai.evaluation.score.value": float(attributes["gen_ai.evaluation.score.value"])}
    logger.emit(LogRecord(
        timestamp=time.time_ns(),
        event_name=EVALUATION_EVENT,
        attributes=attributes,
        # 이벤트를 그 span에 붙이려면 span을 "현재 span"으로 둔 문맥을 넘겨야 합니다.
        context=trace.set_span_in_context(trace.NonRecordingSpan(span_context)),
    ))


def encode_traces(spans) -> dict:
    """SDK의 끝난 span들 → 추적 파일 한 줄 (TracesData, dict)."""
    return json.loads(_encode_spans(spans).to_json())


def encode_logs(records) -> dict:
    """SDK의 로그 기록들 → 평가 이벤트 파일 한 줄 (LogsData, dict)."""
    return json.loads(_encode_logs(records).to_json())


def _append_line(path: Path, line: dict) -> None:
    with open(path, "a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(line, ensure_ascii=False) + "\n")


class JsonLinesSpanExporter(SpanExporter):
    """끝난 span을 OTLP JSON Lines 파일에 덧붙입니다. 내보낼 때마다 한 줄입니다."""

    def __init__(self, path):
        self._path = Path(path)

    def export(self, spans):
        _append_line(self._path, encode_traces(spans))
        return SpanExportResult.SUCCESS

    def shutdown(self):
        pass

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return True   # 줄마다 바로 쓰므로 모아 둔 것이 없습니다.


class JsonLinesLogExporter(LogRecordExporter):
    """평가 이벤트를 OTLP JSON Lines 파일에 덧붙입니다. 추적과 다른 파일이어야 합니다 (한 파일에 한 종류)."""

    def __init__(self, path):
        self._path = Path(path)

    def export(self, batch):
        _append_line(self._path, encode_logs(batch))
        return LogRecordExportResult.SUCCESS

    def shutdown(self):
        pass

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return True


# 읽기 ---------------------------------------------------------------------

def plain(value: dict):
    """OTLP AnyValue → 파이썬 값."""
    if "stringValue" in value:
        return value["stringValue"]
    if "boolValue" in value:
        return value["boolValue"]
    if "intValue" in value:
        return int(value["intValue"])    # 64비트 정수는 문자열로 적혀 있습니다 (proto3 JSON 규칙). 숫자여도 받습니다.
    if "doubleValue" in value:
        return float(value["doubleValue"])
    if "arrayValue" in value:
        return [plain(v) for v in value["arrayValue"].get("values", [])]
    if "kvlistValue" in value:
        return plain_attributes(value["kvlistValue"].get("values", []))
    raise ValueError(f"알 수 없는 AnyValue: {sorted(value)}")


def plain_attributes(pairs: list[dict]) -> dict:
    """OTLP 속성 배열 [{key, value}] → {이름: 값}."""
    return {pair["key"]: plain(pair["value"]) for pair in pairs}


def flatten_spans(data: dict) -> list[dict]:
    """TracesData 한 줄 → span마다 읽기 쉬운 한 행. 비용 장부와 대시보드에서 씁니다."""
    rows = []
    for resource_spans in data.get("resourceSpans", []):
        resource_attributes = plain_attributes(resource_spans.get("resource", {}).get("attributes", []))
        for scope_spans in resource_spans.get("scopeSpans", []):
            for one in scope_spans.get("spans", []):
                rows.append({
                    "traceId": one["traceId"],
                    "spanId": one["spanId"],
                    "parentSpanId": one.get("parentSpanId"),
                    "name": one["name"],
                    "startTimeUnixNano": one["startTimeUnixNano"],
                    "endTimeUnixNano": one["endTimeUnixNano"],
                    "statusCode": one.get("status", {}).get("code", 0),
                    "attributes": plain_attributes(one.get("attributes", [])),
                    "resource": resource_attributes,
                })
    return rows
