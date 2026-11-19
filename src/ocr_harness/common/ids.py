"""id와 해시 만들기. 형식은 플랫폼 계약 0.2.0의 id·digest 규칙을 따릅니다."""
import hashlib
import re

import rfc8785

# 플랫폼 계약의 해시 형식. 괄호 안이 16진수 64자리입니다.
DIGEST = re.compile(r"^sha256:([a-f0-9]{64})$")


def item_id(image_digest: str) -> str:
    """이미지 해시에서 항목 id를 만듭니다 (`img-` + 해시 앞 32자)."""
    found = DIGEST.match(image_digest)
    if not found:
        raise ValueError(f"sha256 해시가 아닙니다: {image_digest!r}")
    # 플랫폼 id는 소문자로 시작하고 64자 이내여야 해서, 접두사를 붙이고 32자만 씁니다.
    return "img-" + found.group(1)[:32]


def canonical_json(value) -> bytes:
    """RFC 8785(JSON Canonicalization Scheme)로 정규화한 JSON 바이트.

    키 정렬, 공백 제거, 숫자와 문자열 표기가 표준으로 정해져 있어서
    다른 언어로 구현해도 같은 내용이면 같은 바이트가 나옵니다.
    """
    return rfc8785.dumps(value)


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def manifest_digest(manifest: dict) -> str:
    """조건 선언의 해시 (플랫폼 manifestDigest). 키 순서와 공백에 영향받지 않습니다."""
    return _sha256(canonical_json(manifest))


def content_digest(content) -> str:
    """rawPayload.content의 해시. 글자열은 UTF-8 바이트 그대로, 구조가 있는 값은 정규화한 JSON으로 계산합니다."""
    if isinstance(content, str):
        return _sha256(content.encode("utf-8"))
    return _sha256(canonical_json(content))
