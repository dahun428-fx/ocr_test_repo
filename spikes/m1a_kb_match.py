"""M1a (나): 데이터의 제품 ↔ 식약처 공개 품목 목록 매칭 수를 셉니다.

데이터가 있는 PC에서 실행합니다. 식약처 의약품 제품 허가 목록(의약품안전나라 또는 공공데이터포털에서
받은 CSV/XLSX)의 품목명 열을 읽습니다. 집계 숫자만 출력합니다.

    python spikes/m1a_kb_match.py --labels <라벨 폴더> --public <허가 목록 파일> --column 품목명
"""
import argparse
import collections
import csv
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from ocr_harness.kb_match import build_index, match  # noqa: E402


def read_names(path: pathlib.Path, column: str) -> list[str]:
    if path.suffix.lower() in (".xlsx", ".xls"):
        import openpyxl

        sheet = openpyxl.load_workbook(path, read_only=True).active
        rows = sheet.iter_rows(values_only=True)
        header = list(next(rows))
        index = header.index(column)
        return [str(row[index]).strip() for row in rows if row[index]]
    for encoding in ("utf-8-sig", "cp949"):
        try:
            with open(path, encoding=encoding, newline="") as handle:
                return [row[column].strip() for row in csv.DictReader(handle) if row.get(column)]
        except UnicodeDecodeError:
            continue
    raise SystemExit("파일 인코딩을 읽을 수 없습니다")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--labels", required=True)
    parser.add_argument("--public", required=True)
    parser.add_argument("--column", default="품목명")
    args = parser.parse_args()

    products = set()
    for label_path in pathlib.Path(args.labels).rglob("*.json"):
        products.add(json.loads(label_path.read_text(encoding="utf-8"))["images"][0]["product_name"])
    public = read_names(pathlib.Path(args.public), args.column)
    index = build_index(public)
    counts = collections.Counter(match(name, index)[0] for name in products)
    print(json.dumps({"products": len(products), "public_items": len(public), **counts}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
