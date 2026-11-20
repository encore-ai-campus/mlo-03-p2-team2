# 데이터 모델과 지표 정의

## 입력과 계보

팀 점검 원천은 점검 ID별 318,627행과 17개 컬럼이다. 지역 경계 77개는 팀 GeoJSON에서 읽으며, 05 공간 처리에 사용할 지역 속성과 도형을 WKT 기반 컬럼에 대응시킨다. 점검 CSV Bronze는 원천 헤더와 문자열을 보존한다. `source_row_num`은 헤더와 완전히 빈 레코드를 제외하고 1부터 부여한다. 인용부호 안 줄바꿈은 같은 논리 레코드에 포함된다. 매니페스트에 파일명, 포맷, SHA-256, 행 수, 빈 레코드 수 및 적재 시각을 기록한다. [원천 컬럼 대응표](../../../metadata/data_dictionary/05_geospatial/column_mapping.csv) · [컬럼 계약](../../../metadata/data_dictionary/05_geospatial/column_contract.json)

Silver는 식별자를 문자열, 달력 날짜를 `date32`, 위경도를 `float64`로 저장한다. 일반 텍스트에서 양끝 공백을 제거하며, 비공란 위반 문구와 로컬 WKT는 원문을 보존한다. 결과와 위험 등급의 원문, 표준 코드, 매핑 상태를 기록한다. 점검 CSV 면허번호의 공란·`0`·`9999999`는 `NULL`과 사유로 기록하고 나머지 식별자의 선행 0은 보존한다. 변환 실패와 검토 대상은 `quality_issues.parquet`에 데이터셋, 배치, 원천 순번, 컬럼, 사유 코드, 원문으로 남긴다. [팀 공용 코드표](../../../metadata/data_dictionary/shared_code_map.csv)

## 공용 산출물 연결

05 Bronze와 Silver는 지역 배정 및 원천 대조를 위한 관점별 산출물이다. 팀 통합 Gold에서는 01 점검 Silver의 키·타입·내용을 05 기준과 점검 ID로 대조한 뒤 01의 점검 컬럼을 사용한다. 02가 공유한 점검별 관측 상태와 고유 위반 코드가 위반 집계의 입력이다. 02 코드는 `inspection_key × code_system_version × violation_cd`에서 유일해야 한다. 점검별 관측 상태로 공란과 파싱 실패를 구분하며, 02의 공유 코드가 있는 점검만 코드 집계 가능 분모에 포함한다. 02의 격리 조각은 02 산출물에서 추적한다. [공용 입력 스키마와 실행법](runbook.md)

## 단계별 산출물

| 단계 | 파일 | 한 행의 의미와 키 |
| --- | --- | --- |
| Bronze | `food_inspections.parquet`, `community_areas.parquet` | 데이터셋 × 배치 × 원천 논리 레코드 순번 |
| Silver | `food_inspections.parquet`, `community_areas.parquet` | 각각 `inspection_key`와 `boundary_version` × `community_area_num` |
| Silver | `inspection_community_areas.parquet`, `inspection_geography.parquet` | 점검의 지역 배정 또는 지역·평가·위반 관측 요약, `inspection_key` |
| Silver | `inspection_violation_observations.parquet` | 점검별 위반 원문 유무와 파싱 상태, `inspection_key` |
| Silver | `inspection_violation_tokens.parquet` | 원문 위반 토큰, `inspection_key` × `violation_sequence` |
| Silver | `inspection_violation_codes.parquet` | 05 로컬 파싱 대조용 고유 코드, `inspection_key` × `code_system_version` × `violation_cd` |
| Gold | `inspection_area_period.parquet` | 기간 단위 × 기간 시작일 × 지역 또는 미배정 사유 |
| Gold | `violation_coverage_area_period.parquet` | 점검 집계 키 × 절차 구간 |
| Gold | `violation_area_period.parquet` | 위반 관측 범위 키 × 기록된 위반 코드 |
| AI-ready | `ai_inspection_metrics.parquet`, `ai_violation_coverage.parquet`, `ai_violation_metrics.parquet` | Gold의 각 행 단위에 대응하며 안정적인 `region_key` 사용 |

공유 지역 차원은 `community_areas.parquet`를 사용한다. 지역의 번호, 이름, 경계 도형은 `boundary_version`과 `community_area_num`으로 조회할 수 있다.

