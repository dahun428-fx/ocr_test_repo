"""JSON Schema 묶음을 읽고 기록을 검증하는 공용 부분.

어떤 종류의 기록이 있고 스키마 파일이 어디 있는지는 프로젝트가 SchemaRegistry에 알려 줍니다.
이 파일은 "파일에서 읽기 → $ref를 사본으로 풀기 → 검증 → 읽을 만한 오류 글"만 압니다.
이 연구의 7종 목록은 ocr_harness.project에 있습니다.
"""
import json
from abc import ABC, abstractmethod
from collections.abc import Mapping
from functools import cache

from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012


class SchemaError(ValueError):
    """레코드가 스키마에 맞지 않을 때."""


class SchemaSource(ABC):
    """기록 한 종류의 스키마를 어디서 가져오는지 (전략 패턴).

    "우리 파일 전체"와 "남의 계약 파일의 일부"를 같은 방식으로 다루기 위한 것입니다.
    load는 "상대 경로 → 그 JSON 파일의 내용"을 돌려주는 함수이고 레지스트리가 넘겨 줍니다.
    """

    @abstractmethod
    def resolve(self, load) -> dict:
        """이 종류의 JSON Schema를 돌려줍니다."""


class FileSchema(SchemaSource):
    """스키마 파일 하나가 그대로 한 종류입니다."""

    def __init__(self, relative: str):
        self.relative = relative

    def resolve(self, load):
        return load(self.relative)


class SubSchema(SchemaSource):
    """스키마 파일 안의 한 부분을 한 종류로 씁니다.

    남의 계약을 고치지 않고 그 일부(예: 검색 응답 안의 문서 1건)만 가져다 쓸 때 필요합니다.
    사본을 잘라 따로 저장하면 원본과 달라질 수 있으므로, 파일은 그대로 두고 읽을 때 경로를 따라 들어갑니다.
    """

    def __init__(self, relative: str, path: tuple[str, ...]):
        self.relative = relative
        self.path = tuple(path)

    def resolve(self, load):
        node = load(self.relative)
        for key in self.path:
            node = node[key]
        return node


class SchemaRegistry:
    """프로젝트 하나의 스키마 묶음: 종류 목록, $ref 사본, 묶음 머리말.

    root        스키마 폴더. pathlib.Path도 되고 importlib.resources.files(...)가 주는 것도 됩니다
                (설치된 패키지 안에서도 같은 방식으로 읽기 위해서입니다).
    kinds       종류 이름 → SchemaSource. validate()가 받는 종류 전체이고, 이 순서가 bundle()의 순서입니다.
    references  $ref 주소 → 사본 파일의 상대 경로. 검증할 때 네트워크로 나가지 않게 합니다.
    header      bundle() 맨 위에 실을 값 (버전 등). 동결 스냅샷이 어느 버전의 것인지 알려 줍니다.
    """

    def __init__(self, root, kinds: Mapping[str, SchemaSource], references: Mapping[str, str] | None = None,
                 header: Mapping[str, str] | None = None):
        self._root = root
        self._kinds = dict(kinds)
        self._reference_files = dict(references or {})
        self._header = dict(header or {})
        # 인스턴스마다 따로 캐시합니다. 클래스에 @cache를 달면 레지스트리끼리 캐시가 섞이고 객체가 영영 남습니다.
        self._load = cache(self._read)
        self._validator = cache(self._build_validator)

    @property
    def kinds(self) -> tuple[str, ...]:
        """validate()가 받는 종류 이름 전체."""
        return tuple(self._kinds)

    def _read(self, relative: str) -> dict:
        """스키마 폴더 아래의 JSON 파일 하나를 읽습니다."""
        return json.loads(self._root.joinpath(relative).read_text(encoding="utf-8"))

    def schema(self, kind: str) -> dict:
        """종류 이름에 해당하는 JSON Schema. 모르는 종류면 KeyError."""
        return self._kinds[kind].resolve(self._load)

    def references(self) -> dict:
        """$ref 주소 → 사본 스키마."""
        return {uri: self._load(relative) for uri, relative in self._reference_files.items()}

    # 검증기를 만드는 비용이 있어 종류별로 한 번만 만들어 둡니다 (__init__의 cache).
    def _build_validator(self, kind: str) -> Draft202012Validator:
        # 사본에 $schema가 없을 수 있어서 2020-12 규격으로 읽으라고 알려 줍니다.
        registry = Registry().with_resources(
            (uri, Resource.from_contents(contents, default_specification=DRAFT202012))
            for uri, contents in self.references().items()
        )
        return Draft202012Validator(self.schema(kind), registry=registry)

    def bundle(self) -> dict:
        """현재 스키마 전체. 동결 스냅샷과 같은지 테스트로 검사하는 데 씁니다."""
        return {
            **self._header,
            "schemas": {kind: self.schema(kind) for kind in self._kinds},
            "references": self.references(),
        }

    def validate(self, kind: str, record: dict) -> None:
        """맞지 않으면 모든 위반 내용을 담아 SchemaError를 냅니다."""
        # 첫 오류에서 멈추지 않고 전부 모읍니다. 위치(경로) 순으로 정렬해 메시지가 매번 같게 합니다.
        errors = sorted(self._validator(kind).iter_errors(record), key=lambda e: [str(p) for p in e.path])
        if errors:
            detail = "; ".join(f"{'/'.join(map(str, e.path)) or '(root)'}: {_message(e)}" for e in errors)
            raise SchemaError(f"{kind}: {detail}")


def _message(error) -> str:
    """오류 한 건을 읽을 만한 길이의 글로 바꿉니다."""
    if error.validator == "contains":
        # OTLP 속성 배열에 "이 이름의 속성이 있어야 한다"는 규칙이 깨진 경우. 기본 메시지는 배열 전체를 쏟아내므로 이름만 알려 줍니다.
        key = error.validator_value.get("properties", {}).get("key", {}).get("const")
        if key:
            return f"필수 속성 없음: {key}"
    return error.message[:300]
