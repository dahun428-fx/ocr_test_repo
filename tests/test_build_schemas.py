"""스키마 JSON 파일은 tools/build_schemas.py의 결과와 같아야 합니다 (손으로 고친 흔적이 없어야 함)."""
import importlib.util
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent


def test_schema_files_match_the_build_script():
    spec = importlib.util.spec_from_file_location("build_schemas", ROOT / "tools" / "build_schemas.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)   # __main__이 아니므로 파일을 쓰지 않고 정의만 읽습니다.
    assert module.schemas, "스크립트가 스키마를 하나도 만들지 않았습니다"
    for name, built in module.schemas.items():
        on_disk = json.loads((module.OUT / name).read_text("utf-8"))
        assert on_disk == built, f"{name}: python tools/build_schemas.py 를 다시 실행하세요"
