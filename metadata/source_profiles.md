# Origin 구조·품질 프로파일

실행 ID `79e8b4280ab443eb9d73f6774dfff5f5` · UTC `2026-11-19T11:11:15Z` · 재실행: `python -m src.profiling.profile_sources` 및 `python -m src.profiling.render_profiles`

## 측정 기준

- CSV는 UTF-8(선택적 BOM), 쉼표 구분자로 파싱했다. GeoJSON은 UTF-8 `FeatureCollection`으로 파싱했다. 원천 파일과 대응 `.sha256`을 대조했다.
- **빈 값**은 CSV 필드가 정확히 빈 문자열이거나 JSON `null`인 경우다. **공백값**은 비어 있지 않으나 `strip()` 결과가 빈 문자열인 경우다. `NULL`·`N/A`·`NA`·`NONE`은 **NULL형 문자값**으로 별도 기록했고 자동 결측 처리하지 않았다.
- 결측률 = (빈 값 + 공백값) / 전체 행 수. 고유값 수는 원천값 전체 대조를 통과한 Bronze 원본 컬럼에서 컬럼별로 정확히 계산했다. 빈 문자열도 고유값에 포함된다.
- 숫자형·문자형 혼합은 **문자 모양**의 분류다. 업무 데이터 타입 오류 판정이 아니다. 날짜의 비정상 연도는 1900년 미만 또는 2100년 초과라는 **조사 기준**이며 자동 정제 기준이 아니다.
- 완전 동일 행 수는 각 행의 128비트 digest로 비교한 결과다. 해시 충돌 가능성이 있으므로 엄밀한 원문 바이트 단위 중복 증명은 아니다.

## 데이터 출처

세 파일은 `data/00_origin/download_manifest.csv`에 시카고시 오픈데이터 다운로드 URL과 SHA-256이 기록된 동일 스냅샷이다. 원천 파일 경로와 제공 컬럼 메타데이터는 아래 데이터셋별로 제시한다.

## food_inspections

- 파일: `data/00_origin/food_inspections/food_inspections.csv` · 형식: CSV · 인코딩: UTF-8 (optional BOM) · 318,552행 × 17컬럼
- 출처 URL(원본 manifest): https://data.cityofchicago.org/api/v3/views/4ijn-s7e5/export.csv?accessType=DOWNLOAD
- 제공 컬럼 메타데이터: `data/00_origin/food_inspections/food_columns.json`. 메타데이터에만 있는 항목: ['Census Tracts', 'Community Areas', 'Historical Wards 2003-2015', 'Location (address)', 'Location (city)', 'Location (state)', 'Location (zip)', 'Wards', 'Zip Codes']. 실제 속성에만 있는 항목: 없음.
- 원본 컬럼 목록·의미·타입·샘플: [data_dictionary.md](data_dictionary.md). 재현 가능한 전체 측정값: [source_profiles.json](source_profiles.json).
- 완전 동일 행 후보: 0건.

### 컬럼별 결측과 고유값

| 원본 컬럼 | 빈 값 | 공백값 | NULL형 문자 | 결측률 | 고유값 수 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Inspection ID | 0 | 0 | 0 | 0.0000% | 318,552 |
| DBA Name | 0 | 0 | 0 | 0.0000% | 35,308 |
| AKA Name | 2,425 | 0 | 0 | 0.7613% | 33,598 |
| License # | 19 | 0 | 0 | 0.0060% | 49,379 |
| Facility Type | 5,358 | 0 | 0 | 1.6820% | 528 |
| Risk | 88 | 0 | 0 | 0.0276% | 5 |
| Address | 0 | 3 | 0 | 0.0009% | 33,352 |
| City | 184 | 0 | 0 | 0.0578% | 97 |
| State | 76 | 0 | 0 | 0.0239% | 8 |
| Zip | 42 | 0 | 0 | 0.0132% | 142 |
| Inspection Date | 0 | 0 | 0 | 0.0000% | 4,250 |
| Inspection Type | 1 | 0 | 0 | 0.0003% | 111 |
| Results | 0 | 0 | 0 | 0.0000% | 7 |
| Violations | 90,000 | 0 | 0 | 28.2528% | 226,798 |
| Latitude | 1,064 | 0 | 0 | 0.3340% | 18,993 |
| Longitude | 1,064 | 0 | 0 | 0.3340% | 18,993 |
| Location | 1,064 | 0 | 0 | 0.3340% | 18,993 |

