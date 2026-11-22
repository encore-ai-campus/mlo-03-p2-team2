# 02 위반 유형 분석 계약

- 입력: `dim_violation`, `fact_inspection_violation`, Food Inspections Bronze의 `Inspection ID`, `Facility Type`, `Results`
- Mart grain: Accepted Silver의 정상 violation fragment 1건
- Mart grain key: `(source_row_num, item_sequence_num)`
- Inspection 연결: 원천에서 NULL·중복 0건으로 확인한 `Inspection ID`
- 행 추적: 02 Bronze 파생에서 부여한 `source_row_num`과 조각 순번을 Silver·Gold 사실·Mart에 보존한다. 원천 파일명 `_SRC_FILE`과 적재 시각 `_LOAD_DTM`은 Bronze와 실행 기록에서 조회한다.
- 위반 유형: `(violation_code, violation_description)` 조합. 같은 코드의 서로 다른 설명을 합치지 않는다.
- 점검 불합격: 원천 `Results`에서 관측한 정확한 값 `Fail`
- 불합격 0건은 정상 결과다. 점검 결과의 공란·미등록 값은 분석 로그에 별도 기록하며 불합격으로 집계하지 않는다.
- 미기재 시설 유형: 원문 빈 문자열을 Mart에 그대로 보존하고 HTML 표시만 `(미기재)`로 바꾼다.
- 격리 데이터: Gold 분석에서 제외하며 `Accepted + Quarantine = 전체 candidate`를 계속 검증한다.

## 공란과 해석 불가 원문

- 원천 위반란이 모두 공란이어도 점검은 Bronze에 보존한다. 대사 보고서에 위반 후보·정상·격리 건수를 각각 `0`으로 기록하고, 기존 스키마를 가진 빈 Gold 팩트·차원·마트를 생성한다.
- Profiling과 Silver는 같은 분류 함수로 상태를 기록한다. 코드 머리를 읽을 수 없으면 `UNPARSED_CODE_HEADER`, 인식할 수 없는 파이프 구분자가 섞이면 셀 원문 전체를 `UNRECOGNIZED_SEPARATOR` 한 건으로 남긴다. 코드가 있으나 코멘트 구분자가 없으면 `MISSING_COMMENTS_MARKER`, 구분 후 설명이나 코멘트가 비면 각각 `EMPTY_DESCRIPTION`, `EMPTY_COMMENTS`로 기록한다.
- 품질 검사는 원문에서 해당 상태 때문에 생길 NULL을 계산하고 Silver의 값과 대조한다. 격리 파일에는 원문 조각, 점검 ID, 원천 행 번호, 조각 순번과 사유를 기록한다. 정상 위반만 Gold에 적재한다.

## Gold 위반 유형 키 유지

워크트리는 `C:\mlo-03-p2-team2`, 작업 브랜치는 `codex/domain-02-stable-violation-keys`다.

기존 공개 Gold 차원에서 추출한 [초기 키 매핑 110개](../../../metadata/standards/02_violation/violation_key_seed.csv)를 기준으로 삼는다. 예를 들어 기존 코드 `55`의 키 `92`에 해당하는 설명 조합은 이후 실행에서도 `92`를 유지한다. 새로 관측한 코드·설명 조합에는 현재 최대 번호 다음부터 부여한다. 특정 배치에서 사라진 유형도 키 레지스트리에 보관하고, 같은 조합이 다시 나오면 기존 키를 사용한다. 출력 차원에는 그 배치에서 관측한 유형을 저장한다.

기본 레지스트리는 저장소의 `data/03_gold/02_violation/02_violation_key_registry.csv`다. 새 유형이 최초로 들어올 때 초기 매핑과 함께 저장하며, 이후에는 실행 폴더를 새로 만들어도 같은 레지스트리를 사용한다. 운영 환경이 바뀌면 확장된 CSV를 백업·이관하고 `python -m src.domains.02_violation.runner --registry <경로>`로 같은 등록부를 지정한다. 여러 작업 환경에서 독립적으로 새 번호를 배정하면 서로 다른 유형에 같은 번호를 쓸 수 있으므로 같은 키 체계를 공유하는 실행은 등록부 하나를 사용한다.

키 배정은 파일 교체 방식으로 저장한 뒤 Gold를 만든다. Gold 생성이 실패해도 이미 배정한 번호는 재사용하지 않는다. 동시 배정 중에는 두 번째 실행이 잠금 오류로 종료되므로 첫 실행이 끝난 후 다시 실행한다. 운영 중에는 레지스트리나 기존 키를 수동으로 재정렬하지 않는다.

실행 명령은 `python -m src.domains.02_violation.build_analysis_mart`이다. 현재 코드 기준 출력은 `data/03_gold/02_violation/02_violations_analysis_mart.parquet`, `reports/02_violation/violations_analysis.html`, 실행 로그는 `logs/02_violation/violations_analysis_runs.jsonl`이다.

## 실행 결과와 변경 기록

[최신 원천 재실행 결과](violation_types_analysis_results.md)와 단계별 변경 기록은 `docs/domains/02_violation/`에 둡니다.

[폴더 구조 정리 및 공통 입력 확인 사항](folder_structure_alignment.md)을 참조하세요. 실행 순서와 현재 입출력 경로를 정리했습니다.
