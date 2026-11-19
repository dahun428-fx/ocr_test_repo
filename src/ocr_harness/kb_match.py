"""데이터의 제품명을 공개 의약품 목록(식약처 품목명)과 맞춰 봅니다. M1a 탐색용 규칙입니다."""
import collections
import re

from ocr_harness.fields import norm

# 괄호와 그 안의 글자: "합성정10밀리그램(가상성분염)"의 "(가상성분염)".
BRACKETS = re.compile(r"\([^()]*\)")
# 제품명 뒤에 붙은 포장 단위: "30정", "5g x 2tube", "0.5ml/관×60관" 등
PACK = re.compile(r"\s+\d[\d.,]*\s*(?:정|캡슐|포|관|매|병|개|회|tabs?\.?|g|mg|ml|l|tube)\b.*$", re.IGNORECASE)


def _keys(name: str) -> tuple[str, str]:
    """(전체 이름 키, 괄호 안 성분명을 뺀 기본 키)."""
    return norm(name), norm(BRACKETS.sub("", name))


def build_index(public_names: list[str]) -> dict:
    """공개 품목명 목록으로 찾아보기 표 두 개를 만듭니다: 전체 이름 기준, 괄호를 뺀 기본 이름 기준."""
    full, base = collections.defaultdict(set), collections.defaultdict(set)
    for name in public_names:
        full_key, base_key = _keys(name)
        full[full_key].add(name)
        base[base_key].add(name)
    return {"full": full, "base": base}


def match(product_name: str, index: dict) -> tuple[str, list[str]]:
    """("exact" | "ambiguous" | "unmatched", 후보 품목명)."""
    # 포장 단위("30정")는 품목명에 없으므로 떼고 비교합니다.
    full_key, base_key = _keys(PACK.sub("", product_name.strip()))
    # 1) 전체 이름이 정확히 하나와 같으면 확정. 기본 이름이 같은 다른 품목이 있어도 전체 이름 일치를 우선합니다.
    if len(index["full"].get(full_key, ())) == 1:
        return "exact", sorted(index["full"][full_key])
    # 2) 전체 이름 또는 기본 이름이 같은 품목을 모두 모아, 하나뿐이면 확정.
    candidates = index["full"].get(full_key, set()) | index["base"].get(base_key, set())
    if len(candidates) == 1:
        return "exact", sorted(candidates)
    # 3) 하나도 없으면 한쪽이 다른 쪽의 앞부분인 품목을 후보로 냅니다 (용량 표기가 빠진 이름 등). 확정하지 않습니다.
    if not candidates and base_key:
        for key, names in index["base"].items():
            if key.startswith(base_key) or base_key.startswith(key):
                candidates |= names
        if candidates:
            return "ambiguous", sorted(candidates)
    return ("ambiguous", sorted(candidates)) if candidates else ("unmatched", [])
