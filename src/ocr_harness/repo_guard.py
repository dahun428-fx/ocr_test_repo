"""공개 저장소에 데이터·개인정보가 들어가지 않았는지 검사합니다 (CLAUDE.md 규칙 1, 2)."""
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

DATA_SUFFIXES = {".jpg", ".jpeg", ".png", ".pdf", ".jsonl"}
# JSON은 스키마 폴더에만 둘 수 있습니다. 라벨 JSON이 섞이는 것을 막습니다.
JSON_ALLOWED_DIR = "src/ocr_harness/schemas"
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+")
ALLOWED_EMAILS = {"noreply@anthropic.com"}
# 원본 라벨에서 촬영자 정보를 담는 키
PII_KEY = re.compile(r"""["']writer_num["']\s*:""")


@dataclass(frozen=True)
class Violation:
    path: str
    reason: str


def find_violations(root: Path, relative_paths: list[str]) -> list[Violation]:
    found = []
    for rel in relative_paths:
        posix = PurePosixPath(rel.replace("\\", "/"))
        suffix = posix.suffix.lower()
        if suffix in DATA_SUFFIXES:
            found.append(Violation(rel, f"데이터 파일 형식 {suffix}"))
            continue
        if suffix == ".json" and str(posix.parent) != JSON_ALLOWED_DIR:
            found.append(Violation(rel, "스키마 폴더 밖의 JSON"))
            continue
        try:
            text = (Path(root) / rel).read_text(encoding="utf-8")
        except (UnicodeDecodeError, FileNotFoundError):
            continue
        if any(m.group(0) not in ALLOWED_EMAILS for m in EMAIL.finditer(text)):
            found.append(Violation(rel, "이메일 주소"))
        elif PII_KEY.search(text):
            found.append(Violation(rel, "촬영자 개인정보 키"))
    return found
