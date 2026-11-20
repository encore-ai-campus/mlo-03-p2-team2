# 00 Origin · 원천 파일과 프로파일링 기준

04번은 `data/origin/`의 시카고 위생점검과 사업체 인허가 스냅샷을 읽습니다. 원천 데이터 문제와 전체 연결 진단은 [04번 통합 문서](../../04_license.md#as-is-원천-데이터-프로파일링)에 기록합니다.

| 원천 파일 | 설명 JSON | 한 행의 단위 | 현재 공용본 | 04번에서 확인하는 정보 |
| --- | --- | --- | ---: | --- |
| `food_inspections.csv` | `food_columns.json` | 위생점검 1건 | 318,627행 × 17열 | 점검 ID, 면허번호, 점검일, 점검 결과 |
| `business_licenses.csv` | `license_columns.json` | 발급·갱신·변경 등 인허가 기록 1건 | 1,212,132행 × 37열 | 원천 ID, 기록 ID, 면허번호, 계정·사업장 번호, 발급일, 유효기간, 상태와 변경일 |

공용 점검 CSV는 `Food_Inspections_20261119.zip`에서 가져왔으며 03번 기록의 SHA-256과 일치합니다. 점검일은 **2010-01-04~2026-11-18**이고 점검 ID 중복은 0건입니다. 인허가·지역 경계와 컬럼 설명 JSON 3개는 기존 파일을 사용했고, 6개 파일 모두 현재 공용 매니페스트와 대조했습니다.

`community_areas.geojson`과 `area_columns.json`은 팀의 지역 분석 원천입니다. 04번 기간 매칭에는 위의 두 CSV를 사용합니다. [팀 원천 인벤토리](../../../source_data_inventory.md)

| 조사 항목 | 확인 방법 |
| --- | --- |
| 스냅샷 일치 | 원천 파일을 읽기 전용으로 열고 파일별 SHA-256을 팀 매니페스트와 대조합니다. |
| 전체 컬럼 | 포털 설명 JSON의 제공 타입과 실제 CSV 헤더·값 형식을 대조합니다. |
| 결측·형식 | 빈 문자열 또는 공백만 있는 값을 결측으로 셉니다. 날짜 형식과 기간의 업무 정합성을 각각 확인합니다. |
| 키와 연결 | `LICENSE ID`는 개별 이력, `LICENSE NUMBER`는 점검과 연결할 후보, `ACCOUNT NUMBER`와 `SITE NUMBER`의 조합은 사업장 식별 후보로 봅니다. 원천 `ID`는 별도로 보존합니다. |

원천 파일은 다음 단계의 입력으로 보존합니다. [원천 설정](../../../../config/sources.example.yaml) · [원천 프로파일링 코드](../../../../src/ingestion/profile_sources.py) · [스냅샷 체크섬](../../../../metadata/source_catalog/verification/download_manifest.csv) · [다음 단계 Bronze](../01_bronze/README.md)
