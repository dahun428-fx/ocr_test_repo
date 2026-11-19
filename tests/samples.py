"""스키마 테스트용 합성 레코드. 실제 데이터나 개인정보를 넣지 않습니다."""

H = "sha256:" + "a" * 64


def item():
    return {
        "item_id": H,
        "dataset_version": "ds-2026-11-19",
        "source_format": "packaging-v1",
        "domain": "medicine_packaging",
        "product_id": "prod-0001",
        "split": "dev",
        "image": {"sha256": H, "width": 1200, "height": 800},
        "fields": [
            {"field_id": "product_name", "query_type": "B", "gold": "합성정 10mg"},
            {"field_id": "expiry", "query_type": "A", "gold": "2027.01.01"},
        ],
    }


def trace():
    return {
        "trace_id": "tr-0001",
        "run_id": "run-0001",
        "item_id": H,
        "dataset_version": "ds-2026-11-19",
        "condition": "C1",
        "condition_version": "c1-v1",
        "repeat": 0,
        "idempotency_key": H + ":c1-v1:0",
        "started_at": "2026-11-19T10:00:00+09:00",
        "status": "ok",
        "steps": {
            "ocr": {"engine": "paddleocr", "engine_version": "x", "text": "합성정", "duration_ms": 10},
            "model_call": {
                "gen_ai.request.model": "fake-model",
                "prompt_sha256": H,
                "raw_output": "{}",
                "duration_ms": 5,
            },
            "postprocess": {"mode": "check_only", "rules": [], "output_before": "{}", "output_after": "{}"},
        },
    }


def eval_record():
    return {
        "eval_id": "ev-0001",
        "run_id": "run-0001",
        "trace_id": "tr-0001",
        "item_id": H,
        "field_id": "product_name",
        "query_type": "B",
        "ocr_misread": True,
        "dataset_version": "ds-2026-11-19",
        "eval_version": "eval-v1",
        "condition": "C1",
        "condition_version": "c1-v1",
        "metric": "normalized_exact_match",
        "stage": "after_postprocess",
        "value": 1.0,
        "scorer_version": "s-v1",
    }


def cost_ledger():
    return {
        "ledger_id": "lg-0001",
        "run_id": "run-0001",
        "trace_id": "tr-0001",
        "idempotency_key": H + ":c1-v1:0",
        "condition": "C1",
        "attempt": 0,
        "model_role": "main",
        "auth_route": "subscription_oauth",
        "gen_ai.request.model": "fake-model",
        "gen_ai.usage.input_tokens": 250,
        "gen_ai.usage.output_tokens": 9,
        "gen_ai.usage.cache_read.input_tokens": 0,
        "gen_ai.usage.cache_creation.input_tokens": 1200,
        "component_tokens": {"instruction": 40, "ocr_text": 120, "retrieved_docs": 0, "history": 0, "image": 0},
        "cost_usd_sdk_reported": 0.004,
        "cost_usd_computed": 0.004,
        "price_table_version": "2026-11-19",
        "error_code": None,
        "duration_ms": 900,
    }


ALL = {"item": item, "trace": trace, "eval_record": eval_record, "cost_ledger": cost_ledger}
