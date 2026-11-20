# Food Inspections Violations Silver 구현 기록

## 작업 개요

- 작업일: 2026-11-20
- 브랜치: feature/violations-silver
- 기준 커밋: c0adae473070c96cee6d143cd8620d4850220960
- 범위: Food Inspections의 Violations 컬럼만 분리·표준화
- 실행 명령: python -m src.silver.violations

전체 65개 컬럼이나 다른 데이터셋의 Silver는 이 브랜치에 포함하지 않았다.

## 입력과 Profiling 근거

입력 Bronze는 data/01_bronze/food_inspections/food_inspections.parquet이며, 그중 Inspection ID, Violations, _SRC_FILE, _LOAD_DTM 네 컬럼만 읽었다. 원천 파일은 data/00_origin/food_inspections/food_inspections.csv다. Bronze 전체는 318,552행이고 Violations는 string이다.

Profiling은 빈 문자열 90,000행, 비공란 228,552행, 여러 항목이 든 셀 197,271행, 후보 조각 1,030,806건을 측정했다. 모든 후보가 코드 헤더 패턴에 맞았고 코드 고유값은 65개였다. Comments: 표식이 있는 조각은 1,029,015건, 표식이 없는 조각은 1,791건이었다. 분리 구분자는 공백으로 둘러싸인 파이프였고 비정상 파이프는 관측되지 않았다.

## Silver 규칙과 Grain

Silver 한 행은 하나의 Bronze 검사 행에서 분리한 위반사항 조각 하나다. 행 순서는 Bronze 원천 행 안의 item_sequence_num으로 보존한다. 기술 추적 키는 bronze_row_number와 item_sequence_num이며 inspection_id와 _SRC_FILE도 함께 저장한다.

조각은 Profiling에서 확인한 공백-파이프-공백 패턴으로 나눈다. source_violations_fragment에는 분리된 조각 원문을 보관한다. 원문 전체 셀은 Inspection ID, bronze_row_number, _SRC_FILE로 원래 Bronze 행에서 추적할 수 있다.

코드는 숫자와 선택적 대문자 접미사 뒤 마침표가 오는 패턴에서 문자열로 추출한다. Comments: 표식이 있으면 그 앞의 설명과 표식 뒤의 코멘트를 분리한다. 표식이 없으면 경계를 추측하지 않고 코드만 추출하며 설명·코멘트는 NULL, parsing_status는 MISSING_COMMENTS_MARKER로 기록한다. 코드 헤더를 읽을 수 없는 경우에는 원문 조각을 보존하고 UNPARSED_CODE_HEADER를 기록한다. 빈 문자열과 공백만 있는 셀에서는 위반 행을 만들지 않는다.

## 코드와 출력

src/silver/violations.py의 parse_fragment는 조각을 파싱하고, run은 Bronze를 배치 단위로 읽어 Silver 파일을 만들고 다시 읽어 검증한다. 출력 경로가 이미 다른 파일로 존재하면 덮어쓰지 않도록 막는다. data/02_silver/food_inspections/violations/inspection_violations.parquet은 1,030,806행, 10열, 101,387,709 byte이며 SHA-256은 22e2d374d3aaacd351771e01f8f45f87550515b9a7d2e3899e88fad7f08296c4다.

스키마는 inspection_id, bronze_row_number, item_sequence_num, _SRC_FILE, _LOAD_DTM, source_violations_fragment, violation_code, violation_description, violation_comments, parsing_status다. 날짜나 코드 의미 매핑은 수행하지 않았다.

## 실제 처리 결과

| 지표 | Bronze/Profiling | Silver 재측정 |
| --- | ---: | ---: |
| Bronze 입력 행 | 318,552 | 318,552 |
| NULL Violations | 0 | 0 |
| 빈 문자열 셀 | 90,000 | 위반 행 생성 안 함 |
| 비공란 셀 | 228,552 | 228,552 |
| 여러 조각이 있는 셀 | 197,271 | 197,271 |
| 후보 조각 / Silver 행 | 1,030,806 | 1,030,806 |
| 코드 추출 및 고유 코드 | 헤더 일치 1,030,806 / 고유 65 | 코드 값 1,030,806 / 고유 65 |
| 설명 추출 | Comments 표식 기준 1,029,015 | 1,029,015 |
| 코멘트 추출 | Comments 표식 기준 1,029,015 | 1,029,015 |
| Comments 표식 누락 | 1,791 조각 | MISSING_COMMENTS_MARKER 1,791 |
| 코드 헤더 실패 | 0 | UNPARSED_CODE_HEADER 0 |
| 구분자 오류 | 0 | UNRECOGNIZED_SEPARATOR 0 |

다시 읽은 Parquet의 행 수·스키마·status별 건수·고유 코드 수·NULL 수를 프로파일 결과와 비교했다. 결과는 모두 일치했다. violation_code NULL은 0건, violation_description과 violation_comments NULL은 각각 1,791건이다. 빈 문자열 90,000행은 자식 행을 만들지 않았다.

## Mapping 기록

metadata/standards/violations_mapping.csv는 실제 실행 건수로 생성했다. 원천 파일·Bronze 파일·원천 컬럼·대상 파일·대상 컬럼·변환·적용 패턴·처리 건수·처리 단위·상태·비고를 기록한다. 주요 매핑은 Violations → source_violations_fragment, violation_code, violation_description, violation_comments, parsing_status다. 여러 조각을 가진 197,271개 원천 셀과 빈 셀 90,000개 처리 방식도 별도 행으로 기록했다.

## 실행 로그와 보존 검증

실제 실행은 2026-11-20 03:46:57Z부터 03:47:11Z까지 진행됐다. 실행 로그 logs/violations_silver_runs.jsonl에 run id 5fb10bb07871d743d2757b30c0bcf7ed, 입력·출력 경로와 SHA-256, 행·열 수, parsing 건수, 성공 여부를 남겼다.

실행 전후 Origin SHA-256은 c97464b9aa02801c7e7bedca876d0d6fff482fb56366ad35befe5c68897e4fe7로 같았다. Bronze SHA-256은 cbc2b9eb8d5feb883d93619d250193ec6d9d59e572ba4f4e9f0b26a9c40c79c5로 같았다. 두 입력 파일을 수정하지 않았다.

## 검증 및 다음 단계

Silver 전용 테스트는 임시 Bronze에서 입력 해시 불변, 빈 셀 제외, 조각 순서, Comments 누락 처리, 출력 스키마, Mapping 파일과 실행 로그를 검사한다. 실제 출력은 별도로 Parquet으로 다시 읽어 1,030,806행과 65개 코드를 확인했다.

다음 Quality 단계에서는 parsing_status와 NULL 상태별 집계, (bronze_row_number, item_sequence_num) 키 유일성, 원천 행별 조각 재결합과 순서, 코드 분포, MISSING_COMMENTS_MARKER 1,791건의 추적성을 검증한다. 아직 의미 코드 매핑이나 Gold 모델은 만들지 않았다.
