# ② 위반 유형 분석 — 최신 원천 재실행 결과

**기준일:** 2026-11-20

**담당:** ② 위반 유형

**대상 원천:** Food Inspections 318,627행. 파일 SHA-256: `b43beb7fae834a8698ca162004caf2929cb2eca7ff75c27b4db6bf07aa103c98`

**Bronze:** `data/01_bronze/food_inspections/food_inspections.parquet`, 318,627행. SHA-256: `8bce236e42751111b74742fbe55081ee0d800e1da48fe7c12b8d3604c8f6d682`

## 처리 흐름 및 산출물

```text
Profiling → Silver 분리·표준화 → Quality / Quarantine
          → Gold Dimension·Fact → 분석 Mart → HTML
```

| 단계 | 산출물 |
| --- | --- |
| Profiling | `reports/profiling/violations_profile.json` |
| Silver 정상 | `data/02_silver/food_inspections/violations/inspection_violations_accepted.parquet` |
| Quality / 격리 | `reports/quality/violations_quality_report.csv`, `data/quarantine/food_inspections/violations/inspection_violations_quarantine.parquet` |
| Gold | `data/03_gold/dimensions/dim_violation.parquet`, `data/03_gold/facts/fact_inspection_violation.parquet` |
| 분석 Mart | `data/03_gold/marts/violations_analysis_mart.parquet` |
| 분석 HTML | `reports/violations_analysis.html` |
| 실행 로그 | `logs/violations_gold_runs.jsonl`, `logs/violations_analysis_runs.jsonl` |

## 새 원천 기준 건수

| 구간 | 행 수 |
| --- | ---: |
| Bronze 점검 | 318,627 |
| `Violations` 빈 셀 | 90,022 |
| `Violations` 비어 있지 않은 셀 | 228,605 |
| 전체 위반 조각 후보 | 1,031,073 |
| Accepted Silver | 1,029,281 |
| Quarantine (`MISSING_COMMENTS_MARKER`) | 1,792 |
| Gold Fact | 1,029,281 |
| 분석 Mart | 1,029,281 |

따라서 `90,022 + 228,605 = 318,627`, `1,029,281 + 1,792 = 1,031,073`, `Accepted Silver = Gold Fact = Mart`가 성립한다. Quality 보고서의 26개 규칙이 모두 PASS이며, 격리 행은 Gold 정상 분석에서 제외하고 원문 추적 데이터로 보존했다.

## 네 가지 분석 결과

1. **위반 코드별 빈도:** 최빈 코드는 `55`로 86,399건이다. 다음은 코드 `38` 78,111건, 코드 `34` 71,698건이다.
2. **시설 유형별 주요 위반:** Restaurant(743,176건)은 코드 `55`가 58,972건으로 1위다. Grocery Store(131,735건)는 코드 `55`가 11,811건, School(54,595건)은 코드 `35`가 5,596건으로 각 1위다.
3. **가장 빈번한 위반 유형:** `(55, PHYSICAL FACILITIES INSTALLED, MAINTAINED & CLEAN)` 조합 86,399건이다.
4. **Fail 점검 주요 위반:** 원천 `Results`의 실제 값 `Fail`을 사용했다. Fail 점검은 61,344건이며 연결된 정상 위반 조각은 383,046건이다. 그중 최빈 유형은 코드 `55`로 28,066건이다.

같은 코드와 여러 설명의 관계를 임의로 하나로 합치지 않았다. Dimension grain은 `(violation_code, violation_description)` 조합이며 110개 member, 코드는 65종이다. Mart grain은 Accepted Silver의 위반 조각 한 건이다.

## 정합성 및 재실행 검증

- Inspection ID 중복/NULL: 각 0건. Inspection JOIN 미매칭: 0건.
- Dimension FK orphan: 0건. Fact grain 중복: 0건.
- Silver→Gold Fact 유실/증가: 0건. Fact→Mart 조인 유실/증가: 0건.
- Gold를 연속 두 번 실행했을 때 Dimension/Fact 내용 해시와 행 수가 동일했다.
- Mart 및 HTML을 연속 두 번 생성했을 때 두 결과의 해시와 집계가 동일했다.
- 전체 테스트: `python -m pytest -q --basetemp C:\mlo-03-p2-team2-testtmp-final` 실행 결과 **24 passed**.

| 결과물 | SHA-256 |
| --- | --- |
| Accepted Silver 파일 | `dbc44730e6ae75db9efadabf58f0464899f72e685f6ad4220a95431e76bc78ab` |
| Quarantine 파일 | `724ab76dff61e1f1e013a7f10b4a4aed6f93654f34964cf8a210a024f0a6f6b8` |
| Gold Dimension 내용 | `cb1b940e5dcff69603252717aa13aa9d1476667badbd6e0347448d051b603830` |
| Gold Fact 내용 | `099274ff8d09abe0a58c2ae999b02ebfb9c3d337343b4ad5e426b9bdc623911d` |
| Mart 내용 | `1ab7a7de2f66288f9f5b192aca72ae069e85d04c1f1b0077503a8d45b3dddbcd` |
| Mart 파일 | `8b1480cd88611c20f1623fea665d22eaaa9fa4ea44f662090f0fb0619123640f` |
| HTML 파일 | `85ea44d15fa85e14a6130da9ca7041c696c2ee40bcfc847c8afc489b53bcf31b` |

상세 단계별 기록은 `violations_profiling_changelog.md`, `violations_silver_changelog.md`, `violations_quality_changelog.md`, `violations_quality_reconciliation_changelog.md`, `violations_gold_changelog.md`, `violations_analysis_changelog.md`를 참고한다.
