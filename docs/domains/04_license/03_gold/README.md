# 03 Gold · 기간 매칭과 사실·차원

Silver의 `data/02_silver/04_license/04_business_licenses.parquet`와 `04_food_inspections.parquet`를 입력으로 사용합니다. 각 출력 컬럼이 어디에서 왔는지는 [컬럼 변환 목록](../../../../metadata/lineage/04_license/column_lineage.csv)의 `03_gold` 행에 기록합니다.

| 출력 파일 (`data/03_gold/` 기준) | 한 행의 의미 | PK | 행 수 |
| --- | --- | --- | ---: |
| `04_license/04_fact_license_event.parquet` | 인허가 기록 1건 | `license_event_key` | 1,212,132 |
| `04_license/04_fact_inspection_license_match.parquet` | 점검 1건 | `inspection_key` | 318,627 |
| `04_license/04_dim_license.parquet` | 면허번호 1개 | `license_number_key` | 350,804 |
| `04_license/04_dim_establishment.parquet` | 계정·사업장 번호 조합 1개 | `establishment_key` | 283,880 |
| `04_license/04_dim_date.parquet` | 점검일 또는 인허가 발급일 1일 | `date_key` | 6,540 |

차원 행 수에는 `__unknown__` 항목이 포함됩니다. 사실 테이블의 면허·사업장·날짜 키는 차원에 연결되며, 키 정보가 부족하거나 사업장 연결을 확정할 수 없으면 해당 차원의 `__unknown__`를 사용합니다. 점검 사실의 `source_license_number`에는 Silver에서 표준화한 면허번호를 남깁니다. 원천 문자열은 Bronze에서 확인합니다.

## 기간 매칭 결과

면허번호가 같고 **시작일 ≤ 점검일 ≤ 만료일**이면 후보로 셉니다. 기간이 결측이거나 역전된 이력은 후보에서 제외합니다. 후보가 한 건이면 해당 인허가 기록 ID와 사업장 키를 연결합니다. 두 건 이상이면 후보 수를 기록하고 확정 인허가 기록 ID를 비워 둡니다. 점검별 결과는 한 행입니다.

| Gold 상태 | 건수 |
| --- | ---: |
| `UNIQUE_MATCH` · 후보 1건 | 232,383 |
| `MULTIPLE_MATCHES` · 후보 2건 이상 | 1,401 |
| `NO_VALID_PERIOD` · 같은 면허번호의 유효기간 후보 없음 | 68,259 |
| `NO_LICENSE_NUMBER_MATCH` · 같은 면허번호의 인허가 기록 없음 | 15,724 |
| `MISSING_LICENSE_NUMBER` · 점검 면허번호 결측 | 860 |
| `MISSING_INSPECTION_DATE` · 점검일 결측 | 0 |

공용본에서 PK 유일성, FK 존재, Silver 대비 키·행 순서·행 수, 확정 연결의 기간 조건 등 **23개 검사**가 통과했습니다. 인허가 사실과 점검 매칭 사실을 Silver에서 다시 계산해 점검일에 따른 후보 수, 매칭 상태, 선택한 인허가, 점검 결과와 날짜 키를 포함한 전체 값을 대조했습니다. [기존·공용본 Gold 비교](../../../../reports/04_license/match_comparison.md) · [품질 규칙 결정 항목](../quality/README.md#결정이-필요한-규칙) · [Gold 생성](../../../../src/domains/04_license/04_modeling.py) · [매칭 구현](../../../../src/domains/04_license/modeling.py) · [Gold 검증](../../../../src/domains/04_license/validate_gold.py)
