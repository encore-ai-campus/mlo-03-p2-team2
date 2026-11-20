# 00 Origin · 원천 파일과 프로파일링

05 지역 분석은 팀 공용 위생점검 CSV의 좌표·결과·위반 원문을 Community Area 경계에 연결합니다. 공용 원천의 기본 경로는 `data/00_origin/`입니다.

| 파일 | 한 행의 의미 | 검증 범위 | 주요 입력 |
| --- | --- | --- | --- |
| `food_inspections.csv` | 점검 ID별 위생점검 1건 | 318,627행 × 17열, 2010-01-04~2026-11-18 | 점검 ID·일자·결과·위반 원문·위경도·시설 및 점검 유형·위험 등급 |
| `community_areas.geojson` | Community Area 경계 1개 | 지역 번호 1~77의 Feature 77개 | 지역 번호·이름·경계 도형 |

팀 점검 CSV는 저장소의 gzip 조각에서 복원합니다. 저장소 루트에서 공용 복원 스크립트를 실행하면 분할 파일의 체크섬을 확인하고 CSV를 복원합니다. 05 적재 시에는 두 입력 파일의 SHA-256을 다시 확인합니다. [공용 원천 복원 방법](../../../project_setup_and_sharing.md#팀-공용-원천) · [05 입력 계약과 체크섬](../../../../metadata/data_dictionary/05_geospatial/column_contract.json)

| 조사 항목 | 확인 내용 |
| --- | --- |
| 점검 키와 기간 | 점검 ID 공란·중복은 0건입니다. 처음과 마지막 관측 점검일은 파일명 날짜와 구분합니다. |
| 좌표 | 공란·파싱 실패·범위 초과를 구분하며, 지역에 배정할 수 없는 건도 집계합니다. |
| 원문 기록 | 위반란 공란과 코드 파싱 상태는 각각 기록합니다. |
| 경계 | GeoJSON의 좌표를 경도·위도 순서로 읽고 지역 번호와 폴리곤의 유효성을 확인합니다. |

05 로컬 비교에는 `origin/05_geospatial/`의 `Food_Inspections_20261120.csv`와 `export.csv`를 사용합니다. 점검 CSV 두 버전은 관측 행 수와 기간이 같고 SHA-256이 다릅니다. 실측 지문과 GeoJSON·WKT 비교는 검증 보고서에 기록합니다. [검증 보고서](../../../../reports/05_geospatial/README.md) · [다음 단계 Bronze](../01_bronze/README.md)
