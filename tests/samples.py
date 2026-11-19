"""스키마 테스트용 합성 레코드. 실제 데이터나 개인정보를 넣지 않습니다."""

D = "sha256:" + "a" * 64
TRACE = "0123456789abcdef0123456789abcdef"
SPAN = "0123456789abcdef"
V = "1.0.0"


def item():
    return {
        "schemaVersion": V,
        "recordType": "item",
        "itemId": "img-" + "a" * 32,
        "imageDigest": D,
        "datasetVersion": "1.0.0",
        "sourceFormat": "packaging-v1",
        "domain": "medicine-packaging",
        "productId": "prod-0001",
        "split": "dev",
        "image": {"width": 1200, "height": 800},
        "classification": "internal",
        "fields": [
            {"fieldId": "product-name", "queryType": "B", "gold": "합성정 10mg", "evidenceDocumentId": "mfds-0001"},
            {"fieldId": "expiry", "queryType": "A", "gold": "2027.01.01"},
        ],
        "queries": [
            {"queryId": "q-0001", "queryType": "C", "question": "이 약의 유효성분은?", "answer": "가상성분염"},
        ],
    }


def knowledge_document():
    return {
        "documentId": "mfds-0001",
        "content": "합성정10밀리그램(가상성분염)",
        "citation": "https://nedrug.mfds.go.kr/searchDrug",
        "classification": "public",
        "tenantId": "ocr-research",
        "allowedPrincipals": ["ocr-research"],
    }


def condition_manifest():
    return {
        "schemaVersion": V,
        "recordType": "conditionManifest",
        "conditionId": "c4",
        "version": "1.0.0",
        "model": {"requestModel": "fake-model", "authRoute": "fake"},
        "components": {
            "ocr": {"id": "paddleocr-ppocrv5-mobile", "version": "3.7.0"},
            "retrieval": {"id": "bm25", "version": "1.0.0"},
            "context": {"id": "ctx-default", "version": "1.0.0"},
            "history": None,
            "postprocess": {"id": "normalize", "version": "1.0.0"},
        },
        "promptTemplateDigest": D,
        "knowledgeIndexVersion": "1.0.0",
        "sdk": {"name": "claude-agent-sdk", "version": "0.0.0", "cliVersion": "0.0.0"},
        "policyVersion": "0.0.0",
        "platformContractVersion": "0.2.0",
        "semconvCommit": "76e0c19e7fe1",
    }


def _span(name, attributes, **extra):
    return {
        "schemaVersion": V,
        "recordType": "span",
        "runId": "run-0001",
        "traceId": TRACE,
        "spanId": SPAN,
        "name": name,
        "startTime": "2026-11-19T10:00:00+09:00",
        "endTime": "2026-11-19T10:00:01+09:00",
        "status": "ok",
        "attributes": attributes,
        **extra,
    }


def span_root():
    return _span("invoke_agent ocr-harness", {
        "gen_ai.operation.name": "invoke_agent",
        "gen_ai.agent.name": "ocr-harness",
        "gen_ai.agent.version": "1.0.0",
        "ocr.item.id": "img-" + "a" * 32,
        "ocr.condition.id": "c4",
        "ocr.manifest.digest": D,
        "ocr.dataset.version": "1.0.0",
        "ocr.repeat": 0,
        "platform.idempotency_key": "img-" + "a" * 32 + ".c4.1.0.0.r0",
        "ocr.outcome": "ok",
    })


def span_ocr():
    return _span("ocr", {
        "ocr.engine.name": "paddleocr",
        "ocr.engine.version": "3.7.0",
        "ocr.output.digest": D,
        "ocr.output.ref": "raw://" + D,
        "ocr.cache.hit": True,
    }, parentSpanId="fedcba9876543210")


def span_retrieval():
    return _span("retrieval mfds", {
        "gen_ai.operation.name": "retrieval",
        "gen_ai.data_source.id": "mfds",
        "gen_ai.retrieval.top_k": 5,
        "gen_ai.retrieval.documents": [{"id": "mfds-0001", "score": 0.9, "rank": 1, "selected": True}],
        "ocr.retrieval.query.digest": D,
    }, parentSpanId="fedcba9876543210")


