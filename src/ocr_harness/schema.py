"""JSONL 레코드 스키마 4종(항목·트레이스·평가 기록·비용 장부) 검증."""
import json
from functools import cache
from importlib import resources

from jsonschema import Draft202012Validator

KINDS = ("item", "trace", "eval_record", "cost_ledger")


class SchemaError(ValueError):
    """레코드가 스키마에 맞지 않을 때."""


@cache
def _validator(kind: str) -> Draft202012Validator:
    if kind not in KINDS:
        raise KeyError(kind)
    text = resources.files("ocr_harness").joinpath(f"schemas/{kind}.schema.json").read_text("utf-8")
    return Draft202012Validator(json.loads(text))


def validate(kind: str, record: dict) -> None:
    """맞지 않으면 모든 위반 내용을 담아 SchemaError를 냅니다."""
    errors = sorted(_validator(kind).iter_errors(record), key=lambda e: list(e.path))
    if errors:
        detail = "; ".join(f"{'/'.join(map(str, e.path)) or '(root)'}: {e.message}" for e in errors)
        raise SchemaError(f"{kind}: {detail}")
