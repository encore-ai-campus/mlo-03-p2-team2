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
| AS-IS | 위반 코드와 설명이 한 셀에 섞여 있고, 점검 한 건에 같은 면허번호의 인허가 이력이 여러 건 연결될 수 있습니다. 좌표 결측과 경계 밖 위치도 별도로 처리해야 합니다. |
| 목표 | 출처·행 단위·품질 사유를 추적할 수 있는 분석 데이터를 만들고, 예측 기준일 이전의 입력과 이후의 정답을 구분하는 학습용 데이터 계약을 정의합니다. |

[시카고시 식품위생 점검](https://data.cityofchicago.org/d/4ijn-s7e5) · [시카고시 사업체 인허가](https://data.cityofchicago.org/d/r5kz-chrr) · [시카고시 지역 경계](https://data.cityofchicago.org/d/igwz-8jzy) · [AS-IS 상세](https://github.com/encore-ai-campus/mlo-03-p2-team2/wiki/Project-Details#원천과-as-is)

## 3. 기술 스택

![Python 3.14](https://img.shields.io/badge/Python-3.14-3776AB?logo=python&logoColor=white) ![Apache Parquet](https://img.shields.io/badge/Apache-Parquet-168B89) ![pytest](https://img.shields.io/badge/Tests-pytest-0A9EDC?logo=pytest&logoColor=white) ![draw.io](https://img.shields.io/badge/ERD-draw.io-F08705?logo=diagramsdotnet&logoColor=white)

| 용도 | 기술 |
| --- | --- |
| 처리·저장 | Python, pandas, PyArrow, Apache Parquet |
| 공간 연산 | Shapely, GeoJSON |
| 검증·협업 | pytest, SHA-256, GitHub PR·Wiki, draw.io |

## 4. WBS

**11월 20일 금요일**에 공용 원천과 단계 구조를 맞추고, 01~05 관점별 파이프라인과 검증을 반영했습니다. [담당·작업·커밋별 WBS](https://github.com/encore-ai-campus/mlo-03-p2-team2/wiki/Project-Details#wbs)

**팀 통합은 역할 분담까지 마쳤습니다.** 공용 Bronze·Silver·Gold 통합, Gold 중복 차원 정리, AI-Ready 데이터 제작은 작업 대기입니다. [팀 통합 작업](https://github.com/encore-ai-campus/mlo-03-p2-team2/wiki/Project-Details#팀-통합-작업)

## 5. 요구사항 명세

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

## 7. 주요 프로시저

**목표 흐름**　Origin → Bronze → 표준화·품질 검증 → Silver → Gold → AI-Ready

관점별 파이프라인은 공용 원천에서 Gold까지 처리 결과를 만듭니다. 팀 통합에서는 단계별 처리를 맞추고, 이후 AI-Ready 데이터의 입력 시점과 정답 기간을 정의할 예정입니다. [단계별 입력·출력·검증](https://github.com/encore-ai-campus/mlo-03-p2-team2/wiki/Project-Details#주요-프로시저)

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
