# OCR 하네스 연구

OCR → 모델 조건과 OCR → 하네스(검색·컨텍스트 구성·이력 선별·후처리) → 모델 조건을 같은 데이터에서 비교해, 하네스가 정확도를 유의하게 올리는지와 그 비용을 측정하는 연구용 저장소입니다.

- 안내와 규칙: [CLAUDE.md](CLAUDE.md)
- 연구 플랜: [docs/research-plan.md](docs/research-plan.md)
- 구현 플랜: [docs/implementation-plan.md](docs/implementation-plan.md)
- 할 일: [docs/TODO.md](docs/TODO.md)
- 기록: [docs/HISTORY.md](docs/HISTORY.md)
- 스키마 설계: [docs/schema-design.md](docs/schema-design.md)
- 오픈소스 도입 검토: [docs/open-source-adoption.md](docs/open-source-adoption.md)

현재 상태: M0(골격)과 M1a(탐색)를 마쳤고 다음은 M1b(수집기)입니다. 데이터는 이 저장소에 포함되지 않습니다.

## 개발

```bash
pip install -e ".[dev]"
pytest -q
```

## 파일별 역할

### 맨 위

| 파일 | 역할 |
| --- | --- |
| `CLAUDE.md` | 이 저장소에서 지킬 규칙과 작업 방식. Claude와 사람이 먼저 읽는 문서 |
| `README.md` | 저장소 소개와 이 파일 목록 |
| `pyproject.toml` | Python 패키지 설정과 의존성 (버전 고정 포함) |
| `.gitignore` | 데이터, 실행 결과, 빌드 부산물이 커밋되지 않게 막음 |
| `.github/workflows/ci.yml` | PR마다 테스트를 돌리는 CI |

### 문서 (`docs/`)

| 파일 | 역할 |
| --- | --- |
| `research-plan.md` | 무엇을 왜 재는가. 연구 질문, 조건, 가설, 통계, 비용 측정 |
| `implementation-plan.md` | 어떤 순서로 만드는가. M0~M8 단계와 관문 |
| `schema-design.md` | 기록 형식의 설계와 근거 (스키마 2.0.0) |
| `open-source-adoption.md` | 오픈소스 도입 판단과 이유 |
| `m1a-results.md` | M1a 탐색의 집계 숫자와 관문 판단 |
| `TODO.md` | 남은 일과 사용자 확인 대기 항목 |
| `HISTORY.md` | 결정과 변경의 날짜순 기록 |

### 공용 코드 (`src/ocr_harness/common/`)

다른 프로젝트에서도 그대로 쓸 수 있는 틀입니다. 이 연구의 이름(`ocr.*`, `ocr-harness`, `img-` 등)은 여기에 없고, 프로젝트가 값이나 자식 클래스로 넣습니다. `tests/test_common.py`가 가상의 다른 프로젝트 설정으로 이 틀을 돌려 그 점을 검사합니다.

| 파일 | 역할 | 프로젝트가 넣는 것 (방식) |
| --- | --- | --- |
| `profile.py` | 프로젝트 설정 `Profile` | 서비스 이름, 속성 접두사, 스키마 버전, 항목 id 접두사 (값) |
| `schema.py` | 스키마 묶음을 읽고 기록을 검증하는 `SchemaRegistry` | 기록 종류와 파일 위치. `FileSchema`(파일 전체) 또는 `SubSchema`(남의 계약 파일의 일부)로 지정 (전략) |
| `otlp.py` | 추적·평가 이벤트를 JSONL로 쓰고 읽음. `Telemetry`가 resource·tracer·logger를 만들고, 두 내보내기는 `JsonLinesWriter`를 물려받음 | `Profile` (값). 새 내보내기는 `_encode`만 정하면 됨 (템플릿 메서드) |
| `ledger.py` | chat span에서 비용 장부 행을 뽑는 `Ledger` | `Profile` (값). 프로젝트만의 열은 상속해서 `extra_columns`에 추가 |
| `ids.py` | 플랫폼 id와 RFC 8785 해시 | id 접두사 (인자) |
| `repo_guard.py` | 저장소에 올리면 안 되는 파일을 찾는 `RepoGuard` | 규칙 목록. `SuffixRule`, `AllowedFolderRule`, `EmailRule`, `ContentPatternRule`을 조립하거나 `Rule`을 상속 (전략) |
| `fields.py` | 위치가 있는 글자 조각(`Token`), 필드(`Field`), 읽는 순서, 오인식 판정 | `FieldExtractor`를 상속해 `extract`를 구현하고 정규화 규칙(`Normalizer`)을 지정 |

