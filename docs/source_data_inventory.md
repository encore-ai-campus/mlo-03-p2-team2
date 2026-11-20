# 원천 데이터 전수 인벤토리

2026-11-20에 팀이 공유한 로컬 스냅샷을 읽기 전용으로 조사했습니다. CSV는 헤더를 제외한 논리 레코드를 모두 읽었고, GeoJSON은 모든 Feature와 속성을 확인했습니다. 결측은 CSV에서 빈 문자열 또는 공백만 있는 값입니다. 이름과 타입의 공통안은 [데이터 취합·표준화 기준](data_integration_conventions.md)에서 설명합니다. [원천 설정](../config/sources.example.yaml) · [다운로드 매니페스트](../metadata/source_catalog/verification/download_manifest.csv) · [재실행 코드](../src/ingestion/profile_sources.py)

| 데이터 파일 | 관측 규모 | 컬럼 메타데이터 |
| --- | ---: | --- |
| `food_inspections.csv` | 318,552행 × 17열 | `food_columns.json`, 정의 26개 |
| `business_licenses.csv` | 1,212,132행 × 37열 | `license_columns.json`, 정의 46개 |
| `community_areas.geojson` | 77개 Feature, Feature당 속성 9개 | `area_columns.json`, 지오메트리와 업무 속성 정의 6개 |

**포털 타입**은 제공자가 메타데이터에 선언한 타입입니다. **실제 값의 형식**은 현재 파일의 비어 있지 않은 값을 검사한 결과입니다. CSV는 파일에서 전부 텍스트로 읽으며, 표의 정수·소수·날짜는 문자열의 형식을 뜻합니다. **표준안**은 팀이 합의할 이름과 타입이며, 04번에서 이미 구현한 컬럼의 이름은 그 사전을 따릅니다.

## 식품위생 점검

| 원천 컬럼 | 포털 API 필드 | 포털 타입 | 실제 값의 형식 | 결측 | 표준안 · 타입 | 의미 |
| --- | --- | --- | --- | ---: | --- | --- |
| `Inspection ID` | `inspection_id` | `number` | 정수 형태 | 0 | `inspection_key` · `string` | 한 점검을 구분하는 ID |
| `DBA Name` | `dba_name` | `text` | 자유 텍스트 | 0 | `dba_name` · `string` | 영업에 사용하는 상호 |
| `AKA Name` | `aka_name` | `text` | 자유 텍스트 | 2,425 | `aka_name` · `string` | 다른 상호 또는 별칭 |
| `License #` | `license_` | `number` | 정수 형태 | 19 | `license_number_key` · `string` | 인허가와 연결할 면허번호 후보 |
| `Facility Type` | `facility_type` | `text` | 범주 텍스트 | 5,358 | `facility_type` · `string` | 시설 유형 원천 분류 |
| `Risk` | `risk` | `text` | 위험등급 라벨 | 88 | `risk_level_cd` · `string` | 시설 위험등급 |
| `Address` | `address` | `text` | 주소 텍스트 | 3 | `address` · `string` | 점검 주소 |
| `City` | `city` | `text` | 도시명 텍스트 | 184 | `city` · `string` | 점검 도시 |
| `State` | `state` | `text` | 주 코드 텍스트 | 76 | `state_cd` · `string` | 점검 주소의 주 |
| `Zip` | `zip` | `number` | 숫자 5자리 | 42 | `zip_code` · `string` | 점검 주소의 우편번호 |
| `Inspection Date` | `inspection_date` | `calendar_date` | MM/DD/YYYY | 0 | `inspection_dtm` · `date32` | 점검일 |
| `Inspection Type` | `inspection_type` | `text` | 범주 텍스트 | 1 | `inspection_type` · `string` | 정기·민원·재검사 등 점검 사유 또는 유형 |
| `Results` | `results` | `text` | 결과 라벨 | 0 | `result_cd` · `string` | 통과, 불합격 등 점검 결과 |
| `Violations` | `violations` | `text` | 자유 텍스트 | 90,000 | `violations_text` · `string` | 위반 코드·설명·메모가 결합된 원문 |
| `Latitude` | `latitude` | `number` | 소수 형태 | 1,064 | `latitude` · `float64` | 점검 위치의 위도 |
| `Longitude` | `longitude` | `number` | 소수 형태 | 1,064 | `longitude` · `float64` | 점검 위치의 경도 |
| `Location` | `location` | `point` | (위도, 경도) 문자열 | 1,064 | `location_text` · `string` | CSV의 위치 원문 |

