# 데이터 취합·표준화 기준 초안

다섯 관점의 Bronze와 Silver를 통합할 때 사용할 공용 데이터 단위, 날짜 형식, 컬럼 이름과 주요 코드 표기안입니다. 현재 파일의 컬럼, 제공 타입과 관측 형식은 [원천 데이터 전수 인벤토리](source_data_inventory.md)에 있습니다. 이미 04번에서 구현한 이름은 [04번 데이터 사전](../src/domains/04_license/%EB%8D%B0%EC%9D%B4%ED%84%B0%20%EC%82%AC%EC%A0%84.csv)과 맞췄습니다.

공통 분석 주제는 **시카고 사업장 위생점검과 인허가·지역 이력의 관계**입니다. 점검 한 건을 기준으로 점검 결과, 위반 요약, 점검일의 인허가 후보, 점검 위치의 커뮤니티 지역을 함께 볼 수 있게 합니다. 관점별 상세 이력은 공용 분석에 필요한 단위로 집계한 뒤 연결합니다.

## 관점별 데이터를 취합하는 방법

| 통합 대상 | 기준 행 단위·키 | 취합 기준 |
| --- | --- | --- |
| 공용 점검 | 점검 한 건, `inspection_key` | 같은 원천 SHA-256을 사용한 Bronze 후보를 대조하고 공용 점검 Bronze를 정합니다. Silver의 점검일·결과 등 공통 컬럼은 한 가지 표준화 규칙을 선택합니다. |
| 공용 인허가 기록 | 인허가 기록 한 건, `license_event_key` | 같은 면허번호에 여러 발급·갱신 기록이 올 수 있으므로 이력을 모두 보존합니다. `license_number_key`는 점검과의 연결 후보를 찾는 데 사용합니다. |
| 공용 지역 경계 | 경계 스냅샷의 Community Area 한 곳, `community_area_num`과 경계 버전 | 지역 코드와 경계 버전을 함께 기록합니다. 점검 좌표로 계산한 지역과 인허가 원천에 적힌 지역은 출처가 드러나도록 관리합니다. |
| 관점별 파생 데이터 | 위반 항목, 재검사, 기간 매칭, 지역 배정 등 각 분석의 행 단위 | 공용 Silver의 키로 참조합니다. 점검 단위 분석에서는 필요한 값을 점검 한 건으로 집계한 뒤 붙입니다. |

1. **스냅샷을 맞춥니다.** 같은 원천 내용을 사용했는지 파일 SHA-256으로 비교합니다. 해시가 다른 파일은 스냅샷을 구분하고, 통합 실행에 사용할 버전을 정합니다.
2. **Bronze 후보를 대조합니다.** 파일별 헤더·논리 레코드 수·순서가 일치하는지 확인합니다. 예를 들어 두 관점이 같은 점검 CSV에서 각각 318,552행을 만들었다면 공용 점검 Bronze도 318,552행입니다. 공용 Bronze에 원천 레코드와 `source_row_num`을 보존합니다.
3. **Silver의 공통 컬럼을 합의합니다.** 각 팀의 이름·타입·결측 처리·사전 규칙을 비교합니다. 공용 점검 또는 인허가 테이블의 한 행 기준을 유지하면서, 공통 컬럼의 표준 표현과 관점별 파생 컬럼의 소유 위치를 정합니다.
4. **관점별 결과를 연결합니다.** 점검·사업장·지역의 키와 적용 시점을 확인합니다. 같은 면허번호의 기간 후보가 여러 개인 점검은 후보 수와 미확정 상태를 남겨 후속 분석에서 확인할 수 있게 합니다.

`LICENSE ID`는 인허가 기록 식별자이고, `LICENSE NUMBER`는 여러 이력에서 반복될 수 있는 면허번호입니다. 사업장 식별은 `account_key + site_key` 조합을 후보로 사용하며, 계정과 사업장이 어떤 범위에서 유지되는지 데이터로 검증합니다. 기간 연결 시 `시작일 ≤ 점검일 ≤ 만료일`은 04번에서 검증한 기준입니다. 취소·철회가 기간에 미치는 영향과 다중 후보 해소는 팀 합의 항목입니다. [04번 단계별 설계](domains/04_license.md)

## 같은 성격의 컬럼을 묶는 기준

전체 컬럼의 변경명은 [원천 인벤토리](source_data_inventory.md)에 있습니다. 이름이 달라도 업무 의미가 같으면 같은 표준 개념으로 묶고, 이름이 같아도 관측 대상이나 시점이 다르면 통합 결과에서 접두사로 출처를 표시합니다.

