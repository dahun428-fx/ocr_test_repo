"""다른 프로젝트에서도 그대로 쓸 수 있는 공용 부분. 특정 프로젝트의 이름은 여기에 없습니다.

  profile     프로젝트 설정 (Profile): 서비스 이름, 속성 접두사, 스키마 버전
  schema      스키마 묶음과 검증 (SchemaRegistry, FileSchema, SubSchema)
  otlp        추적·평가 이벤트 쓰기와 읽기 (Telemetry, JsonLinesWriter)
  ledger      비용 장부 (Ledger)
  ids         id와 해시 (prefixed_id, manifest_digest, content_digest)
  repo_guard  저장소 검사 (RepoGuard와 Rule들)
  fields      위치가 있는 글자 조각과 필드, 오인식 판정 (FieldExtractor)

이 연구의 이름과 규칙은 ocr_harness.project에서 이 틀에 끼웁니다.
"""
