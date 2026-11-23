# 공용 Bronze·Silver 통합

워크트리 `C:\mlo-03-p2-team2`, 브랜치 `codex/06-integration-structure`.

팀 Git 원천의 체크섬을 확인하고 임시 경로에 CSV를 복원한다. 점검, 인허가, 지역 경계를 각자 한 테이블로 적재한다. 통합 결과는 새 실행 경로에 게시하며 기존 01~05 파이프라인의 입력 경로 전환은 후속 작업이다.

| 원천 | 한 행의 의미 | Silver 키 | 스냅샷 행 수 |
| --- | --- | --- | ---: |
| 식품위생 점검 | 점검 1건 | `inspection_key` | 318,627 |
| 사업 인허가 | 인허가 이력 1건 | `license_event_key` | 1,212,132 |
| 지역 경계 | 현재 스냅샷의 지역 1곳 | `community_area_num` | 77 |

- Bronze는 원천 CSV 문자열과 GeoJSON 경계를 보존한다. `_SRC_FILE`, `_LOAD_DTM`을 기록하고 각 원천의 논리 레코드에 1부터 순번을 붙인다. 적재 뒤 원천 값, 순서, 키 중복 및 행 수를 대조한다.
- Silver는 기존 01 점검 표준화와 04 인허가 사전 변환을 사용한다. 지역 번호는 정수로 저장하고, 지역명 양끝 공백을 제거하며 경계 JSON은 보존한다. Silver 세 테이블에서 원천 순번을 유지하고 키 유일성과 행 수를 검사한다.
- 점검 품질 플래그는 [inspection_rule_flags.parquet](../../data/02_silver/06_integration/inspection_rule_flags.parquet)에 행별로 기록한다. `verification.json`에는 원천·단계별 체크섬과 점검 품질 플래그 수가 들어간다. 인허가 기간 대조 및 지역 배정 품질은 해당 관점에서 검증한다.

## 실행

저장소 루트에서 Python 3.14 환경으로 실행한다. 01 표준화에 필요한 pandas와 04에 필요한 PyYAML 등은 기존 의존성 목록으로 설치한다.

```powershell
python -m pip install -r src/domains/05_geospatial/requirements.txt -r src/domains/04_license/requirements.txt
python -m src.domains.06_integration.build --output reports/runs/06_integration/shared-bronze-silver
```

출력에는 `data/01_bronze/06_integration/`과 `data/02_silver/06_integration/`이 생긴다. 실행 중 생성한 점검 품질 플래그는 배포 시 Silver 폴더에 함께 둔다. 다시 실행할 때는 새 출력 경로를 지정한다. 동일 원천의 Bronze 원천 값과 순서는 같고 적재 시각은 실행별로 기록된다.

## 팀 공유 경로를 정할 때

| 방식 | 예시 | 운영 방식 |
| --- | --- | --- |
| 고정 경로 | `data/02_silver/06_integration/food_inspections.parquet` | 팀원이 항상 같은 경로를 읽는다. 배포 시 기존 버전을 보관하고 체크섬이 담긴 게시 기록을 남긴다. |
| 버전별 경로 | `data/02_silver/06_integration/<snapshot_id>/food_inspections.parquet` | 분석별로 사용한 파일 버전을 고정할 수 있다. 최신 버전이 필요하면 매니페스트에 게시된 버전을 읽는다. |
| 검증용 실행 경로 | `reports/runs/06_integration/<run_id>/` | 로컬에서 서로의 경로를 덮어쓰지 않고 검증한다. |

Bronze와 Silver를 함께 배포할 때는 한 매니페스트에 각 데이터셋의 원천 SHA-256, 단계별 경로와 체크섬을 기록한다. 공용 경로 적용 전에 관점별 입력 규격과 기존 집계 비교 결과를 확인한다.

발표 기준으로 원천 스냅샷 하나를 고정하고 **고정 경로**를 사용한다. 팀원은 같은 경로를 실행 인자로 쓰고, 매니페스트로 발표에 사용한 파일을 확인한다. 로컬에서 검증할 때는 실행 경로를 계속 사용한다.