매니페스트는 계층별 파일의 체크섬을 기록하고 Parquet 파일별 행 수와 스키마를 포함한다. Silver의 `quality_summary.json`과 `code_coverage.csv`, Gold의 `metrics_summary.json`, AI-ready의 `validation_summary.json`에서 정제·집계 결과를 확인할 수 있다. [AI-ready 의미 계약](../../../metadata/feature_dictionary/05_geospatial/semantic_contract.json)

## 지역 배정

점검의 경도와 위도를 경계의 경도·위도 축과 대응시킨다. 공간 조건 `intersects`는 폴리곤 내부와 경계선을 포함한다. 단일 경계와 교차할 때 지역 번호를 부여하며, 경계선 위의 단일 교차 여부도 기록한다. 미배정 상태는 좌표 공란, 비정상 좌표, 경계 밖, 복수 경계 후보로 구분한다. 복수 후보의 지역 번호는 목록으로 보존한다. 지역 경계의 키는 입력 파일 SHA-256인 `boundary_version`과 `community_area_num`이다. [공간 배정 코드](../../../src/domains/05_geospatial/silver_spatial.py)

## 지표 산정

| 지표 | 분자 | 분모 |
| --- | --- | --- |
| 불합격률 `failure_rate` | 불합격 점검 | 평가 완료 점검 |
| 위반 원문 기록률 | 원문이 있는 평가 점검 | 평가 완료 점검 |
| 위반 코드 기록률 `code_recorded_rate` | 해당 코드가 한 번 이상 기록된 고유 평가 점검 | 평가 완료 점검 |
| 코드 집계 가능 건 기준 기록률 `code_recorded_among_ready_rate` | 같은 코드의 고유 평가 점검 | 절차 구간을 식별할 수 있고 파싱 가능한 코드가 있는 평가 점검 |

`PASS`, `PASS W/ CONDITIONS`, `FAIL`은 `EVALUATED`로 분류한다. `NO ENTRY`, `OUT OF BUSINESS`, `NOT READY`, `BUSINESS NOT LOCATED`는 `NOT_EVALUATED`로 기록한다. 공란·미등록·평가 상태 미정 결과는 `UNKNOWN_RESULT`로 기록한다. 위반란 공란은 `violation_missing_count`로 집계한다.

비율은 0~1로 저장하며 분모가 0일 때 `NULL`이다. 기간이나 지역을 합칠 때는 분자와 분모를 각각 합산해 다시 나눈다. 여러 코드를 다룰 때 평가 분모는 위반 관측 범위 테이블에서 지역·기간·절차 구간당 한 번 가져온다.

## 기간과 위반 코드

`period_grain_cd`는 `MONTH` 또는 `YEAR` 중 한 단위를 선택한다. 첫 달과 마지막 달처럼 달력 구간의 일부만 관측한 결과는 `covered_start_dtm`, `covered_end_dtm`, `partial_period_flag`로 식별한다.

위반 코드는 2018년 7월 1일 전후 두 절차 구간과 함께 식별한다. 2018년 연간 위반 집계에서도 구간별 분모를 각각 계산한다. 코드 설명의 근거는 해당 구간의 원천 점검에서 관측된 문구다. [시카고시 식품위생 점검 설명](https://catalog.data.gov/dataset/food-inspections)

Gold는 기록된 코드별 행을 제공한다. AI-ready는 각 절차 구간에서 관측된 코드 목록을 해당 지역·기간에 펼치고 다음 상태를 부여한다.

| `code_observation_status_cd` | 의미 |
| --- | --- |
| `RECORDED` | 해당 코드가 한 건 이상 기록됨 |
| `NO_RECORDED_CODE` | 집계 가능한 코드가 있으며 해당 코드 기록은 0건 |
| `NO_CODE_READY_INSPECTIONS` | 평가 완료 점검이 있으며 집계 가능한 코드가 0건 |
| `NO_EVALUATED_INSPECTIONS` | 평가 완료 점검이 0건 |

지역 배정 건만 조회할 때는 Gold의 `unique_area` 또는 AI-ready의 `assigned_area_flag=true`를 적용한다. `community_area:08`과 `unassigned:missing_coordinates`처럼 지역과 미배정 상태에 각각 키를 부여한다.
