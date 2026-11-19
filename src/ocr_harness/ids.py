"""id와 해시 만들기. 형식은 플랫폼 계약 0.2.0의 id·digest 규칙을 따릅니다."""
import hashlib
import json
import re

DIGEST = re.compile(r"^sha256:([a-f0-9]{64})$")


def item_id(image_digest: str) -> str:
    """이미지 해시에서 항목 id를 만듭니다 (`img-` + 해시 앞 32자)."""
    found = DIGEST.match(image_digest)
    if not found:
        raise ValueError(f"sha256 해시가 아닙니다: {image_digest!r}")
    return "img-" + found.group(1)[:32]


def manifest_digest(manifest: dict) -> str:
    """조건 선언의 해시. 키 순서와 공백에 영향받지 않도록 정규화한 JSON으로 계산합니다."""
    canonical = json.dumps(manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()
