# Chicago Food Safety Data Quality & AI-Ready Platform

시카고시 식품위생 점검, 사업체 인허가, 커뮤니티 지역 경계를 연결해 점검 위험을 분석합니다. **AI가 사용할 수 있는 데이터 구축**이 프로젝트의 최종 목표입니다.

[프로젝트 상세 Wiki](https://github.com/encore-ai-campus/mlo-03-p2-team2/wiki/Project-Details) · [저장소 구조](https://github.com/encore-ai-campus/mlo-03-p2-team2/wiki/Repository-Structure) · [로컬 실행 환경](docs/project_setup_and_sharing.md)

## 1. 팀 소개

**Encore AI Campus MLO 03 · Team 2**

| 관점 | 팀원 | GitHub |
| --- | --- | --- |
| 01 점검 성과 | 이하영 | [@coffeewoouuu](https://github.com/coffeewoouuu) |
| 02 위반 유형 | 이자연 | [@naturedevworks](https://github.com/naturedevworks) |
| 03 반복 위반·재검사 | 김한울 | [@hannyeee](https://github.com/hannyeee) |
| 04 사업체 인허가 | 노진산 | [@jinsan02](https://github.com/jinsan02) |
| 05 지역 분석 | 오정민 | [@OZAM0415](https://github.com/OZAM0415) |

## 2. 프로젝트 개요

| 구분 | 내용 |
| --- | --- |
| 원천 | 식품위생 점검 **318,627행**, 인허가 **1,212,132행**, 커뮤니티 지역 **77개** |
| 목표 | 출처·행 단위·품질 사유를 추적할 수 있는 분석 데이터를 만들고, 예측 기준일 이전의 입력과 이후의 정답을 구분하는 학습용 데이터 계약을 정의합니다. |

### AS-IS · 실제 원천을 연결할 때 생기는 문제

점검 `Inspection ID=2646979`와 인허가 이력 `LICENSE ID=3031292`의 실제 값을 예로 들었습니다. 지리 경계는 별도의 GeoJSON 예시입니다.

| 차이 | 실제 원천 컬럼과 값 | 표준화와 연결 기준 |
| --- | --- | --- |
| 같은 면허번호에 서로 다른 컬럼명 | 점검 `License #='2398495'` ↔ 인허가 `LICENSE NUMBER='2398495'`. 점검에는 `License #='0'`인 행도 있습니다. | 두 컬럼을 문자열 `license_number_key`로 통일합니다. `0`처럼 연결에 사용할 수 없는 점검 값은 `null`로 처리합니다. |
| 점검과 인허가 이력의 행 단위 | 점검 `Inspection Date='11/18/2026'`는 사건 날짜입니다. 인허가 `LICENSE TERM START DATE='07/16/2025'`와 `LICENSE TERM EXPIRATION DATE='07/15/2027'`은 한 이력의 유효기간입니다. 한 면허에 발급·갱신 이력이 여러 건 있을 수 있습니다. | 날짜를 `date32`로 표준화합니다. 면허번호가 같고 점검일이 기록된 기간에 포함되는 후보를 찾습니다. 후보가 하나일 때만 이력을 확정해 점검 1건당 1행을 유지합니다. |
| 점 좌표와 지역 경계의 구조 | 점검 CSV는 `Longitude=-87.62249083278`, `Latitude=41.89245290794`처럼 컬럼 두 개로 위치를 제공합니다. 지역 GeoJSON은 `properties.area_numbe`와 `geometry.type='MultiPolygon'`으로 경계를 제공합니다. | 경도·위도를 수치형으로 변환하고 `[경도, 위도]` 순서로 지역 경계와 교차하는지 검사합니다. 좌표가 없거나 경계 밖에 있으면 이유를 남깁니다. |
| 결과 라벨과 위반 원문의 행 단위 | `Results='Fail'`은 점검의 결과입니다. `Violations`는 `50. HOT & COLD WATER AVAILABLE…`처럼 코드·설명·메모가 섞인 텍스트이며 한 점검에 위반이 여러 개 들어갈 수 있습니다. | 결과는 `result_cd='FAIL'`로 변환합니다. 위반은 별도 상세 테이블로 구조화하고, 점검 건수를 셀 때는 점검 단위로 집계합니다. |

[시카고시 식품위생 점검](https://data.cityofchicago.org/d/4ijn-s7e5) · [시카고시 사업체 인허가](https://data.cityofchicago.org/d/r5kz-chrr) · [시카고시 지역 경계](https://data.cityofchicago.org/d/igwz-8jzy) · [원천 차이와 예외 처리](https://github.com/encore-ai-campus/mlo-03-p2-team2/wiki/Project-Details#원천과-as-is)

## 3. 기술 스택

| 용도 | 기술 |
| --- | --- |
| 처리·저장 | ![Python 3.14](https://img.shields.io/badge/Python-3.14-3776AB?logo=python&logoColor=white) ![Apache Parquet](https://img.shields.io/badge/Apache-Parquet-168B89) · pandas · PyArrow |
| 공간 연산 | Shapely, GeoJSON |
| 검증·협업 | ![pytest](https://img.shields.io/badge/Tests-pytest-0A9EDC?logo=pytest&logoColor=white) ![draw.io](https://img.shields.io/badge/ERD-draw.io-F08705?logo=diagramsdotnet&logoColor=white) · SHA-256 · GitHub PR·Wiki |

## 4. WBS

**2026-11-20 금요일 작업 기록**입니다. 시간은 커밋·병합 기록의 한국 시간(KST)입니다.

| ID | 담당 | 작업 | 커밋·병합 기록 |
| --- | --- | --- | --- |
| 1.0 | 공용 기반 | 원천 프로파일링, Bronze 적재, Silver 표준안, 공용 폴더와 체크섬 | 09:49 [Bronze 적재](https://github.com/encore-ai-campus/mlo-03-p2-team2/commit/243ad0d) · 16:45 [공용 원천 구조](https://github.com/encore-ai-campus/mlo-03-p2-team2/commit/69d1105) |
| 1.1 | 이하영 · 01 | 점검 성과 파이프라인과 집계, 팀 경로 정리 | 16:41 [파이프라인](https://github.com/encore-ai-campus/mlo-03-p2-team2/commit/0e1cd9b) · 17:44 [공용 경로 적용](https://github.com/encore-ai-campus/mlo-03-p2-team2/commit/7080986) |
| 1.2 | 이자연 · 02 | 위반 원문 구조화·격리 대사, 위반 Fact·Dim과 스냅샷 | 17:59 [파이프라인 PR #4](https://github.com/encore-ai-campus/mlo-03-p2-team2/pull/4) · 18:18 [스냅샷 PR #5](https://github.com/encore-ai-campus/mlo-03-p2-team2/pull/5) |
| 1.3 | 김한울 · 03 | 반복 위반과 재검사 마트, 후속 점검 기간 검증 | 12:25 [재검사 기간 규칙](https://github.com/encore-ai-campus/mlo-03-p2-team2/commit/5593942) · 17:19 [PR #2](https://github.com/encore-ai-campus/mlo-03-p2-team2/pull/2) |
| 1.4 | 노진산 · 04 | 인허가 기간 매칭, 단계별 검증, Parquet와 체크섬 | 16:52 [산출물 반영](https://github.com/encore-ai-campus/mlo-03-p2-team2/commit/5e5e779) · 16:58 [PR #1](https://github.com/encore-ai-campus/mlo-03-p2-team2/pull/1) |
| 1.5 | 오정민 · 05 | 공간 배정, 기간별 지역 집계, 공용 입력 계약과 검증 | 16:36 [공간 처리](https://github.com/encore-ai-campus/mlo-03-p2-team2/commit/08e03e0) · 17:54 [PR #3](https://github.com/encore-ai-campus/mlo-03-p2-team2/pull/3) |

**11월 23일 진행 상태**　공용 Bronze·Silver 스냅샷을 `main`에 배포했습니다. 관점별 입력 경로 전환, 팀 Gold 통합·중복 차원 정리, 팀 공용 AI-Ready 데이터 제작은 역할 분담 완료 상태입니다. [공용 Bronze·Silver PR #11](https://github.com/encore-ai-campus/mlo-03-p2-team2/pull/11) · [팀 통합 작업](https://github.com/encore-ai-campus/mlo-03-p2-team2/wiki/Project-Details#팀-통합-작업)

## 5. 요구사항 명세

✅는 표에 명시한 검증 범위에서 통과한 결과입니다. ⏳는 역할 분담을 마친 후속 작업입니다.

| ID | 단계 | 요구사항 | 검증방법 | 결과 |
| --- | --- | --- | --- | --- |
| O-01 | Origin | 공용 원천은 분할 조각과 복원본의 SHA-256이 기록과 일치해야 합니다. | [`restore_origin.py`](src/ingestion/restore_origin.py)에서 체크섬 목록을 대조 | ✅ 원천 6개·분할 조각 4개 일치 |
| B-01 | Bronze | 원천의 논리 레코드 수가 Bronze 백업 후에도 원천별로 같아야 합니다. 원천 컬럼·값·행 순서를 보존합니다. | [`validate_bronze.py`](src/domains/04_license/validate_bronze.py)에서 원천 레코드와 Parquet의 스키마·값·행 순서를 대조 | ✅ 04 점검 318,627행·인허가 1,212,132행 일치 |
| B-02 | Bronze | 원천과 Bronze 파일의 SHA-256, 행 수, 적재 기록을 남깁니다. | [`validate_bronze.py`](src/domains/04_license/validate_bronze.py)에서 `ingestion_manifest.json`과 실제 파일을 대조 | ✅ 04 매니페스트 대조 통과 |
| S-01 | 표준화·Silver | 면허번호는 문자열, 점검일과 인허가 기간은 `date32`, 표준 결과는 코드값으로 저장합니다. | [`validate_silver.py`](src/domains/04_license/validate_silver.py)에서 데이터 사전의 스키마와 재계산한 값을 대조 | ✅ 04 타입·변환값 대조 통과 |
| S-02 | Silver | 기본 테이블은 Bronze의 행 수와 `source_row_num`을 보존해야 합니다. | [`validate_silver.py`](src/domains/04_license/validate_silver.py)에서 원천별 행 수와 순번을 대조 | ✅ 04 두 기본 테이블 행 수 일치 |
| S-03 | 공용 Bronze·Silver | 점검·인허가·지역 경계 3종의 행 수를 원천부터 Silver까지 대조하고 배포본을 복원할 수 있어야 합니다. | 공용 [`build.py`](src/domains/integration/build.py)에서 행 수·키 대조, [`publish.py`](src/domains/integration/publish.py)에서 복원본 크기와 SHA-256 대조 | ✅ PR #11의 3종 행 수·배포 산출물 7개 대사 확인 |
| Q-01 | 품질 검증 | 결측·파싱 실패·기간 역전은 예외로 세고, 변환 전후 품질 결과를 재현할 수 있어야 합니다. | [`validate_quality.py`](src/domains/04_license/validate_quality.py)에서 Bronze·Silver 대조 보고서를 다시 계산 | ✅ 04 품질 검증 3/3 |
| Q-02 | 품질 검증 | 위반 후보가 정상과 격리로 모두 설명되고 원천 점검으로 추적돼야 합니다. | [`reconciliation.py`](src/domains/02_violation/reconciliation.py)와 [02 위반 유형 스냅샷 보고서](reports/02_violation/README.md)에서 정상·격리 합계를 대조 | ✅ 02 보고서에서 1,029,281 + 1,792 = 1,031,073조각 대사 확인 |
| G-01 | Gold | Fact와 Dim의 기본키에는 중복·공란이 없어야 하고, 필수 참조 키는 해당 차원에 존재해야 합니다. | [`validate_gold.py`](src/domains/04_license/validate_gold.py)에서 PK·FK와 팩트의 원천 키·순서·행 수를 검증 | ✅ 04 팩트·차원 키 검증 통과 |
| G-02 | Gold | 같은 면허번호에서 `시작일 ≤ 점검일 ≤ 만료일`을 만족하는 후보를 세고, 단일 후보만 확정합니다. | [`validate_gold.py`](src/domains/04_license/validate_gold.py)에서 Silver로 Fact 값·후보 수·매칭 상태를 재계산 | ✅ 04 기간 매칭 검증 통과 |
| T-01 | 관점별 입력 전환·Gold 통합 | 관점별 입력 타입과 메타데이터를 공용 규격에 맞추고 팀 Gold의 조인 전후 행 수와 키를 대조합니다. | 공용 스냅샷과 기존 결과를 [관점별 비교 기준](src/domains/integration/README.md#관점별-비교-실행)으로 대조하고 전환 후 재검증 예정 | ⏳ 역할 분담 완료 |
| G-03 | Gold 공용 차원 | 의미·키·행 단위가 같은 차원을 공용화하고 Fact의 참조 키를 재검증합니다. | 공용 차원 대사 코드 예정 | ⏳ 역할 분담 완료 |
| A-01 | AI-Ready | 기준일 이전 입력과 이후 정답을 분리하고 시간순 학습·검증 구간을 정의합니다. | 입력 시점·정답 관찰 기간·시간 분할 검증 코드 예정 | ⏳ 역할 분담 완료 |

### 관점별 사용자와 분석 질문

| 관점 | 사용자와 분석 질문 |
| --- | --- |
| 01 점검 성과 | 점검 배정 담당자 · 어떤 유형에서 다음 점검의 불합격 위험이 높은가? |
| 02 위반 유형 | 교육 기획자 · 다음 점검에서 집중해서 살필 위반 유형은 무엇인가? |
| 03 반복·재검사 | 재점검 담당자 · 직전 문제가 다시 관측되거나 후속 점검이 불합격할 위험은 어느 정도인가? |
| 04 인허가 | 인허가 분석가 · 점검 당시 사업장을 어느 이력과 연결할 수 있는가? |
| 05 지역 분석 | 지역 운영 담당자 · 다음 기간에 우선적으로 살필 지역은 어디인가? |

[페르소나·시나리오·필요 데이터·수용 기준](https://github.com/encore-ai-campus/mlo-03-p2-team2/wiki/Project-Details#요구사항-명세)

## 6. ERD

아래는 **04번에서 검증한 Gold 스타 스키마**입니다. draw.io 두 번째 탭에서 01~05 공용 모델 검토안을 볼 수 있습니다.

![04번 Gold 스타 스키마. 점검 매칭과 인허가 이력 Fact가 면허·사업장·날짜 차원을 참조합니다.](docs/chicago_food_star_schema.png)

[편집 가능한 draw.io](docs/chicago_food_star_schema.drawio) · [테이블의 한 행과 측정값](https://github.com/encore-ai-campus/mlo-03-p2-team2/wiki/Project-Details#erd와-측정값)

### Fact·마트의 한 행과 측정값

| 관점 | Fact·마트 | 한 행의 의미 | 측정값의 계산 근거 |
| --- | --- | --- | --- |
| 01 | `fact_inspection` | 점검 1건 (`inspection_key`) | 표준 결과에서 평가·불합격 건수를 집계합니다. 불합격률은 `불합격 건수 ÷ 평가 완료 건수`입니다. |
| 02 | `fact_inspection_violation` | 정상 처리한 위반 조각 1개 (`source_row_num` × `item_sequence_num`) | 파싱과 품질 조건을 통과한 위반 조각을 셉니다. 한 점검에 여러 조각이 들어갈 수 있습니다. |
| 03 | `repeat_violation_mart` | 기준 점검 × 위반 코드 버전 × 코드 | 비교 가능한 다음 점검에서 같은 코드가 다시 관측됐는지 계산합니다. |
| 03 | `inspection_reinspection_mart` | 기준 불합격 점검 1건 | 조건에 맞는 후속 점검의 연결 여부와 기준 점검부터의 경과일, 결과를 기록합니다. |
| 04 | `fact_inspection_license_match` | 점검 1건 (`inspection_key`) | `candidate_count_num`은 면허번호와 유효기간이 모두 맞는 인허가 이력 수입니다. |
| 04 | `fact_license_event` | 인허가 이력 1건 (`license_event_key`) | 발급·갱신 등의 이력을 보존합니다. 이력 건수는 해당 행 수입니다. |
| 05 | `inspection_area_period` | 기간 단위 × 기간 시작일 × 지역 또는 미배정 사유 | 점검 좌표를 지역에 배정한 뒤 기간별 점검·평가 완료·불합격 건수를 집계합니다. |

04번의 두 Fact는 `dim_license`, `dim_establishment`, `dim_date`를 참조합니다. 날짜 차원은 점검 Fact에서 **점검일**, 인허가 Fact에서 **발급일**입니다. 팀 전체에서 반복 정의한 차원의 공용화는 역할 분담을 마친 상태입니다.

## 7. 주요 프로시저

**목표 흐름**　Origin → Bronze → Silver(표준화·품질 검증) → Gold → AI-Ready

| 순서 | 입력 → 출력 | 실행 코드 예시 |
| --- | --- | --- |
| Origin | 공용 CSV 조각 → 복원 CSV. GeoJSON·설명 JSON과 함께 체크섬 확인 | [`restore_origin.py`](src/ingestion/restore_origin.py) |
| Bronze | 원천 CSV → 원천 값·순서·`source_row_num`을 보존한 Parquet | 04 [`01_bronze.py`](src/domains/04_license/01_bronze.py) |
| Silver 표준화 | Bronze → 식별자·날짜·결과 코드를 표준화한 Parquet | 04 [`02_normalize.py`](src/domains/04_license/02_normalize.py) |
| 품질 검증 | Bronze와 Silver → 결측·파싱·기간 예외의 전후 대조 보고서 | 04 [`03_quality.py`](src/domains/04_license/03_quality.py) |
| Gold | 검증한 Silver → Fact·Dim·마트. 04번은 점검일 기준 인허가 후보 계산 | 04 [`04_modeling.py`](src/domains/04_license/04_modeling.py) |
| AI-Ready · 계획 | 공용 Gold → 기준일 이전 입력과 이후 정답을 나눈 학습 데이터 | 역할 분담 완료 |

팀 공용 Bronze·Silver의 생성과 배포 검증은 [`build.py`](src/domains/integration/build.py)와 [`publish.py`](src/domains/integration/publish.py)를 사용합니다. 04번 전체 실행과 재검증은 [`run_pipeline.py`](src/domains/04_license/run_pipeline.py)를 사용합니다. [재현 명령과 예외 처리](https://github.com/encore-ai-campus/mlo-03-p2-team2/wiki/Project-Details#시연)

## 8. 수행 결과

| 단계 | 전후 비교 |
| --- | --- |
| Origin → Bronze | 04 점검 318,627행과 인허가 1,212,132행을 그대로 보존하고 원천 순번 추가 |
| Bronze → Silver | 행 수 유지. 예시 점검일 `11/18/2026` → `2026-11-18`, 결과 `Fail` → `FAIL` |
| Silver → Gold | 04 점검 318,627건 중 **232,383건**의 기간 후보가 1개, **1,401건**은 여러 개, **84,843건**은 0개 |

04번 단계 검증 **39개 통과**. [검증 보고서](reports/04_license/README.md) · [관점별 결과](https://github.com/encore-ai-campus/mlo-03-p2-team2/wiki/Project-Details#수행-결과) · [실제 점검 1건 시연](https://github.com/encore-ai-campus/mlo-03-p2-team2/wiki/Project-Details#시연)

## 9. 한 줄 회고

| 팀원 | 한 줄 회고 |
| --- | --- |
| 이하영 | |
| 이자연 | |
| 김한울 | |
| 노진산 | |
| 오정민 | |
