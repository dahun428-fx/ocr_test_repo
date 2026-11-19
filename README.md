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

### 코드 (`src/ocr_harness/`)

| 파일 | 역할 |
| --- | --- |
| `schema.py` | 기록 한 건이 스키마에 맞는지 검증. 스키마 버전 상수의 원본 |
| `otlp.py` | OpenTelemetry SDK로 만든 추적·평가 이벤트를 JSONL 파일로 내보내고 다시 읽음 |
| `ledger.py` | 추적 파일의 chat span에서 비용 장부 행을 뽑음 |
| `ids.py` | 항목 id와 RFC 8785 해시 계산 |
| `fields.py` | 라벨이나 OCR 결과에서 제품명·유효성분명·사용기한을 뽑고, OCR 오인식 여부를 판정 |
| `kb_match.py` | 제품명을 식약처 공개 목록과 맞춤 (정확·모호·미매칭) |
| `repo_guard.py` | 데이터 파일, 이메일, 촬영자 정보가 저장소에 들어갔는지 검사 |
| `__init__.py` | 패키지 표시용 빈 파일 |

### 스키마 (`src/ocr_harness/schemas/`)

| 파일 | 역할 |
| --- | --- |
| `item.schema.json` | 평가 항목 1건의 형식 |
| `condition-manifest.schema.json` | 실험 조건 선언의 형식 |
| `traces-data.schema.json` | 추적 파일 한 줄의 형식 (OTLP + 속성 규칙) |
| `logs-data.schema.json` | 평가 이벤트 파일 한 줄의 형식 (OTLP + 속성 규칙) |
| `raw-payload.schema.json` | 저장소 밖에 두는 원문 기록의 형식 |
| `platform/0.2.0/*.json` | 플랫폼 계약 사본 2개 (평가 결과, 지식 문서). 고치지 않음 |
| `otel-genai/76e0c19e7fe1/*` | OTel 메시지 스키마 사본 2개와 출처·라이선스 안내. 고치지 않음 |
| `released/2.0.0.json` | 스키마 2.0.0 전체를 묶은 동결 스냅샷 |

위 다섯 개 `*.schema.json`과 스냅샷은 손으로 고치지 않고 `tools/build_schemas.py`가 만듭니다.

### 도구, 탐색, 테스트

| 파일 | 역할 |
| --- | --- |
| `tools/build_schemas.py` | 스키마의 원본. 속성 표에서 스키마 JSON과 스냅샷을 생성 |
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
