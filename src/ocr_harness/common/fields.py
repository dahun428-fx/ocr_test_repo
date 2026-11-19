"""위치가 있는 글자 조각(Token)과 필드(Field), 그리고 "OCR이 그 필드를 맞게 읽었는가"의 판정.

어느 문서 종류에나 같은 부분만 여기 둡니다: 상자 겹침, 읽는 순서, 정규화의 틀, 오인식 판정.
라벨에서 어떤 필드를 어떻게 뽑는지는 문서 종류마다 다르므로 FieldExtractor를 상속해 정합니다
(의약품 포장: ocr_harness.pharma.fields.PharmaFieldExtractor).
"""
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass

# 축에 평행한 사각형: (왼쪽 x, 위 y, 오른쪽 x, 아래 y). 이미지 좌표라 y는 아래로 갈수록 커집니다.
Box = tuple[float, float, float, float]


@dataclass(frozen=True)
class Token:
    """글자 조각 하나와 그 위치. 라벨의 단어, OCR의 줄 모두 이 형태로 다룹니다."""

    text: str
    box: Box  # x1, y1, x2, y2


@dataclass(frozen=True)
class Field:
    """라벨에서 뽑은 필드 하나 (예: 제품명). 정답 값은 tokens의 글자입니다.

    name은 item 기록의 fieldId로 그대로 쓰이므로 플랫폼 id 패턴(소문자, 숫자, 점, 붙임표)을 따릅니다.
    """

    name: str
    query_type: str  # A: 문서에만 있는 값, B: 공개 근거로 교정 가능한 값
    tokens: tuple[Token, ...]


@dataclass(frozen=True)
class Normalizer:
    """비교용 정규화 규칙. 소문자로 바꾸고 → 표기를 통일하고 → 뜻 없는 글자를 지웁니다.

    순서가 고정인 이유: 표기 통일("밀리그램" → "mg")이 지우기보다 먼저여야 통일할 글자가 남아 있습니다.
    무엇을 통일하고 무엇을 지울지는 문서 종류마다 다르므로 값으로 받습니다. 함수처럼 부릅니다: norm("글").
    """

    replacements: tuple[tuple[str, str], ...] = ()   # (바꿀 글자, 바뀐 글자). 적힌 순서대로 적용합니다.
    strip: str = r"\s"                               # 지울 글자의 정규식

    def __call__(self, text: str) -> str:
        text = text.lower()
        for old, new in self.replacements:
            text = text.replace(old, new)
        return re.sub(self.strip, "", text)


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


def overlaps(word: Box, line: Box, min_overlap: float) -> bool:
    """두 상자가 겹치는 넓이가 작은 상자 넓이의 min_overlap 이상이면 같은 자리로 봅니다."""
    width = min(word[2], line[2]) - max(word[0], line[0])
    height = min(word[3], line[3]) - max(word[1], line[1])
    if width <= 0 or height <= 0:
        return False
    smaller = min((word[2] - word[0]) * (word[3] - word[1]), (line[2] - line[0]) * (line[3] - line[1]))
    return smaller > 0 and width * height / smaller >= min_overlap


class FieldExtractor(ABC):
    """문서 종류 하나의 필드 규칙. 자식은 extract(라벨에서 필드 뽑기)만 반드시 정합니다.

    오인식 판정은 여기서 한 번만 구현하고, 자식은 정규화 규칙과 겹침 기준만 바꿉니다.
    그래야 문서 종류가 달라도 "오인식"이 같은 뜻이 되어 종류끼리 비율을 견줄 수 있습니다.
    """

    # 자식이 바꿀 수 있는 두 값.
    normalizer = Normalizer()
    # 라벨 단어 상자와 OCR 줄 상자가 "같은 자리"라고 볼 최소 겹침 비율 (작은 상자 넓이 기준).
    min_overlap = 0.3

    @abstractmethod
    def extract(self, label: dict) -> list[Field]:
        """라벨 1장에서 필드를 뽑습니다. 확실하지 않은 필드는 뽑지 않습니다."""

    def is_misread(self, field: Field, ocr_lines: list[Token]) -> bool:
        """필드의 단어 하나라도 같은 자리의 OCR 글자에 없으면 오인식(누락 포함)입니다."""
        norm = self.normalizer
        for word in field.tokens:
            # 이 단어 자리에 겹치는 OCR 줄을 왼쪽부터 이어 붙이고, 정규화한 단어가 그 안에 있는지 봅니다.
            # 겹치는 줄이 없으면 빈 문자열이 되어 누락도 오인식으로 잡힙니다.
            near = sorted((l for l in ocr_lines if overlaps(word.box, l.box, self.min_overlap)), key=lambda l: l.box[0])
            if norm(word.text) not in norm("".join(l.text for l in near)):
                return True
        return False

    def is_misread_text(self, field: Field, ocr_texts: list[str]) -> bool:
        """좌표 없이 글자만으로 보는 오인식 판정. 필드의 단어 하나라도 어느 OCR 줄에도 없으면 오인식입니다.

        좌표를 믿을 만하게 주지 못하는 OCR(비전 모델)에 씁니다. is_misread보다 느슨합니다:
        같은 글자가 문서의 다른 자리에 있어도 맞게 읽은 것으로 칩니다. 그래서 두 판정의 숫자를 한 표에서 견주지 않고,
        엔진끼리 견줄 때는 모든 엔진을 이 판정으로 다시 셉니다.
        줄끼리 이어 붙이지 않는 이유: 앞줄 끝과 뒷줄 처음이 붙어 실제로는 없는 글자가 만들어지기 때문입니다.
        대신 한 단어가 두 줄로 쪼개져 읽힌 경우는 오인식으로 잡힙니다 (보수적인 쪽).
        """
        norm = self.normalizer
        lines = [norm(text) for text in ocr_texts]
        return any(not any(norm(word.text) in line for line in lines) for word in field.tokens)

