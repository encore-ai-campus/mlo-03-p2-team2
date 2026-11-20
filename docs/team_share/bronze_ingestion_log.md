# Bronze 적재 이력

## 범위와 근거

현재 저장소의 Origin·Bronze 파일, 적재 코드, 실행 로그를 읽어 확인했다. 데이터와 로그는 변경하지 않았다. 경로는 프로젝트 루트 기준이다.

- 적재 코드: [load_bronze.py](../../src/bronze/load_bronze.py), [paths.py](../../src/bronze/paths.py)
- 원천 URL·체크섬 기준: data/00_origin/download_manifest.csv와 각 .sha256
- 실행 이력: logs/pipeline_runs.csv
- 데이터 구조·측정: [source_profiles.md](../../metadata/source_profiles.md)

## 현재 프로젝트 Bronze 파일

현재 Parquet 3개를 직접 읽었다. 원천 SHA-256은 현재 파일을 manifest의 체크섬과 대조했고, Bronze SHA-256은 이번 문서 작업에서 다시 계산했다. 세 Bronze 파일의 _LOAD_DTM은 모두 2026-11-19T10:46:10Z이며 _SRC_FILE에는 각 원천 파일명이 들어 있다.

| 데이터셋 | Origin 파일·형식·출처 | 원천 행 × 열 | 적재 시각(UTC) | Bronze 출력 | Bronze 행 × 열 | 추가 컬럼 | 원천 SHA-256 | Bronze SHA-256 |
| --- | --- | ---: | --- | --- | ---: | --- | --- | --- |
| Food Inspections | data/00_origin/food_inspections/food_inspections.csv · CSV, UTF-8(선택 BOM) · [Chicago Open Data](https://data.cityofchicago.org/api/v3/views/4ijn-s7e5/export.csv?accessType=DOWNLOAD) | 318,552 × 17 | 2026-11-19 10:46:10Z | data/01_bronze/food_inspections/food_inspections.parquet | 318,552 × 19 | _SRC_FILE, _LOAD_DTM | C97464B9AA02801C7E7BEDCA876D0D6FFF482FB56366AD35BEFE5C68897E4FE7 | CBC2B9EB8D5FEB883D93619D250193EC6D9D59E572BA4F4E9F0B26A9C40C79C5 |
| Business Licenses | data/00_origin/business_licenses/business_licenses.csv · CSV, UTF-8(선택 BOM) · [Chicago Open Data](https://data.cityofchicago.org/api/v3/views/r5kz-chrr/export.csv?accessType=DOWNLOAD) | 1,212,132 × 37 | 2026-11-19 10:46:10Z | data/01_bronze/business_licenses/business_licenses.parquet | 1,212,132 × 39 | _SRC_FILE, _LOAD_DTM | 783354424BEBE4D367BD3A0F9CDC63A846FAE28D50580B9CCF89590D10CC61BB | E80EFD98FE1319A18B54DD73122D1C28EF29855CEB8F7665F0CD8907469AACC8 |
| Community Areas | data/00_origin/community_areas/community_areas.geojson · GeoJSON FeatureCollection, UTF-8 · [Chicago Open Data](https://data.cityofchicago.org/api/v3/views/igwz-8jzy/query.geojson?accessType=DOWNLOAD) | 77 × 11¹ | 2026-11-19 10:46:10Z | data/01_bronze/community_areas/community_areas.parquet | 77 × 13 | _SRC_FILE, _LOAD_DTM | C4B9C42ADC19BACA0A9C6EE3E84B302D40073D3AD99EE3D8B101D5D8217B0D16 | A39C876E6FD6A860A9EC22384380EEA280E0821D407B95A261AC110AC62A7223 |

¹ Community Areas의 원천 11개 필드는 Feature의 type, geometry, properties 속성 9개를 합산한 수다. Bronze도 이 11개에 기술 컬럼 2개가 추가된다. 모든 Bronze 필드의 Parquet 타입은 string이다. geometry는 좌표 배열을 포함한 JSON 문자열로 보존한다.

## 실행 시각과 성공 근거

logs/pipeline_runs.csv의 최신 Bronze 실행은 run ID 12943ef17a6946b1a77505af159356f2다. 세 데이터셋 모두 SUCCESS이며 입력 행과 출력 행이 일치한다. Parquet 내부 적재 시각은 해당 run의 첫 시작 시각과 일치한다.

| 데이터셋 | 로그 시작(UTC) | 로그 종료(UTC) | 입력 행 | 출력 행 | 상태 |
| --- | --- | --- | ---: | ---: | --- |
| food_inspections | 2026-11-19 10:46:10Z | 2026-11-19 10:46:25Z | 318,552 | 318,552 | SUCCESS |
| business_licenses | 2026-11-19 10:46:25Z | 2026-11-19 10:47:36Z | 1,212,132 | 1,212,132 | SUCCESS |
| community_areas | 2026-11-19 10:47:36Z | 2026-11-19 10:47:36Z | 77 | 77 | SUCCESS |

적재 코드는 main()에서 run ID와 공통 UTC 시각을 만든 뒤 데이터셋별 load_source()를 호출한다. verify_source()는 원천 sidecar SHA-256을 확인한다. verify_output()은 행 수, 컬럼 순서와 string 타입, 원천값·행 순서, 기술 컬럼을 확인한다. 검증을 통과한 임시 Parquet만 정식 경로로 교체하며 log_run()은 요약 CSV를 기록한다.

코드에는 log_run_details()도 있다. 일반 실행이면 상세 레코드는 logs/bronze_run_details.jsonl에 기록되어 원천 절대 경로와 URL, 출력 경로, 해시, 행 수, 성공 여부, 실패 오류를 남긴다. 현재 프로젝트의 logs/에는 이 JSONL이 없다. 따라서 현재 경로 적재 기록의 상세 provenance는 CSV 실행 로그, 현재 Parquet의 기술 컬럼, manifest 및 이번에 직접 계산한 파일 해시를 교차 확인해 작성했다. 로그에 없는 과거 시각이나 상세 레코드는 만들지 않았다.

## 임시 검증 실행

2026-11-20 임시 검증 run f8d69cb821d3482c9a79f9f6f6ce240f의 상세 JSONL과 요약 CSV는 프로젝트 외부 C:\mlo-03-p2-team2-directory-migration-20261120\verification_logs\에서 확인했다. 공통 적재 시각은 2026-11-20T01:58:26Z다. 세 데이터셋 모두 원천·출력 행 수가 일치하고 상태가 SUCCESS다. 출력은 C:\mlo-03-p2-team2-directory-migration-20261120\verification_bronze\ 아래에 기록되었다. 이 임시 검증은 현재 data/01_bronze/ 파일을 만든 실행과 구분한다.

## 재현 방법

프로젝트 루트에서 python -m src.bronze.load_bronze를 실행하면 paths.py에 설정된 Origin을 읽고 data/01_bronze/에 데이터셋별 Parquet을 full refresh한다. 이 명령은 기존 출력에 쓰므로 실행 전 목적 경로와 로그 설정을 확인한다. Origin 원본은 읽기 전용으로 취급한다.