### 키·형식·날짜

| 키 후보 | 중복 출현 행 수 | 중복률 |
| --- | ---: | ---: |
| License # | 269,173 | 84.4989% |

도시명 표기 사례(전체 행 기준): `{'CHICAGO': 317229, 'Chicago': 544, 'chicago': 175, 'CCHICAGO': 62}`.
사업체명 대소문자 표기 차이 사례: `[['TROPICAL SMOOTHIE CAFE', 'Tropical Smoothie Cafe'], ['ROTI', 'Roti'], ['SEE THRU CHINESE KITCHEN', 'See Thru Chinese Kitchen'], ['PAZZA PIZZA', 'Pazza Pizza'], ['SUBWAY', 'Subway']]`. 동일 사업체임을 확정한 것은 아니다.

날짜는 비어 있지 않은 값을 `%m/%d/%Y`로 달력 파싱했다. 파싱 실패와 범위 밖 연도는 별도 측정했다.

| 날짜 컬럼 | 최소 | 최대 | 파싱 실패 | 조사 범위 밖 연도 | 예시 |
| --- | --- | --- | ---: | ---: | --- |
| Inspection Date | 2010-01-04 | 2026-11-17 | 0 | 0 | — |

숫자 모양과 일반 문자가 함께 나온 컬럼(업무상 혼합 타입으로 확정한 것은 아님):

| 컬럼 | 정수 모양 | 소수 모양 | 그 외 문자 |
| --- | ---: | ---: | ---: |
| DBA Name | 23 | 0 | 318,529 |
| AKA Name | 45 | 0 | 316,082 |
| Facility Type | 15 | 0 | 313,179 |

ZIP의 미국 5자리 또는 ZIP+4 정규식 불일치: **0건**. 예시: 없음. 해외 주소·원천 오류 여부는 별도 판단이 필요하다.

## business_licenses

- 파일: `data/00_origin/business_licenses/business_licenses.csv` · 형식: CSV · 인코딩: UTF-8 (optional BOM) · 1,212,132행 × 37컬럼
- 출처 URL(원본 manifest): https://data.cityofchicago.org/api/v3/views/r5kz-chrr/export.csv?accessType=DOWNLOAD
- 제공 컬럼 메타데이터: `data/00_origin/business_licenses/license_columns.json`. 메타데이터에만 있는 항목: ['Census Tracts', 'Community Areas', 'Historical Wards 2003-2015', 'LOCATION (address)', 'LOCATION (city)', 'LOCATION (state)', 'LOCATION (zip)', 'Wards', 'Zip Codes']. 실제 속성에만 있는 항목: 없음.
- 원본 컬럼 목록·의미·타입·샘플: [data_dictionary.md](data_dictionary.md). 재현 가능한 전체 측정값: [source_profiles.json](source_profiles.json).
- 완전 동일 행 후보: 0건.

### 컬럼별 결측과 고유값

