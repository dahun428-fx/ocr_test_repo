r"""M1b: 이미지를 단계별로 나쁘게 만들면 "OCR이 틀리게 읽은 필드"가 얼마나 늘어나는지 봅니다.

원본 사진에서는 OCR이 B 유형 필드의 90% 이상을 맞게 읽어 주 지표의 분모가 너무 작았습니다
(docs/m1b-results.md 4절). 열화 조건(종류 6개 × 강도 3단계 + 대조 identity)마다 같은 이미지를 읽어
오인식 수를 세고, 어떤 조건이 실험에 쓸 만한지 고를 근거를 만듭니다.

데이터가 있는 PC에서 실행합니다. 모델 호출도 외부 전송도 없습니다. 열화 이미지는 임시 파일로만 만들고 지웁니다.
OCR 원문은 --cache 폴더(저장소 밖)에만 두고, 화면과 --summary 파일에는 집계 숫자만 씁니다.

    python tools/ocr_degradation.py --labels <라벨 폴더> --images <이미지 폴더> \
        --cache E:\ocr-harness-data\cache\ocr-degraded --reference-cache E:\ocr-harness-data\cache\ocr\mobile-max960 \
        --summary E:\ocr-harness-data\m1b_ocr_degradation.json

판정은 좌표를 쓰지 않는 "글자만 판정"이 기준입니다. 기울인 그림은 좌표가 달라져 상자 판정을 쓸 수 없고,
나중에 Sonnet 비전 OCR(좌표 없음)과 같은 잣대로 견줘야 하기 때문입니다.
조건을 고르는 일은 개발용 제품의 숫자로만 합니다. 그래서 집계를 dev / eval / all로 나눠 적습니다.
"""
import argparse
import collections
import json
import os
import pathlib
import statistics
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from ocr_harness import project  # noqa: E402
from ocr_harness.common.degrade import DegradedOcr  # noqa: E402
from ocr_harness.common.ocr import CachedOcr, OcrEngine, compare_misreads, to_tokens  # noqa: E402
from ocr_harness.pharma.fields import EXTRACTOR, extract_fields, is_misread  # noqa: E402

KOREAN_REC = "korean_PP-OCRv5_mobile_rec"
# 열화 비교의 바탕이 되는 OCR 설정. 둘 다 M1b 2절에서 원본 이미지로 잰 설정과 같습니다.
DETECTORS = {"mobile": "PP-OCRv5_mobile_det", "server": "PP-OCRv5_server_det"}
MAX_SIDE = 960
B_FIELDS = ("product-name", "active-ingredient")
FIELDS = ("product-name", "active-ingredient", "expiry")


class NothingEngine(OcrEngine):
    """아무 글자도 읽지 못하는 가짜 엔진. PaddleOCR 없이 배선(열화 → 캐시 → 집계)만 확인할 때 씁니다."""

    @property
    def config(self) -> dict:
        return {"engine": "fake-nothing"}

    def read(self, image_path) -> list[dict]:
        return []


def base_engine(args) -> tuple[str, OcrEngine]:
    if args.fake:
        return "fake", NothingEngine()
    # paddleocr는 PC에만 있으므로 실제로 쓸 때 가져옵니다.
    from ocr_harness.common.ocr_paddle import PaddleOcrEngine

    name = f"{args.detector}-max{MAX_SIDE}"
    return name, PaddleOcrEngine(DETECTORS[args.detector], KOREAN_REC, det_limit_side_len=MAX_SIDE, det_limit_type="max")