## 사업체 인허가

| 원천 컬럼 | 포털 API 필드 | 포털 타입 | 실제 값의 형식 | 결측 | 표준안 · 타입 | 의미 |
| --- | --- | --- | --- | ---: | --- | --- |
| `ID` | `id` | `text` | 텍스트, 주로 숫자-8자리 숫자 | 0 | `source_record_id` · `string` | 포털 계산 레코드 ID |
| `LICENSE ID` | `license_id` | `number` | 정수 형태 | 0 | `license_event_key` · `string` | 인허가 기록 내부 ID |
| `ACCOUNT NUMBER` | `account_number` | `number` | 정수 형태 | 0 | `account_key` · `string` | 소유 사업자 계정번호 |
| `SITE NUMBER` | `site_number` | `number` | 정수 형태 | 0 | `site_key` · `string` | 해당 사업자의 사업장 번호 |
| `LEGAL NAME` | `legal_name` | `text` | 자유 텍스트 | 0 | `legal_name` · `string` | 등록된 법적 명칭 |
| `DOING BUSINESS AS NAME` | `doing_business_as_name` | `text` | 자유 텍스트 | 0 | `dba_name` · `string` | 영업 상호 |
| `ADDRESS` | `address` | `text` | 주소 텍스트 | 0 | `address` · `string` | 인허가 기록에 등록된 주소 |
| `CITY` | `city` | `text` | 도시명 텍스트 | 0 | `city` · `string` | 인허가 주소의 도시 |
| `STATE` | `state` | `text` | 지역 코드 텍스트 | 12 | `state_cd` · `string` | 인허가 주소의 주·지역 |
| `ZIP CODE` | `zip_code` | `text` | 주로 5자리 또는 ZIP+4 | 329 | `zip_code` · `string` | 인허가 주소의 우편번호 |
| `WARD` | `ward` | `number` | 정수 형태 | 91,846 | `ward_num` · `int64` | 시의회 선거구 번호 |
| `PRECINCT` | `precinct` | `number` | 정수 형태 | 93,914 | `precinct_num` · `int64` | 선거구 안의 투표구 번호 |
| `WARD PRECINCT` | `ward_precinct` | `text` | 숫자 조합 텍스트 또는 정수 형태 | 91,226 | `ward_precinct_key` · `string` | 원천의 선거구·투표구 결합 값 |
| `POLICE DISTRICT` | `police_district` | `number` | 정수 형태 | 92,200 | `police_district_num` · `int64` | 경찰 관할 구역 번호 |
| `COMMUNITY AREA` | `community_area` | `number` | 정수 형태 | 99,589 | `community_area_num` · `int64` | 인허가에서 제공하는 커뮤니티 지역 코드 |
| `COMMUNITY AREA NAME` | `community_area_name` | `text` | 지역명 텍스트 | 99,655 | `community_area_name` · `string` | 인허가에서 제공하는 커뮤니티 지역명 |
| `NEIGHBORHOOD` | `neighborhood` | `text` | 지역명 텍스트 | 100,632 | `neighborhood_name` · `string` | 인허가에서 제공하는 동네 이름 |
| `LICENSE CODE` | `license_code` | `number` | 정수 형태 | 0 | `license_type_key` · `string` | 면허 유형 코드 |
| `LICENSE DESCRIPTION` | `license_description` | `text` | 설명 텍스트 | 0 | `license_type_description` · `string` | 면허 유형 설명 |
| `BUSINESS ACTIVITY ID` | `business_activity_id` | `text` | 한 개의 숫자 ID 또는 파이프 구분 목록 | 549,101 | `business_activity_ids_text` · `string` | 영업 활동 코드 원문 |
| `BUSINESS ACTIVITY` | `business_activity` | `text` | 설명 텍스트 | 549,101 | `business_activity_text` · `string` | 영업 활동 설명 원문 |
| `LICENSE NUMBER` | `license_number` | `number` | 정수 형태 | 1 | `license_number_key` · `string` | 공개 면허번호 |
| `APPLICATION TYPE` | `application_type` | `text` | 신청 유형 코드 | 0 | `application_cd` · `string` | 발급·갱신·변경 등 신청 유형 |
| `APPLICATION CREATED DATE` | `application_created_date` | `calendar_date` | MM/DD/YYYY | 929,252 | `application_created_dtm` · `date32` | 신청 생성일 |
| `APPLICATION REQUIREMENTS COMPLETE` | `application_requirements_complete` | `calendar_date` | MM/DD/YYYY | 18,415 | `application_requirements_complete_dtm` · `date32` | 요건 완료일 또는 갱신 기록 생성일 |
| `PAYMENT DATE` | `payment_date` | `calendar_date` | MM/DD/YYYY | 22,685 | `payment_dtm` · `date32` | 납부일 |
| `CONDITIONAL APPROVAL` | `conditional_approval` | `text` | Y 또는 N | 0 | `conditional_approval_cd` · `string` | 조건부 승인 여부 코드 |
| `LICENSE TERM START DATE` | `license_start_date` | `calendar_date` | MM/DD/YYYY | 2,719 | `term_start_dtm` · `date32` | 면허 기간 시작일 |
| `LICENSE TERM EXPIRATION DATE` | `expiration_date` | `calendar_date` | MM/DD/YYYY | 170 | `term_end_dtm` · `date32` | 면허 기간 만료일 |
| `LICENSE APPROVED FOR ISSUANCE` | `license_approved_for_issuance` | `calendar_date` | MM/DD/YYYY | 56,233 | `approved_for_issuance_dtm` · `date32` | 발급 준비 승인일 |
| `DATE ISSUED` | `date_issued` | `calendar_date` | MM/DD/YYYY | 0 | `issued_dtm` · `date32` | 발급일 |
| `LICENSE STATUS` | `license_status` | `text` | 상태 코드 | 0 | `recorded_status_cd` · `string` | 원천에 기록된 면허 상태 |
| `LICENSE STATUS CHANGE DATE` | `license_status_change_date` | `calendar_date` | MM/DD/YYYY | 1,131,478 | `status_change_dtm` · `date32` | 특정 면허 상태의 변경일 |
| `SSA` | `ssa` | `text` | 정수 형태 | 896,360 | `ssa_cd` · `string` | 특별 서비스 구역 코드 |
| `LATITUDE` | `latitude` | `number` | 소수 형태 | 93,498 | `latitude` · `float64` | 인허가 위치의 위도 |
| `LONGITUDE` | `longitude` | `number` | 소수 형태 | 93,498 | `longitude` · `float64` | 인허가 위치의 경도 |
| `LOCATION` | `location` | `point` | (위도, 경도) 문자열 | 93,498 | `location_text` · `string` | CSV의 위치 원문 |

