# Violations 정상·격리 데이터 정합성 보완

## 작업 배경과 입력

- 작업일: 2026-11-20
- 브랜치: `feature/violations-quality-reconciliation`, 기준 커밋 `6023688fa2324d618a6d19120c0b1dc76aa223d9`
- 입력: `data/01_bronze/food_inspections/food_inspections.parquet`의 `Inspection ID`, `Violations`, `_SRC_FILE`, `_LOAD_DTM`
- 기존 `data/02_silver/food_inspections/violations/inspection_violations.parquet`는 보존했다. 이전에는 정상·예외 조각이 한 파일에 함께 있었고, 이번에는 Bronze에서 동일한 분리·파싱 규칙을 재적용해 두 산출물로 나눴다.

Bronze 한 행은 검사 한 건이고, Silver 한 행은 검사에서 분리한 위반 조각 한 건이다. 따라서 검사 행과 위반 조각 행을 직접 같다고 비교하지 않는다. `src/silver/violations_reconciliation.py`의 `run()`은 Bronze를 스트리밍으로 읽고 기존 `parse_fragment()`를 호출한다. `PARSED`이며 식별자·lineage·코드·설명·코멘트가 유효한 조각만 정상 Silver에 기록한다. 나머지는 원문 조각과 `rejection_reason`을 붙여 격리한다. `MISSING_COMMENTS_MARKER`의 설명·코멘트 경계는 추측하지 않는다.

## 산출물과 grain

| 산출물 | 경로 | 한 행의 의미 | 실제 행 수 |
| --- | --- | --- | ---: |
| 정상 Silver | `data/02_silver/food_inspections/violations/inspection_violations_accepted.parquet` | 완전히 파싱된 위반 조각 한 건 | 1,029,015 |
| 격리 | `data/quarantine/food_inspections/violations/inspection_violations_quarantine.parquet` | 파싱 또는 추적 정보에 문제가 있는 위반 조각 한 건 | 1,791 |

두 파일 모두 `(bronze_row_number, item_sequence_num)`으로 조각을 식별한다. 격리 파일은 `inspection_id`, 원문 `source_violations_fragment`, 파싱 상태와 `rejection_reason`을 함께 보존한다. 새 Parquet은 기존 파일을 덮어쓰지 않으며, 재실행 시 이미 존재하는 파일의 바이트가 새 결과와 같을 때만 유지한다.

## 두 단계 정합성과 품질

| 검사 | 실제 계산 | 결과 |
| --- | --- | --- |
| 검사 수준 | 빈 `Violations` 90,000 + 비공란 228,552 = Bronze 318,552 | PASS, 차이 0 |
| 조각 수준 | 정상 1,029,015 + 격리 1,791 = 전체 후보 1,030,806 | PASS, 유실·증가 0 |
| 격리 사유 | `MISSING_COMMENTS_MARKER` 1,791 | 알려진 예외, 원문 보존 |
| 신규 격리 사유·예상 밖 구분자 | 0 / 0 | 추가 이상 없음 |
| grain 중복·정상/격리 중복 | 0 / 0 | PASS |
| 원천 행 번호·순번·검사 ID·원문 조각 추적 차이 | 0 | PASS |
| 정상 데이터의 컬럼별 NULL | 전 컬럼 0 | PASS |
| 격리 데이터의 NULL | 설명 1,791, 코멘트 1,791, 나머지 0 | 알려진 예외와 일치 |

품질 결과는 `reports/quality/violations_reconciliation.json`에 입력 건수, 격리 사유, 컬럼별 NULL, 스키마, 내용 해시와 규칙별 문제 건수로 저장했다. 행이 빠지거나 늘면 `fragment_reconciliation`이 FAIL이 되고 산출물을 게시하지 않는다. 중복 또는 원문 추적 오류도 FAIL이다. 알려진 예외 이외의 사유는 `unexpected_quarantine_reasons`에 따로 기록한다.

## Mapping, 실행과 재현성

기존 `metadata/standards/violations_mapping.csv`는 이전 전체 Silver의 1,030,806건 처리 기록이므로 변경하지 않았다. 새 분기 결과는 `metadata/standards/violations_reconciliation_mapping.csv`에 Bronze `Violations` → 정상 Silver 1,029,015건, Bronze `Violations` → 격리 1,791건으로 별도 기록했다.

실행 명령: `python -m src.domains.02_violation.reconciliation`. 최종 코드로 같은 Bronze를 **연속 두 번 실제 실행**했고 두 실행 모두 PASS였다. 각 실행에서 Bronze 318,552, 빈 셀 90,000, 후보 1,030,806, 정상 1,029,015, 격리 1,791건이었다. 정상·격리의 스키마와 내용 SHA-256이 각각 두 실행에서 동일했다.

- 정상 내용 SHA-256: `2a0c9cbbf0acba55594f777cfd239ed7b851b479370ce67c0777a9ecbca8ba52`
- 격리 내용 SHA-256: `5a418be6a48509a42cd7140fdbdcefa5f1fa973a6c9424d06edfba4c94182e71`
- 실제 Parquet SHA-256: 정상 `4219260693301ab580f9c01add3a401b93793c84497acb1ab53a2cd7dabb7550`, 격리 `7cfe289f851337079085fc96f9db3283af8eb07ad82e6de7ca8a04188b5fdd11`
- 실행 로그: `logs/violations_reconciliation_runs.jsonl` (Git 제외, 실제 실행 이력 누적)

기존 숫자를 코드의 조건이나 PASS 기준으로 사용하지 않는다. `tests/silver/test_violations_reconciliation.py`는 소규모 입력의 정상·격리 분기, 두 번 실행한 내용의 동일성, Bronze에 새 검사 행을 추가했을 때 건수가 다시 계산되는지, 기존 출력과 충돌할 때 어느 파티션도 부분 게시하지 않는지 확인한다. `python -m pytest -q --basetemp C:/violations-reconciliation-full-tests-final3` 결과는 **17개 통과**였다.

앞으로 Bronze 스냅샷이 달라질 때는 `run(root, output_root=새_버전_경로)`로 별도 출력 경로에 생성한다. 기존 정상·격리 Parquet과 다른 결과를 같은 경로에 덮어쓰지 않도록 보호한다. 새 입력의 정상·격리 건수와 품질 결과는 코드가 다시 계산한다.

## 입력 보호와 다음 단계

Origin, Bronze, 기존 Silver의 SHA-256은 각각 `c97464b9aa02801c7e7bedca876d0d6fff482fb56366ad35befe5c68897e4fe7`, `cbc2b9eb8d5feb883d93619d250193ec6d9d59e572ba4f4e9f0b26a9c40c79c5`, `22e2d374d3aaacd351771e01f8f45f87550515b9a7d2e3899e88fad7f08296c4`로 기존 검증값과 같았다. 실행 전후 입력 해시 비교도 PASS였다.

Gold 사전검토의 미해결 문제는 그대로 남는다. 코드 65종에서 비NULL 코드·설명 조합 110개가 관측됐고, 45개 코드는 여러 설명과 연결된다. Inspection 부모 Gold 테이블도 없다. 이번 작업에서 의미 기반 코드 매핑이나 Gold 테이블을 만들지 않았다.
