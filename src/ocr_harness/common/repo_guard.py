"""저장소에 올리면 안 되는 파일을 찾는 검사기. 무엇이 "올리면 안 되는 것"인지는 규칙(Rule) 목록으로 받습니다.

검사기(RepoGuard)는 파일을 돌며 규칙을 차례로 물어볼 뿐이고, 판단은 규칙 객체가 합니다 (전략 패턴).
그래서 프로젝트마다 다른 금지 목록(확장자, 허용 폴더, 개인정보 키)을 코드를 고치지 않고 조립할 수 있고,
여기 없는 규칙은 Rule을 상속해 프로젝트 쪽에서 만들면 됩니다.
"""
import re
from abc import ABC, abstractmethod
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

# 이메일 주소 모양.
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+")


@dataclass(frozen=True)
class Violation:
    """규칙을 어긴 파일 하나와 그 이유."""

    path: str
    reason: str


class Rule(ABC):
    """검사 규칙 하나. 어겼으면 이유(글자열)를, 아니면 None을 돌려줍니다."""

    # 파일 내용이 필요한 규칙이면 True. 경로만 보는 규칙은 False로 두어 이진 파일도 검사할 수 있게 합니다.
    needs_text = False

    @abstractmethod
    def check(self, path: PurePosixPath, text: str | None) -> str | None:
        """path는 "/"로 통일한 상대 경로, text는 파일 내용입니다 (needs_text가 False면 None)."""


class SuffixRule(Rule):
    """이 확장자의 파일은 내용과 상관없이 올리지 않습니다 (이미지, 문서, 실행 결과 등)."""

    def __init__(self, suffixes: Iterable[str]):
        # 대소문자를 가리지 않도록 소문자로 맞춰 둡니다 (".JPEG"도 잡습니다).
        self.suffixes = frozenset(s.lower() for s in suffixes)

    def check(self, path, text):
        suffix = path.suffix.lower()
        return f"데이터 파일 형식 {suffix}" if suffix in self.suffixes else None


class AllowedFolderRule(Rule):
    """이 확장자의 파일은 정해진 폴더(와 그 하위)에만 둘 수 있습니다. 예: JSON은 스키마 폴더에만."""

    def __init__(self, suffix: str, folder: str, reason: str):
        self.suffix = suffix.lower()
        # 끝에 "/"를 붙여 비교합니다. 그래야 "schemas-data"처럼 이름이 비슷한 폴더가 허용되지 않습니다.
        self.prefix = folder.rstrip("/") + "/"
        self.reason = reason

    def check(self, path, text):
        if path.suffix.lower() == self.suffix and not str(path).startswith(self.prefix):
            return self.reason
        return None


class EmailRule(Rule):
    """글 안에 이메일 주소가 있으면 안 됩니다. 허용 목록의 주소만 예외입니다."""

    needs_text = True

    def __init__(self, allowed: Iterable[str] = ()):
        self.allowed = frozenset(allowed)

    def check(self, path, text):
        if any(found.group(0) not in self.allowed for found in EMAIL.finditer(text)):
            return "이메일 주소"
        return None


class ContentPatternRule(Rule):
    """글 안에 이 정규식이 걸리면 안 됩니다. 원본 데이터의 개인정보 키 같은 것을 잡는 데 씁니다."""

    needs_text = True

    def __init__(self, pattern: str, reason: str):
        self.pattern = re.compile(pattern)
        self.reason = reason

    def check(self, path, text):
        return self.reason if self.pattern.search(text) else None


class RepoGuard:
    """규칙 목록으로 파일들을 검사합니다. 목록의 순서가 우선순위입니다."""

    def __init__(self, rules: Sequence[Rule]):
        self.rules = tuple(rules)

    def find_violations(self, root: Path, relative_paths: list[str]) -> list[Violation]:
        """root 아래의 파일 목록(보통 `git ls-files` 결과)을 검사해 위반 목록을 돌려줍니다. 비어 있으면 통과입니다."""
        found = []
        for rel in relative_paths:
            reason = self._first_reason(Path(root), rel)
            if reason:
                found.append(Violation(rel, reason))
        return found

    def _first_reason(self, root: Path, rel: str) -> str | None:
        """파일 하나에 대해 처음 걸린 규칙의 이유. 한 파일은 한 번만 보고합니다."""
        # Windows 경로 구분자도 같은 규칙으로 보도록 "/"로 통일합니다.
        posix = PurePosixPath(rel.replace("\\", "/"))
        text, loaded = None, False
        for rule in self.rules:
            if rule.needs_text:
                # 내용은 처음 필요해질 때 한 번만 읽습니다. 경로 규칙에서 이미 걸린 큰 이미지는 열지도 않습니다.
                if not loaded:
                    text, loaded = self._read(root / rel), True
                if text is None:
                    continue
            reason = rule.check(posix, text if rule.needs_text else None)
            if reason:
                return reason
        return None

    @staticmethod
    def _read(path: Path) -> str | None:
        """글자 파일이면 내용을, 읽을 수 없는 파일(이진 파일, 지워진 파일)이면 None을 돌려줍니다."""
        try:
            return path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, FileNotFoundError):
            return None
