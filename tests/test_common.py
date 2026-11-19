"""공용 계층(ocr_harness.common)이 이 연구의 이름 없이도 도는지 검사합니다.

여기서는 일부러 다른 프로젝트(가상의 영수증 프로젝트)의 설정을 넣어 봅니다.
공용 코드에 `ocr.*`, `ocr-harness`, `img-` 같은 이름이 박혀 있으면 이 테스트가 깨집니다.
"""
import json

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from ocr_harness.common import otlp
from ocr_harness.common.fields import Field, FieldExtractor, Normalizer, Token
from ocr_harness.common.ids import prefixed_id
from ocr_harness.common.ledger import Ledger
from ocr_harness.common.profile import Profile
from ocr_harness.common.repo_guard import ContentPatternRule, RepoGuard, Rule, SuffixRule
from ocr_harness.common.schema import FileSchema, SchemaError, SchemaRegistry, SubSchema

RECEIPT = Profile(service_name="receipt-harness", scope_name="receipt_harness", namespace="receipt",
                  schema_version="0.3.0", item_id_prefix="doc-")


# 설정 ---------------------------------------------------------------------

def test_profile_builds_attribute_names_under_its_namespace():
    assert RECEIPT.attr("run.id") == "receipt.run.id"


def test_profile_rejects_a_namespace_that_collides_with_a_standard_prefix():
    # gen_ai.*와 platform.*은 표준과 플랫폼의 이름이라 프로젝트가 가져다 쓰면 안 됩니다.
    with pytest.raises(ValueError):
        Profile("s", "s", "gen_ai", "1.0.0", "x-")


# 추적 ---------------------------------------------------------------------

def _receipt_trace():
    """영수증 프로젝트의 추적 한 줄: 루트 1개 + 모델 호출 1개."""
    telemetry = otlp.Telemetry(RECEIPT)
    memory = InMemorySpanExporter()
    provider = TracerProvider(resource=telemetry.resource("run-r1", "0.1.0"))
    provider.add_span_processor(SimpleSpanProcessor(memory))
    tracer = telemetry.tracer(provider, "0.1.0")
    with tracer.start_as_current_span("invoke_agent receipt-harness") as root:
        root.set_attributes({"receipt.item.id": "doc-1", "receipt.condition.id": "base"})
        with tracer.start_as_current_span("chat fake-model") as chat:
            chat.set_attributes({
                "gen_ai.request.model": "fake-model", "gen_ai.usage.input_tokens": 10, "gen_ai.usage.output_tokens": 2,
                "receipt.model.role": "main", "receipt.cost.computed_usd": 0.001, "receipt.shop.kind": "cafe",
            })
    return otlp.encode_traces(memory.get_finished_spans())


def test_resource_uses_the_profile_names():
    attributes = otlp.flatten_spans(_receipt_trace())[0]["resource"]
    assert attributes == {
        "service.name": "receipt-harness", "service.version": "0.1.0",
        "receipt.run.id": "run-r1", "receipt.schema.version": "0.3.0",
    }


def test_tracer_uses_the_profile_scope_name():
    assert _receipt_trace()["resourceSpans"][0]["scopeSpans"][0]["scope"]["name"] == "receipt_harness"


@pytest.mark.parametrize("exporter_class, encode", [
    (otlp.JsonLinesSpanExporter, "encode_traces"), (otlp.JsonLinesLogExporter, "encode_logs"),
])
def test_both_exporters_share_one_file_writer(tmp_path, exporter_class, encode):
    # 두 내보내기는 "한 묶음을 한 줄로 덧붙인다"는 같은 뼈대(JsonLinesWriter)를 물려받습니다.
    assert issubclass(exporter_class, otlp.JsonLinesWriter)
    exporter = exporter_class(tmp_path / "out.jsonl")
    exporter.export([])
    exporter.export([])
    lines = (tmp_path / "out.jsonl").read_text(encoding="utf-8").splitlines()
    assert [json.loads(line) for line in lines] == [getattr(otlp, encode)([])] * 2


# 비용 장부 -----------------------------------------------------------------

def test_ledger_reads_the_profile_namespace():
    row = Ledger(RECEIPT).model_calls([_receipt_trace()])[0]
    assert (row["runId"], row["itemId"], row["conditionId"]) == ("run-r1", "doc-1", "base")
    assert (row["modelRole"], row["cost"]["computedUsd"]) == ("main", 0.001)
    assert row["usage"] == {"inputTokens": 10, "outputTokens": 2}


def test_ledger_subclass_can_add_project_columns():
    class ReceiptLedger(Ledger):
        def extra_columns(self, call, root, resource):
            return {"shopKind": call.get(self.profile.attr("shop.kind"))}

    assert ReceiptLedger(RECEIPT).model_calls([_receipt_trace()])[0]["shopKind"] == "cafe"


# id ----------------------------------------------------------------------

def test_prefixed_id_takes_any_prefix():
    assert prefixed_id("sha256:" + "ab" * 32, "doc-") == "doc-" + "ab" * 16


def test_prefixed_id_rejects_a_prefix_that_breaks_the_platform_id_pattern():
    with pytest.raises(ValueError):
        prefixed_id("sha256:" + "ab" * 32, "Doc_")


# 저장소 검사 ----------------------------------------------------------------

