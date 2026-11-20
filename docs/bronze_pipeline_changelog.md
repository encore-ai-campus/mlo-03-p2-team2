# Bronze 파이프라인 공유 기록

- **기존 작업 커밋:** `243ad0d89293d6960f74b2f26233538f323b31e9` (`feature/bronze-pipeline`). 이 문서는 2026-11-20 `feature/silver-standardization`에서 기존 코드·문서를 읽고 작성했다. Bronze 코드·데이터는 이번 작업에서 변경하지 않았다.
- **원칙:** Origin은 읽기 전용, CSV 원문 값·행·컬럼을 임의 정제하지 않는다. GeoJSON geometry도 좌표 트리를 보존한다.

| 원천 | Origin 경로 | Bronze Parquet 경로 | Origin 행·열 | Bronze 행·열 |
| --- | --- | --- | ---: | ---: |
| 점검 | `data/00_origin/food_inspections/food_inspections.csv` | `data/01_bronze/food_inspections/food_inspections.parquet` | 318,552 × 17 | 318,552 × 19 |
| 인허가 | `data/00_origin/business_licenses/business_licenses.csv` | `data/01_bronze/business_licenses/business_licenses.parquet` | 1,212,132 × 37 | 1,212,132 × 39 |
| 지역 | `data/00_origin/community_areas/community_areas.geojson` | `data/01_bronze/community_areas/community_areas.parquet` | 77 Feature × 11 필드¹ | 77 × 13 |

¹ 지역 11필드는 GeoJSON Feature의 `type`, `geometry`, `properties` 9개를 센다. 팀 인벤토리의 9개는 `properties`만 센 값이다.

## 변환·검증 방식

[적재 코드](../../src/bronze/load_bronze.py)는 UTF-8 CSV를 표준 CSV 규칙으로 읽어 원본 컬럼을 모두 Parquet `string`으로 저장한다. 날짜·ZIP·식별자·공백·대소문자를 변경하지 않는다. GeoJSON은 Feature 1개당 1행으로 읽고 전체 `geometry` 객체를 JSON 문자열로 저장한다. 일반 Parquet이며 GeoParquet 메타데이터는 없다.

각 데이터셋의 끝에 `_SRC_FILE`(원천 파일명)과 `_LOAD_DTM`(한 실행에서 공통으로 쓰는 UTC ISO 8601 적재 시각)을 추가한다. 원천 `.sha256`과 적재 전 해시를 비교하고, 임시 Parquet을 다시 읽어 원천 행의 값·순서·키·geometry를 대조한 뒤 정식 출력 파일로 교체한다. 동일 원천 재실행은 append 없이 full refresh다. 로그는 Git 제외 대상 `logs/pipeline_runs.csv`에 남는다. 상세 계약은 [Bronze 안내](../bronze.md)에 있다.

```powershell
cd C:\mlo-03-p2-team2
python -m pip install -r requirements.txt
python -m src.bronze.load_bronze
```

## 확인된 결과

- 2026-11-20 **이번 작업에서 직접 확인:** Origin 3종의 대응 `.sha256` 일치, 기존 Parquet 3종의 행 수·열 수와 읽기 가능 여부. 위 표의 수치는 이 읽기 전용 확인 결과다.
- 2026-11-20 **이번 작업에서 직접 실행:** `python -m pytest tests/bronze -q` → **3개 통과**. 테스트는 임시 fixture를 사용하며 실제 Origin/Bronze 출력에 쓰지 않는다.
- 이전 Bronze 구축 당시의 원천값 전체 대조와 재실행 검증은 기존 [Bronze 안내](../bronze.md) 및 커밋의 코드·테스트 기록에 있는 결과다. 이번 문서 작업에서 실제 파이프라인을 재실행하지 않았다.

다음 단계는 Silver의 컬럼·타입·코드·날짜 규칙을 합의하는 것이다. Bronze 원본 데이터는 Git에서 제외하며 Silver에서 정제값을 만들더라도 이 원본 표현을 추적해야 한다.
