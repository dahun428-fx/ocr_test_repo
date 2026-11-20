"""이미지 열화: 촬영 조건이 나쁜 사진을 흉내 내 OCR이 얼마나 더 틀리는지 봅니다.

왜 필요한가. 원본 사진에서는 OCR이 필드의 90% 이상을 맞게 읽어 "하네스가 고칠 것"이 너무 적었습니다
(docs/m1b-results.md 4절). 같은 이미지를 단계별로 나쁘게 만들면 정답(포장에 인쇄된 글자)은 그대로 둔 채
OCR 오류만 늘릴 수 있고, 원본과 짝지어 비교할 수 있습니다.

지키는 것.
- 같은 이미지, 같은 조건이면 언제 만들어도 같은 그림입니다. 난수는 이미지 열쇠와 조건에서만 나옵니다.
- 조건(종류와 강도)은 OCR 설정의 일부로 기록됩니다. 캐시와 결과가 조건마다 갈립니다.
- 원본 파일은 고치지 않습니다. 열화본은 임시 파일로 만들어 OCR에 넘기고 지웁니다.
- 실제 촬영에서 생기는 종류만 둡니다 (초점 흐림, 손떨림, 저해상도, 압축, 어두운 조명, 기울어짐).
  인위적 열화의 결과는 실제 사진의 결과와 섞지 않고 따로 보고합니다.

Pillow와 numpy를 씁니다. 이 모듈을 쓰지 않는 코드는 두 패키지가 없어도 돕니다.
"""
import hashlib
import io
import tempfile
from abc import ABC, abstractmethod
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter, ImageOps

from ocr_harness.common.ocr import OcrEngine


class Degradation(ABC):
    """열화 하나. 자식은 kind, params, _apply를 정합니다."""

    #: 종류 이름. 기록과 캐시 폴더 이름에 씁니다.
    kind: str
    #: 그림의 크기와 좌표가 그대로인지. 아니면 OCR 상자를 원본 라벨 좌표와 견줄 수 없습니다.
    keeps_geometry = True

    @property
    @abstractmethod
    def params(self) -> dict:
        """강도를 정하는 값. JSON으로 적을 수 있어야 합니다."""

    @abstractmethod
    def _apply(self, image: Image.Image, rng: np.random.Generator) -> Image.Image:
        """RGB 그림을 받아 열화한 그림을 돌려줍니다."""

    @property
    def config(self) -> dict:
        return {"kind": self.kind, **self.params}

    def apply(self, image: Image.Image, key: str) -> Image.Image:
        """key는 이미지를 가리키는 이름입니다. 같은 key와 같은 조건이면 같은 난수가 나옵니다."""
        # 실행 순서나 시각에 기대면 다시 만들 때 그림이 달라집니다. 조건과 열쇠의 해시를 씨앗으로 씁니다.
        seed = hashlib.sha256(f"{sorted(self.config.items())}|{key}".encode("utf-8")).digest()
        return self._apply(image.convert("RGB"), np.random.default_rng(int.from_bytes(seed[:8], "big")))


def _long_side(image: Image.Image) -> int:
    return max(image.size)


class Identity(Degradation):
    """아무것도 하지 않습니다. 열화 경로(읽기 → 임시 파일 → OCR) 자체가 결과를 바꾸지 않는지 보는 대조 조건입니다."""

    kind = "identity"

    @property
    def params(self) -> dict:
        return {}

    def _apply(self, image, rng):
        return image


class GaussianBlur(Degradation):
    """초점이 맞지 않은 사진. 반지름은 긴 변에 대한 비율로 적어 해상도가 다른 사진에도 같은 정도로 걸립니다."""

    kind = "gaussian-blur"

    def __init__(self, radius_fraction: float):
        self._fraction = radius_fraction

    @property
    def params(self) -> dict:
        return {"radiusFraction": self._fraction}

    def _apply(self, image, rng):
        return image.filter(ImageFilter.GaussianBlur(self._fraction * _long_side(image)))


class MotionBlur(Degradation):
    """찍는 순간 손이 가로로 흔들린 사진. 길이는 긴 변에 대한 비율입니다."""

    kind = "motion-blur"

    def __init__(self, length_fraction: float):
        self._fraction = length_fraction

    @property
    def params(self) -> dict:
        return {"lengthFraction": self._fraction, "direction": "horizontal"}

    def _apply(self, image, rng):
        length = max(2, round(self._fraction * _long_side(image)))
        data = np.asarray(image).astype("float32")
        # 가로로 length 픽셀만큼의 평균. 누적합으로 계산해 길이가 길어도 느려지지 않게 합니다.
        # 가장자리는 끝 픽셀을 늘려 채웁니다 (검은 띠가 생기면 OCR이 그 띠에 반응할 수 있음).
        left = length // 2
        padded = np.pad(data, ((0, 0), (left + 1, length - left - 1), (0, 0)), mode="edge")
        sums = np.cumsum(padded, axis=1)
        blurred = (sums[:, length:, :] - sums[:, :-length, :]) / length
        return Image.fromarray(np.clip(blurred + 0.5, 0, 255).astype("uint8"), "RGB")


