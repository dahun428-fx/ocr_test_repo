"""단어 조각 라벨에서 필드를 뽑고, OCR 결과가 그 필드를 맞게 읽었는지 판정합니다.

M1a 탐색용 규칙입니다. 유형 코드: 1 제품명, 2 원료약품·분량, 3 사용기한.
"""
import re
from dataclasses import dataclass

DATE = re.compile(r"(?<!\d)(?:20\d{2}|\d{2})\s*[./-]\s*\d{1,2}(?:\s*[./-]\s*\d{1,2})?(?!\d)")
AMOUNT = re.compile(r"\d+(?:[.,]\d+)?\s*(?:mg|g|mL|ml|μg|mcg|㎎|㎖|IU|%|밀리그램|그램|밀리리터)")
ACTIVE_HEAD = re.compile(r"유효성분|주성분")
NOISE = re.compile(r"^(R|®|TM|™|\*|·|【?\[?제품명\]?】?)$")
MAX_ACTIVE_WORDS = 6
MIN_OVERLAP = 0.3

Box = tuple[float, float, float, float]


@dataclass(frozen=True)
class Token:
    text: str
    box: Box  # x1, y1, x2, y2


@dataclass(frozen=True)
class Field:
    name: str
    query_type: str  # A: 포장에만 있는 값, B: 공개 근거로 교정 가능한 값
    tokens: tuple[Token, ...]


def norm(text: str) -> str:
    """비교용 정규화: 공백·괄호·구두점 제거, 소문자, 단위 표기 통일."""
    text = text.lower().replace("밀리그램", "mg").replace("밀리리터", "ml").replace("그램", "g")
    return re.sub(r"[\s()\[\]【】〔〕·.,:/\-_®™*]", "", text)


def _tokens(label: dict, type_code: int) -> list[Token]:
    found = []
    for annotation in label["annotations"]:
        for polygon in annotation["polygons"]:
            text = polygon["text"].strip()
            if polygon["type"] != type_code or not text or not polygon.get("points"):
                continue
            xs = [p[0] for p in polygon["points"]]
            ys = [p[1] for p in polygon["points"]]
            found.append(Token(text, (min(xs), min(ys), max(xs), max(ys))))
    return found


def extract_fields(label: dict) -> list[Field]:
    fields = []
    name = [t for t in _tokens(label, 1) if not NOISE.match(t.text) and norm(t.text)]
    if name:
        fields.append(Field("product_name", "B", tuple(name)))
    dates = [t for t in _tokens(label, 3) if DATE.search(t.text)]
    if len(dates) == 1:
        fields.append(Field("expiry", "A", tuple(dates)))
    ingredient = _tokens(label, 2)
    for index, token in enumerate(ingredient):
        if not ACTIVE_HEAD.search(token.text):
            continue
        active = []
        for following in ingredient[index + 1 : index + 1 + MAX_ACTIVE_WORDS]:
            if AMOUNT.search(following.text) and not re.search(r"[가-힣]{2,}", following.text):
                break
            if norm(following.text):
                active.append(following)
        if active:
            fields.append(Field("active_ingredient", "B", tuple(active)))
        break
    return fields


def _overlaps(word: Box, line: Box) -> bool:
    width = min(word[2], line[2]) - max(word[0], line[0])
    height = min(word[3], line[3]) - max(word[1], line[1])
    if width <= 0 or height <= 0:
        return False
    smaller = min((word[2] - word[0]) * (word[3] - word[1]), (line[2] - line[0]) * (line[3] - line[1]))
    return smaller > 0 and width * height / smaller >= MIN_OVERLAP


def is_misread(field: Field, ocr_lines: list[Token]) -> bool:
    """필드의 단어 하나라도 같은 자리의 OCR 글자에 없으면 오인식(누락 포함)입니다."""
    for word in field.tokens:
        near = sorted((l for l in ocr_lines if _overlaps(word.box, l.box)), key=lambda l: l.box[0])
        if norm(word.text) not in norm("".join(l.text for l in near)):
            return True
    return False
