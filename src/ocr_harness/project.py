"""이 연구(의약품 포장 OCR 하네스)의 설정과, 그 설정을 공용 계층에 묶은 함수들.

공용 계층(ocr_harness.common)은 이름을 모르는 틀이고, 여기서 이 연구의 이름을 한 번만 끼웁니다.
  PROFILE    서비스 이름, 속성 접두사 `ocr`, 스키마 버전, 항목 id 접두사
  SCHEMAS    기록 7종과 스키마 파일의 위치
  TELEMETRY  resource · tracer · logger
  LEDGER     비용 장부
  GUARD      공개 저장소에 올리면 안 되는 것의 규칙 목록

나머지 코드와 테스트는 공용 클래스를 직접 조립하지 않고 이 파일의 함수를 부릅니다.
그래야 이름이 한 곳에서만 정해지고, 다른 프로젝트는 이 파일에 해당하는 것 하나만 새로 쓰면 됩니다.
"""
from importlib import resources

from ocr_harness.common.ids import prefixed_id
from ocr_harness.common.ledger import Ledger
from ocr_harness.common.model_route import PriceTable
from ocr_harness.common.otlp import Telemetry
from ocr_harness.common.profile import Profile
from ocr_harness.common.repo_guard import AllowedFolderRule, ContentPatternRule, EmailRule, RepoGuard, SuffixRule
from ocr_harness.common.schema import FileSchema, SchemaError, SchemaRegistry, SubSchema  # noqa: F401  SchemaError는 호출부가 여기서 가져갑니다.
from ocr_harness.pharma.fields import extract_fields, is_misread  # noqa: F401  이 연구의 필드 규칙도 여기서 한 번에 가져가게 합니다.

# 버전 --------------------------------------------------------------------

# 이 저장소가 정의하는 스키마 묶음의 버전. 스키마를 바꾸면 올리고 released 스냅샷을 추가합니다.
SCHEMA_VERSION = "2.1.0"
# 사본으로 가져온 플랫폼 계약의 버전.
PLATFORM_CONTRACT_VERSION = "0.2.0"
# 사본으로 가져온 OTel GenAI 시맨틱 규약의 커밋.
SEMCONV_COMMIT = "76e0c19e7fe1"

# 설정 --------------------------------------------------------------------

PROFILE = Profile(
    service_name="ocr-harness",
    scope_name="ocr_harness",
    namespace="ocr",                 # 이 연구가 직접 정의한 속성은 ocr.* (docs/schema-design.md)
    schema_version=SCHEMA_VERSION,
    item_id_prefix="img-",           # 항목 1건 = 이미지 1장이라서
)

# 스키마 ------------------------------------------------------------------
#   item, conditionManifest, rawPayload   이 저장소가 정의 (형식 규칙은 플랫폼 계약)
#   tracesData, logsData                  OTLP JSON 형식 + 이 저장소의 속성 규칙
#   knowledgeDocument, evaluation         플랫폼 계약 0.2.0 파일을 고치지 않고 그대로 사용
# 스키마 JSON은 tools/build_schemas.py가 만듭니다. 묶음 전체를 schemas/released/<버전>.json으로 동결합니다.

_PLATFORM = f"platform/{PLATFORM_CONTRACT_VERSION}"
# rawPayload 스키마가 $ref로 가리키는 OTel 메시지 스키마. 주소는 원본의 위치이고, 내용은 저장소 안의 사본에서 읽습니다.
_OTEL_BASE = f"https://raw.githubusercontent.com/open-telemetry/semantic-conventions-genai/{SEMCONV_COMMIT}/model/gen-ai/"
_OTEL_FILES = ("gen-ai-input-messages.json", "gen-ai-output-messages.json")

