r"""M1b: 비전 모델(Sonnet)을 OCR 엔진으로 써서 "틀리게 읽은 필드"를 셉니다. 실제 이미지를 외부 모델로 보냅니다.

데이터가 있는 PC에서 실행합니다. 데이터 이용약관 확인(2026-11-19 사용자 확인) 뒤에만 돌립니다.
읽은 글자는 --cache 폴더(저장소 밖)에, 호출 기록(토큰·비용)은 --traces 파일(저장소 밖)에 두고,
화면과 --summary 파일에는 집계 숫자만 씁니다.

    python tools/ocr_vision_pilot.py --labels <라벨 폴더> --images <이미지 폴더> \
        --cache E:\ocr-harness-data\cache\ocr\sonnet --traces E:\ocr-harness-data\runs\m1b-vision-pilot\traces.jsonl \
        --summary E:\ocr-harness-data\m1b_ocr_vision_pilot.json --limit 3

기본은 제품마다 이미지 1장(파일 이름 순으로 첫 장)입니다. tools/ocr_sensitivity.py와 같은 152장이 됩니다.
--fake는 모델을 부르지 않고 배선만 확인합니다 (가짜 뒷단, 이미지가 밖으로 나가지 않음).
"""
import argparse
import collections
import json
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from opentelemetry.sdk.trace import TracerProvider  # noqa: E402
from opentelemetry.sdk.trace.export import SimpleSpanProcessor  # noqa: E402

from ocr_harness import project  # noqa: E402
from ocr_harness.common import otlp  # noqa: E402
from ocr_harness.common.model_route import FakeBackend, ModelResult, ModelRoute  # noqa: E402
from ocr_harness.common.ocr import CachedOcr  # noqa: E402
from ocr_harness.common.ocr_vision import OcrFailed, VisionOcrEngine  # noqa: E402
from ocr_harness.pharma.fields import EXTRACTOR  # noqa: E402

B_FIELDS = ("product-name", "active-ingredient")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--labels", required=True)
    parser.add_argument("--images", required=True)
    parser.add_argument("--cache", required=True)
    parser.add_argument("--traces", required=True)
    parser.add_argument("--summary", required=True)
    parser.add_argument("--run-id", default="m1b-vision-pilot")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--all", action="store_true", help="제품당 1장이 아니라 전체 이미지")
    parser.add_argument("--fake", action="store_true", help="모델을 부르지 않고 배선만 확인")
    args = parser.parse_args()

    images = {p.stem: p for p in pathlib.Path(args.images).rglob("*") if p.suffix.lower() in (".jpg", ".jpeg", ".png")}
    chosen, seen_products = [], set()
    for label_path in sorted(pathlib.Path(args.labels).rglob("*.json")):
        label = json.loads(label_path.read_text(encoding="utf-8"))
        product = label["images"][0]["product_name"]
        if label_path.stem not in images or (not args.all and product in seen_products):
            continue
        seen_products.add(product)
        chosen.append((label_path.stem, product, EXTRACTOR.extract(label)))
    if args.limit:
        chosen = chosen[: args.limit]

    if args.fake:
        backend = FakeBackend([ModelResult(text="가짜 출력", input_tokens=10, output_tokens=2) for _ in chosen])
    else:
        from ocr_harness.common.model_agent_sdk import AgentSdkBackend

        backend = AgentSdkBackend()
    traces = pathlib.Path(args.traces)
    traces.parent.mkdir(parents=True, exist_ok=True)
    provider = TracerProvider(resource=project.resource(args.run_id, "0.1.0"))
    provider.add_span_processor(SimpleSpanProcessor(otlp.JsonLinesSpanExporter(traces)))
    route = ModelRoute(project.PROFILE, project.tracer(provider, "0.1.0"), backend, project.PRICES)
    engine = CachedOcr(
        VisionOcrEngine(route, "fake-model" if args.fake else project.VISION_OCR_MODEL,
                        project.VISION_OCR_PROMPT, project.VISION_OCR_MAX_SIDE),
        args.cache,
    )

    counts, failures, lines_total, read_ok = collections.Counter(), collections.Counter(), 0, 0
    products_with_b_misread = set()
    started = time.perf_counter()
    for number, (stem, product, fields) in enumerate(chosen, 1):
        try:
            lines = engine.read(images[stem])
        except OcrFailed as problem:
            # 실패한 이미지는 빼지 않고 따로 셉니다. 이유는 코드(오류 분류, 종료 사유)만 남깁니다.
            failures[str(problem).rsplit(": ", 1)[-1]] += 1
            continue
        read_ok += 1
        lines_total += len(lines)
        texts = [line["text"] for line in lines]
        for field in fields:
            misread = EXTRACTOR.is_misread_text(field, texts)
            counts[f"{field.name}:eligible"] += 1
            counts[f"{field.name}:misread_text"] += misread
            if misread and field.name in B_FIELDS:
                products_with_b_misread.add(product)
        if number % 10 == 0:
            print(f"{number}/{len(chosen)}", flush=True)
    provider.shutdown()

    # 비용 장부는 추적 파일에서 뽑습니다. 캐시에서 읽은 이미지는 이번 실행에 호출이 없으므로 줄도 없습니다.
    rows = []
    if traces.exists():
        rows = project.model_calls(json.loads(line) for line in traces.read_text(encoding="utf-8").splitlines() if line)
    rows = [row for row in rows if row["runId"] == args.run_id]

    def total(key, sub=None):
        values = [(row[key][sub] if sub else row[key]) for row in rows]
        return sum(value for value in values if value is not None)

    summary = {
        "images": len(chosen),
        "read_ok": read_ok,
        "failures": dict(failures),
        "sampling": "all" if args.all else "first image per product by file name",
        "config": engine.config,
        "configDigest": engine.config_digest,
        "mean_lines_per_image": lines_total / read_ok if read_ok else None,
        "seconds_this_run": round(time.perf_counter() - started, 1),
        "judgement": "text only (no boxes)",
        "fields": {
            name: {"eligible": counts[f"{name}:eligible"], "ocr_misread_text_only": counts[f"{name}:misread_text"]}
            for name in ("product-name", "active-ingredient", "expiry")
        },
        "b_type": {
            "eligible": sum(counts[f"{f}:eligible"] for f in B_FIELDS),
            "ocr_misread_text_only": sum(counts[f"{f}:misread_text"] for f in B_FIELDS),
            "products_with_misread": len(products_with_b_misread),
        },
        # 이 실행 id로 추적 파일에 쌓인 모든 호출 (여러 번 나눠 돌렸으면 합쳐진 값).
        "model_calls": {
            "calls": len(rows),
            "by_role": dict(collections.Counter(row["modelRole"] for row in rows)),
            "errors": dict(collections.Counter(row["errorCode"] for row in rows if row["errorCode"])),
            "models": sorted({row["requestModel"] for row in rows}),
            "auth_routes": sorted({row["authRoute"] for row in rows}),
            "input_tokens": total("usage", "inputTokens"),
            "output_tokens": total("usage", "outputTokens"),
            "cache_read_input_tokens": total("cacheReadInputTokens"),
            "cache_write_input_tokens": total("cacheWriteInputTokens"),
            "sdk_reported_usd": round(total("cost", "sdkReportedUsd"), 4),
            "computed_usd": round(total("cost", "computedUsd"), 4),
            "price_table_version": project.PRICES.version,
        },
    }
    pathlib.Path(args.summary).write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
