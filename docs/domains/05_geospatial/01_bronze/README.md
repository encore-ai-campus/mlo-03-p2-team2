# 01 Bronze · 원천 적재와 행 계보

공용 원천 두 파일을 `data/01_bronze/05_geospatial/<batch_id>/`에 적재합니다.

| 입력 | 출력 | 원천 행 |
| --- | --- | ---: |
| `food_inspections.csv` | `food_inspections.parquet` | 318,627 |
| `community_areas.geojson` | `community_areas.parquet` | 77 |

점검 CSV의 원천 헤더, 컬럼 순서, 문자열을 보존합니다. 인용부호 안의 줄바꿈은 하나의 논리 레코드에 포함합니다. 헤더와 완전히 빈 레코드를 제외한 뒤 1부터 `source_row_num`을 부여하고, 빈 레코드 수를 매니페스트에 별도로 기록합니다. GeoJSON에서는 공간 연산에 필요한 지역 속성 5개와 도형을 읽어 좌표 정밀도를 유지한 WKT로 변환합니다.

## 적재 기록

각 행은 데이터셋, `batch_id`, `source_row_num`으로 추적합니다. `manifest.json`에는 원천 파일명·포맷·SHA-256·행 수·빈 레코드 수·UTC 적재 시각과 Parquet의 행 수·스키마·체크섬을 기록합니다. 생성한 파일을 검증한 뒤 배치 경로에 게시하며, 같은 입력으로 재실행하면 기존 산출물을 검증합니다. [원천 컬럼 대응표](../../../../metadata/data_dictionary/05_geospatial/column_mapping.csv) · [Bronze·Silver 적재 코드](../../../../src/domains/05_geospatial/geographic_medallion.py)

팀 공유용 적재 기록은 검증한 공용 배치 `11b4c745f6de3592c100`의 실행 매니페스트에서 원천·출력 지문과 UTC 시각을 옮긴 것입니다. 파일 경로는 저장소 기본 경로로 표기합니다. 배치를 다시 적재한 경우 해당 실행의 `manifest.json`에서 출력 지문과 시각을 확인합니다. [팀 공유용 적재 기록](../../../../metadata/lineage/05_geospatial/bronze_manifest.json)

공용 점검 318,627건과 경계 77곳의 원천 컬럼·값·순번을 Bronze와 대조했습니다. [검증 절차](../quality/README.md) · [다음 단계 Silver](../02_silver/README.md)
