"""이미지 열화(ocr_harness.common.degrade)와 제품 단위 분할(ids.hash_split).

열화 이미지는 "OCR이 나빠질수록 하네스가 얼마나 버티는가"를 재려고 만듭니다.
같은 이미지와 같은 조건이면 언제 다시 만들어도 같은 그림이어야 원본과 짝지어 비교할 수 있습니다.
"""
import numpy as np
import pytest
from PIL import Image

from ocr_harness.common.degrade import (
    DegradedOcr, Downscale, GaussianBlur, Identity, JpegCompression, LowLight, MotionBlur, Rotation,
)
from ocr_harness.common.ids import hash_split
from ocr_harness.common.ocr import OcrEngine


def checkerboard(width=240, height=160) -> Image.Image:
    """가장자리가 많은 합성 그림 (5픽셀 칸을 무작위로 흑백으로 칠한 것). 흐림과 압축의 효과가 숫자로 드러납니다.

    규칙적인 8픽셀 바둑판은 쓰지 않습니다. JPEG의 8x8 블록과 딱 맞아 압축해도 변하지 않고,
    흐림 길이가 무늬 주기와 겹치면 강도 순서가 뒤집혀 보입니다.
    """
    cells = np.random.default_rng(7).integers(0, 2, (height // 5, width // 5)).astype("uint8") * 255
    board = np.kron(cells, np.ones((5, 5), dtype="uint8"))
    return Image.fromarray(np.stack([board] * 3, axis=-1), "RGB")


def pixels(image: Image.Image) -> np.ndarray:
    return np.asarray(image.convert("RGB")).astype("float64")


def edge_energy(image: Image.Image) -> float:
    """이웃 픽셀 차이의 평균. 흐릴수록 작아집니다."""
    return float(np.abs(np.diff(pixels(image), axis=1)).mean())


ALL = [GaussianBlur(0.02), MotionBlur(0.05), Downscale(60), JpegCompression(5), LowLight(0.3, 16), Rotation(10)]


@pytest.mark.parametrize("degradation", [Identity(), *ALL], ids=lambda d: d.kind)
def test_same_key_gives_the_same_picture(degradation):
    # 씨앗은 호출하는 쪽이 주는 열쇠(이미지 이름)에서 나옵니다. 실행 순서나 시각에 기대지 않습니다.
    first = degradation.apply(checkerboard(), key="img-1")
    again = degradation.apply(checkerboard(), key="img-1")
    assert np.array_equal(pixels(first), pixels(again))


def test_identity_changes_nothing():
    assert np.array_equal(pixels(Identity().apply(checkerboard(), key="k")), pixels(checkerboard()))


@pytest.mark.parametrize("degradation", ALL[:5], ids=lambda d: d.kind)
def test_size_is_kept_when_geometry_is_kept(degradation):
    # 크기가 같아야 OCR 상자 좌표를 원본 라벨의 좌표와 그대로 견줄 수 있습니다.
    assert degradation.keeps_geometry
    assert degradation.apply(checkerboard(), key="k").size == checkerboard().size


def test_rotation_says_it_moves_coordinates():
    # 돌리면 좌표가 달라지므로 상자로 보는 판정을 쓰면 안 됩니다. 쓰는 쪽이 이 표시를 보고 글자만 판정을 씁니다.
    rotated = Rotation(10).apply(checkerboard(), key="k")
    assert not Rotation(10).keeps_geometry
    assert rotated.size[0] > checkerboard().size[0] and rotated.size[1] > checkerboard().size[1]


@pytest.mark.parametrize("weak, strong", [
    (GaussianBlur(0.01), GaussianBlur(0.04)),
    (MotionBlur(0.04), MotionBlur(0.08)),   # 칸 크기(5픽셀)와 같은 길이는 피합니다. 차이의 합이 그대로라 이 잣대로는 안 보입니다.
    (Downscale(120), Downscale(40)),
], ids=["blur", "motion", "downscale"])
def test_stronger_level_removes_more_detail(weak, strong):
    original = edge_energy(checkerboard())
    weak_energy = edge_energy(weak.apply(checkerboard(), key="k"))
    strong_energy = edge_energy(strong.apply(checkerboard(), key="k"))
    assert original > weak_energy > strong_energy


def test_jpeg_compression_changes_pixels_more_at_lower_quality():
    def error(quality):
        return np.abs(pixels(JpegCompression(quality).apply(checkerboard(), key="k")) - pixels(checkerboard())).mean()
    assert error(5) > error(30) > 0


def test_low_light_darkens_and_noise_depends_on_key():
    dark = LowLight(0.3, 16)
    assert pixels(dark.apply(checkerboard(), key="a")).mean() < pixels(checkerboard()).mean() * 0.5
    # 이미지마다 다른 노이즈가 들어가야 합니다 (모든 장에 같은 무늬가 깔리면 OCR이 그 무늬에 반응할 수 있음).
    assert not np.array_equal(pixels(dark.apply(checkerboard(), key="a")), pixels(dark.apply(checkerboard(), key="b")))


class RecordingEngine(OcrEngine):
    """받은 이미지의 크기와 가장자리 양을 적어 두는 가짜 엔진."""

    def __init__(self):
        self.seen = []

    @property
    def config(self):
        return {"engine": "fake"}

    def read(self, image_path):
        with Image.open(image_path) as image:
            self.seen.append((image.size, edge_energy(image)))
        return [{"text": "합성정", "box": [0, 0, 10, 10], "score": 1.0}]


def test_degraded_ocr_feeds_the_degraded_picture_and_records_the_condition(tmp_path):
    source = tmp_path / "sample.png"
    checkerboard().save(source)
    inner = RecordingEngine()
    blurred = DegradedOcr(inner, GaussianBlur(0.04))
    lines = blurred.read(source)

    assert lines[0]["text"] == "합성정"
    size, energy = inner.seen[0]
    assert size == checkerboard().size and energy < edge_energy(checkerboard()) * 0.5
    # 열화 조건이 OCR 설정의 일부로 남아야 캐시(CachedOcr)가 조건마다 갈립니다.
    assert blurred.config["degradation"] == {"kind": "gaussian-blur", "radiusFraction": 0.04}
    assert blurred.config_digest != DegradedOcr(inner, GaussianBlur(0.02)).config_digest
    assert blurred.config_digest != DegradedOcr(inner, Identity()).config_digest
    # 원본 파일은 건드리지 않습니다.
    assert np.array_equal(pixels(Image.open(source)), pixels(checkerboard()))


def test_hash_split_is_fixed_per_key_and_roughly_balanced():
    keys = [f"product-{number}" for number in range(2000)]
    first = {key: hash_split(key, salt="s1", dev_share=0.5) for key in keys}
    # 다른 제품이 늘거나 줄어도 한 제품의 자리는 그대로입니다 (다른 열쇠를 보지 않는 함수).
    assert all(hash_split(key, salt="s1", dev_share=0.5) == first[key] for key in keys[:50])
    assert set(first.values()) == {"dev", "eval"}
    assert 0.45 < sum(1 for value in first.values() if value == "dev") / len(keys) < 0.55
    # salt를 바꾸면 다른 분할이 됩니다 (분할 버전을 올릴 때).
    assert any(hash_split(key, salt="s2", dev_share=0.5) != first[key] for key in keys)
    assert hash_split("anything", salt="s1", dev_share=0.0) == "eval"


def test_project_conditions_are_nineteen_distinct_settings():
    from ocr_harness import project

    conditions = project.degradation_conditions()
    assert len(conditions) == 19 and conditions["identity"].config == {"kind": "identity"}
    # 이름이 다른데 내용이 같은 조건이 있으면 같은 실험을 두 번 세게 됩니다.
    assert len({str(sorted(c.config.items())) for c in conditions.values()}) == 19
    assert project.split_of("합성제품") == project.split_of("합성제품")
