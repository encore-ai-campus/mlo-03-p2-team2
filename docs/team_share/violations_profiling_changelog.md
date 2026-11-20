# Food Inspections Violations 프로파일링 기록

## 작업 개요

- 작업일: 2026-11-20
- 브랜치: feature/violations-profiling
- 기준 커밋: 25b70f168abdd36c3d2e0ddccd90f70f54340b05
- 범위: Food Inspections의 Violations 원문을 읽어 구조와 파싱 가능성을 측정했다.
- 코드와 결과: src/profiling/profile_violations.py, reports/profiling/violations_profile.json

## 입력 데이터와 방법

Origin 원천은 data/00_origin/food_inspections/food_inspections.csv이며, 원천 파일 크기는 356,846,515 byte다. 분석은 Bronze 파일 data/01_bronze/food_inspections/food_inspections.parquet의 Violations 컬럼에서 수행했다. Bronze Parquet은 318,552행, 19열이고 해당 컬럼 타입은 string이다. 스크립트는 10,000행씩 배치로 읽고 원천과 Bronze 파일의 SHA-256을 결과 JSON에 기록한다. Origin·Bronze에는 쓰기 작업을 하지 않았다.

원문 셀은 공란 유형별로 분류했다. 비공란 값은 공백이 양쪽에 있는 파이프 구분자 패턴을 기준으로 후보 조각으로 나눴다. 각 조각은 숫자 뒤에 선택적인 대문자 하나가 올 수 있는 코드, 마침표, 설명 본문 형식인지 확인했다. 설명 뒤에 Comments:가 나타나는지와 그 앞에 표준 구분자 하이픈이 있는지도 별도로 셌다. 원문은 파싱 결과로 덮어쓰지 않았다.

재실행 명령:

    python -m src.profiling.profile_violations

## 실제 측정 결과

| 지표 | 측정값 |
| --- | ---: |
| Bronze 전체 행 | 318,552 |
| NULL | 0 |
| 비NULL 값 (빈 문자열 포함) | 318,552 |
| 빈 문자열 | 90,000 |
| 공백 문자만 있는 문자열 | 0 |
| 비공란 원문 | 228,552 |
| 여러 조각으로 나뉘는 행 | 197,271 |
| 인식한 파이프 구분자 | 802,254 |
| 원문 파이프 문자 | 802,254 |
| 구분자 형식에 맞지 않는 파이프가 있는 행 | 0 |
| 위반 후보 조각 | 1,030,806 |
| 코드 헤더 패턴 일치 | 1,030,806 |
| 코드 헤더 불일치 | 0 |
| 고유 코드 수 | 65 |
| 비어 있지 않은 설명 | 1,030,806 |
| Comments: 표식이 있는 조각 | 1,029,015 |
| 표준 설명-Comments 패턴 일치 | 1,029,015 |
| Comments: 표식이 없는 조각 | 1,791 |
| 완전 파싱 조각 | 1,029,015 |
| 모든 조각이 완전 파싱된 원문 행 | 227,371 |
| 일부 조각만 완전 파싱된 원문 행 | 997 |
| 완전 파싱 조각이 없는 원문 행 | 184 |

측정 결과의 코드 패턴은 “정수 코드 + 마침표 + 설명 + 공백-하이픈-공백 Comments: + 코멘트” 형태다. 실제 원문 예시는 다음과 같다.

    16. FOOD-CONTACT SURFACES: CLEANED & SANITIZED - Comments: OBSERVED BLACK AND ORANGE MOLDLIKE SUBSTANCE ...

복수 항목 예시에서는 “ | ”가 조각 구분자로 관측됐다. 비공란 값에 존재한 802,254개 파이프 문자가 모두 이 형식으로 인식됐다. 가장 자주 나온 위반 코드는 55(86,407개 조각), 38(78,197개), 34(71,800개), 33(67,668개), 35(65,992개)였다.

## 발견한 예외와 해석

Comments: 표식이 없는 1,791개 조각도 모두 코드 헤더와 비어 있지 않은 설명을 가졌다. 따라서 이는 코드 파싱 실패가 아니라 코멘트 경계가 확인되지 않는 부분 형식이다. 실제 원문 예시는 다음과 같다.

    1. PERSON IN CHARGE PRESENT, DEMONSTRATES KNOWLEDGE, AND PERFORMS DUTIES

184행은 모든 조각에 Comments:가 없었고, 997행은 한 셀 안에 표식이 있는 조각과 없는 조각이 함께 있었다. 이 값들은 파서가 코멘트를 추측해 나누지 않도록 별도 상태로 남겨야 한다. 이번 프로파일에서 코드 헤더 실패와 표준 구분자 밖의 파이프는 관측되지 않았다.

## Silver 단계 제안

다음 단계에서 기본 점검 행은 유지하고, 각 조각을 별도의 inspection_violations 행으로 변환하는 방안을 적용한다. 점검 식별자와 원래 조각 순번을 복합 식별자로 사용하고, 원문 조각을 함께 보존한다. 코드·설명·코멘트로 나누며 Comments: 표식이 없는 조각은 코멘트 경계 미확인 상태로 기록하고 임의 추정하지 않는다. 빈 원문에는 자식 위반 행을 만들지 않는다. 실제 구현과 검증은 다음 Silver 단계에서 진행한다.

## 검증과 보존

측정 결과 JSON에는 Origin 및 Bronze 파일 크기와 SHA-256, 배치 크기, 사용한 정규식과 건수 집계가 포함된다. 결과 파일은 reports/profiling/violations_profile.json이다. 프로파일링 코드는 해당 Parquet 컬럼을 읽고 JSON 결과만 쓴다.

검증 명령 python -m pytest tests/profiling -q --basetemp C:/violations-profile-test는 6개 통과했고, python -m pytest -q --basetemp C:/violations-profile-all은 전체 9개 통과했다. 프로파일 실행은 10,000행 배치로 완료됐다. JSON 결과를 다시 읽었고, 입력 행 수가 Parquet 메타데이터와 일치하며 NULL·빈 문자열·공백 전용·비공란 건수의 합이 318,552인 것을 확인했다. 802,254개 원문 파이프와 인식한 구분자 수도 일치했다. 원천과 Bronze SHA-256은 각각 c97464b9aa02801c7e7bedca876d0d6fff482fb56366ad35befe5c68897e4fe7 및 cbc2b9eb8d5feb883d93619d250193ec6d9d59e572ba4f4e9f0b26a9c40c79c5로 결과 JSON에 기록됐다.

기존 미커밋 Silver 설계자료와 별도 작업 파일은 변경 전 스태시에 보존했다. 사용 전 상태에는 기존 stash도 있었으며 삭제하지 않았다. 현재 단계에서는 Silver·Quality/Mapping·Gold를 구현하지 않았다.
