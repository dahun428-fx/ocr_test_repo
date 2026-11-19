"""공개 저장소에 데이터·개인정보가 들어가지 않았는지 검사합니다 (CLAUDE.md 규칙 1, 2)."""
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

# 이 확장자는 내용과 상관없이 올리지 않습니다 (이미지, 문서, 실행 결과).
DATA_SUFFIXES = {".jpg", ".jpeg", ".png", ".pdf", ".jsonl"}
# JSON은 스키마 폴더와 그 하위 폴더에만 둘 수 있습니다. 라벨 JSON이 섞이는 것을 막습니다.
JSON_ALLOWED_PREFIX = "src/ocr_harness/schemas/"
# 이메일 주소 모양. 촬영자 이메일이 문서나 fixture에 섞이는 것을 잡습니다.
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+")
# 커밋 메시지 서명에 쓰는 주소만 예외입니다.
ALLOWED_EMAILS = {"noreply@anthropic.com"}
# 원본 라벨에서 촬영자 정보를 담는 키
PII_KEY = re.compile(r"""["']writer_num["']\s*:""")


@dataclass(frozen=True)
class Violation:
    """규칙을 어긴 파일 하나와 그 이유."""

    path: str
    reason: str


def find_violations(root: Path, relative_paths: list[str]) -> list[Violation]:
    """root 아래의 파일 목록(보통 `git ls-files` 결과)을 검사해 위반 목록을 돌려줍니다. 비어 있으면 통과입니다."""
    found = []
    for rel in relative_paths:
        # Windows 경로 구분자도 같은 규칙으로 보도록 "/"로 통일합니다.
        posix = PurePosixPath(rel.replace("\\", "/"))
        suffix = posix.suffix.lower()
        if suffix in DATA_SUFFIXES:
            found.append(Violation(rel, f"데이터 파일 형식 {suffix}"))
            continue
        # 접두사 끝의 "/" 때문에 "schemas-data" 같은 비슷한 이름의 폴더는 허용되지 않습니다.
        if suffix == ".json" and not str(posix).startswith(JSON_ALLOWED_PREFIX):
            found.append(Violation(rel, "스키마 폴더 밖의 JSON"))
            continue
        # 글자 파일이면 내용도 검사합니다. 읽을 수 없는 파일(이진 파일, 지워진 파일)은 넘어갑니다.
        try:
            text = (Path(root) / rel).read_text(encoding="utf-8")
        except (UnicodeDecodeError, FileNotFoundError):
            continue
        if any(m.group(0) not in ALLOWED_EMAILS for m in EMAIL.finditer(text)):
            found.append(Violation(rel, "이메일 주소"))
        elif PII_KEY.search(text):
            found.append(Violation(rel, "촬영자 개인정보 키"))
    return found
