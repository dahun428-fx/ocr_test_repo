"""M1a (가): 단어 조각 라벨에서 필드 값을 복원할 수 있는지 세어 봅니다.

데이터가 있는 PC에서 실행합니다. 집계 숫자만 출력하고, 원문이나 개인정보는 출력하지 않습니다.

    python spikes/m1a_field_restore.py <라벨 JSON 폴더>

유형 코드 (485장 샘플에서 확인): 1 제품명, 2 원료약품·분량, 3 사용기한, 4 용법·주의사항,
5 기타, 9 인증 마크·로고, 0 글자 없음.
"""
import collections
import glob
import json
import os
import re
import sys

DATE = re.compile(r"(?<!\d)(20\d{2}|\d{2})\s*[./-]\s*(\d{1,2})(?:\s*[./-]\s*(\d{1,2}))?(?!\d)")
AMOUNT = re.compile(r"\d+(?:[.,]\d+)?\s*(?:mg|g|mL|ml|μg|mcg|㎎|㎖|IU|%|밀리그램|그램|밀리리터)")
ACTIVE_HEAD = re.compile(r"유효성분|주성분")
NOISE = re.compile(r"^(R|®|TM|™|【?\[?제품명\]?】?)$")


def norm(text: str) -> str:
    """비교용 정규화: 공백·괄호·구두점 제거, 소문자, 단위 표기 통일."""
    text = text.lower().replace("밀리그램", "mg").replace("밀리리터", "ml").replace("그램", "g")
    return re.sub(r"[\s()\[\]【】〔〕·.,:/\-_®™]", "", text)


def words(label: dict) -> dict[int, list[str]]:
    by_type = collections.defaultdict(list)
    for annotation in label["annotations"]:
        for polygon in annotation["polygons"]:
            if polygon["text"].strip():
                by_type[polygon["type"]].append(polygon["text"].strip())
    return by_type


def check_product_name(tokens: list[str], meta_name: str) -> str:
    kept = [t for t in tokens if not NOISE.match(t)]
    if not kept:
        return "글자 없음"
    target = norm(meta_name)
    hit = [t for t in kept if norm(t) and norm(t) in target]
    if len(hit) == len(kept):
        return "성공"
    if hit:
        return "일부 조각이 제품 정보와 다름"
    return "제품 정보와 불일치"


def check_expiry(tokens: list[str]) -> str:
    found = DATE.findall(" ".join(tokens))
    if not found:
        return "날짜 형식 없음"
    if len(found) > 1:
        return "날짜 여러 개"
    year, month, day = found[0]
    if not 1 <= int(month) <= 12 or (day and not 1 <= int(day) <= 31):
        return "날짜 값 이상"
    return "성공"


def check_ingredient(tokens: list[str]) -> str:
    text = " ".join(tokens)
    if not AMOUNT.search(text):
        return "분량 없음"
    if not ACTIVE_HEAD.search(text):
        return "유효성분 표지 없음"
    return "성공"


def main(folder: str) -> None:
    files = sorted(glob.glob(os.path.join(folder, "**", "*.json"), recursive=True))
    results = {name: collections.Counter() for name in ("제품명", "사용기한", "원료약품")}
    products = collections.defaultdict(lambda: collections.Counter())
    type_images = collections.Counter()
    for path in files:
        with open(path, encoding="utf-8") as handle:
            label = json.load(handle)
        meta_name = label["images"][0]["product_name"]
        by_type = words(label)
        for code in by_type:
            type_images[code] += 1
        checks = {
            "제품명": check_product_name(by_type[1], meta_name) if by_type.get(1) else None,
            "사용기한": check_expiry(by_type[3]) if by_type.get(3) else None,
            "원료약품": check_ingredient(by_type[2]) if by_type.get(2) else None,
        }
        for name, outcome in checks.items():
            if outcome is None:
                continue
            results[name][outcome] += 1
            if outcome == "성공":
                products[meta_name][name] += 1
    print(f"이미지 {len(files)}장, 제품 {len(products)}종 (성공 필드가 하나라도 있는 제품)")
    print("유형별 이미지 수:", dict(sorted(type_images.items())))
    for name, counter in results.items():
        total = sum(counter.values())
        print(f"[{name}] 대상 {total}, 성공 {counter['성공']}")
        for reason, count in counter.most_common():
            if reason != "성공":
                print(f"    실패: {reason} {count}")
    for name in results:
        covered = sum(1 for c in products.values() if c[name])
        print(f"{name} 복원 성공 필드가 있는 제품 수: {covered}")


if __name__ == "__main__":
    main(sys.argv[1])