def span_context():
    return _span("context", {
        "ocr.context.template.digest": D,
        "ocr.context.order": ["instruction", "mfds-0001", "ocr"],
        "ocr.context.tokens": {"instruction": 40, "ocr": 120, "documents": 300, "history": 0, "image": 0},
    }, parentSpanId="fedcba9876543210")


def span_chat():
    return _span("chat fake-model", {
        "gen_ai.operation.name": "chat",
        "gen_ai.provider.name": "anthropic",
        "gen_ai.request.model": "fake-model",
        "gen_ai.input.messages_ref": "raw://" + D,
        "gen_ai.output.messages_ref": "raw://" + D,
        "ocr.prompt.digest": D,
        "ocr.model_call.ids": ["mc-0001"],
    }, parentSpanId="fedcba9876543210")


def span_postprocess():
    return _span("postprocess", {
        "platform.guardrail.mode": "check_only",
        "ocr.postprocess.kind": "deterministic",
        "ocr.postprocess.rules": [{"id": "normalize-units", "result": "changed"}],
        "ocr.output.before.digest": D,
        "ocr.output.after.digest": D,
    }, parentSpanId="fedcba9876543210")


def raw_payload():
    return {
        "schemaVersion": V,
        "recordType": "rawPayload",
        "runId": "run-0001",
        "traceId": TRACE,
        "spanId": SPAN,
        "digest": D,
        "kind": "output_messages",
        "content": "{}",
        "retention": "study",
    }


def model_call():
    return {
        "schemaVersion": V,
        "recordType": "modelCall",
        "runId": "run-0001",
        "traceId": TRACE,
        "spanId": SPAN,
        "modelCallId": "mc-0001",
        "itemId": "img-" + "a" * 32,
        "conditionId": "c4",
        "at": "2026-11-19T10:00:00+09:00",
        "attempt": 0,
        "modelRole": "main",
        "authRoute": "subscription_oauth",
        "provider": "external",
        "routeDecisionId": "route-default",
        "usage": {"inputTokens": 250, "outputTokens": 9},
        "attributes": {
            "gen_ai.request.model": "fake-model",
            "gen_ai.usage.cache_read.input_tokens": 25000,
            "gen_ai.usage.cache_write.input_tokens": 1200,
            "ocr.usage.hidden_context_tokens": 24000,
        },
        "cost": {"sdkReportedUsd": 0.004, "computedUsd": 0.004, "priceTableVersion": "2026.11.19"},
        "errorCode": None,
        "durationMs": 900,
    }


def field_score():
    return {
        "schemaVersion": V,
        "recordType": "fieldScore",
        "runId": "run-0001",
        "traceId": TRACE,
        "scoreId": "sc-0001",
        "itemId": "img-" + "a" * 32,
        "productId": "prod-0001",
        "target": {"kind": "field", "fieldId": "product-name"},
        "queryType": "B",
        "ocrMisread": True,
        "metric": "normalized_exact_match",
        "score": 1.0,
        "stage": "after_postprocess",
        "datasetVersion": "1.0.0",
        "agentVersion": "1.0.0",
        "manifestDigest": D,
        "scorerVersion": "1.0.0",
    }


def evaluation():
    return {
        "evaluationId": "run-0001.c4.b-misread-em",
        "datasetVersion": "1.0.0",
        "agentVersion": "1.0.0",
        "manifestDigest": D,
        "policyVersion": "0.0.0",
        "metric": "b_misread_normalized_exact_match",
        "score": 0.62,
        "threshold": 0.5,
        "passed": True,
        "traceId": TRACE,
    }


ALL = {
    "item": item,
    "knowledgeDocument": knowledge_document,
    "conditionManifest": condition_manifest,
    "span": span_root,
    "rawPayload": raw_payload,
    "modelCall": model_call,
    "fieldScore": field_score,
    "evaluation": evaluation,
}
SPANS = [span_root, span_ocr, span_retrieval, span_context, span_chat, span_postprocess]