class Downscale(Degradation):
    """멀리서 찍었거나 해상도가 낮은 사진. 긴 변을 줄였다가 원래 크기로 되돌려 좌표를 유지합니다."""

    kind = "downscale"

    def __init__(self, long_side: int):
        self._long_side = long_side

    @property
    def params(self) -> dict:
        return {"longSide": self._long_side}

    def _apply(self, image, rng):
        scale = self._long_side / _long_side(image)
        if scale >= 1:
            return image   # 이미 그보다 작은 사진은 그대로 둡니다. 키우는 것은 열화가 아닙니다.
        small = image.resize((max(1, round(image.width * scale)), max(1, round(image.height * scale))), Image.BILINEAR)
        return small.resize(image.size, Image.BILINEAR)


class JpegCompression(Degradation):
    """메신저 등으로 여러 번 전달되어 심하게 압축된 사진."""

    kind = "jpeg"

    def __init__(self, quality: int):
        self._quality = quality

    @property
    def params(self) -> dict:
        return {"quality": self._quality}

    def _apply(self, image, rng):
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=self._quality)
        buffer.seek(0)
        return Image.open(buffer).convert("RGB")


class LowLight(Degradation):
    """어두운 곳에서 찍은 사진. 밝기를 낮추고, 어두울 때 두드러지는 센서 노이즈를 더합니다."""

    kind = "low-light"

    def __init__(self, gain: float, noise_sigma: float):
        self._gain, self._sigma = gain, noise_sigma

    @property
    def params(self) -> dict:
        return {"gain": self._gain, "noiseSigma": self._sigma}

    def _apply(self, image, rng):
        data = np.asarray(image).astype("float32") * self._gain
        data += rng.normal(0.0, self._sigma, data.shape).astype("float32")
        return Image.fromarray(np.clip(data + 0.5, 0, 255).astype("uint8"), "RGB")


class Rotation(Degradation):
    """기울여 찍은 사진. 잘리지 않게 캔버스를 넓히고 빈 곳은 흰색으로 채웁니다. 좌표가 달라집니다."""

    kind = "rotation"
    keeps_geometry = False

    def __init__(self, degrees: float):
        self._degrees = degrees

    @property
    def params(self) -> dict:
        return {"degrees": self._degrees}

    def _apply(self, image, rng):
        return image.rotate(self._degrees, resample=Image.BICUBIC, expand=True, fillcolor=(255, 255, 255))


class DegradedOcr(OcrEngine):
    """다른 OCR 엔진 앞에 열화를 끼웁니다 (장식자). CachedOcr로 다시 감싸면 조건마다 캐시가 갈립니다."""

    def __init__(self, engine: OcrEngine, degradation: Degradation):
        self._engine, self._degradation = engine, degradation

    @property
    def config(self) -> dict:
        # 열화 조건을 설정에 넣어야 "어떤 그림을 읽은 결과인지"가 해시에 들어갑니다.
        return {**self._engine.config, "degradation": self._degradation.config}

    @property
    def keeps_geometry(self) -> bool:
        return self._degradation.keeps_geometry

    def read(self, image_path) -> list[dict]:
        image_path = Path(image_path)
        with Image.open(image_path) as opened:
            # 휴대폰 사진은 방향을 EXIF에만 적어 두기도 합니다. 픽셀에 반영한 뒤 열화해야 저장한 그림이 바로 섭니다.
            image = ImageOps.exif_transpose(opened).convert("RGB")
        degraded = self._degradation.apply(image, key=image_path.stem)
        with tempfile.TemporaryDirectory() as folder:
            # 손실 없는 PNG로 넘깁니다. JPEG로 다시 저장하면 의도하지 않은 압축 열화가 한 번 더 들어갑니다.
            # 파일 이름은 원본과 같게 둡니다 (이름을 열쇠로 쓰는 엔진이 있어도 같은 열쇠가 되게).
            target = Path(folder) / f"{image_path.stem}.png"
            degraded.save(target, format="PNG", compress_level=1)
            return self._engine.read(target)
