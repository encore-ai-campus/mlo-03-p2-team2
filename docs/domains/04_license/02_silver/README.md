# 02 Silver · 컬럼 표준화와 결측 처리

| 입력 Bronze | 출력 Silver | 업무 컬럼 | 검증한 행 수 |
| --- | --- | ---: | ---: |
| `data/01_bronze/04_license/04_business_licenses.parquet` | `data/02_silver/04_license/04_business_licenses.parquet` | 19 | 1,212,132 |
| `data/01_bronze/04_license/04_food_inspections.parquet` | `data/02_silver/04_license/04_food_inspections.parquet` | 4 | 318,627 |

두 테이블 모두 업무 컬럼과 함께 `source_row_num`을 보존합니다. 04번에서 선택한 컬럼은 [컬럼 변환 목록](../../../../metadata/lineage/04_license/column_lineage.csv)의 `02_silver` 행에 있습니다. 실행 시에는 [04번 데이터 사전](../../../../src/domains/04_license/%EB%8D%B0%EC%9D%B4%ED%84%B0%20%EC%82%AC%EC%A0%84.csv)을 사용합니다.

| 결정 ID | Bronze 컬럼의 예 | Silver 컬럼의 예 | 표준화 |
| --- | --- | --- | --- |
| `D04-N01` | 인허가 `ID`, `ADDRESS`, `ZIP CODE` | `source_record_id`, `address`, `zip_code` | 양끝 공백 제거, 빈 문자열은 `null`. ZIP은 문자열로 저장해 선행 0을 보존합니다. |
| `D04-N02` | 인허가 `LICENSE ID`, `LICENSE NUMBER`, `ACCOUNT NUMBER`, `SITE NUMBER`와 점검 `Inspection ID` | `license_event_key`, `license_number_key`, `account_key`, `site_key`, `inspection_key` | 양의 정수 형태를 문자열로 보존하고, 유효하지 않은 값은 `null`로 바꿉니다. |
| `D04-N03` | 점검 `Results`, 인허가 `APPLICATION TYPE`, `LICENSE STATUS`, `CITY`, `STATE` | `result_cd`, `application_cd`, `recorded_status_cd`, `city`, `state_cd` | 양끝 공백을 제거한 뒤 대문자로 통일합니다. |
| `D04-N04` | 점검 `Inspection Date`와 인허가의 발급일·기간·상태 변경일·신청 생성일 | `inspection_dtm`, `issued_dtm`, `term_start_dtm`, `term_end_dtm`, `status_change_dtm`, `application_created_dtm` | 미국식 월/일/년과 ISO 날짜를 달력 날짜 `date32`로 파싱합니다. 못 읽는 값은 `null`로 바꿉니다. |
| `D04-N05` | 점검 `License #` | `license_number_key` | 빈칸과 유효하지 않은 식별자, `0`, `9999999`를 `null`로 바꿉니다. |

| 실제 원천 값 | Silver 값 |
| --- | --- |
| 점검 `2645189`의 `License # = "0"` | `license_number_key = null` |
| 같은 점검의 `Inspection Date = "10/14/2026"` | `inspection_dtm = 2026-10-14` (`date32`) |
| 같은 점검의 `Results = "Fail"` | `result_cd = "FAIL"` |

빈 유효기간은 추정해서 채우지 않습니다. 기간이 역전되거나 특이한 연도가 들어 있어도 날짜로 파싱되는 값은 원천 순번과 함께 남깁니다. 공유 스냅샷에서 행 수, 표준 스키마, 사전대로 변환된 값과 순번을 대조하는 **6개 검사**가 통과했습니다. [Silver 변환](../../../../src/domains/04_license/02_normalize.py) · [Silver 검증](../../../../src/domains/04_license/validate_silver.py) · [다음 단계 품질 검사](../quality/README.md)
