# 데이터 품질 보고서 작업 변경 기록

## 작업 개요

- **작업일:** 2026-11-20
- **작업 브랜치:** docs/data-quality-report
- **기준 커밋:** b11d0e2eb9e756990fda64220230f0c48e92aa1f
- **목적:** 기존 원천 프로파일링과 Bronze 적재 증거를 팀원이 확인할 문서로 정리하고, 측정 사실과 Silver 제안을 분리한다.
- **작업자:** 별도 식별 정보가 없어 기록하지 않음.
- **README:** 본문은 수정하지 않고 별도 초안만 작성했다.

## 수행 순서

1. 현재 브랜치, HEAD, Git 변경 상태, stash, 미추적 학습 파일 2개를 확인했다.
2. 기준 커밋에서 대상 브랜치가 없는 것을 확인하고 docs/data-quality-report를 생성했다.
3. Origin 파일·manifest·sidecar 체크섬, 현재 Bronze 파일, 적재 코드와 logs/pipeline_runs.csv를 읽었다.
4. 기존 프로파일 JSON/Markdown, 프로파일 코드, logs/profiling_runs.csv, 코드 매핑 검토표를 대조했다.
5. 측정 결과를 보존하면서 품질 보고서, 적재 이력, README 초안과 작업 기록을 작성했다.
6. 생성 문서의 파일과 내부 링크를 직접 확인하고, 작업 트리 상태 및 git diff --check를 대조해 변경 범위를 검증했다.

## 생성 문서

| 파일 | 목적 |
| --- | --- |
| [docs/data_quality_issues.md](../data_quality_issues.md) | 기존 프로파일의 결측, 중복, 날짜, ZIP, 값 모양, 코드 검토, 반복 텍스트, JOIN, geometry 결과와 Silver 제안을 구분 |
| [bronze_ingestion_log.md](bronze_ingestion_log.md) | Origin·Bronze 경로, 형식, 행·열, 해시, 기술 컬럼, 현재 실행 로그와 임시 검증을 기록 |
| [readme_data_quality_draft.md](readme_data_quality_draft.md) | README에 추가할 데이터 품질 설명과 링크 초안 |
| [data_quality_report_changelog.md](data_quality_report_changelog.md) | 이번 문서 작업의 목적, 근거, 산출물, 확인 방법을 팀 공유용으로 기록 |

## 사용한 근거 자료

- 원천: data/00_origin/download_manifest.csv, 원천 CSV 2개, Community Areas GeoJSON, 각 파일의 .sha256
- Bronze: data/01_bronze/food_inspections/food_inspections.parquet, business_licenses.parquet, community_areas.parquet
- 코드: src/bronze/paths.py, src/bronze/load_bronze.py, src/profiling/profile_sources.py
- 프로파일 결과: metadata/source_profiles.json, metadata/source_profiles.md, metadata/standards/code_mapping_review.csv
- 실행 로그: logs/pipeline_runs.csv, logs/profiling_runs.csv
- 임시 적재 검증: 프로젝트 외부 C:\mlo-03-p2-team2-directory-migration-20261120\verification_logs\의 상세 JSONL과 CSV

## 이번에 직접 확인한 결과

- Origin SHA-256 3개와 Bronze Parquet SHA-256 3개를 읽기 전용으로 확인했다. 각 Parquet을 읽어 행·열 수, string 스키마, _SRC_FILE, _LOAD_DTM을 확인했다.
- 현재 파일의 _LOAD_DTM 2026-11-19T10:46:10Z와 logs/pipeline_runs.csv의 최신 성공 run 시작 시각을 대조했다.
- 기존 프로파일 실행 ID 79e8b4280ab443eb9d73f6774dfff5f5와 프로파일 실행 로그를 확인했다. 프로파일링을 재실행하지 않았다.
- 현재 프로젝트의 logs/bronze_run_details.jsonl은 존재하지 않는다. 코드 기본 경로와 외부 임시 검증 로그를 구분했다.
- 임시 검증 run f8d69cb821d3482c9a79f9f6f6ce240f에서 세 입력·출력 행 수가 일치하고 상태가 성공인 것을 외부 상세 로그에서 확인했다. 출력은 외부 임시 경로였다.
- 프로젝트 테스트는 이번 문서 작업에서 실행하지 않았다. Git whitespace 검사와 생성 문서 검토는 별도로 수행했다.

## 데이터 영향과 남은 합의

이번 변경은 문서 4개 신규 작성뿐이다. Origin, Bronze, 프로파일 측정 파일, Python 코드, 실행 로그는 수정하지 않았다. 학습용 미추적 MD·HTML 2개와 기존 stash를 유지한다. Silver 제안은 구현되지 않았다. 코드 등록 기준, 날짜 업무 유효성, 허가 기간 경계와 다중 후보 처리 방식은 팀 합의가 필요하다.


## 최종 문서 검증 기록 (2026-11-20)

| 실행 명령·확인 | 실제 결과 |
| --- | --- |
| git branch --show-current | docs/data-quality-report |
| git rev-parse HEAD | b11d0e2eb9e756990fda64220230f0c48e92aa1f |
| git status --short --branch --untracked-files=all | 검증 전 요청 문서 4개와 기존 학습 파일 2개가 미추적 상태였고, 다른 변경은 없었다. |
| PowerShell here-string을 python -로 실행한 읽기 전용 SHA·CSV·PyArrow 검사 | Origin 3개 SHA-256이 sidecar 및 manifest와 모두 일치. Origin/Bronze 행·열은 각각 318,552×17/19, 1,212,132×37/39, 77×11/13. Bronze 해시, 컬럼 순서, string 타입, _SRC_FILE, _LOAD_DTM도 문서와 일치했다. |
| 동일한 python - 프로파일·로그 검사 | 기존 프로파일 run 79e8b4280ab443eb9d73f6774dfff5f5와 로그가 SUCCESS. 보고서의 Violations 90,000, License # 중복 269,173, License Number 중복 861,328, ZIP 불일치 166, 날짜 범위 밖 2, 번호 JOIN 다중 후보 266,088, 코드 review 24개 및 missing_raw 1개가 원천 프로파일·검토표와 일치했다. |
| python - 임시 실행 로그 확인 | 외부 상세 JSONL run f8d69cb821d3482c9a79f9f6f6ce240f에서 3개 데이터셋 모두 SUCCESS, 입력·출력 행 수 일치, 출력 경로가 verification_bronze 임시 폴더임을 확인했다. |
| python - Markdown 링크·공백 검사 | 문서 4개 모두 내부 링크 유효, 줄 끝 공백 0건. |
| git diff --check | 통과. |
| git diff --cached --check | 통과. 요청 문서 4개를 스테이징한 뒤 오류 출력 없이 종료 코드 0을 확인했다. |

첫 통합 검사에서 외부 임시 로그 경로를 상대 경로로 조합해 해당 파일을 찾지 못했다. 프로젝트 외부의 실제 절대 경로 C:\mlo-03-p2-team2-directory-migration-20261120\verification_logs\bronze_run_details.jsonl로 고쳐 재확인했고 3건 모두 성공을 확인했다. 이는 읽기 전용 검사 경로 오류였으며 데이터나 로그 파일을 수정하지 않았다.

이번 최종 검증에서는 프로젝트 테스트를 실행하지 않았다. 변경 범위는 문서이며 테스트 실행 요청은 없었다.
