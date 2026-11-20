# 03 반복 위반·재검사 제시안

- **담당자** ③ 반복 위반·재검사 담당
- **상태** 초안
- **작성일** 2026-11-20

## 1. 분석 질문과 공유할 결과

- **분석 질문** 같은 면허번호의 연속 점검에서 같은 위반 코드가 다시 관측되는가? 불합격 후 재검사가 관측된 경우 결과는 어떻게 바뀌는가?
- **산출물** `repeat_violation_mart`는 위반 코드별 재발 분석, `inspection_reinspection_mart`는 불합격 점검의 재검사 연결 상태와 결과 전이 분석에 사용합니다.
- **최종 결과 한 행의 의미** `repeat_violation_mart`는 기준 점검과 바로 다음 점검의 비교에서 기준 점검에 관측된 고유 위반 코드 한 개입니다. `inspection_reinspection_mart`는 기준 불합격 점검 한 건입니다.

## 2. 취합할 원천과 행 단위

| 원천 파일·공용 테이블 | 입력 한 행의 의미 | 가져올 주요 컬럼 | 이 관점에서 쓰는 목적 |
| --- | --- | --- | --- |
| 팀 원천 `food_inspections.csv` | 위생점검 한 건 | `Inspection ID`, `License #`, `Inspection Date`, `Inspection Type`, `Results`, `Violations`, `Risk`, `Facility Type` | 팀 공용 점검의 원천 |
| 로컬 `Food_Inspections_20261119.csv` | 위생점검 한 건 | 팀 원천과 같은 점검 컬럼 | 공용 스냅샷 확정 전 로컬 조사와 개발 검증 |
| 공용 점검 Silver 설계안 | 위생점검 한 건 | `inspection_key`, `license_number_key`, `inspection_dtm`, `inspection_type`, `result_cd`, `violations_text`, `source_row_num` | 점검 이력 정렬과 파생 결과의 참조 기준 |

- **원천 스냅샷 확인 방법** 팀 인벤토리의 원천은 318,552행 × 17열, 로컬 원천은 318,627행 × 17열입니다. 팀 공용 매니페스트의 SHA-256을 확인해 사용할 파일을 확정합니다. 이 문서의 관측 수치는 로컬 원천 기준입니다.
- **원천 행 추적** Bronze에서 원본 CSV의 바이트, 헤더, 논리 레코드 순서를 보존합니다. `source_row_num`은 헤더와 완전히 빈 레코드를 제외한 **1부터 시작하는 논리 레코드 순번**입니다. 인용부호 안의 줄바꿈은 같은 레코드에 속합니다. 원본 CSV와 `metadata.json` 두 파일을 두고 메타데이터에 헤더, 논리 행 수, SHA-256과 순번 계산 기준을 기록하는 안입니다. 공용 Silver에 `source_row_num`을 `int64` 컬럼으로 전달하고 변환 예외도 원천 순번으로 추적합니다.
- **공용으로 재사용할 테이블과 기준** 점검 Silver는 `inspection_key`(`string`) 기준으로 점검 한 건을 유지합니다. ②에서 `inspection_key`와 위반 코드를 제공하는 공용 위반 상세가 합의되면 그 파싱 결과를 재사용합니다. 초기 분석은 Food Inspections만 사용합니다.

## 3. 컬럼명·타입·변경 규칙

| 성격·공통 용어 | 원천 컬럼 | 표준 컬럼명 | 저장 타입 | 변경 규칙과 예외 |
| --- | --- | --- | --- | --- |
| 점검 식별자 | `Inspection ID` | `inspection_key` | `string` | `STD-01~03`. 양끝 공백 제거, 키의 공란·중복 여부를 검증 |
| 면허번호 | `License #` | `license_number_key` | `string` | `STD-03`. 선행 0을 보존하고 공란·`0`·`9999999`는 `null`로 처리. 원천 행은 유지 |
| 점검일 | `Inspection Date` | `inspection_dtm` | `date32` | `STD-05`. `MM/DD/YYYY`로 읽고 `YYYY-MM-DD`로 표시. 변환 실패는 `null`과 원천 순번 기록 |
| 점검 유형 | `Inspection Type` | `inspection_type` | `string` | `STD-02`. 양끝 공백을 제거. 재검사 판정에 사용할 유형 목록은 ①과 합의 |
| 점검 결과 | `Results` | `result_cd` | `string` | `STD-06`. 공용 코드표의 7개 코드 사용. 예를 들어 `Pass w/ Conditions`는 `PASS W/ CONDITIONS`. 미등록 값은 코드 `null`과 원천 값·검토 상태 기록 |
| 위험등급 | `Risk` | `risk_level_cd` | `string` | `STD-06`. 공용 코드표 사용. `All`은 `ALL`로 매핑하고 `review` 상태를 추적 |
| 시설 유형 | `Facility Type` | `facility_type` | `string` | `STD-02`. 양끝 공백 제거, 공란은 `null` |
| 위반 원문 | `Violations` | `violations_text` | `string` | `STD-02`. 공란은 `null`, 값이 있는 원문은 문구와 내부 줄바꿈을 보존. 개별 위반 코드는 파생 데이터에서 추출 |
| 원천 행 순번 | CSV 논리 레코드 순서 | `source_row_num` | `int64` | 같은 SHA-256의 원천 스냅샷 안에서 행 위치를 식별 |

