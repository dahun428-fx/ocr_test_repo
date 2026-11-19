r"""M1a (다): 로컬 OCR을 돌려 적격 필드 수와 OCR 오인식 필드 수를 셉니다.

데이터가 있는 PC에서 실행합니다. 모델 호출은 없습니다. OCR 원문은 --cache 폴더(저장소 밖)에만
저장하고, 화면과 --summary 파일에는 집계 숫자만 씁니다.

    python spikes/m1a_ocr_misread.py --labels <라벨 폴더> --images <이미지 폴더> \
        --cache E:\ocr-harness-data\cache\ocr-paddle --summary E:\ocr-harness-data\m1a_ocr_summary.json
"""
import argparse
import collections
import json
import pathlib
import statistics
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from ocr_harness.fields import Token, extract_fields, is_misread  # noqa: E402


def load_ocr():
    from paddleocr import PaddleOCR

    return PaddleOCR(
        text_detection_model_name="PP-OCRv5_mobile_det",
        text_recognition_model_name="korean_PP-OCRv5_mobile_rec",
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
        device="cpu",
        enable_mkldnn=False,
    )


def run_ocr(ocr, image_path: pathlib.Path) -> list[dict]:
    result = ocr.predict(str(image_path))[0].json
    result = result.get("res", result)
    lines = []
    for text, poly, score in zip(result["rec_texts"], result["rec_polys"], result["rec_scores"]):
        xs, ys = [p[0] for p in poly], [p[1] for p in poly]
        lines.append({"text": text, "box": [min(xs), min(ys), max(xs), max(ys)], "score": score})
    return lines


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--labels", required=True)
    parser.add_argument("--images", required=True)
    parser.add_argument("--cache", required=True)
    parser.add_argument("--summary", required=True)
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    cache = pathlib.Path(args.cache)
    cache.mkdir(parents=True, exist_ok=True)
    images = {p.stem: p for p in pathlib.Path(args.images).rglob("*") if p.suffix.lower() in (".jpg", ".jpeg", ".png")}
    labels = sorted(pathlib.Path(args.labels).rglob("*.json"))
    if args.limit:
        labels = labels[: args.limit]

    ocr = None
    eligible = collections.Counter()
    misread = collections.Counter()
    per_product = collections.defaultdict(collections.Counter)
    missing_images, seconds = 0, []
    for number, label_path in enumerate(labels, 1):
        label = json.loads(label_path.read_text(encoding="utf-8"))
        fields = extract_fields(label)
        image_path = images.get(label_path.stem)
        if image_path is None:
            missing_images += 1
            continue
        cached = cache / f"{label_path.stem}.json"
        if cached.exists():
            lines = json.loads(cached.read_text(encoding="utf-8"))
        else:
            ocr = ocr or load_ocr()
            start = time.perf_counter()
            lines = run_ocr(ocr, image_path)
            seconds.append(time.perf_counter() - start)
            cached.write_text(json.dumps(lines, ensure_ascii=False), encoding="utf-8")
        tokens = [Token(l["text"], tuple(l["box"])) for l in lines]
        product = label["images"][0]["product_name"]
        for field in fields:
            eligible[field.name] += 1
            per_product[product][f"{field.name}:eligible"] += 1
            if is_misread(field, tokens):
                misread[field.name] += 1
                per_product[product][f"{field.name}:misread"] += 1
        if number % 25 == 0:
            print(f"{number}/{len(labels)}", flush=True)

    def distribution(key: str) -> dict:
        counts = [c[key] for c in per_product.values() if c[key]]
        if not counts:
            return {"products": 0}
        return {"products": len(counts), "min": min(counts), "median": statistics.median(counts), "max": max(counts)}

    b_fields = ("product_name", "active_ingredient")
    summary = {
        "ocr": "PaddleOCR PP-OCRv5 mobile det + korean mobile rec, CPU",
        "images": len(labels) - missing_images,
        "missing_images": missing_images,
        "products": len(per_product),
        "mean_ocr_seconds": statistics.mean(seconds) if seconds else None,
        "fields": {
            name: {
                "query_type": "A" if name == "expiry" else "B",
                "eligible": eligible[name],
                "ocr_misread": misread[name],
                "eligible_per_product": distribution(f"{name}:eligible"),
                "misread_per_product": distribution(f"{name}:misread"),
            }
            for name in ("product_name", "active_ingredient", "expiry")
        },
        "b_type_total": {
            "eligible": sum(eligible[n] for n in b_fields),
            "ocr_misread": sum(misread[n] for n in b_fields),
            "products_with_misread": sum(
                1 for c in per_product.values() if any(c[f"{n}:misread"] for n in b_fields)
            ),
        },
    }
    pathlib.Path(args.summary).write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