| 원본 컬럼 | 빈 값 | 공백값 | NULL형 문자 | 결측률 | 고유값 수 |
| --- | ---: | ---: | ---: | ---: | ---: |
| ID | 0 | 0 | 0 | 0.0000% | 1,211,880 |
| LICENSE ID | 0 | 0 | 0 | 0.0000% | 1,212,132 |
| ACCOUNT NUMBER | 0 | 0 | 0 | 0.0000% | 197,767 |
| SITE NUMBER | 0 | 0 | 0 | 0.0000% | 544 |
| LEGAL NAME | 0 | 0 | 0 | 0.0000% | 194,473 |
| DOING BUSINESS AS NAME | 0 | 0 | 398 | 0.0000% | 224,197 |
| ADDRESS | 0 | 0 | 0 | 0.0000% | 199,590 |
| CITY | 0 | 0 | 0 | 0.0000% | 2,457 |
| STATE | 12 | 0 | 0 | 0.0010% | 57 |
| ZIP CODE | 329 | 0 | 0 | 0.0271% | 3,583 |
| WARD | 91,846 | 0 | 0 | 7.5772% | 51 |
| PRECINCT | 93,914 | 0 | 0 | 7.7478% | 79 |
| WARD PRECINCT | 91,226 | 0 | 0 | 7.5261% | 2,761 |
| POLICE DISTRICT | 92,200 | 0 | 0 | 7.6064% | 33 |
| COMMUNITY AREA | 99,589 | 0 | 0 | 8.2160% | 79 |
| COMMUNITY AREA NAME | 99,655 | 0 | 0 | 8.2215% | 78 |
| NEIGHBORHOOD | 100,632 | 0 | 0 | 8.3021% | 99 |
| LICENSE CODE | 0 | 0 | 0 | 0.0000% | 152 |
| LICENSE DESCRIPTION | 0 | 0 | 0 | 0.0000% | 152 |
| BUSINESS ACTIVITY ID | 549,101 | 0 | 0 | 45.3004% | 4,146 |
| BUSINESS ACTIVITY | 549,101 | 0 | 0 | 45.3004% | 4,146 |
| LICENSE NUMBER | 1 | 0 | 0 | 0.0001% | 350,804 |
| APPLICATION TYPE | 0 | 0 | 0 | 0.0000% | 6 |
| APPLICATION CREATED DATE | 929,252 | 0 | 0 | 76.6626% | 6,615 |
| APPLICATION REQUIREMENTS COMPLETE | 18,415 | 0 | 0 | 1.5192% | 7,037 |
| PAYMENT DATE | 22,685 | 0 | 0 | 1.8715% | 9,067 |
| CONDITIONAL APPROVAL | 0 | 0 | 0 | 0.0000% | 2 |
| LICENSE TERM START DATE | 2,719 | 0 | 0 | 0.2243% | 6,448 |
| LICENSE TERM EXPIRATION DATE | 170 | 0 | 0 | 0.0140% | 4,042 |
| LICENSE APPROVED FOR ISSUANCE | 56,233 | 0 | 0 | 4.6392% | 8,847 |
| DATE ISSUED | 0 | 0 | 0 | 0.0000% | 6,463 |
| LICENSE STATUS | 0 | 0 | 0 | 0.0000% | 5 |
| LICENSE STATUS CHANGE DATE | 1,131,478 | 0 | 0 | 93.3461% | 6,152 |
| SSA | 896,360 | 0 | 0 | 73.9490% | 54 |
| LATITUDE | 93,498 | 0 | 0 | 7.7135% | 87,113 |
| LONGITUDE | 93,498 | 0 | 0 | 7.7135% | 87,112 |
| LOCATION | 93,498 | 0 | 0 | 7.7135% | 87,113 |

### 키·형식·날짜

| 키 후보 | 중복 출현 행 수 | 중복률 |
| --- | ---: | ---: |
| LICENSE NUMBER | 861,328 | 71.0589% |
| ID | 252 | 0.0208% |

도시명 표기 사례(전체 행 기준): `{'CHICAGO': 1120881}`.

날짜는 비어 있지 않은 값을 `%m/%d/%Y`로 달력 파싱했다. 파싱 실패와 범위 밖 연도는 별도 측정했다.

| 날짜 컬럼 | 최소 | 최대 | 파싱 실패 | 조사 범위 밖 연도 | 예시 |
| --- | --- | --- | ---: | ---: | --- |
| APPLICATION CREATED DATE | 2000-06-19 | 2026-11-17 | 0 | 0 | — |
| APPLICATION REQUIREMENTS COMPLETE | 2000-06-16 | 2026-11-17 | 0 | 0 | — |
| PAYMENT DATE | 1997-04-15 | 2026-11-17 | 0 | 0 | — |
| LICENSE TERM START DATE | 1995-02-16 | 2028-07-16 | 0 | 0 | — |
| LICENSE TERM EXPIRATION DATE | 0206-08-17 | 9999-01-01 | 0 | 2 | 08/17/0206, 01/01/9999 |
| LICENSE APPROVED FOR ISSUANCE | 2000-06-16 | 2026-11-17 | 0 | 0 | — |
| DATE ISSUED | 2002-01-02 | 2026-11-17 | 0 | 0 | — |
| LICENSE STATUS CHANGE DATE | 2002-01-08 | 2026-11-17 | 0 | 0 | — |