SCHEMAS = SchemaRegistry(
    # 패키지 안의 폴더로 읽습니다. 설치된 뒤에도 같은 경로로 읽힙니다.
    root=resources.files("ocr_harness").joinpath("schemas"),
    kinds={
        "item": FileSchema("item.schema.json"),
        "conditionManifest": FileSchema("condition-manifest.schema.json"),
        "tracesData": FileSchema("traces-data.schema.json"),
        "logsData": FileSchema("logs-data.schema.json"),
        "rawPayload": FileSchema("raw-payload.schema.json"),
        # 플랫폼 검색 응답의 문서 1건 형식을 그대로 씁니다. 그래서 따로 된 파일이 없습니다.
        "knowledgeDocument": SubSchema(f"{_PLATFORM}/retrieval.schema.json", ("properties", "documents", "items")),
        "evaluation": FileSchema(f"{_PLATFORM}/evaluation.schema.json"),
    },
    references={_OTEL_BASE + name: f"otel-genai/{SEMCONV_COMMIT}/{name}" for name in _OTEL_FILES},
    header={
        "schemaVersion": SCHEMA_VERSION,
        "platformContractVersion": PLATFORM_CONTRACT_VERSION,
        "semconvCommit": SEMCONV_COMMIT,
    },
)
KINDS = SCHEMAS.kinds
validate = SCHEMAS.validate      # validate("item", 레코드). 맞지 않으면 SchemaError
bundle = SCHEMAS.bundle          # 현재 스키마 전체. released 스냅샷과 같은지 테스트로 검사합니다.

# 추적 --------------------------------------------------------------------

TELEMETRY = Telemetry(PROFILE)
resource = TELEMETRY.resource    # resource(run_id, service_version)
tracer = TELEMETRY.tracer        # tracer(provider, version)
logger = TELEMETRY.logger        # logger(provider, version)

# 비용 장부 ----------------------------------------------------------------

LEDGER = Ledger(PROFILE)
# 재시도, 보조 모델 호출, 실패한 호출도 각각 한 행입니다 (CLAUDE.md 규칙 7, 8).
model_calls = LEDGER.model_calls

# 모델 가격표 ---------------------------------------------------------------
# 100만 토큰당 달러. 입력·출력·캐시 읽기는 Anthropic 공개 가격(2026-11-03 기준으로 받은 표)이고,
# 캐시 쓰기는 "입력의 1.25배(5분 보존)" 규칙으로 계산한 값입니다. SDK가 1시간 보존을 쓰면 실제는 더 높습니다.
# Haiku의 캐시 읽기 가격은 확인하지 못해 "입력의 0.1배" 규칙으로 적었습니다.
PRICES = PriceTable("2026.11.03", {
    "claude-sonnet-5-5": {"input": 2.0, "output": 10.0, "cache_read": 0.10, "cache_write": 2.5},
    "claude-haiku-5-5": {"input": 0.10, "output": 0.50, "cache_read": 0.01, "cache_write": 0.125},
})
# OCR 단계에서 이미지를 읽히는 모델과 지시문. 바꾸면 OCR 엔진이 달라지는 것이므로 결과 캐시도 따로 둬야 합니다.
VISION_OCR_MODEL = "claude-sonnet-5-5"
VISION_OCR_PROMPT = (
    "이 이미지에 인쇄된 글자를 보이는 그대로 모두 옮겨 적어 주세요.\n"
    "- 한 줄에 글자 한 줄씩, 위에서 아래로, 왼쪽에서 오른쪽 순서로 적습니다.\n"
    "- 고치거나 추측해서 채우지 않습니다. 오타처럼 보여도 인쇄된 대로 적고, 읽을 수 없는 글자는 건너뜁니다.\n"
    "- 설명, 머리말, 번호, 따옴표, 코드 블록 없이 옮겨 적은 글자만 출력합니다."
)
# 보내기 전에 줄이는 긴 변의 크기(px). 1568은 Anthropic 문서가 권하던 긴 변 기준으로 기억하는 값이고,
# 이 모델에서 가장 좋은 크기인지는 확인하지 않았습니다. 바꿔 가며 비교할 수 있게 설정으로 둡니다.
VISION_OCR_MAX_SIDE = 1568

