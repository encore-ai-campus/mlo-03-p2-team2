# ② 위반 유형 분석 Mart 및 HTML

## 작업 목적과 기준

검증된 Violations Gold를 바탕으로 위반 코드 빈도, 시설 유형별 주요 위반, 최빈 위반 유형, `Fail` 점검의 주요 위반을 같은 기준으로 재현할 수 있게 만들었다. Mart 한 행은 Accepted Silver에서 Gold Fact로 전달된 **정상 violation fragment 한 건**이다. 위반 유형은 Gold grain인 `(violation_code, violation_description)`을 유지하며, 코드별 대표 설명을 임의로 선택하지 않았다.

시설 유형과 점검 결과는 Gold에 없어서 Bronze의 `Inspection ID`, `Facility Type`, `Results`만 사용했다. Bronze 318,552행에서 `Inspection ID` NULL·중복은 각각 0건이었다. `Results`의 실제 값 7종 가운데 정확한 `Fail` 값 61,328개 inspection이 존재함을 확인한 뒤 사용했다. 시설 유형 빈 문자열 5,358개 inspection은 원문 그대로 Mart에 보존하고 HTML에서 `(미기재)`로만 표시했다.

## 산출 구조와 실제 결과

- 코드: `src/domains/02_violation/build_analysis_mart.py`
- Mart: `data/03_gold/marts/violations_analysis_mart.parquet`
- HTML: `reports/02_violation/legacy/violations_analysis.html`
- 실행 로그: `logs/violations_analysis_runs.jsonl`
- 테스트: `tests/domains/02_violation/test_analysis_mart.py`

Mart 컬럼은 `bronze_row_number`, `item_sequence_num`, `inspection_id`, `facility_type`, `inspection_result`, `violation_key`, `violation_code`, `violation_description`, `violation_comments`이다. Fact grain과 Inspection/Dimension 연결을 모두 추적할 수 있다.

| 항목 | 실측 결과 |
| --- | ---: |
| Gold Fact / Mart | 1,029,015 / 1,029,015 |
| Accepted / Quarantine / 전체 candidate | 1,029,015 / 1,791 / 1,030,806 |
| Inspection 미매칭 / Dimension 미매칭 | 0 / 0 |
| 조인 유실·증가 / Mart grain 중복 | 0 / 0 |
| 위반 코드 / code-description 유형 | 65 / 110 |
| Fail 점검의 정상 위반 조각 | 382,908 |

전체 최빈 코드는 `55`로 86,347건이다. 전체 최빈 유형도 `55 · PHYSICAL FACILITIES INSTALLED, MAINTAINED & CLEAN` 86,347건이며, `Fail` 점검에서도 같은 유형이 28,050건으로 가장 많았다. 시설별 주요 위반은 HTML에서 위반 조각 수가 많은 시설 유형 15개와 각 시설의 상위 3개 code-description 조합을 보여준다. 예를 들어 Restaurant은 전체 위반 742,992건 중 코드 55 유형이 58,940건, Grocery Store는 전체 131,706건 중 같은 유형이 11,809건으로 각 1위였다. School은 전체 54,594건 중 코드 35 유형이 5,596건으로 1위였다.

## 정합성·재현성

`Accepted 1,029,015 + Quarantine 1,791 = Candidate 1,030,806`과 `Gold Fact 1,029,015 = Mart 1,029,015`를 실행 때마다 계산한다. Inspection 또는 Dimension 미매칭, Fact grain 중복, 행 수 차이가 있으면 Mart와 HTML을 발행하지 않는다. Origin·Bronze·기존 Silver·Accepted·Quarantine·Gold Dimension/Fact의 SHA-256도 실행 전후 비교한다.

동일 입력으로 실제 2회 실행해 Mart 행 수·schema·content hash, HTML hash가 동일한지 확인한다. 테스트 fixture에는 운영 건수를 넣지 않고 신규 inspection/violation 행을 추가하여 집계가 입력에서 다시 계산되는 것도 검증한다. HTML에는 전체 정상 위반 건수, 코드 TOP, 시설별 주요 위반, 최빈 유형, Fail 주요 위반과 실제 건수를 표 및 막대로 표시한다.

최종 두 실행의 Mart content SHA-256은 모두 `af9e51f3f9965d4b17003620bac0a361e43aa042f078fc8e31e6b1e58a937675`, HTML SHA-256은 모두 `1492a005756f05649a2ad46d6b254e9efd590c266be0ac2b22b34215ad2ce53a`였다. `python -m pytest -q --basetemp C:/violations-analysis-all-tests-final` 실행에서 전체 23개 테스트가 통과했고 `git diff --check`도 통과했다.
