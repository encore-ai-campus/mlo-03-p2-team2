# 원천 데이터 품질 이슈

## 조사 범위와 판정 기준

이 보고서는 기존 프로파일링 결과를 요약한 문서다. 원천 데이터나 측정 결과를 정제·수정하지 않았다. 인용한 프로파일 실행 ID는 79e8b4280ab443eb9d73f6774dfff5f5이며 JSON의 기준 시각은 2026-11-19T11:11:15Z다. 상세 값은 [source_profiles.json](../metadata/source_profiles.json), 설명은 [source_profiles.md](../metadata/source_profiles.md)에 있다.

- 빈 값은 CSV 필드가 정확히 빈 문자열인 경우이고, 공백값은 strip() 결과가 빈 문자열인 비어 있지 않은 문자열이다.
- NULL, N/A, NA, NONE은 별도 NULL형 문자값이며 빈 값에 포함하지 않았다.
- 날짜 원천 형식은 MM/DD/YYYY다. 파싱 실패와 조사 범위 1900~2100 밖 연도를 별도로 센다. 범위 밖은 조사 신호이지 자동 무효 판정이 아니다.
- 중복 건수는 키가 이미 나온 뒤 다시 나타난 행 수다. 완전 동일 행 후보는 128비트 digest 비교 결과라 원문 바이트 단위 증명은 아니다.
- 숫자/문자 혼합 수치는 원천 문자열의 모양을 분류한 것이다. 타입 오류나 업무 오류로 확정하지 않는다.

## 측정 결과 및 Silver 제안

