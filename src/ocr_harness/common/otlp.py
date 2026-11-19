"""OpenTelemetry로 추적과 평가 이벤트를 쓰고 읽습니다.

기록을 만드는 일은 직접 하지 않고 OpenTelemetry(Apache 2.0)의 것을 씁니다.
  - span과 로그 만들기: opentelemetry-sdk
  - OTLP JSON으로 바꾸기: opentelemetry-exporter-otlp-json-common (공식 인코더, 아직 베타)
  - 파일 형식: OTLP File Exporter (JSON Lines, 한 줄이 TracesData 또는 LogsData)

여기에는 SDK에 없는 얇은 부분만 둡니다.
  - 파일로 내보내기 (파이썬 SDK에는 OTLP JSON 파일 내보내기가 없습니다): JsonLinesWriter와 그 자식 둘
  - 프로젝트 이름을 싣는 일: Telemetry (resource 속성, tracer, logger). 이름은 Profile에서 받습니다
  - 어느 프로젝트나 같은 규칙: 오류 표시(finish), 평가 이벤트(emit_evaluation)
  - 읽기: OTLP JSON → 파이썬 값 (비용 장부와 대시보드에서 씁니다)

이 파일에는 특정 프로젝트의 이름이 없습니다. 이 연구의 이름은 ocr_harness.project에 있습니다.
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

from ocr_harness.common.profile import Profile

EVALUATION_EVENT = "gen_ai.evaluation.result"   # OTel GenAI 규약의 평가 결과 이벤트 이름


# 쓰기 ---------------------------------------------------------------------

class Telemetry:
    """프로젝트 하나의 추적 설정. Profile의 이름으로 resource, tracer, logger를 만들어 줍니다.

    함수 여러 개에 profile을 매번 넘기는 대신 객체 하나로 묶었습니다.
    그래야 한 실행 안에서 resource의 이름과 tracer의 이름이 서로 다른 Profile에서 나오는 실수가 없습니다.
    """

    def __init__(self, profile: Profile):
        self.profile = profile

    def resource(self, run_id: str, service_version: str) -> Resource:
        """TracerProvider / LoggerProvider에 넘기는 resource. 실행 묶음 id와 스키마 버전이 줄마다 실립니다."""
        # Resource.create()는 SDK 정보(telemetry.sdk.*)를 자동으로 붙이므로 쓰지 않습니다. 스키마가 네 가지만 받습니다.
        return Resource({
            "service.name": self.profile.service_name,
            "service.version": service_version,
            self.profile.attr("run.id"): run_id,
            self.profile.attr("schema.version"): self.profile.schema_version,
        })

    def tracer(self, provider, version: str):
        """이 프로젝트의 계측 범위 이름으로 tracer를 받습니다."""
        return provider.get_tracer(self.profile.scope_name, version)

    def logger(self, provider, version: str):
        """이 프로젝트의 계측 범위 이름으로 logger를 받습니다 (평가 이벤트용)."""
        return provider.get_logger(self.profile.scope_name, version)


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


class JsonLinesWriter:
    """OTLP JSON Lines 파일에 "한 묶음 = 한 줄"로 덧붙이는 공통 뼈대 (템플릿 메서드).

    span 내보내기와 로그 내보내기는 "묶음을 dict로 바꾸는 법"과 "성공을 알리는 값"만 다릅니다.
    그 두 가지만 자식이 정하고, 파일을 여는 방식·줄바꿈·인코딩은 여기 한 곳에서 정합니다.
    SDK의 SpanExporter / LogRecordExporter와 함께 다중 상속으로 씁니다 (이 클래스를 앞에 둡니다).
    """

    # 자식이 정하는 두 가지.
    _success = None   # export()가 돌려줄 SDK의 성공 값

    def _encode(self, batch) -> dict:
        """묶음 → 파일 한 줄(dict). 자식이 구현합니다."""
        raise NotImplementedError

    def __init__(self, path):
        self._path = Path(path)

    def export(self, batch):
        # newline="\n": Windows에서도 줄 끝을 LF로 고정합니다. 같은 기록이면 어느 PC에서 써도 같은 바이트여야 합니다.
        with open(self._path, "a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(self._encode(batch), ensure_ascii=False) + "\n")
        return self._success

    def shutdown(self):
        pass   # 내보낼 때마다 파일을 열고 닫으므로 정리할 것이 없습니다.

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return True   # 줄마다 바로 쓰므로 모아 둔 것이 없습니다.


class JsonLinesSpanExporter(JsonLinesWriter, SpanExporter):
    """끝난 span을 OTLP JSON Lines 파일에 덧붙입니다. 내보낼 때마다 한 줄입니다."""

    _success = SpanExportResult.SUCCESS

    def _encode(self, batch) -> dict:
        return encode_traces(batch)


class JsonLinesLogExporter(JsonLinesWriter, LogRecordExporter):
    """평가 이벤트를 OTLP JSON Lines 파일에 덧붙입니다. 추적과 다른 파일이어야 합니다 (한 파일에 한 종류)."""

    _success = LogRecordExportResult.SUCCESS

    def _encode(self, batch) -> dict:
        return encode_logs(batch)


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
