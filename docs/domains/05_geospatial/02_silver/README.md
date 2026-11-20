# 02 Silver · 표준화, 지역 배정과 위반 구조화

Bronze 배치에서 원천의 한 행 단위를 유지한 기본 테이블과 점검별 파생 테이블을 생성합니다. 출력은 `data/02_silver/05_geospatial/<batch_id>/<rules_id>/`에 저장합니다.

| 출력 파일 | 행 단위와 키 |
| --- | --- |
| `food_inspections.parquet` | 점검 1건, `inspection_key` |
| `community_areas.parquet` | 지역 경계 1개, `boundary_version × community_area_num` |
| `inspection_community_areas.parquet` | 점검별 지역 배정 결과, `inspection_key` |
| `inspection_geography.parquet` | 점검별 지역·평가·위반 관측 요약, `inspection_key` |
| `inspection_violation_observations.parquet` | 점검별 위반 원문과 파싱 상태, `inspection_key` |
| `inspection_violation_tokens.parquet` | 위반 원문 토큰 1개, `inspection_key × violation_sequence` |
| `inspection_violation_codes.parquet` | 05 대조용 점검 내 고유 코드, `inspection_key × code_system_version × violation_cd` |
| `quality_issues.parquet` | 데이터셋·배치·원천 순번·컬럼·사유별 품질 기록 |

## 컬럼 표준화

식별자는 문자열, 달력 날짜는 `date32`, 위경도는 `float64`로 저장합니다. 일반 텍스트의 양끝 공백을 제거하고 비공란 위반 문구와 로컬 WKT는 원문을 보존합니다. 점검 결과와 위험 등급은 팀 공용 코드표를 적용하며 원문·표준 코드·매핑 상태를 기록합니다. 점검 CSV의 면허번호가 공란·`0`·`9999999`인 경우 `NULL`과 사유를 기록하고, 그 외 식별자는 선행 0을 보존합니다. [컬럼 계약](../../../../metadata/data_dictionary/05_geospatial/column_contract.json) · [팀 공용 코드표](../../../../metadata/data_dictionary/shared_code_map.csv)

## 지역 배정

점검의 경도·위도를 경계와 대응시키고 Shapely의 `intersects`로 경계선까지 포함해 비교합니다. 반복 좌표는 한 번 계산하고 원래 점검 순서로 복원합니다.

| 상태 | 처리 |
| --- | --- |
| `unique_area` | 단일 경계와 교차한 지역 번호를 부여하고 경계선 위 여부를 기록 |
| `missing_coordinates` | 필요한 좌표가 공란이면 지역 번호를 비우고 사유를 기록 |
| `invalid_coordinates` | 파싱 실패나 범위 초과이면 지역 번호를 비우고 사유를 기록 |
| `outside_boundary` | 어느 경계와도 교차하지 않은 경우를 기록 |
| `multiple_boundaries` | 여러 경계 후보의 번호를 보존하고 지역 번호를 비움 |

공유 지역 차원은 `community_areas.parquet`입니다. 지역 번호·이름·도형은 경계 원천의 SHA-256인 `boundary_version`과 `community_area_num`으로 연결합니다. [경계 읽기와 WKT 비교](../../../../src/domains/05_geospatial/geographic_boundary.py) · [공간 배정 코드](../../../../src/domains/05_geospatial/silver_spatial.py)

## 위반 구조화

위반 원문과 토큰·원문 순번을 보존하고 점검별 관측 상태를 기록합니다. 개별 코드 관측은 점검과 절차 구간 안에서 중복을 제거합니다. 05의 토큰과 코드 관측은 검증·로컬 비교에 사용하며, 팀 Gold는 02가 공유한 관측 결과를 사용합니다. [위반 파싱 코드](../../../../src/domains/05_geospatial/silver_violations.py) · [품질 검증](../quality/README.md) · [다음 단계 Gold](../03_gold/README.md)
