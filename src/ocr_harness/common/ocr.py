"""OCR 엔진의 틀. 어떤 엔진이든 "이미지 → 위치가 있는 글자 줄"로 맞추고, 설정을 기록에 남깁니다.

OCR은 이 연구에서 모델에 들어가는 입력을 만드는 단계라, 설정이 조금만 달라도 뒤의 모든 숫자가 달라집니다.
그래서 (1) 출력에 영향을 주는 값을 전부 config로 내놓게 하고, (2) 그 해시로 결과를 구분하며,
(3) 캐시 폴더 하나에는 한 설정의 결과만 들어가게 막습니다.
실제 엔진(PaddleOCR)은 ocr_harness.common.ocr_paddle에 있습니다.
"""
import json
from abc import ABC, abstractmethod
from pathlib import Path

from ocr_harness.common.fields import Token
from ocr_harness.common.ids import manifest_digest

# 캐시 폴더에 남기는 설정 기록의 파일 이름. 이미지 이름과 겹치지 않게 밑줄로 시작합니다.
CONFIG_FILE = "_ocr_config.json"


class OcrConfigMismatch(RuntimeError):
    """캐시 폴더가 다른 설정으로 만들어졌거나, 어떤 설정으로 만들었는지 기록이 없을 때."""


class OcrEngine(ABC):
    """OCR 엔진 하나. 자식은 config와 read만 정합니다."""

    @property
    @abstractmethod
    def config(self) -> dict:
        """출력에 영향을 주는 모든 값 (엔진 이름과 버전, 모델 이름, 입력 크기 규칙 등). JSON으로 적을 수 있어야 합니다."""

    @abstractmethod
    def read(self, image_path) -> list[dict]:
        """이미지 1장 → 줄 목록. 줄은 {"text", "box": [x1, y1, x2, y2], "score"}입니다."""

    @property
    def config_digest(self) -> str:
        """설정의 해시. 키 순서와 상관없이 같은 설정이면 같은 값입니다 (RFC 8785)."""
        return manifest_digest(self.config)


class CachedOcr(OcrEngine):
    """다른 엔진을 감싸 결과를 파일에 남기고 다시 씁니다 (장식자 패턴).

    OCR은 이미지 1장에 몇 초가 걸리고 결과가 결정적이라, 한 번 읽은 것은 다시 읽지 않습니다.
    감싸도 OcrEngine이므로 쓰는 쪽은 캐시가 있는지 몰라도 됩니다.
    캐시 폴더는 저장소 밖에 둡니다. OCR 원문은 데이터입니다.
    """

    def __init__(self, engine: OcrEngine, folder, adopt_unlabeled: bool = False):
        self._engine = engine
        self._folder = Path(folder)
        self._folder.mkdir(parents=True, exist_ok=True)
        record = self._folder / CONFIG_FILE
        if record.exists():
            saved = json.loads(record.read_text(encoding="utf-8"))
            if manifest_digest(saved) != engine.config_digest:
                raise OcrConfigMismatch(f"{self._folder}는 다른 OCR 설정으로 만든 캐시입니다")
        else:
            # 설정 기록 없이 결과만 있는 폴더는 어느 설정의 것인지 알 수 없습니다. 알고 이어 쓸 때만 받습니다.
            if any(self._folder.glob("*.json")) and not adopt_unlabeled:
                raise OcrConfigMismatch(f"{self._folder}에 설정 기록이 없는 캐시가 있습니다")
            record.write_text(json.dumps(engine.config, ensure_ascii=False, indent=2), encoding="utf-8")

    @property
    def config(self) -> dict:
        return self._engine.config

    def read(self, image_path) -> list[dict]:
        # 파일 이름(확장자 제외)을 열쇠로 씁니다. 이 데이터는 이미지 이름이 겹치지 않습니다.
        cached = self._folder / f"{Path(image_path).stem}.json"
        if cached.exists():
            return json.loads(cached.read_text(encoding="utf-8"))
        lines = self._engine.read(image_path)
        cached.write_text(json.dumps(lines, ensure_ascii=False), encoding="utf-8")
        return lines


def to_tokens(lines: list[dict]) -> list[Token]:
    """OCR 줄 목록 → 필드 판정에 쓰는 Token 목록."""
    return [Token(line["text"], tuple(line["box"])) for line in lines]


def compare_misreads(baseline: dict, other: dict) -> dict:
    """같은 필드들에 대한 두 OCR 설정의 오인식 판정({필드 열쇠: 오인식 여부})을 견줍니다.

    개수만 같아도 "같은 필드를 틀렸는지"는 다를 수 있어서, 겹침과 엇갈림을 따로 셉니다.
    주 지표의 분모가 "OCR이 틀리게 읽은 필드"이므로, 엇갈림이 크면 엔진 선택이 결론을 바꿀 수 있다는 뜻입니다.
    """
    if baseline.keys() != other.keys():
        raise ValueError("두 설정이 판정한 필드가 서로 다릅니다")
    both = sum(1 for key in baseline if baseline[key] and other[key])
    only_baseline = sum(1 for key in baseline if baseline[key] and not other[key])
    only_other = sum(1 for key in baseline if other[key] and not baseline[key])
    fields = len(baseline)
    return {
        "fields": fields,
        "baseline_misread": both + only_baseline,
        "other_misread": both + only_other,
        "both_misread": both,
        "only_baseline": only_baseline,
        "only_other": only_other,
        # 두 설정이 같은 판정(둘 다 오인식 또는 둘 다 정상)을 내린 비율.
        "agreement": (fields - only_baseline - only_other) / fields if fields else None,
    }
