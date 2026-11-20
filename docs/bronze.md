# Origin 정리와 Bronze 적재

## 입력과 경로

`data/00_origin/`은 로컬 읽기 전용 원천 스냅샷이며 Git에서 제외한다. `CHICAGO_RAW_DIR`을 지정하지 않으면 저장소 루트의 `data/00_origin/`을 사용한다. `config/sources.example.yaml`에도 데이터셋별 상대 경로를 기록했다. 원본 다운로드 목록인 `data/00_origin/download_manifest.csv`는 파일명 기준으로 작성되어 있으며, 폴더 이동에 맞춰 수정하지 않았다. 기존 압축 해제 안내문 `data/00_origin/README.txt`도 원본 그대로 보존했다.

| 데이터셋 | 원천 | Bronze |
| --- | --- | --- |
| food_inspections | `data/00_origin/food_inspections/food_inspections.csv` | `data/01_bronze/food_inspections/food_inspections.parquet` |
| business_licenses | `data/00_origin/business_licenses/business_licenses.csv` | `data/01_bronze/business_licenses/business_licenses.parquet` |
| community_areas | `data/00_origin/community_areas/community_areas.geojson` | `data/01_bronze/community_areas/community_areas.parquet` |

각 데이터와 컬럼 JSON은 같은 데이터셋 폴더에 `.sha256` 파일과 함께 있다. 컬럼 JSON, 체크섬, manifest는 Bronze 행으로 적재하지 않는다. 적재 전 각 데이터 파일을 대응하는 `.sha256`과 대조하고, 적재 후 다시 해시를 계산한다.

## 저장 계약

CSV는 UTF-8(선택적 BOM 허용), 쉼표 구분, 표준 CSV 인용 규칙으로 읽는다. CSV의 모든 원본 컬럼은 Parquet `string` 타입으로 저장한다. 따라서 빈 필드는 빈 문자열이고, 앞자리 0·날짜 표기·대소문자·이상값은 변환되지 않는다. 원천 컬럼 순서도 유지한다.

GeoJSON은 `FeatureCollection`의 각 Feature를 한 행으로 저장한다. `type`과 `properties`의 문자열 값은 그대로 두고, `geometry`는 전체 GeoJSON geometry 객체를 JSON 문자열로 직렬화한다. 이는 일반 Parquet에서도 `MultiPolygon`의 좌표 배열과 순서를 손실 없이 보존하며, 읽을 때 `json.loads(geometry)`로 geometry 객체를 복원할 수 있다. 현재 단계에서 공간 연산은 하지 않으므로 GeoParquet 의존성을 추가하지 않았다. 이 파일은 **GeoParquet이 아니며**, 공간 도구의 geometry 자동 인식이 필요하면 후속 단계에서 메타데이터나 GeoParquet 변환을 검토한다.

모든 데이터셋의 끝에 `_SRC_FILE`과 `_LOAD_DTM`을 `string` 기술 컬럼으로 추가한다. `_SRC_FILE`은 원천 파일의 이름이고, `_LOAD_DTM`은 한 번의 실행 시작 시 생성한 **UTC ISO 8601 초 단위 `Z` 시각**이다. 한 실행의 세 데이터셋과 모든 행에서 동일한 값을 사용한다. 실행 ID와 데이터셋별 시작·종료·입출력 행 수·상태는 Git 제외 대상인 `logs/pipeline_runs.csv`에 기록한다.

향후 적재 실행은 `logs/bronze_run_details.jsonl`에도 실행 ID, 원천 파일명·절대 경로·manifest 출처 URL, 적재 시각, 출력 파일명·절대 경로, 입출력 행 수, 원천 SHA-256, 성공 여부와 오류를 기록한다. 기존 CSV 로그의 열과 과거 기록은 유지한다. 이 상세 로그는 새 코드로 실행한 건부터 생성하며 과거 시각을 소급해 작성하지 않는다.

각 데이터셋은 임시 Parquet에 전체를 적재하고, 원본 행과 저장된 행의 모든 값을 순서대로 다시 비교한다. 행 수, 원본 컬럼, 기술 컬럼, 키 유일성 및 geometry를 확인한 다음 출력 파일을 교체한다. 따라서 재실행은 append가 아닌 full refresh다. 같은 원천은 동일한 원본 값과 행 수를 만들며 실행 시각과 로그만 달라진다. 한 데이터셋 검증에 실패하면 해당 데이터셋의 기존 성공 출력은 유지된다. 세 데이터셋의 게시는 하나의 트랜잭션으로 묶지 않는다.

## 실행

```powershell
python -m pip install -r requirements.txt
python -m src.bronze.load_bronze
python -m pytest tests/bronze --basetemp=data/pytest_tmp
```

고정 행 수는 이 원천 스냅샷의 기준값인 점검 318,552건, 인허가 1,212,132건, 지역 77건이다. 다른 스냅샷을 사용하려면 행 수 계약을 검토해야 한다.