```powershell
# 검증을 마친 실행 결과를 고정 경로에 게시한다.
python -m src.domains.06_integration.publish --run reports/runs/06_integration/shared-bronze-silver
# 공유 파일을 받은 뒤 분할 파일을 복원하고 전체 체크섬을 검증한다.
python -m src.domains.06_integration.publish --restore
```

게시 매니페스트는 `data/02_silver/06_integration/snapshot_manifest.json`이다. 동일한 결과는 다시 게시할 수 있으며, 경로에 다른 내용이 있으면 게시를 중단한다. 100 MB를 초과한 인허가 Bronze와 점검 Silver는 분할본을 공유하고, 복원본은 로컬에서 사용한다. 소비자 경로 적용 시 02 원천 해시 메타데이터와 04 점검 키 타입은 아래의 관점별 규격을 확인한다.

## 요구사항별 검증

배포 파일을 복원한 뒤 저장소 루트에서 실행한다.

```powershell
python -m src.bronze.check_integration_bronze
python -m src.silver.validate_integration_silver
```

| ID | 요구사항 | 검증 코드 |
| --- | --- | --- |
| B-01 | 원천과 Bronze의 논리 행 수, 순서 및 원문 값 확인 | [check_integration_bronze.py](../../src/bronze/check_integration_bronze.py) |
| B-02 | 원천 파일명 `_SRC_FILE`, UTC 적재 시각 `_LOAD_DTM`, 원천 순번 확인 | [check_integration_bronze.py](../../src/bronze/check_integration_bronze.py) |
| S-01 | Silver 컬럼명을 01 표준 매핑, 04 사전, 지역 경계 규칙과 대조 | [validate_integration_silver.py](../../src/silver/validate_integration_silver.py) |
| S-02 | 점검·인허가 달력 날짜의 Parquet `date32` 검증. 문서 표기는 `YYYY-MM-DD` | [validate_integration_silver.py](../../src/silver/validate_integration_silver.py) |
| S-03 | 관점별 기본 키 중복 검사와 점검의 완전 중복·키 충돌 플래그 집계 | [validate_integration_silver.py](../../src/silver/validate_integration_silver.py) |

Silver는 원천 행을 모두 보존한다. 점검 품질 플래그는 원천 순번으로 확인한다. 같은 면허번호의 여러 발급·갱신 기록은 인허가 이력으로 보존한다. 이전 검증 산출물은 실행 당시 경로를 유지한다.

## 관점별 비교 실행

경로 개편 전 검증 산출물은 로컬 `reports/runs/06_integration/consumer-check/`에서 확인할 수 있다. 비교 시 Parquet 메타데이터의 실행·입력 지문 차이는 제외하고 컬럼과 값을 대조했다.

| 관점 | 공급한 입력 | 비교 결과 |
| --- | --- | --- |
| 01 | 공용 점검 Silver와 품질 플래그를 기존 파일명으로 배치 | Gold Parquet 7개 및 집계 CSV 10개 일치 |
| 02 | 공용 점검 Bronze를 02 파일명으로 배치하고 원천 해시를 `origin_sha256` 필드에도 제공 | 위반 Silver, 정상·격리, Gold 차원·Fact·mart 일치. 정상·Fact·mart 각 1,029,281행 |
| 03 | 공용 점검 Silver와 검증 매니페스트, 기존 02 위반 결과 | 점검 이력·재점검·반복 위반 Parquet 일치. HTML은 점검 Silver 출처 표시만 변경 |
| 04 | 공용 인허가 Silver와 공용 점검 Silver의 기존 04 규격 5개 컬럼 | 원본 공용 점검 파일은 `inspection_key`의 `large_string` 타입이 기존 `string`과 달라 검사 실패. 임시 호환 입력으로 전체 검사 23개 통과, Fact 2개·차원 3개 일치 |
| 05 | 공용 점검 Silver, 기존 05 공간 배정 및 02 공유 파일 | Gold 집계 3개 일치. 공용 경계의 지역 키, 지역명, 원천 순번, 도형 77개가 05와 일치. Gold 실행 시 Windows 파일 핸들은 검증 프로세스에서 정리 |