def _write(tmp_path, name, text="ok"):
    (tmp_path / name).write_text(text, encoding="utf-8")
    return name


def test_guard_is_a_list_of_rules(tmp_path):
    guard = RepoGuard([SuffixRule({".csv"}), ContentPatternRule(r"card_number", "카드 번호 키")])
    paths = [_write(tmp_path, "a.csv"), _write(tmp_path, "b.py", "card_number = 1"), _write(tmp_path, "c.py")]
    assert [(v.path, v.reason) for v in guard.find_violations(tmp_path, paths)] == [
        ("a.csv", "데이터 파일 형식 .csv"), ("b.py", "카드 번호 키"),
    ]


def test_guard_accepts_a_rule_written_by_the_project(tmp_path):
    class NoTodo(Rule):
        needs_text = True

        def check(self, path, text):
            return "TODO 남음" if "TODO" in text else None

    violations = RepoGuard([NoTodo()]).find_violations(tmp_path, [_write(tmp_path, "a.py", "# TODO")])
    assert [v.reason for v in violations] == ["TODO 남음"]


def test_guard_reports_one_violation_per_file(tmp_path):
    # 한 파일이 여러 규칙에 걸려도 먼저 걸린 규칙 하나만 보고합니다 (목록의 순서가 우선순위).
    guard = RepoGuard([SuffixRule({".csv"}), ContentPatternRule(r"x", "x 있음")])
    assert len(guard.find_violations(tmp_path, [_write(tmp_path, "a.csv", "x")])) == 1


# 스키마 --------------------------------------------------------------------

def _registry(tmp_path):
    (tmp_path / "receipt.schema.json").write_text(json.dumps({
        "type": "object", "required": ["total"], "properties": {"total": {"$ref": "https://example.test/money.json"}},
    }), encoding="utf-8")
    (tmp_path / "money.json").write_text(json.dumps({"type": "number", "minimum": 0}), encoding="utf-8")
    (tmp_path / "response.schema.json").write_text(json.dumps({
        "properties": {"lines": {"items": {"type": "object", "required": ["text"]}}},
    }), encoding="utf-8")
    return SchemaRegistry(
        root=tmp_path,
        kinds={"receipt": FileSchema("receipt.schema.json"),
               "line": SubSchema("response.schema.json", ("properties", "lines", "items"))},
        references={"https://example.test/money.json": "money.json"},
        header={"schemaVersion": "0.3.0"},
    )


def test_registry_validates_a_file_schema_and_follows_local_references(tmp_path):
    registry = _registry(tmp_path)
    registry.validate("receipt", {"total": 12.5})
    with pytest.raises(SchemaError, match="receipt: total"):
        registry.validate("receipt", {"total": -1})


def test_registry_can_use_a_part_of_another_schema(tmp_path):
    registry = _registry(tmp_path)
    registry.validate("line", {"text": "아메리카노"})
    with pytest.raises(SchemaError):
        registry.validate("line", {})


def test_registry_rejects_an_unknown_kind(tmp_path):
    with pytest.raises(KeyError):
        _registry(tmp_path).validate("nope", {})


def test_registry_bundle_holds_header_schemas_and_references(tmp_path):
    bundle = _registry(tmp_path).bundle()
    assert bundle["schemaVersion"] == "0.3.0"
    assert set(bundle["schemas"]) == {"receipt", "line"}
    assert bundle["references"] == {"https://example.test/money.json": {"type": "number", "minimum": 0}}


# 필드 ----------------------------------------------------------------------

class TotalExtractor(FieldExtractor):
    """가상의 영수증 라벨 {"total": {"text", "box"}}에서 합계 필드 하나를 뽑습니다."""

    normalizer = Normalizer(replacements=(("원", "krw"),), strip=r"[\s,]")

    def extract(self, label):
        return [Field("total", "A", (Token(label["total"]["text"], tuple(label["total"]["box"])),))]


def test_normalizer_applies_the_project_rules():
    assert TotalExtractor.normalizer("12,000 원") == "12000krw"


def test_extractor_judges_misread_with_its_own_normalizer():
    extractor = TotalExtractor()
    field = extractor.extract({"total": {"text": "12,000원", "box": [0, 0, 100, 20]}})[0]
    assert extractor.is_misread(field, [Token("12000 KRW", (0, 0, 100, 20))]) is False
    assert extractor.is_misread(field, [Token("72000 KRW", (0, 0, 100, 20))]) is True
    assert extractor.is_misread(field, [Token("12000 KRW", (500, 500, 600, 520))]) is True   # 그 자리에 아무것도 없음


def test_extractor_cannot_be_used_without_an_extract_rule():
    with pytest.raises(TypeError):
        FieldExtractor()


# 의존 방향 -----------------------------------------------------------------

def test_common_does_not_import_project_code():
    # 공용 계층이 이 연구의 설정(project)이나 도메인(pharma)을 가져다 쓰면 다른 프로젝트로 옮길 수 없습니다.
    from pathlib import Path

    import ocr_harness.common

    for path in Path(ocr_harness.common.__file__).parent.glob("*.py"):
        imports = [line for line in path.read_text(encoding="utf-8").splitlines() if line.startswith(("import ", "from "))]
        assert not [line for line in imports if "ocr_harness.project" in line or "ocr_harness.pharma" in line], path.name
