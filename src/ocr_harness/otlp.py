"""OTLP JSON 기록을 만들고 읽는 도우미.

추적과 평가 이벤트 파일은 OpenTelemetry의 표준 파일 형식을 그대로 씁니다.
  - 파일 형식: OTLP File Exporter (JSON Lines, 한 줄이 TracesData 또는 LogsData)
  - 인코딩: OTLP JSON (opentelemetry-proto docs/specification.md "JSON Protobuf Encoding")

이 형식은 OTel 도구가 바로 읽지만 사람이 읽고 쓰기에는 번거롭습니다. 그래서
  - 쓸 때: 파이썬 값 → OTLP (any_value, key_values, span, traces_data, evaluation_event, logs_data)
  - 읽을 때: OTLP → 파이썬 값 (plain, plain_attributes, flatten_spans)
을 여기에 모았습니다.
"""
from datetime import datetime, timezone

SCHEMA_VERSION = "2.0.0"
SERVICE_NAME = "ocr-harness"
SCOPE_NAME = "ocr_harness"
EVALUATION_EVENT = "gen_ai.evaluation.result"   # OTel GenAI 규약의 평가 결과 이벤트 이름

# OTLP JSON에서 enum은 정수로만 적습니다.
SPAN_KIND_INTERNAL, SPAN_KIND_CLIENT = 1, 3
STATUS_OK, STATUS_ERROR = 1, 2


def any_value(value) -> dict:
    """파이썬 값을 OTLP AnyValue로 바꿉니다."""
    if value is None:
        # OTLP에는 "값 없음"이 없습니다. 모르는 값은 속성을 빼야 합니다.
        raise TypeError("None은 속성 값이 될 수 없습니다. 속성을 빼세요.")
    if isinstance(value, bool):          # bool은 int의 하위 타입이라 먼저 가립니다.
        return {"boolValue": value}
    if isinstance(value, int):
        return {"intValue": str(value)}  # 64비트 정수는 JSON에서 문자열 (proto3 JSON 규칙)
    if isinstance(value, float):
        return {"doubleValue": value}
    if isinstance(value, str):
        return {"stringValue": value}
    if isinstance(value, dict):
        return {"kvlistValue": {"values": key_values(value)}}
    if isinstance(value, (list, tuple)):
        return {"arrayValue": {"values": [any_value(v) for v in value]}}
    raise TypeError(f"속성 값으로 쓸 수 없는 타입: {type(value).__name__}")


def key_values(attributes: dict) -> list[dict]:
    """{이름: 값} → OTLP 속성 배열 [{key, value}]."""
    return [{"key": key, "value": any_value(value)} for key, value in attributes.items()]


def plain(value: dict):
    """OTLP AnyValue → 파이썬 값 (any_value의 반대)."""
    if "stringValue" in value:
        return value["stringValue"]
    if "boolValue" in value:
        return value["boolValue"]
    if "intValue" in value:
        return int(value["intValue"])    # 문자열로 적혀 있어도, 숫자로 적혀 있어도 받습니다.
    if "doubleValue" in value:
        return float(value["doubleValue"])
    if "arrayValue" in value:
        return [plain(v) for v in value["arrayValue"].get("values", [])]
    if "kvlistValue" in value:
        return plain_attributes(value["kvlistValue"].get("values", []))
    raise ValueError(f"알 수 없는 AnyValue: {sorted(value)}")


def plain_attributes(pairs: list[dict]) -> dict:
    """OTLP 속성 배열 → {이름: 값}."""
    return {pair["key"]: plain(pair["value"]) for pair in pairs}


def unix_nano(rfc3339: str) -> str:
    """RFC 3339 시각 → 유닉스 나노초 문자열 (OTLP의 시간 표기)."""
    moment = datetime.fromisoformat(rfc3339.replace("Z", "+00:00"))
    delta = moment - datetime(1970, 1, 1, tzinfo=timezone.utc)
    # 실수 연산의 오차를 피하려고 정수로만 계산합니다.
    return str((delta.days * 86400 + delta.seconds) * 1_000_000_000 + delta.microseconds * 1000)


def span(trace_id: str, span_id: str, name: str, start_nano: str, end_nano: str, attributes: dict,
         parent_span_id: str | None = None, kind: int = SPAN_KIND_INTERNAL, error_type: str | None = None) -> dict:
    """span 하나. error_type을 주면 상태를 ERROR로 하고 error.type 속성을 답니다."""
    if error_type is not None:
        attributes = {**attributes, "error.type": error_type}
    record = {"traceId": trace_id, "spanId": span_id}
    if parent_span_id is not None:       # 루트 span에는 부모 키 자체가 없습니다.
        record["parentSpanId"] = parent_span_id
    record.update({
        "name": name,
        "kind": kind,
        "startTimeUnixNano": start_nano,
        "endTimeUnixNano": end_nano,
        "attributes": key_values(attributes),
        "status": {"code": STATUS_ERROR if error_type is not None else STATUS_OK},
    })
    return record


def _resource(run_id: str, service_version: str) -> dict:
    """기록을 만든 주체. 실행 묶음 id와 스키마 버전은 줄마다 여기에 적습니다."""
    return {"attributes": key_values({
        "service.name": SERVICE_NAME,
        "service.version": service_version,
        "ocr.run.id": run_id,
        "ocr.schema.version": SCHEMA_VERSION,
    })}


def traces_data(run_id: str, service_version: str, spans: list[dict]) -> dict:
    """추적 파일의 한 줄 (TracesData). 보통 실행 1회의 span 전부를 한 줄에 담습니다."""
    return {"resourceSpans": [{
        "resource": _resource(run_id, service_version),
        "scopeSpans": [{"scope": {"name": SCOPE_NAME, "version": service_version}, "spans": spans}],
    }]}


def evaluation_event(trace_id: str, span_id: str, time_nano: str, attributes: dict) -> dict:
    """채점 1건 (OTel gen_ai.evaluation.result 이벤트). span_id는 채점한 출력을 만든 span입니다."""
    if "gen_ai.evaluation.score.value" in attributes:
        # 점수는 규약에서 실수(double)입니다. 1처럼 정수로 넘어와도 실수로 적습니다.
        attributes = {**attributes, "gen_ai.evaluation.score.value": float(attributes["gen_ai.evaluation.score.value"])}
    return {
        "timeUnixNano": time_nano,
        "eventName": EVALUATION_EVENT,
        "traceId": trace_id,
        "spanId": span_id,
        "attributes": key_values(attributes),
    }


def logs_data(run_id: str, service_version: str, records: list[dict]) -> dict:
    """평가 이벤트 파일의 한 줄 (LogsData)."""
    return {"resourceLogs": [{
        "resource": _resource(run_id, service_version),
        "scopeLogs": [{"scope": {"name": SCOPE_NAME, "version": service_version}, "logRecords": records}],
    }]}


def flatten_spans(data: dict) -> list[dict]:
    """TracesData 한 줄 → span마다 읽기 쉬운 한 행. 대시보드와 집계에서 씁니다."""
    rows = []
    for resource_spans in data.get("resourceSpans", []):
        resource = plain_attributes(resource_spans.get("resource", {}).get("attributes", []))
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
                    "resource": resource,
                })
    return rows
