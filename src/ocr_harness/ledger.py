"""비용 장부. 원본은 추적 파일의 chat span이고, 장부는 거기서 뽑는 집계입니다.

토큰과 비용을 한 곳(chat span)에만 적기 때문에 장부와 추적이 서로 어긋날 수 없습니다.
행의 키는 플랫폼 계약 0.2.0의 model-result와 같은 이름을 씁니다 (usage.inputTokens, provider, routeDecisionId).
"""
from collections.abc import Iterable

from ocr_harness import otlp


def model_calls(lines: Iterable[dict]) -> list[dict]:
    """추적 파일의 줄들(TracesData)에서 모델 호출 1회당 한 행을 만듭니다.

    재시도와 보조 모델 호출, 실패한 호출도 각각 한 행입니다 (CLAUDE.md 규칙 7, 8).
    """
    spans = [row for line in lines for row in otlp.flatten_spans(line)]
    # 항목 id와 조건 id는 루트 span에만 있으므로 traceId로 찾아 붙입니다.
    roots = {row["traceId"]: row["attributes"] for row in spans if row["name"].startswith("invoke_agent")}
    rows = []
    for row in spans:
        if not row["name"].startswith("chat"):
            continue
        a, root = row["attributes"], roots.get(row["traceId"], {})
        rows.append({
            "runId": row["resource"].get("ocr.run.id"),
            "traceId": row["traceId"],
            "spanId": row["spanId"],
            "itemId": root.get("ocr.item.id"),
            "conditionId": root.get("ocr.condition.id"),
            "requestModel": a.get("gen_ai.request.model"),
            "modelRole": a.get("ocr.model.role"),
            "authRoute": a.get("ocr.model.auth_route"),
            "attempt": a.get("ocr.model.attempt"),
            "provider": a.get("platform.model.provider"),
            "routeDecisionId": a.get("platform.route_decision.id"),
            "usage": {"inputTokens": a.get("gen_ai.usage.input_tokens"), "outputTokens": a.get("gen_ai.usage.output_tokens")},
            "cacheReadInputTokens": a.get("gen_ai.usage.cache_read.input_tokens"),
            "cacheWriteInputTokens": a.get("gen_ai.usage.cache_write.input_tokens"),
            "hiddenContextTokens": a.get("ocr.usage.hidden_context_tokens"),
            # 비용을 모르면 속성이 없으므로 None이 됩니다. 0과 "모름"을 구분합니다.
            "cost": {
                "sdkReportedUsd": a.get("ocr.cost.sdk_reported_usd"),
                "computedUsd": a.get("ocr.cost.computed_usd"),
                "priceTableVersion": a.get("ocr.cost.price_table.version"),
            },
            "errorCode": a.get("error.type"),
            "durationMs": (int(row["endTimeUnixNano"]) - int(row["startTimeUnixNano"])) // 1_000_000,
        })
    return rows
