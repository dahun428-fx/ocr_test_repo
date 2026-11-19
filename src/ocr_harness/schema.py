"""JSONL 기록 스키마 7종 검증 (설계: docs/schema-design.md).

  item, conditionManifest, rawPayload   이 저장소가 정의 (형식 규칙은 플랫폼 계약)
  tracesData, logsData                  OTLP JSON 형식 + 이 저장소의 속성 규칙
  knowledgeDocument, evaluation         플랫폼 계약 0.2.0 파일을 고치지 않고 그대로 사용

스키마 JSON은 tools/build_schemas.py가 만듭니다. 묶음 전체를 schemas/released/<버전>.json으로 동결합니다.
"""
import json
from functools import cache
from importlib import resources

from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

# 이 저장소가 정의하는 스키마 묶음의 버전. 스키마를 바꾸면 올리고 released 스냅샷을 추가합니다.
SCHEMA_VERSION = "2.0.0"
# 사본으로 가져온 플랫폼 계약의 버전.
PLATFORM_CONTRACT_VERSION = "0.2.0"
# 사본으로 가져온 OTel GenAI 시맨틱 규약의 커밋.
SEMCONV_COMMIT = "76e0c19e7fe1"
# 이 저장소가 정의하는 기록: 종류 이름 → 스키마 파일 이름.
OWN = {
    "item": "item",
    "conditionManifest": "condition-manifest",
    "tracesData": "traces-data",
    "logsData": "logs-data",
    "rawPayload": "raw-payload",
}
# validate()가 받는 종류 전체. 뒤의 둘은 플랫폼 계약입니다.
KINDS = (*OWN, "knowledgeDocument", "evaluation")

# rawPayload 스키마가 $ref로 가리키는 OTel 메시지 스키마. 주소는 원본의 위치이고, 내용은 저장소 안의 사본에서 읽습니다.
_OTEL_BASE = f"https://raw.githubusercontent.com/open-telemetry/semantic-conventions-genai/{SEMCONV_COMMIT}/model/gen-ai/"
_OTEL_FILES = ("gen-ai-input-messages.json", "gen-ai-output-messages.json")


class SchemaError(ValueError):
    """레코드가 스키마에 맞지 않을 때."""


def _load(relative: str) -> dict:
    """패키지에 들어 있는 스키마 JSON 파일을 읽습니다 (설치된 뒤에도 같은 경로로 읽힙니다)."""
    return json.loads(resources.files("ocr_harness").joinpath(f"schemas/{relative}").read_text("utf-8"))


@cache
def _references() -> dict:
    """$ref 주소 → 사본 스키마. 검증할 때 네트워크로 나가지 않게 합니다."""
    return {_OTEL_BASE + name: _load(f"otel-genai/{SEMCONV_COMMIT}/{name}") for name in _OTEL_FILES}


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
    # OTel 사본에는 $schema가 없어서 2020-12 규격으로 읽으라고 알려 줍니다.
    registry = Registry().with_resources(
        (uri, Resource.from_contents(contents, default_specification=DRAFT202012))
        for uri, contents in _references().items()
    )
    return Draft202012Validator(_schema(kind), registry=registry)


def bundle() -> dict:
    """현재 스키마 전체. released 스냅샷과 같은지 테스트로 검사합니다."""
    return {
        "schemaVersion": SCHEMA_VERSION,
        "platformContractVersion": PLATFORM_CONTRACT_VERSION,
        "semconvCommit": SEMCONV_COMMIT,
        "schemas": {kind: _schema(kind) for kind in KINDS},
        "references": _references(),
    }


def _message(error) -> str:
    """오류 한 건을 읽을 만한 길이의 글로 바꿉니다."""
    if error.validator == "contains":
        # "이 이름의 속성이 배열에 있어야 한다"는 규칙이 깨진 경우. 기본 메시지는 배열 전체를 쏟아내므로 이름만 알려 줍니다.
        key = error.validator_value.get("properties", {}).get("key", {}).get("const")
        if key:
            return f"필수 속성 없음: {key}"
    return error.message[:300]


def validate(kind: str, record: dict) -> None:
    """맞지 않으면 모든 위반 내용을 담아 SchemaError를 냅니다."""
    # 첫 오류에서 멈추지 않고 전부 모읍니다. 위치(경로) 순으로 정렬해 메시지가 매번 같게 합니다.
    errors = sorted(_validator(kind).iter_errors(record), key=lambda e: [str(p) for p in e.path])
    if errors:
        detail = "; ".join(f"{'/'.join(map(str, e.path)) or '(root)'}: {_message(e)}" for e in errors)
        raise SchemaError(f"{kind}: {detail}")
