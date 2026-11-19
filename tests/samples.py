"""스키마 테스트용 합성 기록. 실제 데이터나 개인정보를 넣지 않습니다.

추적(tracesData)과 평가 이벤트(logsData)는 OTLP JSON 형식이라 손으로 쓰면 길어집니다.
그래서 ocr_harness.otlp의 도우미로 만들고, 형식 자체는 tests/test_otlp.py에서 글자 그대로 확인합니다.
"""
from ocr_harness import otlp

D = "sha256:" + "a" * 64          # 형식만 맞춘 가짜 해시
TRACE = "0123456789abcdef0123456789abcdef"   # traceId: 16진수 32자리
SPAN = "0123456789abcdef"                    # spanId: 16진수 16자리
PARENT = "fedcba9876543210"
V = "2.0.0"                        # 스키마 버전
ITEM = "img-" + "a" * 32
T0, T1 = "1795050000000000000", "1795050001000000000"   # 유닉스 나노초 (문자열)


def item():
    return {
        "schemaVersion": V,
        "recordType": "item",
        "itemId": ITEM,
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


# span 종류별 속성 (파이썬 값). otlp.span()이 OTLP 속성 배열로 바꿉니다. ---------------

def root_attributes():
    return {
        "gen_ai.operation.name": "invoke_agent",
        "gen_ai.agent.name": "ocr-harness",
        "gen_ai.agent.version": "1.0.0",
        "ocr.item.id": ITEM,
        "ocr.condition.id": "c4",
        "ocr.manifest.digest": D,
        "ocr.dataset.version": "1.0.0",
        "ocr.repeat": 0,
        "platform.idempotency_key": ITEM + ".c4.1.0.0.r0",
        "ocr.outcome": "ok",
    }


def ocr_attributes():
    return {
        "ocr.engine.name": "paddleocr",
        "ocr.engine.version": "3.7.0",
        "ocr.output.digest": D,
        "ocr.output.ref": "raw://" + D,
        "ocr.cache.hit": True,
    }


def retrieval_attributes():
    return {
        "gen_ai.operation.name": "retrieval",
        "gen_ai.data_source.id": "mfds",
        "gen_ai.retrieval.top_k": 5,
        "gen_ai.retrieval.documents": [{"id": "mfds-0001", "score": 0.9, "rank": 1, "selected": True}],
        "ocr.retrieval.query.digest": D,
    }


def context_attributes():
    return {
        "ocr.context.template.digest": D,
        "ocr.context.order": ["instruction", "mfds-0001", "ocr"],
        "ocr.context.tokens.instruction": 40,
        "ocr.context.tokens.ocr": 120,
        "ocr.context.tokens.documents": 300,
        "ocr.context.tokens.history": 0,
        "ocr.context.tokens.image": 0,
    }


def chat_attributes():
    """모델 호출 1회. 토큰과 비용이 여기에만 적힙니다 (비용 장부는 이 span에서 뽑습니다)."""
    return {
        "gen_ai.operation.name": "chat",
        "gen_ai.provider.name": "anthropic",
        "gen_ai.request.model": "fake-model",
        "gen_ai.usage.input_tokens": 250,
        "gen_ai.usage.output_tokens": 9,
        "gen_ai.usage.cache_read.input_tokens": 25000,
        "gen_ai.usage.cache_write.input_tokens": 1200,
        "gen_ai.input.messages_ref": "raw://" + D,
        "gen_ai.output.messages_ref": "raw://" + D,
        "ocr.prompt.digest": D,
        "ocr.model.role": "main",
        "ocr.model.auth_route": "subscription_oauth",
        "ocr.model.attempt": 0,
        "platform.model.provider": "external",
        "platform.route_decision.id": "route-default",
        "ocr.usage.hidden_context_tokens": 24000,
        "ocr.cost.sdk_reported_usd": 0.004,
        "ocr.cost.computed_usd": 0.004,
        "ocr.cost.price_table.version": "2026.11.19",
    }


def postprocess_attributes():
    return {
        "platform.guardrail.mode": "check_only",
        "ocr.postprocess.kind": "deterministic",
        "ocr.postprocess.rules": [{"id": "normalize-units", "result": "changed"}],
        "ocr.output.before.digest": D,
        "ocr.output.after.digest": D,
    }


SPAN_KINDS = {
    "invoke_agent ocr-harness": root_attributes,
    "ocr": ocr_attributes,
    "retrieval mfds": retrieval_attributes,
    "context": context_attributes,
    "chat fake-model": chat_attributes,
    "postprocess": postprocess_attributes,
}


def traces(name="invoke_agent ocr-harness", attributes=None, **span_extra):
    """span 하나가 든 추적 파일 한 줄 (OTLP TracesData)."""
    if attributes is None:
        attributes = SPAN_KINDS[name]()
    parent = None if name.startswith("invoke_agent") else PARENT
    one = otlp.span(TRACE, SPAN, name, T0, T1, attributes, parent_span_id=parent, **span_extra)
    return otlp.traces_data("run-0001", "0.1.0", [one])


def the_span(data):
    """위 traces()가 만든 한 줄에서 span을 꺼냅니다 (테스트에서 고쳐 보려고)."""
    return data["resourceSpans"][0]["scopeSpans"][0]["spans"][0]


def score_attributes():
    return {
        "gen_ai.evaluation.name": "normalized_exact_match",
        "gen_ai.evaluation.score.value": 1.0,
        "gen_ai.evaluation.score.label": "correct",
        "ocr.score.id": "sc-0001",
        "ocr.item.id": ITEM,
        "ocr.product.id": "prod-0001",
        "ocr.condition.id": "c4",
        "ocr.condition.version": "1.0.0",
        "ocr.manifest.digest": D,
        "ocr.dataset.version": "1.0.0",
        "ocr.scorer.version": "1.0.0",
        "ocr.target.kind": "field",
        "ocr.target.id": "product-name",
        "ocr.query.type": "B",
        "ocr.ocr_misread": True,
        "ocr.score.stage": "after_postprocess",
    }


def logs(attributes=None):
    """채점 1건이 든 평가 이벤트 파일 한 줄 (OTLP LogsData)."""
    event = otlp.evaluation_event(TRACE, SPAN, T1, score_attributes() if attributes is None else attributes)
    return otlp.logs_data("run-0001", "0.1.0", [event])


def the_event(data):
    return data["resourceLogs"][0]["scopeLogs"][0]["logRecords"][0]


def raw_payload():
    return {
        "schemaVersion": V,
        "recordType": "rawPayload",
        "runId": "run-0001",
        "traceId": TRACE,
        "spanId": SPAN,
        "digest": D,
        "kind": "output_messages",
        "content": [{"role": "assistant", "parts": [{"type": "text", "content": "합성정"}], "finish_reason": "stop"}],
        "retention": "study",
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
    "tracesData": traces,
    "logsData": logs,
    "rawPayload": raw_payload,
    "evaluation": evaluation,
}
