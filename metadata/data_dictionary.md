# 원천 데이터 사전

생성 명령: `python -m src.profiling.render_dictionary`. 수치는 `metadata/source_profiles.json`의 실제 측정값이다. 의미는 제공된 컬럼 메타데이터의 설명을 사용하며 설명이 없거나 불명확하면 `확인 필요`로 표시했다. 이 문서의 Silver 타입은 원천 조사 당시 권장안이다. 현재 구현은 [공용 Silver 데이터 사전](data_dictionary/README.md)을 참고한다.

결측은 원천의 빈 문자열과 공백만 있는 문자열의 합이다. `NULL` 같은 문자 토큰은 별도 집계하고 결측률에 넣지 않는다. 고유값 수는 검증된 Bronze의 원본 컬럼을 한 컬럼씩 정확히 계산했다.

## food_inspections

원천: `food_inspections/food_inspections.csv` · 318,552행 · 17개 원천 컬럼

| 원본 컬럼명 | 의미 | 원본 형식 | Bronze 타입 | Silver 권장 타입 | 결측 건수·비율 | 고유값 수 | 샘플 값 | 주의사항 |
| --- | --- | --- | --- | --- | ---: | ---: | --- | --- |
| Inspection ID | 확인 필요 | CSV 문자열 / 메타데이터: number | string | string (키) | 0 / 0.0000% | 318,552 | 2646852 | 없음 (측정 범위) |
| DBA Name | Doing Business As | CSV 문자열 / 메타데이터: text | string | string (검토 필요) | 0 / 0.0000% | 35,308 | FLASH HERNANDEZ TACOS | 숫자형·문자형 혼합 |
| AKA Name | Also Known As | CSV 문자열 / 메타데이터: text | string | string (검토 필요) | 2,425 / 0.7613% | 33,598 | FLASH HERNANDEZ TACOS | 숫자형·문자형 혼합 |
| License # | 확인 필요 | CSV 문자열 / 메타데이터: number | string | string (키) | 19 / 0.0060% | 49,379 | 2817892 | 이력/매칭 기준 검토 |
| Facility Type | 확인 필요 | CSV 문자열 / 메타데이터: text | string | string (검토 필요) | 5,358 / 1.6820% | 528 | Mobile Food Preparer | 숫자형·문자형 혼합 |
| Risk | 확인 필요 | CSV 문자열 / 메타데이터: text | string | string (검토 필요) | 88 / 0.0276% | 5 | Risk 2 (Medium) | 없음 (측정 범위) |
| Address | 확인 필요 | CSV 문자열 / 메타데이터: text | string | string (검토 필요) | 3 / 0.0009% | 33,352 | 2300 S THROOP ST | 공백값 3 |
| City | 확인 필요 | CSV 문자열 / 메타데이터: text | string | string (검토 필요) | 184 / 0.0578% | 97 | CHICAGO | 없음 (측정 범위) |
| State | 확인 필요 | CSV 문자열 / 메타데이터: text | string | string (검토 필요) | 76 / 0.0239% | 8 | IL | 없음 (측정 범위) |
| Zip | 확인 필요 | CSV 문자열 / 메타데이터: number | string | string | 42 / 0.0132% | 142 | 60608 | 형식 예외 별도 검증 |
| Inspection Date | 확인 필요 | CSV 문자열 / 메타데이터: calendar_date | string | date (예외 검증 후) | 0 / 0.0000% | 4,250 | 11/17/2026 | 없음 (측정 범위) |
| Inspection Type | 확인 필요 | CSV 문자열 / 메타데이터: text | string | string (검토 필요) | 1 / 0.0003% | 111 | License | 없음 (측정 범위) |
| Results | 확인 필요 | CSV 문자열 / 메타데이터: text | string | string (검토 필요) | 0 / 0.0000% | 7 | Pass | 없음 (측정 범위) |
| Violations | 확인 필요 | CSV 문자열 / 메타데이터: text | string | string (검토 필요) | 90,000 / 28.2528% | 226,798 | 16. FOOD-CONTACT SURFACES: CLEANED & SANITIZED - Comments: OBSERVED BLACK AND ORANGE MOLDLIKE SUBSTANCE ON UPPER INTERIO | 복합 구조, 분해 전 원본 보존 |
| Latitude | 확인 필요 | CSV 문자열 / 메타데이터: number | string | decimal (원본값 병행 보존) | 1,064 / 0.3340% | 18,993 | 41.85045102427 | 없음 (측정 범위) |
| Longitude | 확인 필요 | CSV 문자열 / 메타데이터: number | string | decimal (원본값 병행 보존) | 1,064 / 0.3340% | 18,993 | -87.65879785568 | 없음 (측정 범위) |
| Location | 확인 필요 | CSV 문자열 / 메타데이터: point | string | string (검토 필요) | 1,064 / 0.3340% | 18,993 | (41.85045102427, -87.65879785567869) | 없음 (측정 범위) |

