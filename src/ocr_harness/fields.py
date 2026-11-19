"""단어 조각 라벨에서 필드를 뽑고, OCR 결과가 그 필드를 맞게 읽었는지 판정합니다.

M1a 탐색용 규칙입니다. 유형 코드: 1 제품명, 2 원료약품·분량, 3 사용기한.
"""
import re
from dataclasses import dataclass

# 날짜: "2027.01.01", "27-1", "2027 / 01" 같은 표기. 앞뒤에 숫자가 붙어 있으면 날짜로 보지 않습니다.
DATE = re.compile(r"(?<!\d)(?:20\d{2}|\d{2})\s*[./-]\s*\d{1,2}(?:\s*[./-]\s*\d{1,2})?(?!\d)")
# 분량: 숫자 + 단위 ("10mg", "0.5 밀리리터", "5%").
AMOUNT = re.compile(r"\d+(?:[.,]\d+)?\s*(?:mg|g|mL|ml|μg|mcg|㎎|㎖|IU|%|밀리그램|그램|밀리리터)")
# 유효성분 이름이 시작되는 자리를 알려 주는 표지 단어.
ACTIVE_HEAD = re.compile(r"유효성분|주성분")
# 제품명 유형에 섞여 있지만 이름이 아닌 조각 (등록상표 기호, "[제품명]" 머리말 등).
NOISE = re.compile(r"^(R|®|TM|™|\*|·|【?\[?제품명\]?】?)$")
# 표지 단어 뒤에서 성분명으로 볼 최대 단어 수. 그 이상은 다른 문장으로 넘어간 것으로 봅니다.
MAX_ACTIVE_WORDS = 6
# 라벨 단어 상자와 OCR 줄 상자가 "같은 자리"라고 볼 최소 겹침 비율 (작은 상자 넓이 기준).
MIN_OVERLAP = 0.3

# 축에 평행한 사각형: (왼쪽 x, 위 y, 오른쪽 x, 아래 y). 이미지 좌표라 y는 아래로 갈수록 커집니다.
Box = tuple[float, float, float, float]


@dataclass(frozen=True)
class Token:
    """글자 조각 하나와 그 위치. 라벨의 단어, OCR의 줄 모두 이 형태로 다룹니다."""

    text: str
    box: Box  # x1, y1, x2, y2


@dataclass(frozen=True)
class Field:
    """라벨에서 뽑은 필드 하나 (예: 제품명). 정답 값은 tokens의 글자입니다."""

    name: str
    query_type: str  # A: 포장에만 있는 값, B: 공개 근거로 교정 가능한 값
    tokens: tuple[Token, ...]


def norm(text: str) -> str:
    """비교용 정규화: 공백·괄호·구두점 제거, 소문자, 단위 표기 통일."""
    text = text.lower().replace("밀리그램", "mg").replace("밀리리터", "ml").replace("그램", "g")
    return re.sub(r"[\s()\[\]【】〔〕·.,:/\-_®™*]", "", text)


def _tokens(label: dict, type_code: int) -> list[Token]:
    """라벨에서 유형 코드가 type_code인 단어만 모읍니다. 다각형은 감싸는 사각형으로 바꿉니다."""
    found = []
    for annotation in label["annotations"]:
        for polygon in annotation["polygons"]:
            text = polygon["text"].strip()
            # 다른 유형, 빈 글자, 좌표 없는 조각은 건너뜁니다.
            if polygon["type"] != type_code or not text or not polygon.get("points"):
                continue
            xs = [p[0] for p in polygon["points"]]
            ys = [p[1] for p in polygon["points"]]
            found.append(Token(text, (min(xs), min(ys), max(xs), max(ys))))
    return found


