# 02 위반유형 실행 구조

02 위반유형은 팀 공용 Food Inspections Bronze인 `data/01_bronze/food_inspections/food_inspections.parquet`를 재사용합니다. 공용 Bronze에 적힌 원천 파일명 `_SRC_FILE`과 최초 Bronze 적재 시각 `_LOAD_DTM`은 02 Bronze 파생에도 그대로 보존합니다. 강사 실습의 Silver 저장 규칙에 따라 두 기술 컬럼은 Silver부터 제외합니다. 원천 CSV는 공용 Bronze의 값·순서·행 수와 SHA-256을 검증할 때 읽습니다.

개발 워크트리는 `C:\mlo-03-p2-team2`이며 작업 브랜치는 `codex/domain-02-bronze-lineage`입니다.

## 전체 실행

저장소 루트에서 공용 점검 Bronze가 준비된 상태로 아래 명령을 실행합니다. 공용 Bronze의 적재 계약은 [Bronze 안내](../../bronze.md)를 따릅니다.

```powershell
python -m src.domains.02_violation.runner
```

명령이 출력한 `reports/runs/02_violation/lineage-…/` 아래에 새 산출물이 생성됩니다. 실행별 폴더에는 `data/`, `metadata/`, `reports/`, `logs/`가 있습니다. 기존 Git 공유 스냅샷과 체크섬은 당시 실행의 기록으로 유지합니다. 실제 결과를 사용할 때는 해당 실행의 `run.json`에서 `status`가 `PASS`인지 확인합니다.

다음 표의 단일 단계 명령은 해당 작업 루트에 각 단계의 입력이 준비돼 있을 때 사용합니다. 기존 공유 산출물이 있는 저장소에서는 위 전체 실행 명령으로 새 결과를 생성합니다.

| 단계 | 실행 명령 | 생성 위치 |
| --- | --- | --- |
| 02 Bronze 파생 | `python -m src.domains.02_violation.bronze` | `data/01_bronze/02_violation/02_food_inspections.parquet` |
| Profiling | `python -m src.domains.02_violation.profiling` | `reports/runs/02_violation/` |
| Silver | `python -m src.domains.02_violation.silver` | `data/02_silver/02_violation/` |
| 품질 확인 | `python -m src.domains.02_violation.quality` | `reports/runs/02_violation/` |
| 정상·격리 분리 | `python -m src.domains.02_violation.reconciliation` | `data/02_silver/02_violation/` |
| Gold | `python -m src.domains.02_violation.gold` | `data/03_gold/02_violation/` |
| 분석 Mart | `python -m src.domains.02_violation.build_analysis_mart` | `data/03_gold/02_violation/`, `reports/02_violation/` |

## 추적 컬럼과 품질 대사

| 단계 | 한 행의 의미 | 저장하는 추적 정보 |
| --- | --- | --- |
| 공용 Bronze | 원천 점검 1건 | 원천 컬럼 17개, `_SRC_FILE`, `_LOAD_DTM` |
| 02 Bronze 파생 | 같은 원천 점검 1건 | 공용 Bronze의 전체 컬럼과 1부터 시작하는 `source_row_num` |
| Silver 후보·정상·격리 | 점검의 위반 조각 1개 | `inspection_id`, `source_row_num`, `item_sequence_num` |
| Gold 사실·분석 Mart | 승인된 위반 조각 1개 | Silver에서 이어받은 점검 ID·원천 행 번호·조각 순번 |
| Gold 위반 차원 | 코드·설명 조합 1개 | 위반 유형 키와 설명. 점검별 추적은 연결된 사실에서 조회 |

`source_row_num`은 02 Bronze 파생에서 한 번 부여합니다. CSV에서 따옴표로 묶인 줄바꿈이 있어도 논리 레코드 한 건에 번호 하나만 붙입니다. Silver가 한 점검을 여러 위반 조각으로 펼칠 때는 같은 번호를 복사하고 `item_sequence_num`으로 조각 순서를 구분합니다.

품질 검사는 두 단위에서 따로 대사합니다. 점검 단위에서는 **공란 점검 + 위반 원문이 있는 점검 = Bronze 점검**입니다. 위반 조각 단위에서는 **정상 조각 + 격리 조각 = 전체 후보 조각**입니다. 원문 공란은 위반 0건으로 해석하지 않으며, 코멘트 구분자가 없어 해석을 완료하지 못한 조각은 원문과 격리 사유를 남깁니다. Gold 사실·마트의 행 수는 정상 조각 수와 같아야 합니다.

- `metadata/standards/02_violation/violations_mapping.csv`에 원천·대상 컬럼, 변경 규칙, 적용 건수를 기록합니다.
- `violations_quality_report.csv`와 `violations_reconciliation.json`에 품질 검사와 정상·격리 건수를 기록합니다.
- `run.json`에 전체 실행 상태, 입력 SHA-256, 공용 Bronze 경로와 그 적재 정보, 시작·종료 시각을 기록하고 `logs/02_violation/`에 단계별 실행 로그를 남깁니다. Silver 실행 시각은 Bronze의 `_LOAD_DTM`과 별개입니다.

동일한 원천과 동일한 공용 Bronze로 재실행하면 데이터 결과가 재현됩니다. 새 원천이 추가되면 팀에서 새 스냅샷과 체크섬을 먼저 확정하고 공용 Bronze를 갱신합니다. 02는 공란, 후보, 정상, 격리 건수를 새 입력에서 다시 계산합니다.

## 원천 품질과 검증 결과

검증에 사용한 점검 원천의 SHA-256은 `b43beb7fae834a8698ca162004caf2929cb2eca7ff75c27b4db6bf07aa103c98`입니다.

| 검증 항목 | 실제 결과 | 처리 |
| --- | ---: | --- |
| 위반 원문 공란 | 90,022점검 | 원천과 02 Bronze 파생에 모두 보존. 위반 조각 생성 대상에서 제외 |
| 위반 원문이 있는 점검 | 228,605점검 | 공란 점검을 합하면 Bronze 318,627건과 일치 |
| 코멘트 구분자가 없는 조각 | 1,792조각 | `MISSING_COMMENTS_MARKER`로 격리하고 원문을 보존 |
| 파싱된 정상 위반 | 1,029,281조각 | 격리와 합하면 후보 1,031,073조각과 일치. Gold 사실·마트 각각 1,029,281행 |
| 적재 정보 및 행 번호 | 02 Bronze 파생 행 번호 1~318,627 | 공용 Bronze의 두 기술 컬럼은 02 Bronze 파생에 보존하고 Silver부터 제외 |

수정 후 실제 데이터로 전체 실행을 완료했습니다. Silver 품질 검사 24개를 통과했고, Bronze 파생에는 두 기술 컬럼이 있으며 Silver 후보·정상·격리와 Gold에는 없음을 실제 Parquet 스키마에서 확인했습니다.

Silver의 `inspection_id`와 `violation_code`는 문자열로 유지합니다. 위반 원문을 정해진 구분자로 분리하고 설명·코멘트의 양끝 공백을 정리합니다. 코드 번호의 여러 설명을 임의로 하나로 통합하지 않으며, 자세한 규칙과 예외는 [위반 유형 분석 계약](violation_types_analysis_contract.md)을 따릅니다. 점검일·위험등급 등 공용 점검 컬럼의 표준화는 [팀 데이터 통합 기준](../../data_integration_conventions.md)에서 다룹니다.

과거 실행 기록의 경로와 컬럼은 당시 산출물 기준입니다.
