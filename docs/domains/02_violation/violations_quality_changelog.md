# Food Inspections Violations Quality 검사 기록

## 작업 개요

- 작업일: 2026-11-20
- Worktree: C:\mlo-03-p2-team2
- 브랜치: feature/violations-quality
- 기준 커밋: 810caa048a5d5c0d58a5f48656a5e85a0c878953
- 검사 범위: Food Inspections의 Violations Silver 결과만
- 실행 명령: python -m src.domains.02_violation.quality

Silver 표준화나 다른 데이터셋 품질관리는 수행하지 않았다. Origin, Bronze, Silver, Mapping은 읽기만 했다.

## 검사 입력과 기준

Bronze 입력은 data/01_bronze/food_inspections/food_inspections.parquet이며, Violations, Inspection ID와 _SRC_FILE/_LOAD_DTM lineage를 사용했다. 검사 대상 Silver는 data/02_silver/food_inspections/violations/inspection_violations.parquet이다. 프로파일 결과 reports/profiling/violations_profile.json과 metadata/standards/violations_mapping.csv를 실제 Bronze/Silver 결과와 대조했다.

Quality 코드는 Bronze를 다시 배치로 읽어 분리 후보와 기대 파싱 값을 계산한다. 각 Silver 행의 원천 행 번호, 조각 순번, Inspection ID, lineage 값, 원문 조각을 해당 Bronze 행과 순서대로 대조한다. 코드·설명·코멘트·상태도 원문 조각에서 다시 계산해 비교한다. Silver grain은 Bronze 검사 행 안의 위반사항 조각 한 건이며 키는 bronze_row_number + item_sequence_num이다. 같은 코드가 반복돼도 중복으로 세지 않는다.

각 품질 규칙은 issue_rows가 0이면 PASS, 0보다 크면 FAIL이다. 설명·코멘트 NULL은 MISSING_COMMENTS_MARKER 상태의 수와 같을 때 의도된 값으로 PASS 처리한다. 다른 Silver 컬럼의 NULL은 0건을 기대한다. 규칙별 결과는 reports/quality/violations_quality_report.csv에 남긴다.

## 실제 검사 결과

| 항목 | 재측정 결과 | 상태 |
| --- | ---: | --- |
| Bronze 전체 행 | 318,552 | PASS |
| Violations 빈 문자열 | 90,000 | PASS, Silver 행 미생성 |
| Violations 비공란 | 228,552 | PASS |
| 여러 위반사항 셀이 포함된 수 | 197,271 | PASS |
| Bronze에서 재분리한 후보 조각 | 1,030,806 | PASS |
| Silver 행 | 1,030,806 | PASS, 후보와 일치 |
| 정상 파싱 PARSED | 1,029,015 | PASS |
| MISSING_COMMENTS_MARKER | 1,791 | PASS, 프로파일과 일치 |
| 그 외 status | 0 | PASS |
| 코드 헤더 추출 실패 / Silver 코드 NULL | 0 / 0 | PASS |
| Bronze / Silver 고유 코드 수 | 65 / 65 | PASS, 코드 집합 차이 0 |
| description/comments 추출 불일치 | 0 / 0 | PASS |
| 원천 lineage 또는 raw fragment 불일치 | 0 | PASS |
| grain 키 중복 / 순번 오류 | 0 / 0 | PASS |
| 품질 규칙 전체 | 26 PASS / 0 FAIL | PASS |

Silver의 NULL은 inspection_id 0, bronze_row_number 0, item_sequence_num 0, _SRC_FILE 0, _LOAD_DTM 0, source_violations_fragment 0, violation_code 0, violation_description 1,791, violation_comments 1,791, parsing_status 0이다. 설명·코멘트 각 1,791건은 모두 MISSING_COMMENTS_MARKER 행에만 존재하는 의도된 NULL이며, 이 상태의 조각을 보정하거나 경계를 추정하지 않았다.

## Mapping 확인

metadata/standards/violations_mapping.csv는 8개 대상 행을 검사했다. 중복 target, 누락 target, 예상 외 target, 처리 건수 불일치가 모두 0이다.

| Mapping 대상 | 실제 affected_rows |
| --- | ---: |
| source_violations_fragment | 1,030,806 |
| inspection_id | 1,030,806 |
| violation_code | 1,030,806 |
| violation_description | 1,029,015 |
| violation_comments | 1,029,015 |
| parsing_status | 1,030,806 |
| no child record | 90,000 |
| multiple violation records | 197,271 |

Mapping 값이 실측과 일치해 수정하지 않았다.

## 검증 코드와 실행 로그

품질검사 코드는 src/quality/violations_quality.py, 테스트는 tests/quality/test_violations_quality.py다. 테스트는 일치하는 임시 Bronze/Silver에서 PASS를 확인하고, grain 키와 원문 조각이 손상된 fixture에서 FAIL을 감지하는지 확인한다.

실행 로그는 logs/violations_quality_runs.jsonl에 기록했다. 최종 실행 ID는 ee5ffd28aae14b35a105de91a8a88c93이며, 실행 시간은 2026-11-20 05:10:22Z~05:10:40Z다. 로그에는 입력·출력 SHA-256, 규칙 상태, 집계, 성공 여부를 남겼다. 이전 실제 실행 이력도 로그에서 삭제하지 않았다.

실행한 테스트:

    python -m pytest tests/quality/test_violations_quality.py -q --basetemp C:/violations-quality-tests5
    python -m pytest -q --basetemp C:/violations-quality-all

Quality 전용 테스트 2개, 전체 테스트 14개가 통과했다. git diff --check와 staged diff 검사도 수행한다.

## 데이터 보존 및 다음 단계

Origin SHA-256은 실행 전후 c97464b9aa02801c7e7bedca876d0d6fff482fb56366ad35befe5c68897e4fe7로 같았다. Bronze는 cbc2b9eb8d5feb883d93619d250193ec6d9d59e572ba4f4e9f0b26a9c40c79c5, Silver는 22e2d374d3aaacd351771e01f8f45f87550515b9a7d2e3899e88fad7f08296c4로 각각 실행 전후 일치했다. 기존 Silver 파일은 수정하지 않았다.

현재 품질 기준에서는 Gold 모델 설계를 시작할 수 있다. 다만 65개 violation_code는 형식과 코드 집합만 검증했으며 업무 의미를 제공하는 공인 코드 사전과의 매핑은 검증하지 않았다. Gold에서 위반 유형 차원이나 표준 설명을 만들 때 코드 의미의 기준 자료를 정해야 한다. 이번 단계에서는 Gold 데이터를 생성하지 않았다.