공용 코드표는 `dataset`, `source_column`, 양끝 공백을 제거한 `source_value`로 조회합니다. `inspection_type`의 유사 명칭 통합과 위반 코드 체계는 이번 공용 코드표의 범위 밖이므로 별도 합의 대상으로 둡니다.

## 4. 연결 방식과 팀에 제공할 컬럼

- **이력 연결 키** `license_number_key`가 있는 점검끼리 점검일 순으로 연결합니다. 면허번호가 같은 점검 이력으로 해석하며, 번호가 없으면 이력 연결 상태에 사유를 남깁니다. 동일 날짜 때문에 선후 관계가 모호하면 `source_row_num`을 날짜 내 발생 순서로 사용하지 않고 미확정으로 표시합니다.
- **반복 위반** `PASS`, `PASS W/ CONDITIONS`, `FAIL`에 해당하는 점검 사이의 연속된 점검 쌍을 비교합니다. 기준 점검에서 같은 위반 코드가 여러 번 추출돼도 한 번만 셉니다. 분모는 두 점검에서 위반 코드 관측과 파싱 상태를 확인할 수 있는 쌍의 기준 점검 위반 코드 수입니다. 위반 원문 공란·파싱 실패로 재발 여부를 판단할 수 없으면 별도 상태로 기록합니다. **2018-07-01 이후**를 초기 비교 범위로 제안합니다. [시카고 점검 절차 변경 이후 데이터](https://data.cityofchicago.org/Health-Human-Services/Food-Inspections-7-1-2018-Present/qizy-d2wf)
- **재검사** 재검사로 분류된 점검을 같은 면허번호의 **더 이른 가장 최근 `FAIL`**에 연결합니다. 기준 `FAIL` 한 건에는 기간 안에서 처음 관측된 재검사 한 건을 붙입니다. 초안 기간은 **1~30일**이며, 동일 날짜에 후보가 여러 개라 선후를 판단하기 어려운 경우 미확정으로 둡니다. 미연결, 면허번호 없음, 관측 기간 부족은 구분합니다. 결과 전이는 `PASS`, `PASS W/ CONDITIONS`, `FAIL`을 각각 집계하고 나머지 결과는 별도 범주로 표시합니다.
- **공유 결과 키** `repeat_violation_mart`는 `base_inspection_key + followup_inspection_key + violation_cd`, `inspection_reinspection_mart`는 `base_inspection_key`입니다. 공용 점검 테이블과 결합할 때 반복 위반 상세는 조인 전에 기준 점검 단위로 집계합니다.

| 제공 컬럼 | 타입 | 한 행에서의 의미 | 다른 관점의 사용 방법 |
| --- | --- | --- | --- |
| `base_inspection_key` | `string` | 기준 점검의 `inspection_key` | 공용 점검에 결과를 붙이는 키 |
| `followup_inspection_key` | `string`, null 허용 | 후속 점검 또는 연결된 재검사의 `inspection_key` | 후속 점검 상세 확인 |
| `license_number_key` | `string`, null 허용 | 관측된 면허번호 | 면허번호별 점검 이력 집계 |
| `days_to_followup_num` | `int64`, null 허용 | 기준 점검일부터 후속 점검일까지의 일수 | 재검사 소요 기간 집계 |
| `base_result_cd` / `followup_result_cd` | `string`, 후속 결과 null 허용 | 기준·후속 점검의 공용 결과 코드 | 결과 전이 집계 |
| `violation_cd` | `string` | 기준 점검에서 관측된 위반 코드 | ② 위반 유형별 재발 집계 |
| `repeat_flag` | `bool`, null 허용 | 같은 위반 코드의 재관측 여부. 판단 불가는 `null` | 반복 위반 분자와 분모 구분 |
| `reinspection_match_status_cd` | `string` | 연결 확정·미관측·동일 날짜 모호·면허번호 없음·관측 기간 부족 등의 상태 | 연결 가능 범위와 제외 사유 집계 |

## 5. 검증 결과

| 검증 항목 | 비교 기준 | 실제 건수·결과 또는 검증 예정 |
| --- | --- | --- |
| 로컬 원천 규모와 식별자 | 논리 레코드, 헤더, `Inspection ID` 공란·중복 | 318,627행 × 17열. 점검 ID 공란 0건, 초과 중복 0건 |
| 팀 스냅샷 일치 여부 | 팀 매니페스트 SHA-256과 로컬 원천 SHA-256 | 행 수가 달라 스냅샷이 다름. 팀 공식 파일·해시 확인 예정 |
| 원천 → Bronze → Silver 행 보존 | 논리 레코드 수, 헤더, SHA-256, `source_row_num` | 현재 작업 폴더에는 공용 Bronze가 없습니다. 팀 스냅샷 확정 후 검증 예정 |
| 점검일 변환 | 공란, 파싱 실패, 최소·최대 | 로컬 원천 공란 및 파싱 실패 0건. 2010-01-04~2026-11-18 |
| 면허번호 예외 | 공란, `0`, `9999999` | 로컬 공란 19건, `0` 840건, `9999999` 1건 |
| 공용 코드표 적용 범위 | `Results`·`Risk`의 양끝 공백을 제거한 비결측 값 | 로컬 비결측 미등록 값 0건. `Risk` 공란 88건 |
| 위반 공란 | 전체 점검과 `Fail` 중 위반 원문 공란 | 로컬 90,022건, 그중 `Fail` 3,665건 |
| 결과 키와 연결 품질 | 결과별 고유 키, 연결 전후 행 수, 동률·미확정 건수, 위반 코드 파싱률 | 유형 목록과 연결 기간 확정 후 검증 예정 |

로컬 점검 파일 SHA-256은 `b43beb7fae834a8698ca162004caf2929cb2eca7ff75c27b4db6bf07aa103c98`입니다. [로컬 품질 조사 스크립트](../../src/domains/03_repeat_inspection/quality_datasets.py)와 [Bronze 스냅샷 매니페스트](../../metadata/lineage/03_repeat_inspection/bronze_manifest.json)에서 확인할 수 있습니다.

## 6. 팀에서 합의할 항목

- **공용으로 정해야 할 규칙** 사용할 원천 SHA-256, 재검사 유형 목록과 기간, 동일 날짜 점검 처리, 관측 기간의 종료일, 반복 위반의 분모와 위반 공란의 처리 기준을 확정합니다.
- **입력이 필요한 다른 관점** ①의 공용 점검 Silver 및 점검 유형 정의, ②의 위반 코드 파싱 결과와 파싱 상태를 재사용할 수 있는지 확인합니다. 04번 제시안의 `establishment_key`는 확인된 사업장 단위로 결과를 비교할 때 사용할 수 있는 후속 확장입니다. 초기 산출은 면허번호 기준으로 작성합니다.
- **합의가 필요한 이유** 재검사 기간과 유형 분류에 따라 연결 건수가 달라지고, 위반 원문 공란 처리 방식과 위반 코드 버전에 따라 재발률의 분모가 달라집니다.

팀 참고 자료는 `domain_proposal_template.md`, `source_data_inventory.md`, `data_integration_conventions.md`, `shared_code_map.csv`, `04_license_proposal.md`입니다.

## 7. 로컬 실행

저장소 루트에서 실행합니다. 로컬 스냅샷 `Food_Inspections_20261119.csv`를 `origin/03_repeat_inspection/`에 두고, 같은 파일을 바이트 그대로 `data/bronze/03_repeat_inspection/`에 복사한 뒤 Silver를 빌드합니다.

```powershell
python -m pip install -r src/domains/03_repeat_inspection/requirements.txt
python src/domains/03_repeat_inspection/build_food_inspections_silver.py
python src/domains/03_repeat_inspection/build_inspection_marts.py
```

Silver와 Gold Parquet은 각각 `data/silver/03_repeat_inspection/`과 `data/gold/marts/03_repeat_inspection/`에 생성됩니다. 새 HTML은 `reports/runs/03_repeat_inspection/`에서 열 수 있습니다. [기존 점검 분석 리포트](../../reports/03_repeat_inspection/inspection_analysis.html)와 [데이터 프로파일](../../reports/03_repeat_inspection/data_profile.html)도 함께 확인할 수 있습니다.

Windows 터미널에서 품질 조사 스크립트의 문자 인코딩 오류를 피하려면 `python -X utf8 src/domains/03_repeat_inspection/quality_datasets.py community_areas`처럼 실행합니다. 스크립트에 지정된 CSV를 `origin/03_repeat_inspection/`에서 읽습니다.