## business_licenses

원천: `business_licenses/business_licenses.csv` · 1,212,132행 · 37개 원천 컬럼

| 원본 컬럼명 | 의미 | 원본 형식 | Bronze 타입 | Silver 권장 타입 | 결측 건수·비율 | 고유값 수 | 샘플 값 | 주의사항 |
| --- | --- | --- | --- | --- | ---: | ---: | --- | --- |
| ID | A calculated ID for each record. | CSV 문자열 / 메타데이터: text | string | string (키) | 0 / 0.0000% | 1,211,880 | 1697585-20270116 | 숫자형·문자형 혼합; 이력/매칭 기준 검토 |
| LICENSE ID | An internal database ID for each record.  Each license can have multiple records as it goes through renewals and other transactions.  See the LICENSE NUMBER field for the number generally known to the public and used in most other data sources that refer to the license. | CSV 문자열 / 메타데이터: number | string | string (키) | 0 / 0.0000% | 1,212,132 | 3111539 | 없음 (측정 범위) |
| ACCOUNT NUMBER | The account number of the business owner, which will stay consistent across that owner's licenses and can be used to find the owner in the Business Owners dataset. | CSV 문자열 / 메타데이터: number | string | string (키) | 0 / 0.0000% | 197,767 | 304027 | 없음 (측정 범위) |
| SITE NUMBER | An internal database ID indicating the location of this licensed business to account for business owners with more than one location. | CSV 문자열 / 메타데이터: number | string | string (키) | 0 / 0.0000% | 544 | 1 | 없음 (측정 범위) |
| LEGAL NAME | 확인 필요 | CSV 문자열 / 메타데이터: text | string | string (검토 필요) | 0 / 0.0000% | 194,473 | VARGAS FINANCIAL INCORPORATED | 숫자형·문자형 혼합 |
| DOING BUSINESS AS NAME | 확인 필요 | CSV 문자열 / 메타데이터: text | string | string (검토 필요) | 0 / 0.0000% | 224,197 | VARGAS FINANCIAL INCORPORATED | NULL형 문자 398; 숫자형·문자형 혼합 |
| ADDRESS | 확인 필요 | CSV 문자열 / 메타데이터: text | string | string (검토 필요) | 0 / 0.0000% | 199,590 | 4009 W ARMITAGE AVE 1 | 없음 (측정 범위) |
| CITY | 확인 필요 | CSV 문자열 / 메타데이터: text | string | string (검토 필요) | 0 / 0.0000% | 2,457 | CHICAGO | 숫자형·문자형 혼합 |
| STATE | 확인 필요 | CSV 문자열 / 메타데이터: text | string | string (검토 필요) | 12 / 0.0010% | 57 | IL | 없음 (측정 범위) |
| ZIP CODE | 확인 필요 | CSV 문자열 / 메타데이터: text | string | string | 329 / 0.0271% | 3,583 | 60639 | 숫자형·문자형 혼합; 형식 예외 별도 검증 |
| WARD | The ward where the business is located. | CSV 문자열 / 메타데이터: number | string | string (검토 필요) | 91,846 / 7.5772% | 51 | 26 | 없음 (측정 범위) |
| PRECINCT | The precinct within the ward where the business is located. Note the the same precinct numbers exist in multiple wards. | CSV 문자열 / 메타데이터: number | string | string (검토 필요) | 93,914 / 7.7478% | 79 | 20 | 없음 (측정 범위) |
| WARD PRECINCT | The ward and precinct where the business is located. This column can be used to filter by precinct more easily across multiple wards. | CSV 문자열 / 메타데이터: text | string | string (검토 필요) | 91,226 / 7.5261% | 2,761 | 26-20 | 숫자형·문자형 혼합 |
| POLICE DISTRICT | 확인 필요 | CSV 문자열 / 메타데이터: number | string | string (검토 필요) | 92,200 / 7.6064% | 33 | 25 | 없음 (측정 범위) |
| COMMUNITY AREA | Community Area Number | CSV 문자열 / 메타데이터: number | string | string (검토 필요) | 99,589 / 8.2160% | 79 | 20 | 없음 (측정 범위) |
| COMMUNITY AREA NAME | Community Area Name | CSV 문자열 / 메타데이터: text | string | string (검토 필요) | 99,655 / 8.2215% | 78 | HERMOSA | 없음 (측정 범위) |
| NEIGHBORHOOD | 확인 필요 | CSV 문자열 / 메타데이터: text | string | string (검토 필요) | 100,632 / 8.3021% | 99 | HERMOSA | 없음 (측정 범위) |
| LICENSE CODE | A code for the type of license. Each code value corresponds to a specific LICENSE DESCRIPTION value. | CSV 문자열 / 메타데이터: number | string | string (검토 필요) | 0 / 0.0000% | 152 | 1010 | 없음 (측정 범위) |
| LICENSE DESCRIPTION | 확인 필요 | CSV 문자열 / 메타데이터: text | string | string (검토 필요) | 0 / 0.0000% | 152 | Limited Business License | 없음 (측정 범위) |
| BUSINESS ACTIVITY ID | A code for the business activity. Each ID value corresponds to a specific BUSINESS ACTIVITY value. | CSV 문자열 / 메타데이터: text | string | string (검토 필요) | 549,101 / 45.3004% | 4,146 | 197 | 숫자형·문자형 혼합 |
| BUSINESS ACTIVITY | 확인 필요 | CSV 문자열 / 메타데이터: text | string | string (검토 필요) | 549,101 / 45.3004% | 4,146 | Provide Tax Preparation Services | 없음 (측정 범위) |
| LICENSE NUMBER | The license number known to the public and generally used in other data sources that refer to the license. This is the field most users will want for most purposes. Each license has a single license number that stays consistent throughout the lifetime of the license. By contrast, the LICENSE ID field is an internal database ID and not generally useful to external users. | CSV 문자열 / 메타데이터: number | string | string (키) | 1 / 0.0001% | 350,804 | 1697585 | 이력/매칭 기준 검토 |
| APPLICATION TYPE | 확인 필요 | CSV 문자열 / 메타데이터: text | string | string (검토 필요) | 0 / 0.0000% | 6 | RENEW | 없음 (측정 범위) |
| APPLICATION CREATED DATE | The date the business license application was created.  RENEW type records do not have an application. | CSV 문자열 / 메타데이터: calendar_date | string | date (예외 검증 후) | 929,252 / 76.6626% | 6,615 | 10/01/2026 | 없음 (측정 범위) |
| APPLICATION REQUIREMENTS COMPLETE | For all application types except RENEW, this is the date all required application documents were received.  For RENEW type records, this is the date the record was created. | CSV 문자열 / 메타데이터: calendar_date | string | string (검토 필요) | 18,415 / 1.5192% | 7,037 | 11/15/2026 | 없음 (측정 범위) |
| PAYMENT DATE | 확인 필요 | CSV 문자열 / 메타데이터: calendar_date | string | date (예외 검증 후) | 22,685 / 1.8715% | 9,067 | 11/16/2026 | 없음 (측정 범위) |
| CONDITIONAL APPROVAL | This pertains to applications that contain liquor licenses. Customers may request a conditional approval prior to building out the space. | CSV 문자열 / 메타데이터: text | string | string (검토 필요) | 0 / 0.0000% | 2 | N | 없음 (측정 범위) |
| LICENSE TERM START DATE | 확인 필요 | CSV 문자열 / 메타데이터: calendar_date | string | date (예외 검증 후) | 2,719 / 0.2243% | 6,448 | 01/16/2027 | 없음 (측정 범위) |
| LICENSE TERM EXPIRATION DATE | 확인 필요 | CSV 문자열 / 메타데이터: calendar_date | string | date (예외 검증 후) | 170 / 0.0140% | 4,042 | 01/15/2029 | 없음 (측정 범위) |
| LICENSE APPROVED FOR ISSUANCE | This is the date the license was ready for issuance. Licenses may not be issued if the customer owes debt to the City. | CSV 문자열 / 메타데이터: calendar_date | string | string (검토 필요) | 56,233 / 4.6392% | 8,847 | 11/16/2026 | 없음 (측정 범위) |
| DATE ISSUED | 확인 필요 | CSV 문자열 / 메타데이터: calendar_date | string | date (예외 검증 후) | 0 / 0.0000% | 6,463 | 11/17/2026 | 없음 (측정 범위) |
| LICENSE STATUS | See the dataset description for the codes used. | CSV 문자열 / 메타데이터: text | string | string (검토 필요) | 0 / 0.0000% | 5 | AAI | 없음 (측정 범위) |
| LICENSE STATUS CHANGE DATE | 확인 필요 | CSV 문자열 / 메타데이터: calendar_date | string | date (예외 검증 후) | 1,131,478 / 93.3461% | 6,152 | 11/09/2026 | 없음 (측정 범위) |
| SSA | Special Service Areas  are local tax districts that fund expanded services and programs, to foster commercial and economic development, through a localized property tax. In other cities these areas are sometimes called Business Improvement Districts (BIDs). This portal contains a map of all Chicago SSAs | CSV 문자열 / 메타데이터: text | string | string (검토 필요) | 896,360 / 73.9490% | 54 | 31 | 없음 (측정 범위) |
| LATITUDE | 확인 필요 | CSV 문자열 / 메타데이터: number | string | decimal (원본값 병행 보존) | 93,498 / 7.7135% | 87,113 | 41.917050893 | 없음 (측정 범위) |
| LONGITUDE | 확인 필요 | CSV 문자열 / 메타데이터: number | string | decimal (원본값 병행 보존) | 93,498 / 7.7135% | 87,112 | -87.7269843986 | 없음 (측정 범위) |
| LOCATION | 확인 필요 | CSV 문자열 / 메타데이터: point | string | string (검토 필요) | 93,498 / 7.7135% | 87,113 | (41.91705089299086, -87.72698439860197) | 없음 (측정 범위) |

