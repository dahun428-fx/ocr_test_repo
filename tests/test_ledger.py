"""비용 장부는 원본이 아니라 chat span에서 뽑는 집계입니다 (ocr_harness.ledger)."""
from ocr_harness import ledger, otlp

import samples


def _run():
    """루트 1개 + 모델 호출 2개(주 모델, 실패한 보조 모델) + OCR 1개가 든 추적 한 줄."""
    aux_attributes = samples.chat_attributes() | {
        "ocr.model.role": "auxiliary", "gen_ai.request.model": "fake-small",
        "gen_ai.usage.input_tokens": 30, "gen_ai.usage.output_tokens": 2,
    }
    del aux_attributes["ocr.cost.sdk_reported_usd"]      # 모르는 비용은 속성을 뺍니다.
    return otlp.encode_traces(samples.run_spans([
        ("invoke_agent ocr-harness", samples.root_attributes(), None),
        ("chat fake-model", samples.chat_attributes(), None),
        ("chat fake-small", aux_attributes, "RATE_LIMITED"),
        ("ocr", samples.ocr_attributes(), None),
    ]))


def test_one_row_per_model_call_span():
    rows = ledger.model_calls([_run()])
    assert [row["requestModel"] for row in rows] == ["fake-model", "fake-small"]


def test_row_carries_item_and_condition_from_the_root_span():
    row = ledger.model_calls([_run()])[0]
    assert (row["runId"], row["itemId"], row["conditionId"]) == ("run-0001", samples.ITEM, "c4")


def test_row_uses_platform_usage_names():
    # 플랫폼 model-result 계약의 이름: usage.inputTokens, usage.outputTokens, provider, routeDecisionId
    row = ledger.model_calls([_run()])[0]
    assert row["usage"] == {"inputTokens": 250, "outputTokens": 9}
    assert (row["provider"], row["routeDecisionId"]) == ("external", "route-default")
    assert (row["modelRole"], row["authRoute"], row["requestModel"]) == ("main", "subscription_oauth", "fake-model")
    assert (row["cacheReadInputTokens"], row["cacheWriteInputTokens"]) == (25000, 1200)
    assert row["durationMs"] >= 0


def test_unknown_cost_is_none_and_errors_are_kept():
    row = ledger.model_calls([_run()])[1]
    assert row["cost"]["sdkReportedUsd"] is None
    assert row["cost"]["computedUsd"] == 0.004
    assert row["errorCode"] == "RATE_LIMITED"       # 실패한 호출도 장부에 남습니다 (CLAUDE.md 규칙 7, 8).
    assert ledger.model_calls([_run()])[0]["errorCode"] is None