| 데이터셋 | 문제 컬럼 | 문제 내용 | 실제 건수 | 영향 | 처리 제안(미구현) |
| --- | --- | --- | --- | --- | --- |
| food_inspections | AKA Name, License #, Facility Type, Risk, City, State, Zip, Inspection Type, Violations | 빈 문자열 결측 | AKA Name 2,425; License # 19; Facility Type 5,358; Risk 88; City 184; State 76; Zip 42; Inspection Type 1; Violations 90,000(28.2528%) | 업체명·번호·범주·위반 서술 분석의 유효 분모가 달라질 수 있음 | 원문을 보존하고 컬럼별 결측 의미를 정한다. Violations 빈 값이 없음인지 미기록인지 합의 전 같은 값으로 묶지 않는다. |
| food_inspections | Address | 공백 문자열 | 3 | 주소 표준화·위치 연결 시 공백이 값처럼 남을 수 있음 | 원문을 유지하고 Silver에서 공백 상태를 별도 표시할지 합의한다. |
| food_inspections | Latitude, Longitude, Location | 빈 값 | 각 1,064행(0.3340%) | 해당 행의 위치 분석 또는 Community Area 공간 연결이 어려울 수 있음 | 세 필드의 결측을 보존하고 공간 연결의 미매칭 사유로 기록한다. 공간 JOIN은 아직 수행하지 않았다. |
| food_inspections | Inspection ID, License # | 키 중복 | Inspection ID 중복 0; License # 중복 출현 행 269,173(84.4989%); 완전 동일 행 후보 0 | License #는 점검 식별자로 사용할 수 없고 번호 기준 인허가 JOIN에서 행이 늘 수 있음 | Inspection ID 유일성을 확인하고 License # 반복은 이력/점검 관계로 보존한다. 중복 행 제거 기준으로 사용하지 않는다. |
| food_inspections | Inspection Date | 날짜 파싱·연도 조사 | MM/DD/YYYY 파싱 실패 0; 1900~2100 밖 0; 측정 범위 2010-01-04~2026-11-17 | 현재 프로파일 기준 날짜 형식 문제는 관측되지 않음 | 원문을 보존하고 Silver에서 명시 형식으로 파싱·건수를 검증한다. |
| food_inspections | Zip | 미국 5자리/ZIP+4 패턴 | 불일치 0 | 해당 검사 기준의 형식 이상은 발견되지 않음. 모든 주소의 업무 유효성을 증명하지는 않음 | 형식 검사를 검증 규칙으로 유지하되 원천값은 바꾸지 않는다. |
| food_inspections | DBA Name, AKA Name, Facility Type | 숫자 모양과 일반 문자가 함께 관측됨 | 정수 모양 각각 23, 45, 15건 | 문자열을 숫자로 변환하는 규칙은 이름·유형 값을 손상시킬 수 있음 | Bronze 문자열 보존을 유지한다. 업무 타입은 의미와 코드표를 기준으로 정한다. |
| food_inspections | City, DBA Name | 표기 차이 | City: CHICAGO 317,229; Chicago 544; chicago 175; CCHICAGO 62. 사업체명 case 변형 예시는 프로파일에 기록됨 | 동일 사업체 여부를 대소문자 비교만으로 확정할 수 없음 | 원문과 표준 후보를 병행하고 승인된 매핑으로만 통합한다. |
| food_inspections | Violations | 반복 위반 텍스트와 빈 값 | 빈 값 90,000; 비어 있지 않은 행 228,552; 구분자 후보 항목 1,030,806; 복수 항목 행 197,271; Comments: 표지 없는 행 184; 비표준 번호 머리글 0; 공백 없는 파이프 0 | 셀을 여러 위반으로 분해하면 항목 수와 점검 행 grain이 달라질 수 있음. 후보 항목은 확정 위반 수가 아님 | 원문 전체·점검 ID·항목 순서를 보존하는 파생 구조를 검토한다. Comments: 누락을 자동 실패로 처리하지 않는다. |
| business_licenses | STATE, ZIP CODE, WARD, PRECINCT, WARD PRECINCT, POLICE DISTRICT, COMMUNITY AREA, COMMUNITY AREA NAME, NEIGHBORHOOD | 빈 문자열 결측 | 각각 12, 329, 91,846, 93,914, 91,226, 92,200, 99,589, 99,655, 100,632행 | 주소·지역 분석에서 사용할 수 있는 분모가 줄고 일부 번호 조인이 불가능할 수 있음 | 원문 빈 값은 유지하고 업무상 NULL 여부를 컬럼별로 결정한다. |
| business_licenses | BUSINESS ACTIVITY ID, BUSINESS ACTIVITY | 빈 문자열 결측 | 각각 549,101행(45.3004%) | 업종 세분 분석에 큰 결측이 생길 수 있음 | 두 컬럼의 결측 동반 여부와 의미를 확인하고 결측 상태를 보존한다. |
| business_licenses | APPLICATION CREATED DATE, APPLICATION REQUIREMENTS COMPLETE, PAYMENT DATE, LICENSE TERM START DATE, LICENSE TERM EXPIRATION DATE, LICENSE APPROVED FOR ISSUANCE, LICENSE STATUS CHANGE DATE, SSA | 빈 문자열 결측 | 각각 929,252(76.6626%), 18,415(1.5192%), 22,685(1.8715%), 2,719(0.2243%), 170(0.0140%), 56,233(4.6392%), 1,131,478(93.3461%), 896,360(73.9490%)행 | 신청·허가 시점, 유효기간 JOIN, SSA 분석에 사용 가능한 행이 달라짐 | 이벤트 의미를 확인하고 날짜를 임의로 채우지 않는다. |
| business_licenses | LICENSE NUMBER, LATITUDE, LONGITUDE, LOCATION | 빈 문자열 결측 | LICENSE NUMBER 1; LATITUDE, LONGITUDE, LOCATION 각 93,498행(7.7135%) | 허가번호 연결 또는 좌표 활용이 불가능한 행이 있음 | 결측 사유를 추정하지 않고 별도 상태로 보존한다. |
| business_licenses | DOING BUSINESS AS NAME | NULL형 문자값 | NULL/N/A/NA/NONE 토큰 398건; 프로파일 결측률에는 포함되지 않음 | 자동 NULL 변환 시 원문 분포가 달라짐 | 원문과 결측 분류를 분리하고 허용 토큰을 합의한다. |
| business_licenses | ID, LICENSE ID, LICENSE NUMBER | 키 후보 반복 | ID 중복 출현 행 252(0.0208%); LICENSE ID 중복 0; LICENSE NUMBER 중복 출현 행 861,328(71.0589%); 완전 동일 행 후보 0 | ID 반복 및 허가번호별 이력은 같은 행 중복과 다를 수 있음 | LICENSE ID를 이벤트 키 후보로 유지하고 반복 의미를 확인한다. 임의 삭제·병합하지 않는다. |
| business_licenses | 날짜 8개 컬럼 | 달력 파싱 및 연도 범위 | 날짜 파싱 실패 0. LICENSE TERM EXPIRATION DATE 조사 범위 밖 2건: 08/17/0206, 01/01/9999 각 1건. 다른 날짜의 범위 밖 연도 0 | 두 값은 파싱되지만 통상적인 유효기간인지 판단되지 않아 기간 JOIN에 영향 가능 | 원본 문자열, parse 상태, 업무 유효성 상태를 구분한다. 검증 전 보정·삭제·JOIN에 사용하지 않는다. |
| business_licenses | ZIP CODE | 미국 5자리/ZIP+4 패턴 불일치 | 166행. 예: H3P3C 14, L3R2N 12, J3Y 10, 60 8, M3B1Z 6 | 해외 우편번호, 잘린 값 또는 원천 표기가 섞였을 수 있어 모두 오류라 단정할 수 없음 | 국가·주소 맥락을 검토하고 상태를 분리한다. 선행 0과 원문을 보존한다. |
| business_licenses | ID, LEGAL NAME, DOING BUSINESS AS NAME, CITY, ZIP CODE, WARD PRECINCT, BUSINESS ACTIVITY ID | 숫자 모양과 일반 문자가 혼합됨 | 예: ID 정수 모양 1/그 외 1,212,131; ZIP CODE 정수 모양 1,211,713/그 외 90; BUSINESS ACTIVITY ID 정수 모양 602,449/그 외 60,582. 나머지 상세값은 source_profiles.md 참조. | 식별자·코드·우편번호를 숫자로 일괄 변환하면 선행 0 또는 문자 접미를 잃을 수 있음 | 표준 타입 후보와 실제 분포를 함께 검토한다. 문자열 모양만으로 타입 오류를 확정하지 않는다. |
| 두 CSV 데이터셋 | Results, Risk, APPLICATION TYPE, LICENSE STATUS, CONDITIONAL APPROVAL 등 | 표준 코드 등록 상태 미확정 | 표준 대조표에 비공란 코드값 24종이 집계됐고 모두 review. Risk 원천 공란 88건은 missing_raw. 승인 코드표와 대조한 미등록 수는 미측정. | 코드 의미·유효성을 확정하기 전 매핑하면 분석 분류가 달라질 수 있음 | 승인 코드표를 확보하고 raw_value, 후보 mapped_code, mapping_status를 분리한다. 검토·미등록·확정·원천 공란을 구별한다. |
| food_inspections ↔ business_licenses | License # ↔ LICENSE NUMBER | 번호만 쓴 JOIN의 다중 후보 | 점검 행 기준 공란 19, 비공란 미매칭 16,558, 후보 1건 35,887, 후보 복수 266,088; 공유 비공란 번호 46,485개; 번호당 최대 후보 26건 | 단순 JOIN은 점검 행을 증폭하거나 잘못된 허가 이력을 붙일 수 있음 | 번호 일치와 번호+유효기간을 분리해 검증한다. 무매칭·다중 후보를 보존하고 임의로 한 행을 선택하지 않는다. 이 값은 번호 전용 프로파일이며 기간 JOIN 결과가 아니다. |
| business_licenses ↔ community_areas | COMMUNITY AREA ↔ area_numbe | 지역 번호 결측·미매칭 | COMMUNITY AREA 빈 값 99,589행; 비공란 미매칭 38행이며 값은 0; 유효 지역번호 77개 매칭 | 0 또는 공란을 실제 지역으로 해석할 위험 | 0, 공란, 유효 번호를 구분하고 승인된 번호 사전으로 확인한다. |
| food_inspections ↔ community_areas | 점검 좌표 ↔ 지역 geometry | 공간 연결은 실행되지 않음 | 점검 좌표/Location 결측 각 1,064행; 공간 JOIN의 미매칭·경계 중첩은 미측정 | 점검에 지역 번호가 없어 좌표 연결이 필요하지만 결과 건수는 아직 없음 | 좌표 범위, geometry, 경계 포함 규칙을 합의한 뒤 JOIN 전후 행 수와 예외를 측정한다. |
| community_areas | area_numbe, geometry | 기본 구조 검사 | 77개 area_numbe 중복 0; geometry 77/77 MultiPolygon; 구조 오류 0; Bronze 대조 오류 0; 결측 0 | 이번 프로파일에서 이 항목의 품질 오류는 발견되지 않음 | geometry를 보존하고 재처리 시 구조·건수·원천 대조를 검증한다. |

## 해석 및 우선순위

### 확인된 사실

- 세 데이터셋의 완전 동일 행 후보는 각각 0건이다. 이는 digest 기반 후보 검사이며 행 삭제 근거가 아니다.
- 날짜 형식 파싱 실패는 0건이고, 인허가 만료일 2건의 연도만 조사 범위 밖이다.
- 번호 전용 점검-인허가 JOIN에는 다중 후보가 많다. 기간 JOIN 결과와 동일시하지 않는다.
- 이 보고서 작성 중 프로파일링을 다시 실행하거나 Silver 정제를 하지 않았다.

### Silver 구현 제안

1. 행 식별자, 원문 추적 컬럼, 날짜 업무 의미를 먼저 합의한다.
2. 미등록 코드와 검토 코드를 판정할 승인 코드표를 마련한다.
3. 기간 JOIN 경계일, 무매칭, 다중 후보 처리와 grain을 결정한다.
4. 결측·공백·NULL형 문자, ZIP, 위반 텍스트, 공간 연결 규칙과 rejected 기준을 확정한다.

위 항목들은 제안이며 아직 Silver 파이프라인에 구현되지 않았다.
