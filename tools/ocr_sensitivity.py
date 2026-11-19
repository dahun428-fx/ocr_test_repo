r"""M1b: OCR 설정에 따라 "OCR이 틀리게 읽은 필드"가 얼마나 달라지는지 봅니다.

주 지표의 분모가 OCR 오인식 필드라서, 엔진을 고정하기 전에 설정에 얼마나 민감한지 확인합니다.
데이터가 있는 PC에서 실행합니다. 모델 호출은 없습니다. OCR 원문은 --cache 폴더(저장소 밖)에만 두고,
화면과 --summary 파일에는 집계 숫자만 씁니다.

    python tools/ocr_sensitivity.py --labels <라벨 폴더> --images <이미지 폴더> \
        --cache E:\ocr-harness-data\cache\ocr --baseline-cache E:\ocr-harness-data\cache\ocr-paddle \
        --summary E:\ocr-harness-data\m1b_ocr_sensitivity.json

기본은 제품마다 이미지 1장(파일 이름 순으로 첫 장)만 봅니다. --all이면 전체를 봅니다.
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
from ocr_harness.common.ocr import CachedOcr, compare_misreads, to_tokens  # noqa: E402
from ocr_harness.common.ocr_paddle import PaddleOcrEngine  # noqa: E402
# ocr_harness.project를 거치지 않고 필드 규칙만 가져옵니다. project는 추적 패키지(OpenTelemetry)까지 불러오는데,
# OCR을 돌리는 PC 환경에는 그 버전이 없고 이 스크립트는 추적을 쓰지 않습니다.
from ocr_harness.pharma.fields import EXTRACTOR, extract_fields, is_misread  # noqa: E402

KOREAN_REC = "korean_PP-OCRv5_mobile_rec"
# 비교할 설정. 첫 번째가 기준(M1a에서 쓴 것)입니다.
CONFIGS = {
    "mobile": PaddleOcrEngine("PP-OCRv5_mobile_det", KOREAN_REC),
    # 검출만 큰 모델로. (인식은 한국어 모델이 mobile뿐인지 실행 전에 확인합니다.)
    "server-det": PaddleOcrEngine("PP-OCRv5_server_det", KOREAN_REC),
    # 긴 변을 960으로 줄여서 검출. 입력 크기에 얼마나 민감한지 봅니다.
    "mobile-max960": PaddleOcrEngine("PP-OCRv5_mobile_det", KOREAN_REC, det_limit_side_len=960, det_limit_type="max"),
    # 큰 검출 모델 + 줄인 입력. 원본 크기(긴 변 약 3000)에서는 CPU로 1장에 15분이 넘어 쓸 수 없었습니다.
    "server-det-max960": PaddleOcrEngine("PP-OCRv5_server_det", KOREAN_REC, det_limit_side_len=960, det_limit_type="max"),
    # 960이 원본 크기보다 훨씬 나았으므로, 가장 좋은 크기가 어디인지 사이 값을 더 봅니다.
    **{
        f"{size}-max{side}": PaddleOcrEngine(f"PP-OCRv5_{size.split('-')[0]}_det", KOREAN_REC, det_limit_side_len=side, det_limit_type="max")
        for size, side in (("mobile", 736), ("mobile", 1280), ("mobile", 1600), ("mobile", 1920), ("server-det", 1280))
    },
}
BASELINE = "mobile"
B_FIELDS = ("product-name", "active-ingredient")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--labels", required=True)
    parser.add_argument("--images", required=True)
    parser.add_argument("--cache", required=True, help="설정마다 하위 폴더를 만듭니다")
    parser.add_argument("--baseline-cache", help="M1a에서 만든 기준 설정의 캐시 폴더 (설정 기록이 없어도 이어 씁니다)")
    parser.add_argument("--summary", required=True)
    parser.add_argument("--all", action="store_true", help="제품당 1장이 아니라 전체 이미지")
    parser.add_argument("--configs", nargs="*", default=list(CONFIGS))
    parser.add_argument("--limit", type=int, default=0, help="앞에서부터 이 장수만 (0이면 전부). 느린 설정을 먼저 재 볼 때 씁니다")
    parser.add_argument("--model-cache", help="PaddleOCR 모델 파일을 받아 둘 폴더. 지정하지 않으면 사용자 홈 폴더에 받습니다")
    args = parser.parse_args()
    if args.model_cache:
        # paddlex가 모델 파일을 두는 위치. paddleocr를 가져오기 전에 정해야 해서 맨 앞에서 설정합니다
        # (엔진은 처음 읽을 때 가져오므로 여기서 정하면 됩니다).
        os.environ["PADDLE_PDX_CACHE_HOME"] = args.model_cache

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

    verdicts, per_config = {}, {}
    for name in args.configs:
        if name == BASELINE and args.baseline_cache:
            engine = CachedOcr(CONFIGS[name], args.baseline_cache, adopt_unlabeled=True)
        else:
            engine = CachedOcr(CONFIGS[name], pathlib.Path(args.cache) / name)
        verdict, counts, seconds, lines_total = {}, collections.Counter(), [], 0
        products_with_b_misread = set()
        for number, (stem, product, fields) in enumerate(chosen, 1):
            start = time.perf_counter()
            lines = engine.read(images[stem])
            seconds.append(time.perf_counter() - start)
            lines_total += len(lines)
            tokens = to_tokens(lines)
            for field in fields:
                misread = is_misread(field, tokens)
                verdict[f"{stem}|{field.name}"] = misread
                counts[f"{field.name}:eligible"] += 1
                counts[f"{field.name}:misread"] += misread
                # 좌표 없는 판정도 함께 셉니다. 좌표를 주지 못하는 엔진(Sonnet 비전)과 같은 기준으로 견주기 위한 숫자입니다.
                counts[f"{field.name}:misread_text"] += EXTRACTOR.is_misread_text(field, [line["text"] for line in lines])
                if misread and field.name in B_FIELDS:
                    products_with_b_misread.add(product)
            if number % 25 == 0:
                print(f"{name} {number}/{len(chosen)}", flush=True)
        verdicts[name] = verdict
        per_config[name] = {
            "config": engine.config,
            "configDigest": engine.config_digest,
            # 캐시에서 읽은 것이 섞이면 시간이 짧게 나옵니다. 중앙값은 참고용입니다.
            "median_seconds_per_image": statistics.median(seconds) if seconds else None,
            "mean_lines_per_image": lines_total / len(chosen) if chosen else None,
            "fields": {
                field: {"eligible": counts[f"{field}:eligible"], "ocr_misread": counts[f"{field}:misread"],
                        "ocr_misread_text_only": counts[f"{field}:misread_text"]}
                for field in ("product-name", "active-ingredient", "expiry")
            },
            "b_type": {
                "eligible": sum(counts[f"{f}:eligible"] for f in B_FIELDS),
                "ocr_misread": sum(counts[f"{f}:misread"] for f in B_FIELDS),
                "ocr_misread_text_only": sum(counts[f"{f}:misread_text"] for f in B_FIELDS),
                "products_with_misread": len(products_with_b_misread),
            },
        }

    def b_only(verdict: dict) -> dict:
        return {key: value for key, value in verdict.items() if key.split("|")[1] in B_FIELDS}

    summary = {
        "images": len(chosen),
        "products": len({product for _, product, _ in chosen}),
        "sampling": "all" if args.all else "first image per product by file name",
        "baseline": BASELINE,
        "configs": per_config,
        "b_type_vs_baseline": {
            name: compare_misreads(b_only(verdicts[BASELINE]), b_only(verdicts[name]))
            for name in args.configs if name != BASELINE and BASELINE in verdicts
        },
    }
    pathlib.Path(args.summary).write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
