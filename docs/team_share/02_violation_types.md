# ② 위반 유형 최종 공유

담당은 **② 위반 유형**이며, Food Inspections의 `Violations` 원문을 실제 데이터에서 조사한 뒤 아래 흐름을 재실행 가능한 코드로 완성했다.

```text
Profiling → Silver 분리·표준화 → Quality → 정상 / Quarantine
          → Gold Dimension·Fact → 분석 Mart → HTML
```

## 주요 산출물

| 단계 | 산출물 |
| --- | --- |
| Profiling | `src/profiling/profile_violations.py`, `reports/profiling/violations_profile.json` |
| Silver | `src/silver/violations.py`, `data/02_silver/food_inspections/violations/` |
| Quality·격리 | `src/quality/violations_quality.py`, `src/silver/violations_reconciliation.py`, `data/quarantine/food_inspections/violations/` |
| Gold | `src/gold/violations.py`, `data/03_gold/dimensions/dim_violation.parquet`, `data/03_gold/facts/fact_inspection_violation.parquet` |
| Mart·분석 | `src/domains/02_violation/build_analysis_mart.py`, `data/03_gold/marts/violations_analysis_mart.parquet` |
| 최종 HTML | `reports/violations_analysis.html` |

세부 근거는 `violations_profiling_changelog.md`, `violations_silver_changelog.md`, `violations_quality_changelog.md`, `violations_quality_reconciliation_changelog.md`, `violations_gold_changelog.md`, `violations_analysis_changelog.md`에 단계별로 남겼다.

## 분석 결과

1. **위반 코드별 빈도:** 최빈 코드는 `55`, 86,347건이다.
2. **시설 유형별 주요 위반:** Restaurant은 정상 위반 742,992건 중 코드 55 유형이 58,940건, Grocery Store는 131,706건 중 코드 55 유형이 11,809건, School은 54,594건 중 코드 35 유형이 5,596건으로 각 1위였다.
3. **가장 빈번한 위반 유형:** `55 · PHYSICAL FACILITIES INSTALLED, MAINTAINED & CLEAN`, 86,347건이다.
4. **Fail 점검 주요 위반:** Fail 점검에 연결된 정상 위반은 382,908건이며, 최빈 유형은 같은 코드 55 유형 28,050건이다.

같은 코드에 설명이 여러 개 존재하므로 대표 설명을 임의 선택하지 않았다. Gold Dimension과 유형별 분석은 `(violation_code, violation_description)` 조합을 grain으로 사용한다.

## 정합성과 검증

- 전체 후보 `1,030,806 = Accepted 1,029,015 + Quarantine 1,791`
- `Accepted Silver 1,029,015 = Gold Fact 1,029,015 = Mart 1,029,015`
- Inspection·Dimension 미매칭, 조인 유실·증가, Fact/Mart grain 중복, FK orphan: 모두 0건
- 동일 입력 2회 실행에서 Gold와 Mart의 schema·content hash·surrogate key가 동일
- 최종 전체 테스트: 23개 통과
- Origin·Bronze·Silver·Accepted·Quarantine과 기존 Gold 입력은 변경하지 않음