### 이 연구의 설정 (`src/ocr_harness/project.py`)

공용 틀에 이 연구의 이름을 끼우는 한 곳입니다. `PROFILE`, `SCHEMAS`, `TELEMETRY`, `LEDGER`, `GUARD`를 만들고, 거기에 묶인 함수를 내놓습니다: `validate`, `bundle`, `resource`, `tracer`, `logger`, `model_calls`, `item_id`, `find_violations`, `extract_fields`, `is_misread`. 나머지 코드와 테스트는 이 함수들을 부릅니다. 다른 프로젝트는 이 파일에 해당하는 것 하나와 자기 도메인 폴더만 새로 쓰면 됩니다.

### 이 프로젝트 전용 코드 (`src/ocr_harness/pharma/`)

의약품 패키징 OCR 데이터에만 해당합니다. 다른 도메인이 오면 이 폴더 옆에 새 폴더를 둡니다.

| 파일 | 역할 |
| --- | --- |
| `fields.py` | 라벨에서 제품명·유효성분명·사용기한을 뽑는 규칙 (`PharmaFieldExtractor`)과 단위 표기 정규화. 오인식 판정은 공용 `FieldExtractor`의 것을 물려받음 |
| `kb_match.py` | 제품명을 식약처 공개 목록과 맞춤 (정확·모호·미매칭) |

### 스키마 (`src/ocr_harness/schemas/`)

| 파일 | 역할 | 공용 / 전용 |
| --- | --- | --- |
| `item.schema.json` | 평가 항목 1건의 형식 | 전용에 가까움 (필드, 질의 유형 A/B/C) |
| `condition-manifest.schema.json` | 실험 조건 선언의 형식 | 공용에 가까움 (구성요소 5개의 이름만 이 연구의 것) |
| `traces-data.schema.json` | 추적 파일 한 줄의 형식 (OTLP + 속성 규칙) | OTLP 구조는 공용, `ocr.*` 속성 규칙은 전용 |
| `logs-data.schema.json` | 평가 이벤트 파일 한 줄의 형식 (OTLP + 속성 규칙) | 위와 같음 |
| `raw-payload.schema.json` | 저장소 밖에 두는 원문 기록의 형식 | 공용 |
| `platform/0.2.0/*.json` | 플랫폼 계약 사본 2개 (평가 결과 `evaluation`, 지식 문서 `knowledgeDocument`는 `retrieval.schema.json`의 문서 형식). 고치지 않음 | 공용 |
| `otel-genai/76e0c19e7fe1/*` | OTel 메시지 스키마 사본 2개와 출처·라이선스 안내. 고치지 않음 | 공용 |
| `released/2.0.0.json` | 스키마 2.0.0 전체를 묶은 동결 스냅샷 | - |

위 다섯 개 `*.schema.json`과 스냅샷은 손으로 고치지 않고 `tools/build_schemas.py`가 만듭니다.

### 도구, 탐색, 테스트

| 파일 | 역할 |
| --- | --- |
| `tools/build_schemas.py` | 스키마의 원본. 속성 표에서 스키마 JSON과 스냅샷을 생성. 만드는 방법은 공용, 안의 속성 표는 전용 |
| `spikes/m1a_field_restore.py` | M1a (가): 라벨에서 필드가 복원되는지 집계 (PC에서 실행) |
| `spikes/m1a_kb_match.py` | M1a (나): 제품 152종을 식약처 목록과 매칭 (PC에서 실행) |
| `spikes/m1a_ocr_misread.py` | M1a (다): 로컬 OCR을 돌려 오인식 필드 수 집계 (PC에서 실행) |
| `tests/samples.py` | 테스트용 합성 기록을 SDK로 만드는 도우미 |
| `tests/test_schemas.py` | 스키마가 맞는 기록은 받고 틀린 기록은 거부하는지 |
| `tests/test_build_schemas.py` | 스키마 파일이 생성 스크립트 결과와 같은지 |
| `tests/test_otlp.py` | 파일 내보내기와 읽기 |
| `tests/test_ledger.py` | 비용 장부 집계 |
| `tests/test_ids.py` | id와 해시 |
| `tests/test_fields.py` | 필드 추출과 오인식 판정 |
| `tests/test_kb_match.py` | 식약처 매칭 |
| `tests/test_repo_guard.py` | 저장소 검사. 이 저장소의 추적 파일 전체도 검사 |