숫자 코드처럼 보여도 의미가 식별자인 필드는 문자열로 보존하는 안을 제안합니다. 예를 들어 점검 `Zip`은 318,510개 비결측 값이 모두 숫자 5자리였고, 인허가 `ZIP CODE`에는 5자리 또는 ZIP+4 형식 밖의 값이 166건 있었습니다. `BUSINESS ACTIVITY ID`는 단일 숫자 ID가 602,449행, `|`로 나뉜 목록이 60,582행이었습니다. 이 열의 한 칸은 현재 인허가 레코드의 일부로 취급합니다.

## 커뮤니티 지역 경계

GeoJSON 루트에는 `type`과 `features`가 있습니다. 루트 `type`은 문자열 `FeatureCollection`, `features`는 아래 구조를 가진 Feature 77개의 배열입니다.

| 구조 경로 | 실제 JSON 타입·형식 | 역할 |
| --- | --- | --- |
| `features[].type` | 문자열 `Feature` | 레코드 유형 |
| `features[].geometry` | 객체 | 지역 경계 |
| `features[].geometry.type` | 문자열 `MultiPolygon` | 77개 모두 멀티폴리곤 |
| `features[].geometry.coordinates` | 폴리곤 → 링 → 점 → 숫자의 중첩 배열 | 점의 좌표 순서는 `[경도, 위도]` |
| `features[].properties` | 객체 | 아래 업무·시스템 속성 9개 |

