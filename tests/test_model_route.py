"""모델 경로(ocr_harness.common.model_route): 모든 모델 호출이 여기를 지나 chat span 하나로 남는지 검사합니다.

실제 모델은 부르지 않습니다. 정해진 답을 주는 가짜 뒷단(FakeBackend)을 씁니다.
"""
import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from ocr_harness import project
from ocr_harness.common import otlp
from ocr_harness.common.model_route import FakeBackend, ModelBackend, ModelRequest, ModelResult, ModelRoute, PriceTable
from ocr_harness.common.ocr import CachedOcr
from ocr_harness.common.ocr_vision import OcrFailed, VisionOcrEngine

PRICES = PriceTable("2026.11.19", {"fake-model": {"input": 2.0, "output": 10.0, "cache_read": 0.1, "cache_write": 2.5}})


def _route(backend, prices=PRICES):
    memory = InMemorySpanExporter()
    provider = TracerProvider(resource=project.resource("run-0001", "0.1.0"))
    provider.add_span_processor(SimpleSpanProcessor(memory))
    return ModelRoute(project.PROFILE, project.tracer(provider, "0.1.0"), backend, prices), memory


def _request(**changes):
    return ModelRequest(**({"model": "fake-model", "content": [{"type": "text", "text": "안녕"}]} | changes))


def _result(**changes):
    return ModelResult(**({"text": "네", "input_tokens": 1000, "output_tokens": 100, "cache_read_input_tokens": 2000,
                           "cache_write_input_tokens": 400} | changes))


def _line(memory):
    return otlp.encode_traces(memory.get_finished_spans())


def test_every_call_leaves_one_chat_span_that_passes_the_schema():
    route, memory = _route(FakeBackend([_result(), _result()]))
    route.call(_request())
    route.call(_request(role="ocr", attempt=1))
    line = _line(memory)
    project.validate("tracesData", line)
    assert [row["name"] for row in otlp.flatten_spans(line)] == ["chat fake-model", "chat fake-model"]


def test_tokens_and_cost_reach_the_ledger():
    route, memory = _route(FakeBackend([_result(sdk_reported_usd=0.5)]))
    route.call(_request(role="ocr"))
    row = project.model_calls([_line(memory)])[0]
    assert row["usage"] == {"inputTokens": 1000, "outputTokens": 100}
    assert (row["cacheReadInputTokens"], row["cacheWriteInputTokens"]) == (2000, 400)
    assert (row["modelRole"], row["authRoute"], row["provider"]) == ("ocr", "fake", "external")
    # 1000×2 + 100×10 + 2000×0.1 + 400×2.5 = 4200 → 100만 토큰당 달러이므로 0.0042
    assert row["cost"] == {"sdkReportedUsd": 0.5, "computedUsd": pytest.approx(0.0042), "priceTableVersion": "2026.11.19"}


def test_unknown_model_price_leaves_the_computed_cost_out():
    # 가격을 모르는 모델의 비용을 0으로 적으면 "공짜"로 읽힙니다. 속성을 빼서 "모름"으로 둡니다.
    route, memory = _route(FakeBackend([_result()]), PriceTable("2026.11.19", {}))
    route.call(_request())
    assert project.model_calls([_line(memory)])[0]["cost"]["computedUsd"] is None


def test_backend_error_is_recorded_and_returned_not_raised():
    route, memory = _route(FakeBackend([_result(text="", error_type="RATE_LIMITED")]))
    result = route.call(_request())
    assert result.error_type == "RATE_LIMITED"
    line = _line(memory)
    project.validate("tracesData", line)
    assert project.model_calls([line])[0]["errorCode"] == "RATE_LIMITED"


def test_backend_exception_becomes_an_error_span():
    # 뒷단이 예외를 던져도 호출 기록이 사라지면 안 됩니다. 실패한 호출도 장부에 남깁니다.
    class Broken(ModelBackend):
        auth_route = "fake"

        def call(self, request):
            raise RuntimeError("연결 끊김")

    route, memory = _route(Broken())
    assert route.call(_request()).error_type == "UPSTREAM_ERROR"
    assert project.model_calls([_line(memory)])[0]["errorCode"] == "UPSTREAM_ERROR"