숫자 모양과 일반 문자가 함께 나온 컬럼(업무상 혼합 타입으로 확정한 것은 아님):

| 컬럼 | 정수 모양 | 소수 모양 | 그 외 문자 |
| --- | ---: | ---: | ---: |
| ID | 1 | 0 | 1,212,131 |
| LEGAL NAME | 22 | 0 | 1,212,110 |
| DOING BUSINESS AS NAME | 172 | 3 | 1,211,957 |
| CITY | 7 | 0 | 1,212,125 |
| ZIP CODE | 1,211,713 | 0 | 90 |
| WARD PRECINCT | 620 | 0 | 1,120,286 |
| BUSINESS ACTIVITY ID | 602,449 | 0 | 60,582 |

ZIP의 미국 5자리 또는 ZIP+4 정규식 불일치: **166건**. 예시: H3P3C (14), L3R2N (12), J3Y (10), 60 (8), M3B1Z (6). 해외 주소·원천 오류 여부는 별도 판단이 필요하다.

## community_areas

- 파일: `data/00_origin/community_areas/community_areas.geojson` · 형식: GeoJSON FeatureCollection · 인코딩: UTF-8 · 77행 × 11컬럼
- 출처 URL(원본 manifest): https://data.cityofchicago.org/api/v3/views/igwz-8jzy/query.geojson?accessType=DOWNLOAD
- 제공 컬럼 메타데이터: `data/00_origin/community_areas/area_columns.json`. 메타데이터에만 있는 항목: 없음. 실제 속성에만 있는 항목: [':created_at', ':id', ':updated_at', ':version'].
- 원본 컬럼 목록·의미·타입·샘플: [data_dictionary.md](data_dictionary.md). 재현 가능한 전체 측정값: [source_profiles.json](source_profiles.json).
- 완전 동일 행 후보: 0건.

### 컬럼별 결측과 고유값

| 원본 컬럼 | 빈 값 | 공백값 | NULL형 문자 | 결측률 | 고유값 수 |
| --- | ---: | ---: | ---: | ---: | ---: |
| type | 0 | 0 | 0 | 0.0000% | 1 |
| geometry | 0 | 0 | 0 | 0.0000% | 77 |
| :id | 0 | 0 | 0 | 0.0000% | 77 |
| :version | 0 | 0 | 0 | 0.0000% | 77 |
| :created_at | 0 | 0 | 0 | 0.0000% | 1 |
| :updated_at | 0 | 0 | 0 | 0.0000% | 1 |
| area_numbe | 0 | 0 | 0 | 0.0000% | 77 |
| community | 0 | 0 | 0 | 0.0000% | 77 |
| area_num_1 | 0 | 0 | 0 | 0.0000% | 77 |
| shape_area | 0 | 0 | 0 | 0.0000% | 77 |
| shape_len | 0 | 0 | 0 | 0.0000% | 77 |

### 키·형식·날짜

| 키 후보 | 중복 출현 행 수 | 중복률 |
| --- | ---: | ---: |
| area_numbe | 0 | 0.0000% |

GeoJSON 최상위 키: `['type', 'features']`. Feature 키: `['type', 'geometry', 'properties']`. `properties` 키: `[':id', ':version', ':created_at', ':updated_at', 'area_numbe', 'community', 'area_num_1', 'shape_area', 'shape_len']`.
Geometry 유형: `{'MultiPolygon': 77}`. 속성·geometry 구조 및 Bronze 값 대조 오류: `{}`. `area_numbe` 중복은 0건이다.