def reading_order(tokens: list[Token]) -> list[Token]:
    """라벨 순서는 읽는 순서가 아니므로, 세로 중심이 가까운 단어를 한 줄로 묶어 왼쪽부터 읽습니다."""
    lines: list[dict] = []
    # 위에서 아래로 훑으면서, 바로 앞 줄과 세로 중심이 가까우면 같은 줄로 묶습니다.
    for token in sorted(tokens, key=lambda t: (t.box[1] + t.box[3]) / 2):
        center, height = (token.box[1] + token.box[3]) / 2, token.box[3] - token.box[1]
        # 기준은 두 글자 높이 중 큰 쪽의 60%. 글자 크기가 달라도 같은 줄이면 묶이게 합니다.
        if lines and abs(center - lines[-1]["center"]) < 0.6 * max(height, lines[-1]["height"]):
            lines[-1]["tokens"].append(token)
        else:
            lines.append({"center": center, "height": height, "tokens": [token]})
    # 줄 안에서는 왼쪽부터.
    return [t for line in lines for t in sorted(line["tokens"], key=lambda t: t.box[0])]


def extract_fields(label: dict) -> list[Field]:
    """라벨 1장에서 제품명, 사용기한, 유효성분명을 뽑습니다. 확실하지 않으면 뽑지 않습니다."""
    fields = []
    # 제품명 (유형 1): 기호와 머리말을 뺀 나머지 전부. 공개 근거로 교정할 수 있으므로 B.
    name = [t for t in _tokens(label, 1) if not NOISE.match(t.text) and norm(t.text)]
    if name:
        fields.append(Field("product_name", "B", tuple(name)))
    # 사용기한 (유형 3): 날짜가 정확히 하나일 때만. 제조일과 섞여 여러 개면 어느 것인지 알 수 없어 버립니다.
    # 포장에만 있는 값이므로 A.
    dates = [t for t in _tokens(label, 3) if DATE.search(t.text)]
    if len(dates) == 1:
        fields.append(Field("expiry", "A", tuple(dates)))
    # 유효성분명 (유형 2): 표지 단어("유효성분", "주성분") 바로 뒤부터 분량이 나오기 전까지의 단어.
    ingredient = reading_order(_tokens(label, 2))
    for index, token in enumerate(ingredient):
        if not ACTIVE_HEAD.search(token.text):
            continue
        active = []
        for following in ingredient[index + 1 : index + 1 + MAX_ACTIVE_WORDS]:
            # 분량만 있는 조각("10mg")에서 멈춥니다. 한글 이름과 분량이 붙은 조각("가상성분염10mg")은 이름으로 칩니다.
            if AMOUNT.search(following.text) and not re.search(r"[가-힣]{2,}", following.text):
                break
            if norm(following.text):
                active.append(following)
        if active:
            fields.append(Field("active_ingredient", "B", tuple(active)))
        break  # 첫 번째 표지 단어만 씁니다.
    return fields


def _overlaps(word: Box, line: Box) -> bool:
    """두 상자가 겹치는 넓이가 작은 상자 넓이의 MIN_OVERLAP 이상이면 같은 자리로 봅니다."""
    width = min(word[2], line[2]) - max(word[0], line[0])
    height = min(word[3], line[3]) - max(word[1], line[1])
    if width <= 0 or height <= 0:
        return False
    smaller = min((word[2] - word[0]) * (word[3] - word[1]), (line[2] - line[0]) * (line[3] - line[1]))
    return smaller > 0 and width * height / smaller >= MIN_OVERLAP


def is_misread(field: Field, ocr_lines: list[Token]) -> bool:
    """필드의 단어 하나라도 같은 자리의 OCR 글자에 없으면 오인식(누락 포함)입니다."""
    for word in field.tokens:
        # 이 단어 자리에 겹치는 OCR 줄을 왼쪽부터 이어 붙이고, 정규화한 단어가 그 안에 있는지 봅니다.
        # 겹치는 줄이 없으면 빈 문자열이 되어 누락도 오인식으로 잡힙니다.
        near = sorted((l for l in ocr_lines if _overlaps(word.box, l.box)), key=lambda l: l.box[0])
        if norm(word.text) not in norm("".join(l.text for l in near)):
            return True
    return False