# 분할과 열화 조건 ---------------------------------------------------------

# 제품을 개발용과 평가용으로 가르는 분할의 이름과 개발용 비율. 조건을 고르거나 튜닝하는 일은 개발용에서만 합니다.
# 비율 0.5는 2026-11-20에 Claude가 잠정으로 둔 값입니다 (사용자가 정한 값이 아님). 평가셋을 동결하기 전에 확정합니다.
SPLIT_SALT = "ocr-harness-split-1"
DEV_SHARE = 0.5


def split_of(product: str) -> str:
    """제품 이름 → "dev" 또는 "eval". 같은 제품의 사진은 모두 같은 쪽에 갑니다."""
    from ocr_harness.common.ids import hash_split

    return hash_split(product, SPLIT_SALT, DEV_SHARE)


def degradation_conditions() -> dict:
    """열화 조건 이름 → 열화 객체. 종류 6개에 강도 3단계, 그리고 대조용 identity.

    강도 값은 2026-11-20에 결과를 보기 전에 Claude가 정했습니다. 근거가 있는 값이 아니라
    "약한 것부터 뚜렷이 나쁜 것까지"를 훑으려는 첫 눈금입니다. 실제로 쓸 조건은 개발용 제품의 결과로 고릅니다.
    비율로 적은 값은 이미지 긴 변에 대한 비율입니다 (이 데이터의 긴 변은 약 2700~3500px).
    함수로 둔 것은 Pillow와 numpy를 이 조건을 쓰는 실행에서만 불러오기 위해서입니다.
    """
    from ocr_harness.common.degrade import (
        Downscale, GaussianBlur, Identity, JpegCompression, LowLight, MotionBlur, Rotation,
    )

    levels = {
        "blur": [GaussianBlur(0.002), GaussianBlur(0.004), GaussianBlur(0.008)],
        "motion": [MotionBlur(0.004), MotionBlur(0.008), MotionBlur(0.016)],
        "lowres": [Downscale(800), Downscale(500), Downscale(320)],
        "jpeg": [JpegCompression(20), JpegCompression(10), JpegCompression(5)],
        "lowlight": [LowLight(0.5, 8), LowLight(0.3, 16), LowLight(0.15, 32)],
        "rotate": [Rotation(5), Rotation(10), Rotation(20)],
    }
    conditions = {"identity": Identity()}
    for kind, steps in levels.items():
        for level, degradation in enumerate(steps, 1):
            conditions[f"{kind}-{level}"] = degradation
    return conditions

# id ----------------------------------------------------------------------


def item_id(image_digest: str) -> str:
    """이미지 해시에서 항목 id를 만듭니다 (`img-` + 해시 앞 32자)."""
    return prefixed_id(image_digest, PROFILE.item_id_prefix)


# 저장소 검사 (CLAUDE.md 규칙 1, 2) -------------------------------------------

GUARD = RepoGuard([
    # 이 확장자는 내용과 상관없이 올리지 않습니다 (이미지, 문서, 실행 결과).
    SuffixRule({".jpg", ".jpeg", ".png", ".pdf", ".jsonl"}),
    # JSON은 스키마 폴더와 그 하위 폴더에만 둘 수 있습니다. 라벨 JSON이 섞이는 것을 막습니다.
    AllowedFolderRule(".json", "src/ocr_harness/schemas", "스키마 폴더 밖의 JSON"),
    # 촬영자 이메일이 문서나 fixture에 섞이는 것을 잡습니다. 커밋 메시지 서명에 쓰는 주소만 예외입니다.
    EmailRule(allowed={"noreply@anthropic.com"}),
    # 원본 라벨에서 촬영자 정보를 담는 키.
    ContentPatternRule(r"""["']writer_num["']\s*:""", "촬영자 개인정보 키"),
])
find_violations = GUARD.find_violations   # find_violations(root, 상대 경로 목록)
