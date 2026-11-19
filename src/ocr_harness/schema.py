"""JSONL 기록 스키마 8종 검증 (설계: docs/schema-design.md).

evaluation과 knowledgeDocument는 플랫폼 계약 0.2.0 파일을 고치지 않고 그대로 씁니다.
나머지 6종은 이 저장소에서 정의하고 schemas/released/<버전>.json으로 동결합니다.
"""
import json
from functools import cache
from importlib import resources

from jsonschema import Draft202012Validator

# 이 저장소가 정의하는 스키마 묶음의 버전. 스키마를 바꾸면 올리고 released 스냅샷을 추가합니다.
SCHEMA_VERSION = "1.0.0"
# 사본으로 가져온 플랫폼 계약의 버전.
PLATFORM_CONTRACT_VERSION = "0.2.0"
# 이 저장소가 정의하는 기록: 종류 이름 → 스키마 파일 이름.
OWN = {
    "item": "item",
    "conditionManifest": "condition-manifest",
    "span": "span",
    "rawPayload": "raw-payload",
    "modelCall": "model-call",
    "fieldScore": "field-score",
}
# validate()가 받는 종류 전체. 뒤의 둘은 플랫폼 계약입니다.
KINDS = (*OWN, "knowledgeDocument", "evaluation")


class SchemaError(ValueError):
    """레코드가 스키마에 맞지 않을 때."""


def _load(relative: str) -> dict:
    """패키지에 들어 있는 스키마 JSON 파일을 읽습니다 (설치된 뒤에도 같은 경로로 읽힙니다)."""
    return json.loads(resources.files("ocr_harness").joinpath(f"schemas/{relative}").read_text("utf-8"))


@cache
def _schema(kind: str) -> dict:
    """종류 이름에 해당하는 JSON Schema. 모르는 종류면 KeyError."""
    if kind in OWN:
        return _load(f"{OWN[kind]}.schema.json")
    platform = f"platform/{PLATFORM_CONTRACT_VERSION}"
    if kind == "evaluation":
        return _load(f"{platform}/evaluation.schema.json")
    if kind == "knowledgeDocument":
        # 플랫폼 검색 응답의 문서 1건 형식을 그대로 씁니다.
        return _load(f"{platform}/retrieval.schema.json")["properties"]["documents"]["items"]
    raise KeyError(kind)


# 검증기를 만드는 비용이 있어 종류별로 한 번만 만들어 둡니다.
@cache
def _validator(kind: str) -> Draft202012Validator:
    return Draft202012Validator(_schema(kind))


def bundle() -> dict:
    """현재 스키마 전체. released 스냅샷과 같은지 테스트로 검사합니다."""
    return {
        "schemaVersion": SCHEMA_VERSION,
        "platformContractVersion": PLATFORM_CONTRACT_VERSION,
        "schemas": {kind: _schema(kind) for kind in KINDS},
    }


def validate(kind: str, record: dict) -> None:
    """맞지 않으면 모든 위반 내용을 담아 SchemaError를 냅니다."""
    # 첫 오류에서 멈추지 않고 전부 모읍니다. 위치(경로) 순으로 정렬해 메시지가 매번 같게 합니다.
    errors = sorted(_validator(kind).iter_errors(record), key=lambda e: [str(p) for p in e.path])
    if errors:
        detail = "; ".join(f"{'/'.join(map(str, e.path)) or '(root)'}: {e.message}" for e in errors)
        raise SchemaError(f"{kind}: {detail}")
