"""데이터의 제품명을 공개 의약품 목록(식약처 품목명)과 맞춰 봅니다. M1a 탐색용 규칙입니다."""
import collections
import re

from ocr_harness.fields import norm

BRACKETS = re.compile(r"\([^()]*\)")
# 제품명 뒤에 붙은 포장 단위: "30정", "5g x 2tube", "0.5ml/관×60관" 등
PACK = re.compile(r"\s+\d[\d.,]*\s*(?:정|캡슐|포|관|매|병|개|회|tabs?\.?|g|mg|ml|l|tube)\b.*$", re.IGNORECASE)


def _keys(name: str) -> tuple[str, str]:
    """(전체 이름 키, 괄호 안 성분명을 뺀 기본 키)."""
    return norm(name), norm(BRACKETS.sub("", name))


def build_index(public_names: list[str]) -> dict:
    full, base = collections.defaultdict(set), collections.defaultdict(set)
    for name in public_names:
        full_key, base_key = _keys(name)
        full[full_key].add(name)
        base[base_key].add(name)
    return {"full": full, "base": base}


def match(product_name: str, index: dict) -> tuple[str, list[str]]:
    """("exact" | "ambiguous" | "unmatched", 후보 품목명)."""
    full_key, base_key = _keys(PACK.sub("", product_name.strip()))
    if len(index["full"].get(full_key, ())) == 1:
        return "exact", sorted(index["full"][full_key])
    candidates = index["full"].get(full_key, set()) | index["base"].get(base_key, set())
    if len(candidates) == 1:
        return "exact", sorted(candidates)
    if not candidates and base_key:
        for key, names in index["base"].items():
            if key.startswith(base_key) or base_key.startswith(key):
                candidates |= names
        if candidates:
            return "ambiguous", sorted(candidates)
    return ("ambiguous", sorted(candidates)) if candidates else ("unmatched", [])