def count(verdict: dict, fields: tuple, split: dict, part: str) -> dict:
    """판정({"이미지|필드": 오인식 여부})에서 한 분할의 적격·오인식 수를 셉니다."""
    chosen = [value for key, value in verdict.items()
              if key.split("|")[1] in fields and (part == "all" or split[key.split("|")[0]] == part)]
    return {"eligible": len(chosen), "misread": sum(chosen)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--labels", required=True)
    parser.add_argument("--images", required=True)
    parser.add_argument("--cache", required=True, help="바탕 설정과 조건마다 하위 폴더를 만듭니다")
    parser.add_argument("--reference-cache", help="같은 바탕 설정으로 원본 이미지를 읽어 둔 캐시. identity 조건과 판정이 같은지 대조합니다")
    parser.add_argument("--summary", required=True)
    parser.add_argument("--detector", choices=list(DETECTORS), default="mobile",
                        help="검출 모델. mobile은 장당 약 3초, server는 약 10초")
    parser.add_argument("--conditions", nargs="*", help="돌릴 조건 이름 (기본은 전부). identity는 항상 포함합니다")
    parser.add_argument("--all", action="store_true", help="제품당 1장이 아니라 전체 이미지")
    parser.add_argument("--limit", type=int, default=0, help="앞에서부터 이 장수만 (0이면 전부)")
    parser.add_argument("--model-cache", help="PaddleOCR 모델 파일 폴더")
    parser.add_argument("--fake", action="store_true", help="가짜 엔진으로 배선만 확인")
    args = parser.parse_args()
    if args.model_cache:
        os.environ["PADDLE_PDX_CACHE_HOME"] = args.model_cache

    conditions = project.degradation_conditions()
    names = list(conditions) if not args.conditions else ["identity", *[n for n in args.conditions if n != "identity"]]
    unknown = [name for name in names if name not in conditions]
    if unknown:
        parser.error(f"모르는 조건: {unknown}. 가능한 이름: {list(conditions)}")

    # 제품마다 첫 장을 고르는 규칙은 tools/ocr_sensitivity.py와 같습니다 (같은 152장이어야 앞 결과와 견줄 수 있음).
    images = {p.stem: p for p in pathlib.Path(args.images).rglob("*") if p.suffix.lower() in (".jpg", ".jpeg", ".png")}
    chosen, seen_products = [], set()
    for label_path in sorted(pathlib.Path(args.labels).rglob("*.json")):
        label = json.loads(label_path.read_text(encoding="utf-8"))
        product = label["images"][0]["product_name"]
        if label_path.stem not in images or (not args.all and product in seen_products):
            continue
        seen_products.add(product)
        chosen.append((label_path.stem, product, extract_fields(label)))
    if args.limit:
        chosen = chosen[: args.limit]
    split = {stem: project.split_of(product) for stem, product, _ in chosen}

    base_name, base = base_engine(args)

    def judge(engine: OcrEngine, with_boxes: bool):
        """한 엔진으로 고른 이미지를 모두 읽어 글자만 판정, 상자 판정, 걸린 시간을 돌려줍니다."""
        text_verdict, box_verdict, seconds, lines_total = {}, {}, [], 0
        for number, (stem, _, fields) in enumerate(chosen, 1):
            start = time.perf_counter()
            lines = engine.read(images[stem])
            seconds.append(time.perf_counter() - start)
            lines_total += len(lines)
            texts = [line["text"] for line in lines]
            for field in fields:
                text_verdict[f"{stem}|{field.name}"] = EXTRACTOR.is_misread_text(field, texts)
                if with_boxes:
                    box_verdict[f"{stem}|{field.name}"] = is_misread(field, to_tokens(lines))
            if number % 50 == 0:
                print(f"{engine.config.get('degradation', {}).get('kind', 'reference')} {number}/{len(chosen)}", flush=True)
        return text_verdict, box_verdict, seconds, lines_total

    verdicts, per_condition = {}, {}
    for name in names:
        degraded = DegradedOcr(base, conditions[name])
        engine = CachedOcr(degraded, pathlib.Path(args.cache) / base_name / name)
        text_verdict, box_verdict, seconds, lines_total = judge(engine, degraded.keeps_geometry)
        verdicts[name] = text_verdict
        per_condition[name] = {
            "degradation": conditions[name].config,
            "configDigest": engine.config_digest,
            "keeps_geometry": degraded.keeps_geometry,
            # 캐시에서 읽은 것이 섞이면 짧게 나옵니다. 참고용입니다.
            "median_seconds_per_image": statistics.median(seconds) if seconds else None,
            "mean_lines_per_image": lines_total / len(chosen) if chosen else None,
            "fields_text_only": {field: count(text_verdict, (field,), split, "all") for field in FIELDS},
            "b_type_text_only": {part: count(text_verdict, B_FIELDS, split, part) for part in ("dev", "eval", "all")},
            # 상자 판정은 좌표가 그대로인 조건에서만 뜻이 있습니다.
            "b_type_boxes": count(box_verdict, B_FIELDS, split, "all") if degraded.keeps_geometry else None,
            "products_with_b_misread": len({key.split("|")[0] for key, value in text_verdict.items()
                                            if value and key.split("|")[1] in B_FIELDS}),
        }
        print(name, per_condition[name]["b_type_text_only"], flush=True)

    def b_only(verdict: dict) -> dict:
        return {key: value for key, value in verdict.items() if key.split("|")[1] in B_FIELDS}

    summary = {
        "images": len(chosen),
        "products": len({product for _, product, _ in chosen}),
        "sampling": "all" if args.all else "first image per product by file name",
        "split": {"salt": project.SPLIT_SALT, "dev_share": project.DEV_SHARE,
                  "dev_images": sum(1 for value in split.values() if value == "dev"),
                  "eval_images": sum(1 for value in split.values() if value == "eval")},
        "base": {"name": base_name, "config": base.config},
        "judgement": "text only (no boxes)",
        "conditions": per_condition,
        # 원본(identity)에서 맞던 필드가 열화 뒤에 틀리는지, 그 반대는 얼마나 되는지를 조건마다 짝지어 셉니다.
        "b_type_vs_identity": {name: compare_misreads(b_only(verdicts["identity"]), b_only(verdicts[name]))
                               for name in names if name != "identity"},
    }
    if args.reference_cache:
        # 열화 경로(읽기 → PNG 임시 파일 → OCR)가 결과를 바꾸지 않는지: 원본을 바로 읽은 캐시와 identity를 견줍니다.
        reference_verdict, _, _, _ = judge(CachedOcr(base, args.reference_cache), False)
        summary["identity_vs_reference"] = compare_misreads(b_only(reference_verdict), b_only(verdicts["identity"]))

    pathlib.Path(args.summary).write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
