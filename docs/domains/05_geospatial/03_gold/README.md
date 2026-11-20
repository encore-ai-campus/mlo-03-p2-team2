# 03 Gold · 지역·기간별 분석 지표

Gold는 지역 또는 미배정 사유별 점검 평가와 위반 기록을 월·연도 단위로 집계합니다. 출력은 `data/03_gold/05_geospatial/<batch_id>/<gold_id>/`에 둡니다.

| 출력 파일 | 한 행의 의미 |
| --- | --- |
| `inspection_area_period.parquet` | 기간 단위 × 시작일 × 지역 또는 미배정 사유 |
| `violation_coverage_area_period.parquet` | 점검 집계 키 × 위반 절차 구간 |
| `violation_area_period.parquet` | 위반 관측 범위 키 × 기록된 위반 코드 |

## 팀 공용 입력

05의 점검별 지역 배정과 01의 공용 점검 Silver를 `inspection_key`로 연결합니다. 02의 점검별 관측 상태와 코드 결과를 사용해 위반 기록의 분모와 분자를 집계합니다.

| 생산자 | 입력 | 필요한 컬럼 |
| --- | --- | --- |
| 01 | 공용 점검 Silver | 문자열 `inspection_key`, `license_number_key`, `result_cd`, `risk_level_cd`, `facility_type`, `inspection_type`, `violations_text`. `inspection_dtm`은 `date32`, 좌표 `latitude`·`longitude`는 `float64`, `source_row_num`은 `int64` |
| 02 | `inspection_violation_codes.parquet` | 문자열 `inspection_key`, `code_system_version`, `violation_cd`. 선택 문자열 `description_text` |
| 02 | `inspection_violation_observations.parquet` | 점검당 한 행의 문자열 `inspection_key`와 `violation_observation_status`. 상태는 `parsed`, `partial`, `unrecognized`, `raw_missing` |

01의 값·타입·키를 05 원천과 대조합니다. 02 위반 코드는 `inspection_key × code_system_version × violation_cd`를 기준으로 유일해야 합니다. 02의 공유 코드가 있는 점검을 코드 집계 가능 분모에 포함합니다. 격리 조각은 02 산출물에서 추적합니다. [공용 입력 대조 코드](../../../../src/domains/05_geospatial/geographic_integration.py)

## 지표 정의

| 지표 | 분자 | 분모 |
| --- | --- | --- |
| 불합격률 `failure_rate` | `FAIL` 점검 | 평가 완료 점검 |
| 위반 원문 기록률 `violation_recorded_rate` | 비공란 위반 원문이 있는 평가 점검 | 평가 완료 점검 |
| 코드 기록률 `code_recorded_rate` | 해당 코드를 적어도 한 번 기록한 고유 평가 점검 | 평가 완료 점검 |
| 집계 가능 건 기준 코드 기록률 `code_recorded_among_ready_rate` | 같은 코드가 기록된 고유 평가 점검 | 절차 구간을 식별할 수 있고 집계 가능한 위반 코드가 있는 평가 점검 |

평가 완료는 `PASS`, `PASS W/ CONDITIONS`, `FAIL`입니다. `NO ENTRY`, `OUT OF BUSINESS`, `NOT READY`, `BUSINESS NOT LOCATED`는 미평가로 기록합니다. 공란·미등록·평가 상태 미정 결과는 `UNKNOWN_RESULT`로 구분합니다. 평가 완료 점검의 위반란 공란은 `violation_missing_count`로 집계합니다.

분모가 0이면 비율은 `NULL`입니다. 여러 지역이나 기간을 합칠 때는 분자와 분모를 각각 합산해 비율을 계산합니다. 여러 코드의 평가 분모는 위반 관측 범위 표에서 지역·기간·절차 구간마다 한 번 가져옵니다.

## 기간과 조회 조건

- `period_grain_cd`는 `MONTH` 또는 `YEAR` 중 한 단위를 선택합니다.
- 관측 기간의 시작·종료일은 `covered_start_dtm`, `covered_end_dtm`에 기록합니다. 달력 기준으로 일부만 포함되는 기간은 `partial_period_flag`로 표시합니다.
- 코드 식별에는 2018-07-01 전후의 절차 구간을 포함합니다. 2018년 연간 위반 집계는 두 구간의 분모를 각각 기록합니다. 코드 설명은 해당 구간에서 관측된 원문을 사용합니다. [시카고시 식품위생 점검 설명](https://catalog.data.gov/dataset/food-inspections)
- 지역 배정 건은 `community_area_match_status=unique_area`로 조회합니다. 실행 시에는 기간, 시설, 점검 유형, 위험 등급, 지역 번호로 범위를 지정할 수 있습니다.

`metrics_summary.json`에서 입력 범위, 건수·분모, 월·연도별 집계 대사를 확인할 수 있습니다. [Gold 생성 코드](../../../../src/domains/05_geospatial/geographic_gold.py) · [실행 방법](../../05_geospatial.md#실행) · [다음 단계 AI-ready](../04_ai_ready/README.md)