## community_areas

원천: `community_areas/community_areas.geojson` · 77행 · 11개 원천 컬럼

| 원본 컬럼명 | 의미 | 원본 형식 | Bronze 타입 | Silver 권장 타입 | 결측 건수·비율 | 고유값 수 | 샘플 값 | 주의사항 |
| --- | --- | --- | --- | --- | ---: | ---: | --- | --- |
| type | GeoJSON Feature 유형 | GeoJSON FeatureCollection 문자열 | string | string (검토 필요) | 0 / 0.0000% | 1 | Feature | 없음 (측정 범위) |
| geometry | GeoJSON 공간 geometry 객체 | GeoJSON 객체 | string | geometry/GeoJSON (검토 필요) | 0 / 0.0000% | 77 | {"type":"MultiPolygon","coordinates":[[[[-87.65455590025104,41.99816614970252],[-87.65573692713699,41.99817520952651],[- | 복합 구조, 분해 전 원본 보존 |
| :id | 확인 필요 | GeoJSON FeatureCollection 문자열 | string | string (검토 필요) | 0 / 0.0000% | 77 | row-m77e_pkv8.vjvf | 없음 (측정 범위) |
| :version | 확인 필요 | GeoJSON FeatureCollection 문자열 | string | string (검토 필요) | 0 / 0.0000% | 77 | rv-3hjp_vkhx~fqfx | 없음 (측정 범위) |
| :created_at | 확인 필요 | GeoJSON FeatureCollection 문자열 | string | string (검토 필요) | 0 / 0.0000% | 1 | 2025-04-22T23:06:36.944Z | 없음 (측정 범위) |
| :updated_at | 확인 필요 | GeoJSON FeatureCollection 문자열 | string | date (예외 검증 후) | 0 / 0.0000% | 1 | 2025-04-22T23:06:36.944Z | 없음 (측정 범위) |
| area_numbe | 확인 필요 | GeoJSON FeatureCollection 문자열 / 메타데이터: number | string | string (키) | 0 / 0.0000% | 77 | 1 | 없음 (측정 범위) |
| community | 확인 필요 | GeoJSON FeatureCollection 문자열 / 메타데이터: text | string | string (검토 필요) | 0 / 0.0000% | 77 | ROGERS PARK | 없음 (측정 범위) |
| area_num_1 | 확인 필요 | GeoJSON FeatureCollection 문자열 / 메타데이터: text | string | string (키) | 0 / 0.0000% | 77 | 1 | 없음 (측정 범위) |
| shape_area | 확인 필요 | GeoJSON FeatureCollection 문자열 / 메타데이터: number | string | decimal (원본값 병행 보존) | 0 / 0.0000% | 77 | 51259902.4506 | 없음 (측정 범위) |
| shape_len | 확인 필요 | GeoJSON FeatureCollection 문자열 / 메타데이터: number | string | decimal (원본값 병행 보존) | 0 / 0.0000% | 77 | 34052.3975757 | 없음 (측정 범위) |
