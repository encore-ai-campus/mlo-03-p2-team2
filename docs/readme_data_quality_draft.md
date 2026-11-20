# README 데이터 품질 섹션 초안

아래 내용을 README의 데이터 구조 또는 실행 방법 섹션에 추가할 수 있다. 이 파일은 초안이며 README 본문은 이번 작업에서 수정하지 않았다.

## 데이터 품질과 실행 이력

현재 저장소에는 세 원천 데이터의 구조·결측·키 중복·날짜·코드·반복 텍스트·JOIN 후보를 조사한 결과가 정리되어 있습니다.

- 원천 데이터 품질 결과: [데이터 품질 이슈 보고서](../data_quality_issues.md)
- Bronze 원천·출력 경로, 적재 이력 및 해시: [Bronze 적재 이력](bronze_ingestion_log.md)
- 팀 공유 변경 기록: [데이터 품질 보고서 작업 기록](data_quality_report_changelog.md)

요약 실행 로그는 파이프라인 실행 시 logs/pipeline_runs.csv에 기록됩니다. 상세 Bronze provenance 로그는 코드 설정상 실행 시 logs/bronze_run_details.jsonl에 기록됩니다. 현재 작업 시점에는 프로젝트 logs/에 상세 JSONL이 없으며, 문서는 기존 CSV 로그와 실제 데이터에서 확인한 값을 구분해 적었습니다.

프로파일 수치는 측정 결과이고, Silver 처리 방식은 구현 제안입니다. Silver 정제 규칙은 팀 합의와 검증 후 별도 구현합니다.
