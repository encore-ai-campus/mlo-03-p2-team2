# 02 위반 유형 분석 계약

- 입력: `dim_violation`, `fact_inspection_violation`, Food Inspections Bronze의 `Inspection ID`, `Facility Type`, `Results`
- Mart grain: Accepted Silver의 정상 violation fragment 1건
- Mart grain key: `(bronze_row_number, item_sequence_num)`
- Inspection 연결: 원천에서 NULL·중복 0건으로 확인한 `Inspection ID`
- 위반 유형: `(violation_code, violation_description)` 조합. 같은 코드의 서로 다른 설명을 합치지 않는다.
- 점검 불합격: 원천 `Results`에서 관측한 정확한 값 `Fail`
- 미기재 시설 유형: 원문 빈 문자열을 Mart에 그대로 보존하고 HTML 표시만 `(미기재)`로 바꾼다.
- 격리 데이터: Gold 분석에서 제외하며 `Accepted + Quarantine = 전체 candidate`를 계속 검증한다.

실행 명령은 `python -m src.domains.02_violation.build_analysis_mart`이다. 출력은 `data/03_gold/marts/violations_analysis_mart.parquet`, `reports/violations_analysis.html`, 실행 로그는 `logs/violations_analysis_runs.jsonl`이다.

## 실행 결과와 변경 기록

[최신 원천 재실행 결과](violation_types_analysis_results.md)와 단계별 변경 기록은 `docs/domains/02_violation/`에 둡니다.
