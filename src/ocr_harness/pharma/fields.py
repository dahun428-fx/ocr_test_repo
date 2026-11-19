"""의약품 포장 라벨(단어 조각)에서 필드를 뽑는 규칙. 공용 틀은 ocr_harness.common.fields에 있습니다.

M1a 탐색용 규칙입니다. 유형 코드: 1 제품명, 2 원료약품·분량, 3 사용기한.
"""
import re

from ocr_harness.common.fields import Field, FieldExtractor, Normalizer, Token, reading_order

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
# 비교용 정규화: 단위 표기 통일, 공백·괄호·구두점 제거 (소문자 변환은 Normalizer가 합니다).
# "밀리그램"을 "그램"보다 먼저 바꿔야 "밀리g"가 되지 않습니다.
norm = Normalizer(
    replacements=(("밀리그램", "mg"), ("밀리리터", "ml"), ("그램", "g")),
    strip=r"[\s()\[\]【】〔〕·.,:/\-_®™*]",
)


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


class PharmaFieldExtractor(FieldExtractor):
    """의약품 포장의 필드 규칙. 오인식 판정은 부모의 것을 쓰고, 정규화 규칙만 이 도메인의 것으로 바꿉니다."""

    normalizer = norm

    def extract(self, label: dict) -> list[Field]:
        """라벨 1장에서 제품명, 사용기한, 유효성분명을 뽑습니다. 확실하지 않으면 뽑지 않습니다."""
        fields = []
        # 제품명 (유형 1): 기호와 머리말을 뺀 나머지 전부. 공개 근거로 교정할 수 있으므로 B.
        name = [t for t in _tokens(label, 1) if not NOISE.match(t.text) and norm(t.text)]
        if name:
            fields.append(Field("product-name", "B", tuple(name)))
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
                fields.append(Field("active-ingredient", "B", tuple(active)))
            break  # 첫 번째 표지 단어만 씁니다.
        return fields


# 규칙에 상태가 없어서 하나만 만들어 두고 씁니다. 아래 두 함수는 그 객체에 묶은 것입니다 (기존 호출부용).
EXTRACTOR = PharmaFieldExtractor()
extract_fields = EXTRACTOR.extract
is_misread = EXTRACTOR.is_misread
