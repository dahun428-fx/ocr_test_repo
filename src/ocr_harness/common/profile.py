"""프로젝트 설정(Profile). 공용 코드가 프로젝트마다 달라지는 이름을 여기서 받습니다.

공용 계층은 "어떻게"(형식, 절차)만 알고 "무슨 이름으로"는 모릅니다.
서비스 이름, 속성 접두사, 스키마 버전처럼 프로젝트마다 다른 값은 이 객체 하나에 모아
공용 클래스(Telemetry, Ledger 등)에 넘깁니다. 두 번째 프로젝트는 Profile을 하나 더 만들면 됩니다.
"""
import re
from dataclasses import dataclass

# 프로젝트가 자기 것으로 쓸 수 없는 접두사. OTel 규약과 플랫폼이 이미 주인입니다.
RESERVED_NAMESPACES = frozenset({"gen_ai", "platform", "service", "error", "telemetry", "otel"})
# 속성 접두사의 모양: 소문자로 시작하고 소문자·숫자·밑줄만 (OTel 속성 이름 규칙).
_NAMESPACE = re.compile(r"^[a-z][a-z0-9_]*$")


@dataclass(frozen=True)
class Profile:
    """프로젝트 하나의 이름표. 한 번 만들면 바꾸지 않습니다 (실행 도중 이름이 바뀌면 기록이 섞입니다)."""

    service_name: str      # resource의 service.name
    scope_name: str        # get_tracer / get_logger에 넘기는 계측 범위 이름
    namespace: str         # 이 프로젝트가 직접 정의한 속성의 접두사 (예: "ocr" → ocr.run.id)
    schema_version: str    # 이 프로젝트 스키마 묶음의 버전. 줄마다 resource에 실립니다.
    item_id_prefix: str    # 항목 id 앞에 붙이는 글자 (예: "img-")

    def __post_init__(self):
        # 표준의 접두사를 가져다 쓰면 "누가 정한 이름인지"를 접두사로 가르는 규칙이 무너지므로 만들 때 막습니다.
        if not _NAMESPACE.match(self.namespace) or self.namespace in RESERVED_NAMESPACES:
            raise ValueError(f"프로젝트 속성 접두사로 쓸 수 없습니다: {self.namespace!r}")

    def attr(self, name: str) -> str:
        """이 프로젝트의 속성 이름을 만듭니다. attr("run.id") → "ocr.run.id"."""
        return f"{self.namespace}.{name}"
