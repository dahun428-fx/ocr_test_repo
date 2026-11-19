"""공개 저장소에 데이터·개인정보가 들어가지 않는지 검사 (CLAUDE.md 규칙 1, 2)."""
import subprocess
from pathlib import Path

import pytest

from ocr_harness.repo_guard import find_violations

ROOT = Path(__file__).resolve().parents[1]
# 검사기에 걸리지 않도록 실행 시점에 조립합니다.
EMAIL = "someone" + "@" + "example.com"
PII_JSON = '{"writer' + '_num": "x"}'


def _write(tmp_path, name, text="ok"):
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return name


@pytest.mark.parametrize("name", ["a.jpg", "b.JPEG", "c.png", "d.pdf", "runs/e.jsonl", "labels/f.json"])
def test_data_file_types_are_flagged(tmp_path, name):
    rel = _write(tmp_path, name)
    assert [v.path for v in find_violations(tmp_path, [rel])] == [rel]


def test_schema_json_is_allowed(tmp_path):
    rel = _write(tmp_path, "src/ocr_harness/schemas/item.schema.json", "{}")
    assert find_violations(tmp_path, [rel]) == []


def test_schema_json_in_subfolders_is_allowed(tmp_path):
    rel = _write(tmp_path, "src/ocr_harness/schemas/released/1.0.0.json", "{}")
    assert find_violations(tmp_path, [rel]) == []


def test_json_in_a_lookalike_folder_is_still_flagged(tmp_path):
    rel = _write(tmp_path, "src/ocr_harness/schemas-data/label.json", "{}")
    assert len(find_violations(tmp_path, [rel])) == 1


def test_email_address_in_text_is_flagged(tmp_path):
    rel = _write(tmp_path, "notes.md", f"촬영자 {EMAIL}")
    violations = find_violations(tmp_path, [rel])
    assert len(violations) == 1 and "이메일" in violations[0].reason


def test_annotator_pii_key_in_text_is_flagged(tmp_path):
    rel = _write(tmp_path, "fixture.py", f"x = '{PII_JSON}'")
    violations = find_violations(tmp_path, [rel])
    assert len(violations) == 1 and "개인정보" in violations[0].reason


def test_clean_text_file_passes(tmp_path):
    rel = _write(tmp_path, "doc.md", "제품 152종, 이미지 485장")
    assert find_violations(tmp_path, [rel]) == []


def test_tracked_files_in_this_repo_are_clean():
    tracked = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout.split()
    assert tracked, "git 추적 파일 목록이 비어 있습니다"
    assert find_violations(ROOT, tracked) == []
