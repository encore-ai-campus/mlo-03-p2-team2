# 02 위반유형 실행 구조

02 위반유형은 각 데이터 단계의 02 폴더를 사용합니다. 입력은 팀 공용 Food Inspections Origin이며, Bronze는 원천의 17개 값과 원천 행 번호인 source_row_num을 보존합니다. 02 실행에는 다른 관점의 Bronze가 필요하지 않습니다.

| 단계 | 실행 명령 | 생성 위치 |
| --- | --- | --- |
| Bronze | `python -m src.domains.02_violation.bronze` | `data/01_bronze/02_violation/02_food_inspections.parquet` |
| Profiling | `python -m src.domains.02_violation.profiling` | `reports/runs/02_violation/` |
| Silver | `python -m src.domains.02_violation.silver` | `data/02_silver/02_violation/` |
| 품질 확인 | `python -m src.domains.02_violation.quality` | `reports/runs/02_violation/` |
| 정상·격리 분리 | `python -m src.domains.02_violation.reconciliation` | `data/02_silver/02_violation/` |
| Gold | `python -m src.domains.02_violation.gold` | `data/03_gold/02_violation/` |
| 분석 Mart | `python -m src.domains.02_violation.build_analysis_mart` | `data/03_gold/02_violation/`, `reports/02_violation/` |

Bronze는 공용 체크섬으로 검증한 로컬 CSV를 읽습니다. CSV가 없으면 공유 분할 파일을 임시 위치에 복원해 읽습니다. Silver 한 행은 위반 조각 하나이며, 원천 행 번호와 조각 순번인 `(source_row_num, item_sequence_num)`으로 식별합니다. 원천 점검 번호 `inspection_id`도 함께 보존합니다.

과거 실행 기록의 경로와 컬럼은 당시 산출물 기준입니다.