| 속성 경로의 필드명 | 포털 타입 | 실제 JSON 타입·형식 | 표준안 · 타입 | 의미 |
| --- | --- | --- | --- | --- |
| `properties.area_numbe` | `number` | 문자열, 정수 형태 | `community_area_num` · `int64` | 커뮤니티 지역 번호 |
| `properties.community` | `text` | 문자열, 지역명 | `community_area_name` · `string` | 커뮤니티 지역 이름 |
| `properties.area_num_1` | `text` | 문자열, 정수 형태 | `community_area_code_raw` · `string` | 원천의 보조 지역 코드 |
| `properties.shape_area` | `number` | 문자열, 소수 형태 | `shape_area_num` · `float64` | 원천의 경계 면적 값 |
| `properties.shape_len` | `number` | 문자열, 소수 형태 | `shape_length_num` · `float64` | 원천의 경계 길이 값 |
| `properties.:id` | — | 문자열 | `source_feature_id` · `string` | 포털 시스템 레코드 ID |
| `properties.:version` | — | 문자열 | `source_version_id` · `string` | 포털 시스템 버전 ID |
| `properties.:created_at` | — | UTC 날짜·시간 문자열 | `source_created_at` · `timestamp[ms, UTC]` | 포털 레코드 생성 시각 |
| `properties.:updated_at` | — | UTC 날짜·시간 문자열 | `source_updated_at` · `timestamp[ms, UTC]` | 포털 레코드 갱신 시각 |

속성 9개는 77개 Feature 모두에 있습니다. 제공 메타데이터의 `the_geom`은 포털의 `multipolygon` 정의이며, GeoJSON 추출본에서는 별도 속성 없이 Feature의 `geometry` 객체로 전달됩니다. 표준안에서는 지오메트리 이름을 `geometry`로 둡니다. [공식 지역 경계 메타데이터](https://catalog.data.gov/dataset/boundaries-community-areas)

## 메타데이터에만 있고 CSV에서 빠진 컬럼

아래 9개 API 필드는 두 CSV의 실제 헤더에 없습니다. 저장소에는 현재 내려받은 CSV에 있는 컬럼 기준으로 사전을 작성합니다.

| API 필드 | 점검 메타데이터 표시명 | 인허가 메타데이터 표시명 | 포털 타입 |
| --- | --- | --- | --- |
| `location_address` | Location (address) | LOCATION (address) | `text` |
| `location_city` | Location (city) | LOCATION (city) | `text` |
| `location_state` | Location (state) | LOCATION (state) | `text` |
| `location_zip` | Location (zip) | LOCATION (zip) | `text` |
| `:@computed_region_awaf_s7ux` | Historical Wards 2003-2015 | Historical Wards 2003-2015 | `number` |
| `:@computed_region_6mkv_f3dw` | Zip Codes | Zip Codes | `number` |
| `:@computed_region_vrxf_vc4k` | Community Areas | Community Areas | `number` |
| `:@computed_region_bdys_3d7i` | Census Tracts | Census Tracts | `number` |
| `:@computed_region_43wa_7qmu` | Wards | Wards | `number` |

세 컬럼 설명 JSON의 루트는 컬럼 정의 객체의 배열입니다. 정의 객체에서 실제로 확인한 필드는 다음과 같습니다.

| JSON 타입 | 컬럼 설명 객체의 필드 |
| --- | --- |
| 문자열 | `name`, `fieldName`, `dataTypeName`, `description`, `renderTypeName` |
| 정수 | `id`, `position`, `tableColumnId`, `width` |
| 객체 | `cachedContents`, `format`, `computationStrategy` |

`width`, `description`, `cachedContents`, `computationStrategy`는 모든 컬럼 정의에 나타나지는 않습니다. `computationStrategy`는 두 CSV의 포털 메타데이터에 나오는 계산 필드의 정의입니다.
