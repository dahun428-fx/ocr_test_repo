"""OCR 엔진 틀(ocr_harness.common.ocr): 설정 해시, 파일 캐시, 설정끼리의 오인식 비교."""
import json

import pytest

from ocr_harness.common.ocr import CachedOcr, OcrConfigMismatch, OcrEngine, compare_misreads, to_tokens


class FakeEngine(OcrEngine):
    """정해진 줄을 돌려주고, 몇 번 불렸는지 셉니다."""

    def __init__(self, config, lines):
        self._config, self._lines, self.calls = config, lines, 0

    @property
    def config(self):
        return self._config

    def read(self, image_path):
        self.calls += 1
        return self._lines


LINES = [{"text": "합성정", "box": [0, 0, 100, 20], "score": 0.9}]


def test_config_digest_ignores_key_order_and_changes_with_any_value():
    a = FakeEngine({"det": "m", "rec": "k"}, LINES).config_digest
    assert a == FakeEngine({"rec": "k", "det": "m"}, LINES).config_digest
    assert a != FakeEngine({"det": "s", "rec": "k"}, LINES).config_digest


def test_engine_cannot_be_used_without_read_and_config():
    with pytest.raises(TypeError):
        OcrEngine()


def test_cached_engine_reads_each_image_once(tmp_path):
    engine = FakeEngine({"det": "m"}, LINES)
    cached = CachedOcr(engine, tmp_path / "cache")
    assert cached.read(tmp_path / "a.jpg") == LINES
    assert cached.read(tmp_path / "a.jpg") == LINES
    assert engine.calls == 1
    assert cached.config == engine.config        # 캐시를 씌워도 설정(과 해시)은 안쪽 엔진의 것입니다.


def test_cache_survives_a_new_process(tmp_path):
    CachedOcr(FakeEngine({"det": "m"}, LINES), tmp_path).read(tmp_path / "a.jpg")
    second = FakeEngine({"det": "m"}, [])
    assert CachedOcr(second, tmp_path).read(tmp_path / "a.jpg") == LINES and second.calls == 0


def test_cache_folder_made_with_another_config_is_refused(tmp_path):
    # 설정이 다른 OCR 결과가 한 폴더에 섞이면 어느 설정의 숫자인지 알 수 없게 됩니다.
    CachedOcr(FakeEngine({"det": "m"}, LINES), tmp_path).read(tmp_path / "a.jpg")
    with pytest.raises(OcrConfigMismatch):
        CachedOcr(FakeEngine({"det": "s"}, LINES), tmp_path)


def test_cache_folder_without_a_config_record_can_be_adopted_explicitly(tmp_path):
    # 설정 기록을 남기기 전에 만든 캐시(M1a 탐색분)를 이어 쓰는 경우. 기본은 거부이고, 알고 쓸 때만 허용합니다.
    (tmp_path / "a.json").write_text(json.dumps(LINES), encoding="utf-8")
    with pytest.raises(OcrConfigMismatch):
        CachedOcr(FakeEngine({"det": "m"}, []), tmp_path)
    engine = FakeEngine({"det": "m"}, [])
    assert CachedOcr(engine, tmp_path, adopt_unlabeled=True).read(tmp_path / "a.jpg") == LINES and engine.calls == 0


def test_to_tokens_keeps_text_and_box():
    token = to_tokens(LINES)[0]
    assert (token.text, token.box) == ("합성정", (0, 0, 100, 20))


def test_compare_misreads_counts_agreement_and_flips():
    baseline = {"a": True, "b": True, "c": False, "d": False}
    other = {"a": True, "b": False, "c": True, "d": False}
    assert compare_misreads(baseline, other) == {
        "fields": 4, "baseline_misread": 2, "other_misread": 2,
        "both_misread": 1, "only_baseline": 1, "only_other": 1, "agreement": 0.5,
    }


def test_compare_misreads_requires_the_same_fields():
    with pytest.raises(ValueError):
        compare_misreads({"a": True}, {"b": True})