| 컬럼 묶음 | 원천 예시 | 통일 기준 |
| --- | --- | --- |
| 연결 식별자 | 점검의 `License #`, 인허가의 `LICENSE NUMBER` | 둘 다 `license_number_key`로 매핑합니다. 점검 ID인 `Inspection ID`와 인허가 기록 ID인 `LICENSE ID`는 각각 `inspection_key`, `license_event_key`로 구분합니다. |
| 상호와 주소 | 점검의 `DBA Name`·`Address`, 인허가의 `DOING BUSINESS AS NAME`·`ADDRESS` | 각 입력에서는 `dba_name`·`address`로 맞춥니다. 함께 제공하는 테이블에서는 `inspection_address`·`license_address`처럼 출처를 드러냅니다. 법적 명칭과 별칭은 각각 `legal_name`과 `aka_name`으로 관리합니다. |
| 공간 위치와 지역 | 두 CSV의 위도·경도, 인허가의 `COMMUNITY AREA`, 경계의 `area_numbe` | 위도·경도는 `latitude`·`longitude`로 통일합니다. 지역 코드의 공통 개념은 `community_area_num`이며, 인허가에 기재된 값과 점검 좌표에서 산출한 값은 출처를 기록합니다. |
| 날짜·기간 | `Inspection Date`, `DATE ISSUED`, `LICENSE TERM START DATE`·`LICENSE TERM EXPIRATION DATE` | 달력 날짜 타입은 같게 하고, 컬럼명으로 점검일·발급일·기간 시작일·만료일을 구분합니다. |
| 범주 코드와 자유 텍스트 | 점검의 `Results`·`Violations`, 인허가의 `APPLICATION TYPE`·`LICENSE DESCRIPTION` | 결과와 신청 유형은 코드표에 매핑합니다. 위반 원문과 면허 설명은 각각 분석 목적에 맞는 텍스트 컬럼으로 보존합니다. |

## 변경 규칙과 예외 처리

규칙은 **원천 컬럼 매핑 → 공백·결측 표준화 → 타입 변환·코드 조회 → 예외 기록** 순서로 적용하는 안입니다. Bronze의 원천 값과 행 순번으로 변환 전후를 대조합니다.

| 규칙 ID | 대상 | 변환 기준 |
| --- | --- | --- |
| `STD-01` | 컬럼명 | 데이터셋과 원천 컬럼명을 기준으로 [인벤토리의 표준명](source_data_inventory.md)을 조회합니다. 새 이름은 영문 소문자 `snake_case`로 정하고, 한 테이블 안에 같은 표준명이 두 번 나오면 매핑을 검토합니다. |
| `STD-02` | 일반 텍스트·공란 | 일반 텍스트의 양끝 공백은 제거하고 빈 값은 `null`로 통일합니다. `violations_text`의 비어 있지 않은 원문은 문구와 내부 줄바꿈을 보존합니다. |
| `STD-03` | 번호·코드·문자 | 면허번호처럼 숫자로 보이는 식별자와 ZIP은 `string`으로 저장해 선행 0을 보존합니다. 점검 면허번호 `0`과 `9999999`는 04번의 결정에 따라 해당 필드에서만 `null`로 바꾸고 원천 순번을 남깁니다. |
| `STD-04` | 수치 | 정수로 정한 지역 번호는 `int64`, 위도·경도와 원천의 경계 면적·길이는 `float64`로 변환합니다. 숫자로 파싱할 수 없는 값은 `null`과 변환 실패 사유를 기록합니다. 좌표 범위나 지역 코드 유효성은 형식 변환과 별도로 검사합니다. |
| `STD-05` | 날짜와 시각 | 실제 CSV의 `MM/DD/YYYY`는 `date32`로 파싱해 `YYYY-MM-DD`로 표시합니다. UTC 시각은 시간대와 밀리초를 갖는 타입으로 변환합니다. 파싱 실패, 기간 역전, 특이 연도는 각각 판정합니다. |
| `STD-06` | 고정 범주 코드 | 데이터셋·원천 컬럼·양끝 공백을 제거한 원천 값을 기준으로 코드표를 조회합니다. 미등록 값은 표준 코드를 `null`로 두고 원천 값과 검토 상태를 기록합니다. 정의가 확정되면 코드표에 추가합니다. |

## 날짜와 시간 형식

두 CSV의 날짜 관련 9개 컬럼은 비결측 값이 모두 **`MM/DD/YYYY`** 형식이며 달력 날짜로 파싱됐습니다. 표준안은 `date32`로 저장하고, 문서나 표에서는 **`YYYY-MM-DD`**로 표시합니다. 경계 GeoJSON의 시스템 시각 2개는 밀리초와 UTC를 포함한 ISO 형식입니다.

