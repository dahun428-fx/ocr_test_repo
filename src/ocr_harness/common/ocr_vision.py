"""비전 모델(예: Claude Sonnet)을 OCR 엔진으로 씁니다. 이미지를 보내 글자를 줄 단위로 받아 옵니다.

로컬 OCR과 다른 점 세 가지를 설정과 기록에 드러냅니다.
  - 좌표가 없습니다. 줄의 box는 None이고, 오인식은 글자만으로 판정합니다 (FieldExtractor.is_misread_text).
  - 호출마다 비용이 듭니다. 모델 경로(ModelRoute)를 지나므로 OCR 단계의 토큰과 비용도 장부에 잡힙니다.
  - 같은 이미지라도 출력이 달라질 수 있습니다. 한 번 읽은 결과를 CachedOcr로 저장해 고정하고 그것만 씁니다.
"""
import base64
import io
from pathlib import Path

from ocr_harness.common.ids import content_digest
from ocr_harness.common.model_route import ModelRequest, ModelRoute
from ocr_harness.common.ocr import OcrEngine

MEDIA_TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}


class OcrFailed(RuntimeError):
    """모델이 이미지를 읽지 못했을 때 (오류, 거절). 빈 결과로 바꾸지 않고 알립니다."""


class VisionOcrEngine(OcrEngine):
    """비전 모델 하나 + 지시문 하나 + 입력 크기 규칙 하나."""

    def __init__(self, route: ModelRoute, model: str, prompt: str, max_side: int | None):
        self._route = route
        self._model = model
        self._prompt = prompt
        # 보내기 전에 긴 변을 이 크기로 줄입니다. None이면 원본 그대로 보냅니다.
        # 줄이는 이유: 모델 쪽에서 큰 이미지를 어떻게 줄이는지는 우리가 고정할 수 없어서, 직접 줄여 설정으로 남깁니다.
        self._max_side = max_side

    @property
    def config(self) -> dict:
        return {
            "engine": "vision-model",
            "model": self._model,
            # 지시문이 한 글자만 달라도 다른 엔진으로 봅니다. 원문은 코드에 있으므로 해시만 적습니다.
            "promptDigest": content_digest(self._prompt),
            "maxSide": self._max_side,
        }

    def _image_block(self, image_path: Path) -> dict:
        data, media_type = image_path.read_bytes(), MEDIA_TYPES.get(image_path.suffix.lower(), "image/jpeg")
        if self._max_side is not None:
            from PIL import Image   # 줄일 때만 필요합니다. 이미지 처리 패키지가 없는 환경에서도 나머지는 돕니다.

            with Image.open(io.BytesIO(data)) as image:
                if max(image.size) > self._max_side:
                    image.thumbnail((self._max_side, self._max_side))   # 비율을 지키며 줄입니다.
                    buffer = io.BytesIO()
                    image.convert("RGB").save(buffer, format="JPEG", quality=90)
                    data, media_type = buffer.getvalue(), "image/jpeg"
        return {"type": "image", "source": {"type": "base64", "media_type": media_type,
                                            "data": base64.standard_b64encode(data).decode("ascii")}}

    def read(self, image_path) -> list[dict]:
        request = ModelRequest(
            model=self._model, role="ocr",
            content=[self._image_block(Path(image_path)), {"type": "text", "text": self._prompt}],
        )
        result = self._route.call(request)
        # 오류, 거절, 잘린 출력은 결과로 쓰지 않습니다. 잘린 글을 그대로 쓰면 뒤쪽 필드가 전부 "누락"으로 잡힙니다.
        problem = result.error_type or (result.stop_reason if result.stop_reason in ("refusal", "max_tokens") else None)
        if problem is not None:
            # 여기서 예외를 내면 CachedOcr가 캐시에 쓰지 않으므로 나중에 다시 시도할 수 있습니다. 호출 기록은 이미 span에 남았습니다.
            raise OcrFailed(f"{Path(image_path).name}: {problem}")
        # 좌표와 점수는 없습니다. 로컬 OCR의 줄과 같은 모양으로 맞추되 모르는 값은 None으로 둡니다.
        return [{"text": line.strip(), "box": None, "score": None} for line in result.text.splitlines() if line.strip()]
