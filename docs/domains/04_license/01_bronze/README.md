# 01 Bronze · 원천 읽기와 적재 기록

| 입력 | 출력 | 논리 레코드 수 | 원천 → Bronze 컬럼 수 |
| --- | --- | ---: | ---: |
| `data/00_origin/business_licenses.csv` | `data/01_bronze/04_license/business_licenses.parquet` | 1,212,132 | 37 → 38 |
| `data/00_origin/food_inspections.csv` | `data/01_bronze/04_license/food_inspections.parquet` | 318,627 | 17 → 18 |

| 작업 | 적용 내용 |
| --- | --- |
| 원천 값 보존 | 기본 설정에서 CSV 헤더·컬럼 순서와 레코드 순서를 유지합니다. 날짜, 식별자, 빈 문자열까지 CSV 값을 문자열로 읽습니다. |
| 원천 행 추적 | `source_row_num`을 `int64`로 추가합니다. 헤더를 제외한 논리 레코드에 1부터 번호를 매깁니다. 따옴표 안의 줄바꿈은 같은 레코드에 포함됩니다. |
| 입력 검사 | 빈 헤더, 중복 헤더, 예약 컬럼 `source_row_num`, 설정에 지정한 컬럼의 누락을 확인합니다. 커스텀 설정은 CSV 컬럼이나 XLSX 시트·컬럼을 선택할 수 있습니다. |
| 저장과 재실행 | 배치 단위로 읽어 ZSTD 압축 Parquet로 저장합니다. 원천 해시는 읽기 전후에 대조합니다. 같은 위치에 산출물이 있으면 체크섬이 같은지 확인합니다. |

예를 들어 점검 원천의 `License # = "0"`, `Inspection Date = "10/14/2026"`은 Bronze에도 같은 이름과 문자열 값으로 들어갑니다. [전체 입력·출력 컬럼 변환 목록](../../../../metadata/lineage/04_license/column_lineage.csv)

## 적재 기록

두 Parquet 옆의 `ingestion_manifest.json`에는 테이블별로 원천 파일명·형식·인코딩·선택 컬럼·시트·SHA-256, Bronze 파일명·SHA-256·행 수를 기록합니다. 읽기 시작 시각과 적재 기록 시각은 UTC로 기록합니다. 새 산출물은 `created`와 생성 시각을, 기존 산출물 검증은 `verified_existing`과 생성 시각 `null`을 기록합니다. 검증된 동일 입력을 다시 실행하면 기존 적재 기록을 사용합니다. [팀 공유용 매니페스트](../../../../metadata/lineage/04_license/bronze_manifest.json)는 이 스냅샷의 실행 기록을 복사한 파일입니다.

공용본 실행에서 두 Parquet를 생성했고, 원천 값·순서·스키마·행 수와 적재 기록을 대조하는 **7개 검사**가 통과했습니다. [Bronze 변환](../../../../src/domains/04_license/01_bronze.py) · [Bronze 검증](../../../../src/domains/04_license/validate_bronze.py) · [적재 기록 코드](../../../../src/domains/04_license/bronze_manifest.py) · [다음 단계 Silver](../02_silver/README.md)
