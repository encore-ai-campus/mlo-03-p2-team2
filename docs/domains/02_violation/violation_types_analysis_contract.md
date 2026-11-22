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

실행 명령은 `python -m src.domains.02_violation.build_analysis_mart`이다. 현재 코드 기준 출력은 `data/03_gold/02_violation/02_violations_analysis_mart.parquet`, `reports/02_violation/violations_analysis.html`, 실행 로그는 `logs/02_violation/violations_analysis_runs.jsonl`이다.

## 실행 결과와 변경 기록

[최신 원천 재실행 결과](violation_types_analysis_results.md)와 단계별 변경 기록은 `docs/domains/02_violation/`에 둡니다.

[폴더 구조 정리 및 공통 입력 확인 사항](folder_structure_alignment.md)을 참조하세요. 실행 순서와 현재 입출력 경로를 정리했습니다.
