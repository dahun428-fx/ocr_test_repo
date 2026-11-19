"""PaddleOCR(Apache-2.0)를 OcrEngine으로 감쌉니다.

paddleocr는 무겁고 PC에만 설치하므로 패키지 의존성에 넣지 않고, 엔진을 실제로 쓸 때 가져옵니다.
그래서 이 파일은 CI에서 실행되지 않습니다. 틀(설정 해시, 캐시, 비교)은 ocr_harness.common.ocr의 테스트가 검사합니다.
"""
from ocr_harness.common.ocr import OcrEngine


class PaddleOcrEngine(OcrEngine):
    """PaddleOCR 3.x의 검출 모델 + 인식 모델 조합 하나."""

    def __init__(self, detection_model: str, recognition_model: str, det_limit_side_len: int | None = None,
                 det_limit_type: str | None = None):
        self._detection_model = detection_model
        self._recognition_model = recognition_model
        # 검출 전에 이미지를 줄이는 규칙. None이면 PaddleOCR의 기본값을 씁니다.
        self._det_limit_side_len = det_limit_side_len
        self._det_limit_type = det_limit_type
        self._ocr = None   # 모델을 올리는 데 몇 초가 걸려서 처음 읽을 때 만듭니다. 캐시만 쓰는 실행은 아예 올리지 않습니다.

    @property
    def config(self) -> dict:
        from importlib.metadata import version

        return {
            "engine": "paddleocr",
            # 같은 모델 이름이라도 라이브러리 버전에 따라 전처리가 달라질 수 있어 버전을 함께 적습니다.
            "engineVersion": version("paddleocr"),
            "detectionModel": self._detection_model,
            "recognitionModel": self._recognition_model,
            "detLimitSideLen": self._det_limit_side_len,
            "detLimitType": self._det_limit_type,
            # 아래 셋은 끈 채로 고정합니다. 켜면 좌표가 원본 이미지와 어긋나 라벨 상자와 겹침을 볼 수 없습니다.
            "docOrientationClassify": False,
            "docUnwarping": False,
            "textlineOrientation": False,
            "device": "cpu",
        }

    def _load(self):
        from paddleocr import PaddleOCR

        options = {}
        if self._det_limit_side_len is not None:
            options["text_det_limit_side_len"] = self._det_limit_side_len
        if self._det_limit_type is not None:
            options["text_det_limit_type"] = self._det_limit_type
        return PaddleOCR(
            text_detection_model_name=self._detection_model,
            text_recognition_model_name=self._recognition_model,
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
            device="cpu",
            enable_mkldnn=False,   # M1a 때 이 PC에서 mkldnn을 켜면 실행이 실패해 꺼 두었습니다.
            **options,
        )

    def read(self, image_path) -> list[dict]:
        self._ocr = self._ocr or self._load()
        result = self._ocr.predict(str(image_path))[0].json
        result = result.get("res", result)
        lines = []
        for text, poly, score in zip(result["rec_texts"], result["rec_polys"], result["rec_scores"]):
            # 기울어진 사각형은 감싸는 축 평행 사각형으로 바꿉니다 (라벨 상자와 같은 방식).
            xs, ys = [p[0] for p in poly], [p[1] for p in poly]
            lines.append({"text": text, "box": [min(xs), min(ys), max(xs), max(ys)], "score": score})
        return lines
