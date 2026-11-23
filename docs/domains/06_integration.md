# 공용 Bronze·Silver 통합

팀 Git 원천의 체크섬을 확인하고 점검, 인허가, 지역 경계를 각각 한 테이블로 적재한다. 팀 일괄 실행은 게시된 `06_integration` Bronze·Silver를 공용 입력으로 사용해 01~05 Gold와 AI-ready를 생성한다. 관점별 기존 스냅샷은 결과를 비교할 때 사용한다.

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

게시 매니페스트는 `data/02_silver/06_integration/snapshot_manifest.json`이다. 동일한 결과는 다시 게시할 수 있으며, 경로에 다른 내용이 있으면 게시를 중단한다. 100 MB를 초과한 인허가 Bronze와 점검 Silver는 분할본을 공유하고, 일괄 코드에서 실행 경로에 복원한다.

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

게시 스냅샷을 사용하는 일괄 실행이다. 저장소 루트에서 실행하며, 이전 실행과 별도로 비교할 때는 새 `--output` 경로를 지정한다.

```powershell
python -m src.domains.06_integration.run_pipeline
python -m src.domains.06_integration.run_pipeline --verify
python -m pytest -q
```

| 관점 | 공용 입력 | 생성 결과 |
| --- | --- | --- |
| 01 점검 | 점검 Silver와 품질 플래그 | 적격 점검, 점검 Fact·차원, 성과 집계와 질의용 AI-ready |
| 02 위반 | 점검 Bronze와 원천 해시 | 위반 파싱·격리·대사, 위반 Fact·차원과 05 공유용 코드·관측 상태 |
| 03 재점검 | 점검 Silver와 이번 실행의 02 파싱 결과 | 점검 이력, 재점검·반복 위반 Gold |
| 04 인허가 | 인허가·점검 Silver | 인허가 이벤트와 점검일의 기간 매칭. 문자열 키는 Arrow `string`과 `large_string`을 모두 지원 |
| 05 지역 | 점검·지역 경계 Silver, 품질 플래그, 이번 실행의 02 코드·관측 상태 | 점검별 지역 배정, 지역·기간 집계와 질의용 AI-ready |
| 팀 학습용 | 점검 Silver, 이번 실행의 02 위반·격리와 03 반복 위반 Gold | 점검 직전 불합격, 동일 위반 재관측 Parquet 2종 |

실행 결과는 `reports/runs/06_integration/end-to-end/` 아래에 저장한다. 관점별 산출물과 공용 Gold의 `dimensions/`, `facts/` 경로는 기존 구조를 따른다. 팀 학습용 Parquet은 `data/ai_ready/inspection_training/<release_id>/`에 생성되며, 각 단계 경로는 실행 폴더 기준이다. [일괄 실행 코드](../../src/domains/06_integration/run_pipeline.py) · [결과 비교 및 검증 코드](../../src/domains/06_integration/validate_pipeline.py)

실행 폴더의 `verification.json`에 사용한 원천 해시, 비교한 테이블의 행 수, 실행 결과 파일의 SHA-256이 기록된다. 비교에서는 행과 컬럼의 값을 대조하고, 실행 버전에 따라 달라지는 Parquet 메타데이터는 별도로 식별한다. 학습 데이터는 기존 릴리스의 분할별 행 수와 정답 분포도 대조한다. [팀 스냅샷 검증 기록](../../reports/quality/team_integration_verification.json)
