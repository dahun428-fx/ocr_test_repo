# OCR 하네스 연구

OCR → 모델 조건과 OCR → 하네스(검색·컨텍스트 구성·이력 선별·후처리) → 모델 조건을 같은 데이터에서 비교해, 하네스가 정확도를 유의하게 올리는지와 그 비용을 측정하는 연구용 저장소입니다.

- 안내와 규칙: [CLAUDE.md](CLAUDE.md)
- 연구 플랜: [docs/research-plan.md](docs/research-plan.md)
- 구현 플랜: [docs/implementation-plan.md](docs/implementation-plan.md)
- 할 일: [docs/TODO.md](docs/TODO.md)
- 기록: [docs/HISTORY.md](docs/HISTORY.md)

현재 상태: 설계 단계입니다. 코드는 아직 없습니다. 데이터는 이 저장소에 포함되지 않습니다.

## 개발

```bash
pip install -e ".[dev]"
pytest -q
```

- `src/ocr_harness/schemas/`: 항목, 트레이스, 평가 기록, 비용 장부 스키마 (JSON Schema)
- `src/ocr_harness/schema.py`: 레코드 검증
- `src/ocr_harness/repo_guard.py`: 데이터·개인정보가 저장소에 들어가지 않았는지 검사
- `spikes/`: M1a 탐색 스크립트 (데이터가 있는 PC에서 실행, 집계 숫자만 문서에 기록)