`pd.json_normalize()` 같은 평탄화는 `properties`의 속성에만 적용할 수 있다. `geometry.coordinates`는 중첩 배열을 유지해야 하므로 평탄화 대상이 아니다. 현재 Bronze의 JSON 문자열을 파싱해 원본 geometry 객체와 77건 모두 비교했다.

## 반복 위반 텍스트

`Violations` 빈 문자열 90,000건, 비어 있지 않은 행 228,552건. 공백만 있는 행 0건. 공백을 양쪽에 둔 `|`로 나눈 **후보 항목**은 1,030,806개이고, 복수 항목 행은 197,271건이다. 이 수는 아직 확정된 위반 건수가 아니다.
후보 조각의 번호 머리글 정규식 `^\d+[A-Z]?\.\s+`에 맞지 않는 행은 0건이었다. `Comments:` 표지가 없는 행은 184건이다. 예를 들어 `56. ADEQUATE VENTILATION & LIGHTING; DESIGNATED AREAS USED`처럼 머리글만 있고 설명이 없는 형태가 있다. 구분자 없는 `|` 관측 행은 0건이다.

**설계 제안:** Silver에서 `inspection_violations` 파생 테이블을 만들면 점검 1건의 여러 위반을 표현할 수 있다. `Inspection ID`와 원래 항목 순서, 원문 전체, 파싱 상태를 유지하고, 조각 분해 실패는 별도 예외로 기록한다. `Comments:`가 없는 행을 무조건 실패로 버리지 않는다. 위반 코드의 시대별 의미와 분모는 팀 결정이 필요하다. Bronze는 1점검 1행을 유지한다.

## 인허가 이력과 연결성

인허가 `ID`는 중복 출현 행 252건, `LICENSE ID`는 0건, `LICENSE NUMBER`는 861,328건이다. `ID=2835961-20260416`의 두 행은 `LICENSE ID`가 `3072380`·`3072378`로 다르고 상태도 `AAI`·`AAC`로 다르다. 즉 단순 동일 행은 아니다. `LICENSE NUMBER=1697585`에는 `ISSUE` 후 여러 `RENEW` 기간이 관찰된다. 중복을 삭제하지 않는다.

발급·갱신·상태 관련 컬럼: `APPLICATION TYPE`, `APPLICATION CREATED DATE`, `APPLICATION REQUIREMENTS COMPLETE`, `PAYMENT DATE`, `CONDITIONAL APPROVAL`, `LICENSE TERM START DATE`, `LICENSE TERM EXPIRATION DATE`, `LICENSE APPROVED FOR ISSUANCE`, `DATE ISSUED`, `LICENSE STATUS`, `LICENSE STATUS CHANGE DATE`. 시점별 의미와 유효기간 경계는 아직 결정되지 않았다.

점검 `License #` ↔ 인허가 `LICENSE NUMBER`: 비공란 번호가 양쪽에 존재하는 고유 번호 46,485개. 점검 행 기준 번호 공란 19, 비공란 무매칭 16,558, 후보 1건 35,887, 후보 복수 266,088; 번호당 최대 후보 26건. 따라서 번호만으로 JOIN하면 행이 늘어난다.
인허가 `COMMUNITY AREA` ↔ 지역 `area_numbe`: 77개 지역 번호가 모두 나타난다. 인허가 지역번호 공란 99,589건, 비공란 미매칭 38건(`{'0': 38}`). 점검에는 지역번호가 없어 좌표 기반 연결이 필요하지만 아직 공간 JOIN을 수행하지 않았다.

## Silver 작업 후보

1. 키·원본 행 식별과 날짜 의미를 합의하고 인허가 이력의 기간·다중 후보 규칙을 설계한다.
2. 위반 텍스트를 원문 보존형 파생 테이블로 구조화하고 예외 형식을 기록한다.
3. 만료일 이상 연도, ZIP 형식, 표기 차이, 결측·NULL형 문자값을 규칙별로 판정한다.
4. 지역 경계 연결과 좌표 결측·경계 밖 처리 기준을 정한다.

이 문서는 측정 결과와 설계 제안을 구분한다. 위 항목은 Silver 구현 결과가 아니다.
