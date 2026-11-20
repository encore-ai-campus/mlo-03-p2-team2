# 04 사업체 인허가 통합 제시안

점검 한 건이 **어느 면허·사업장 이력과 점검일 기준으로 연결되는지** 기록합니다. 팀의 공용 점검 테이블에는 `inspection_key`로 04번 결과를 붙일 수 있습니다. [공용 취합·표준화 기준](../data_integration_conventions.md)

## 취합할 데이터와 행 단위

| 원천 | 한 행의 의미 | 04번에서 가져오는 정보 |
| --- | --- | --- |
| `food_inspections.csv` | 점검 한 건 | 점검 ID, 면허번호, 점검일, 점검 결과 |
| `business_licenses.csv` | 인허가 기록 한 건 | 인허가 기록 ID, 면허번호, 계정·사업장 번호, 발급·갱신 정보, 유효기간 |

Bronze와 Silver에서는 원천별 행 수와 순번을 보존합니다. 기간 후보 계산은 파생 테이블에서 수행하고, **팀에 제공할 매칭 결과는 점검 1건당 1행**으로 유지합니다. [04번 AS-IS와 단계별 변환 기록](04_license.md)

## 공용으로 맞출 이름과 타입

| 원천 컬럼 | 표준 컬럼 · 타입 | 04번 사용 목적 |
| --- | --- | --- |
| `Inspection ID` | `inspection_key` · `string` | 공용 점검과 04번 결과 연결 |
| `License #` / `LICENSE NUMBER` | `license_number_key` · `string` | 점검과 인허가 사이 면허번호 대조 |
| `LICENSE ID` | `license_event_key` · `string` | 발급·갱신 등 개별 인허가 기록 식별 |
| `ACCOUNT NUMBER` / `SITE NUMBER` | `account_key` / `site_key` · `string` | 사업장 키의 후보 조합 |
| `Inspection Date` | `inspection_dtm` · `date32` | 기간 매칭 기준일 |
| `LICENSE TERM START DATE` / `LICENSE TERM EXPIRATION DATE` | `term_start_dtm` / `term_end_dtm` · `date32` | 해당 인허가의 시작일과 만료일 |
| `Results` / `APPLICATION TYPE` / `LICENSE STATUS` | `result_cd` / `application_cd` / `recorded_status_cd` · `string` | 결과와 상태를 각각 표준 코드로 표현 |

숫자처럼 보이는 식별자는 문자열로 보관합니다. 원천 날짜의 `MM/DD/YYYY` 형식을 달력 날짜로 바꾸고, 문서에는 `YYYY-MM-DD`로 표시합니다. [04번 데이터 사전](../../src/domains/04_license/%EB%8D%B0%EC%9D%B4%ED%84%B0%20%EC%82%AC%EC%A0%84.csv) · [공용 코드표 초안](../../metadata/data_dictionary/shared_code_map.csv)

## 연결 방식과 다른 관점에 제공할 컬럼

면허번호가 같고 **시작일 ≤ 점검일 ≤ 만료일**인 인허가 기록을 후보로 셉니다. 시작일이나 만료일이 비어 있거나 기간이 역전된 기록은 원천 행을 보존한 상태에서 기간 후보에서 제외합니다. 후보 한 건은 인허가 기록과 연결하며, 여러 건이면 후보 수와 미확정 상태를 남깁니다.

| 제공 컬럼 | 타입 | 해석 |
| --- | --- | --- |
| `inspection_key` | `string` | 공용 점검 테이블에 붙이는 키 |
| `candidate_count_num` | `int64` | 점검일을 포함하는 인허가 기록의 수 |
| `match_status_cd` | `string` | 단일 후보·다중 후보 또는 후보 없음의 사유 |
| `matched_license_event_id` | `string`, null 허용 | 후보가 한 건일 때 연결한 인허가 기록 ID |
| `establishment_key` | `string` | 연결한 인허가의 계정·사업장 조합. 확인이 어려운 경우 `__unknown__` |

03번 반복 점검 분석은 확인된 사업장 키를 이력 연결에 활용할 수 있습니다. 05번 지역 분석은 `inspection_key`로 후보 수와 매칭 상태를 붙여 지역별 매칭 품질을 확인할 수 있습니다.

## 현재 스냅샷 검증

| 점검일 기준 후보 | 점검 건수 |
| --- | ---: |
| 0건 | 84,828 |
| 1건 | 232,323 |
| 2건 이상 | 1,401 |
| 전체 | 318,552 |

전체 점검 중 인허가 기간 후보가 있는 비율은 **73.37%**입니다. 이 결과는 원천에 기록된 기간을 기준으로 한 후보 집계입니다. [04번 실행과 검증](04_license.md)

## 팀에서 합의할 항목

1. 공용 점검·인허가 컬럼 이름과 타입, 코드표 적용 범위를 확정합니다.
2. 기간 경계를 양쪽 포함으로 둘지, 취소·철회일을 면허 상태와 기간에 어떻게 반영할지 정합니다.
3. 사업장 키 조합의 유효 범위와 다중 후보를 확정할 근거를 정합니다. AI-Ready에 쓸 때는 예측 기준일에 확인할 수 있었던 정보의 범위도 함께 검증합니다.