| 원천 | 원천 날짜 컬럼 또는 속성 | 표준 이름 | 관측 최솟값 ~ 최댓값 또는 원천 예시 |
| --- | --- | --- | --- |
| 점검 | `Inspection Date` | `inspection_dtm` | 2010-01-04 ~ 2026-11-17 |
| 인허가 | `APPLICATION CREATED DATE` | `application_created_dtm` | 2000-06-19 ~ 2026-11-17 |
| 인허가 | `APPLICATION REQUIREMENTS COMPLETE` | `application_requirements_complete_dtm` | 2000-06-16 ~ 2026-11-17 |
| 인허가 | `PAYMENT DATE` | `payment_dtm` | 1997-04-15 ~ 2026-11-17 |
| 인허가 | `LICENSE TERM START DATE` | `term_start_dtm` | 1995-02-16 ~ 2028-07-16 |
| 인허가 | `LICENSE TERM EXPIRATION DATE` | `term_end_dtm` | 0206-08-17 ~ 9999-01-01 |
| 인허가 | `LICENSE APPROVED FOR ISSUANCE` | `approved_for_issuance_dtm` | 2000-06-16 ~ 2026-11-17 |
| 인허가 | `DATE ISSUED` | `issued_dtm` | 2002-01-02 ~ 2026-11-17 |
| 인허가 | `LICENSE STATUS CHANGE DATE` | `status_change_dtm` | 2002-01-08 ~ 2026-11-17 |
| 지역 경계 | `properties.:created_at` | `source_created_at` | `2025-04-22T23:06:36.944Z`, 77개 모두 같은 UTC 값 |
| 지역 경계 | `properties.:updated_at` | `source_updated_at` | `2025-04-22T23:06:36.944Z`, 77개 모두 같은 UTC 값 |

