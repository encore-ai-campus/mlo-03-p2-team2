# 04 AI-ready · 질의용 지역 지표

검증된 Gold에서 지역별 입력과 조회 조건을 명시한 질의용 테이블을 생성합니다. 출력은 `data/ai_ready/05_geospatial/<batch_id>/<release_id>/`에 저장합니다.

| 출력 파일 | 한 행의 의미 |
| --- | --- |
| `ai_inspection_metrics.parquet` | 기간 단위 × 시작일 × `region_key` |
| `ai_violation_coverage.parquet` | 점검 집계 키 × 위반 절차 구간 |
| `ai_violation_metrics.parquet` | 위반 관측 범위 키 × 위반 코드 |

`region_key`는 `community_area:08`, `unassigned:missing_coordinates`처럼 지역 번호 또는 미배정 사유를 식별합니다. 지역 배정 건만 조회하려면 `assigned_area_flag=true`를 적용합니다.

Gold의 코드 표에 관측된 코드를 절차 구간마다 지역·기간에 펼칩니다. 코드가 관측되지 않은 구간과 계산에 필요한 평가 분모가 없는 구간을 다음 상태로 구분합니다.

| `code_observation_status_cd` | 의미 |
| --- | --- |
| `RECORDED` | 해당 코드가 한 건 이상 기록됨 |
| `NO_RECORDED_CODE` | 집계 가능한 코드가 있으나 해당 코드 기록은 0건 |
| `NO_CODE_READY_INSPECTIONS` | 평가 완료 점검 중 집계 가능한 코드가 0건 |
| `NO_EVALUATED_INSPECTIONS` | 평가 완료 점검이 0건 |

분자·분모·비율과 테이블의 타입·키는 Gold 및 의미 계약과 대조합니다. 릴리스 행 수와 집계 대사 결과는 `validation_summary.json`에 기록합니다. [의미 계약](../../../../metadata/feature_dictionary/05_geospatial/semantic_contract.json) · [AI-ready 생성 코드](../../../../src/domains/05_geospatial/geographic_ai_ready.py) · [실행 방법](../../05_geospatial.md#실행)