def test_prompt_digest_changes_with_the_content():
    route, memory = _route(FakeBackend([_result(), _result()]))
    route.call(_request())
    route.call(_request(content=[{"type": "text", "text": "다른 질문"}]))
    first, second = (row["attributes"]["ocr.prompt.digest"] for row in otlp.flatten_spans(_line(memory)))
    assert first != second


# 비전 모델 OCR 엔진 ------------------------------------------------------------

def _image(tmp_path):
    path = tmp_path / "a.png"
    path.write_bytes(b"not-a-real-image")   # 가짜 뒷단은 내용을 보지 않습니다.
    return path


def test_vision_engine_turns_the_model_text_into_lines(tmp_path):
    route, memory = _route(FakeBackend([_result(text="합성정 10mg\n\n  사용기한 2027.01.31  \n")]))
    engine = VisionOcrEngine(route, "fake-model", prompt="읽어 주세요", max_side=None)
    assert engine.read(_image(tmp_path)) == [
        {"text": "합성정 10mg", "box": None, "score": None}, {"text": "사용기한 2027.01.31", "box": None, "score": None},
    ]
    assert otlp.flatten_spans(_line(memory))[0]["attributes"]["ocr.model.role"] == "ocr"


def test_vision_engine_config_covers_model_prompt_and_size(tmp_path):
    route, _ = _route(FakeBackend([]))
    base = VisionOcrEngine(route, "fake-model", prompt="읽어 주세요", max_side=1568).config_digest
    assert base != VisionOcrEngine(route, "fake-model", prompt="다르게", max_side=1568).config_digest
    assert base != VisionOcrEngine(route, "fake-model", prompt="읽어 주세요", max_side=1024).config_digest
    assert base != VisionOcrEngine(route, "other-model", prompt="읽어 주세요", max_side=1568).config_digest


def test_vision_engine_failure_is_raised_and_not_cached(tmp_path):
    # 실패를 빈 결과로 캐시에 남기면 "글자가 없는 이미지"와 구분되지 않고 다시 시도할 수도 없습니다.
    route, _ = _route(FakeBackend([_result(text="", error_type="RATE_LIMITED"), _result(text="합성정")]))
    cached = CachedOcr(VisionOcrEngine(route, "fake-model", prompt="읽어 주세요", max_side=None), tmp_path / "cache")
    with pytest.raises(OcrFailed, match="RATE_LIMITED"):
        cached.read(_image(tmp_path))
    assert cached.read(_image(tmp_path))[0]["text"] == "합성정"     # 두 번째 시도는 성공하고 그때 캐시에 남습니다.


def test_auxiliary_model_calls_get_their_own_rows():
    # SDK가 안에서 따로 부른 작은 모델도 비용이 드는 호출입니다. 주 호출에 합치지 않고 따로 남깁니다.
    aux = _result(text="", input_tokens=30, output_tokens=2, cache_read_input_tokens=0, cache_write_input_tokens=0)
    route, memory = _route(FakeBackend([_result(auxiliary=(("fake-small", aux),))]))
    route.call(_request())
    line = _line(memory)
    project.validate("tracesData", line)
    rows = project.model_calls([line])
    assert [(row["requestModel"], row["modelRole"], row["usage"]["inputTokens"]) for row in rows] == [
        ("fake-model", "main", 1000), ("fake-small", "auxiliary", 30),
    ]


@pytest.mark.parametrize("stop_reason", ["refusal", "max_tokens"])
def test_vision_engine_does_not_accept_refused_or_cut_off_output(tmp_path, stop_reason):
    route, memory = _route(FakeBackend([_result(text="합성", stop_reason=stop_reason)]))
    with pytest.raises(OcrFailed, match=stop_reason):
        VisionOcrEngine(route, "fake-model", prompt="읽어 주세요", max_side=None).read(_image(tmp_path))
    project.validate("tracesData", _line(memory))     # 종료 사유는 span에 남습니다.