- **형식과 업무 정합성은 별도 검사로 기록합니다.** 만료일의 `0206-08-17`과 `9999-01-01`은 각각 1건이며, 날짜로 읽을 수 있지만 업무상 의미를 확인해야 합니다. 시작일과 만료일이 둘 다 있을 때 만료일이 더 빠르면 기간 오류로 표시합니다.
- **공란은 업무 의미와 함께 해석합니다.** 발급 상태 `AAI` 1,131,478행의 상태 변경일은 모두 비어 있습니다. 갱신의 신청 생성일도 원천 정책과 함께 해석합니다. 결측 원인은 같은 값으로 추정해 채우기 전에 상태·유형·출처 근거로 확인합니다. [시카고시 인허가 날짜와 상태 정의](https://catalog.data.gov/dataset/business-licenses)
- **날짜와 시각을 구분합니다.** 04번의 기존 `*_dtm` 이름은 일자만 저장하는 `date32` 필드입니다. UTC 시각을 가진 경계 시스템 속성에는 `*_at`과 `timestamp[ms, UTC]`를 씁니다. 경계의 포털 생성·갱신 시각은 포털 레코드에 관한 시각으로 해석하고 경계의 업무 적용 기간은 별도 확인합니다.

## 컬럼명과 업무 용어

공용 컬럼명은 소문자 영문 `snake_case`를 씁니다. 원천 이름·포털 API 이름·표준안은 인벤토리에서 추적합니다. `_key`는 식별·연결 값, `_id`는 출처 식별자, `_cd`는 범주 코드, `_num`은 수치 또는 정수로 정한 지역 번호, `_text`는 원문 텍스트에 사용합니다. 숫자처럼 보이는 식별자와 우편번호는 문자열로 저장해 선행 0을 보존합니다.

| 팀에서 쓰는 한국어 | 공통 영문 표기 | 뜻과 사용 기준 |
| --- | --- | --- |
| 위생점검 | `inspection` | 개별 점검 사건입니다. 키 `inspection_key` |
| 인허가 기록 | `license_event` | 특정 면허의 발급·갱신·변경 기록입니다. 키 `license_event_key` |
| 면허번호 | `license_number` | 점검과 인허가 이력을 연결하는 번호입니다. `license_number_key` |
| 사업자 계정 / 사업장 | `account` / `establishment` | 계정은 소유 사업자 단위입니다. 사업장은 특정 영업장 단위이며 원천의 `site_key`와 조합을 검증합니다. |
| 법적 명칭 / 영업 상호 / 별칭 | `legal_name` / `dba_name` / `aka_name` | 등록 명칭, 실제 영업 상호, 알려진 다른 이름을 구분합니다. |
| 위반 원문 / 위반 항목 | `violations_text` / `violation` | 원문 한 칸은 점검 단위로 저장하고, 분리한 위반 항목은 별도 테이블에서 관리합니다. |
| 점검 결과 / 인허가 상태 | `result_cd` / `recorded_status_cd` | 점검 결과와 원천에 기록된 면허 상태는 서로 다른 범주입니다. |
| 커뮤니티 지역 / 동네 | `community_area` / `neighborhood` | 경계 데이터와 연결하는 행정·통계 지역 코드와 인허가의 동네 이름을 구분합니다. |
| 시의회 선거구 / 투표구 | `ward` / `precinct` | 투표구 번호는 여러 선거구에서 반복될 수 있으므로 둘을 함께 확인합니다. |
| 위도·경도 / 경계 | `latitude`·`longitude` / `geometry` | CSV 위치 문자열은 `(위도, 경도)` 형식입니다. GeoJSON의 점 배열은 `[경도, 위도]` 순서입니다. [GeoJSON 명세](https://www.rfc-editor.org/rfc/rfc7946) |

## 주요 범주값 표기

[공용 코드표 초안](../metadata/data_dictionary/shared_code_map.csv)에 현재 확인한 고정 범주 5개 컬럼의 **원천 값 → 표준 코드 → 한글 뜻**을 24개 행으로 기록했습니다. `mapping_status`가 `review`인 값은 표에 적힌 코드를 쓰되 의미는 확인 대상으로 표시합니다.

| 컬럼 | 매핑 예시 | 적용 기준 |
| --- | --- | --- |
| 점검 결과 `result_cd` | `Pass w/ Conditions` → `PASS W/ CONDITIONS` | 7개 결과를 04번의 대문자 표기에 맞춥니다. 불합격률의 분모는 분석 정의에서 결정합니다. |
| 위험등급 `risk_level_cd` | `Risk 1 (High)` → `RISK_1` | 세 위험등급과 `All`을 구분합니다. `ALL`로 표현할 원천 값은 90행이었으며, 업무 의미는 팀에서 확인합니다. |
| 인허가 신청 유형 `application_cd` | `RENEW` → `RENEW` | 최초 신청, 갱신, 소재지·규모·영업 활동 변경의 기존 코드를 보존합니다. [시카고시 인허가 코드 설명](https://catalog.data.gov/dataset/business-licenses) |
| 인허가 상태 `recorded_status_cd` | `AAI` → `AAI`, `INQ` → `INQ` | 알려진 상태 코드를 보존합니다. 원천에 1건 있는 `INQ`는 의미 확인 대상으로 표시합니다. [시카고시 인허가 상태 설명](https://catalog.data.gov/dataset/business-licenses) |
| 조건부 승인 `conditional_approval_cd` | `Y` → `Y` | 인허가 신청의 조건부 승인 코드입니다. 점검 결과는 별도의 `result_cd`에 둡니다. |

면허 유형은 `LICENSE CODE`와 `LICENSE DESCRIPTION`의 조합, 커뮤니티 지역은 경계 파일의 `area_numbe`와 `community`의 조합을 각각 참조 코드표 후보로 사용합니다. 영업 활동 ID 목록의 분해, 시설·점검 유형의 유사 명칭 통합, 주·특별 서비스 구역·행정 구역의 허용 코드 범위는 별도 참조표와 팀 검토를 거쳐 정합니다.

이 문서와 CSV는 통합에 사용할 기준안입니다. 현재 조사 코드는 원천 값과 분포를 확인하며, 공용 Silver 구현에서 합의된 규칙을 적용할 수 있도록 값을 명시했습니다.

## 조사 코드 실행

프로젝트 루트에서 [원천 조사 코드](../src/ingestion/profile_sources.py)를 실행하면 결과가 JSON으로 출력됩니다. Python에 `pyarrow`와 `PyYAML`이 필요합니다. 기본 설정은 `config/sources.example.yaml`이며, 원천 폴더는 `--raw-dir`, `CHICAGO_RAW_DIR` 환경 변수, 기본 `data/00_origin/` 순으로 찾습니다. 다른 설정은 `--sources-config`로 지정할 수 있습니다.

```powershell
python src/ingestion/profile_sources.py
```

조사 코드는 세 데이터 파일과 세 컬럼 설명 JSON을 읽기 전용으로 확인합니다. 실제 컬럼과 포털에만 있는 컬럼, 결측과 값 형식, 날짜 범위, 범주 분포, GeoJSON 속성 타입, 기존 체크섬과의 일치 여부를 출력합니다.
