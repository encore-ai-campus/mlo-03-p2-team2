# 01 시카고 식품 위생 점검 성과 분석 리포트

**분석 질문** — 어떤 시설 유형과 점검 유형에서 불합격률이 높고, 연도·월·위험등급에 따라 어떤 차이가 나타나는가?

**분석 범위** — 2026년 11월 20일 처리한 로컬 스냅샷. 점검일 기준 2010-01-04~2026-11-18이며, 전체 점검 **318,627건** 중 **273,488건**에 통과·조건부 통과·불합격 판정이 기록됐습니다. [Gold 매니페스트](../../data/gold/metadata/inspection_gold_manifest.json)

**주요 결과** — 전체 기간 순위에서 시설 유형은 **LIQUOR(36.89%)**, 점검 유형은 **LICENSE-TASK FORCE(60.80%)**, 두 유형의 조합은 **RESTAURANT × LICENSE-TASK FORCE(60.27%)**가 가장 높았습니다. 최근 완료된 연도의 전체 불합격률은 2023년 **24.88%**에서 2025년 **21.11%**로 **3.77%p** 낮아졌습니다.

## 시설 유형과 점검 유형

불합격률은 **불합격 건수 ÷ (통과 + 조건부 통과 + 불합격 건수)**입니다. 폐업·출입 불가 등 기타 결과는 전체 점검 건수에는 포함되고 판정 분모에서는 제외됩니다. 순위는 유형을 확인할 수 있고 판정이 100건 이상인 그룹에 적용했습니다.

| 비교 기준 | 불합격률 상위 그룹 | 불합격 / 판정 | 불합격률 |
| --- | --- | ---: | ---: |
| 시설 유형 | LIQUOR | 432 / 1,171 | 36.89% |
| 점검 유형 | LICENSE-TASK FORCE | 366 / 602 | 60.80% |
| 시설 × 점검 유형 | RESTAURANT × LICENSE-TASK FORCE | 176 / 292 | 60.27% |

`Facility Type`은 점검 당시 기록된 시설 분류입니다. 점검의 선정 사유가 유형별로 다르므로, 이 순위는 **실제로 점검한 건의 판정 결과**를 보여줍니다. 표기상 대소문자와 공백은 정리했고, 의미가 같은 별칭은 추가 검토 항목입니다.

[시설 유형 순위](../../data/gold/analysis/failure_ranking_by_facility.csv) · [점검 유형 순위](../../data/gold/analysis/failure_ranking_by_inspection_type.csv) · [시설·점검 유형 조합 순위](../../data/gold/analysis/failure_ranking_by_facility_inspection.csv)

## 연도·월·위험등급별 추세

| 기간 | 전체 점검 | 판정 | 불합격 | 불합격률 |
| --- | ---: | ---: | ---: | ---: |
| 2023년 | 18,261 | 15,413 | 3,835 | 24.88% |
| 2024년 | 19,228 | 15,995 | 3,481 | 21.76% |
| 2025년 | 19,205 | 16,060 | 3,391 | 21.11% |
| 2026년 11월 18일까지 | 14,279 | 12,101 | 2,589 | 21.39% |

2023~2025년에는 판정 건수가 늘면서 불합격 건수는 줄었습니다. 2026년 월별 예시로는 9월 **24.78%**(251/1,013), 10월 **24.28%**(228/939), 11월 18일까지 **21.37%**(78/365)입니다. 2026년과 11월 수치는 부분 기간이므로 연도·월을 직접 비교할 때는 전년 동일 기간을 기준으로 봅니다. 장기 추세 해석에는 점검 기준 변경 시점과 유형별 구성도 고려합니다.

[연도별 집계](../../data/gold/analysis/performance_by_year.csv) · [월별 집계](../../data/gold/analysis/performance_by_month.csv)

| 위험등급 | 불합격 / 판정 | 불합격률 |
| --- | ---: | ---: |
| RISK_1 (높음) | 45,419 / 208,040 | 21.83% |
| RISK_2 (중간) | 10,747 / 47,653 | 22.55% |
| RISK_3 (낮음) | 5,151 / 17,753 | 29.01% |

세 표준 등급 가운데 **RISK_3**에서 관측된 불합격률이 가장 높았습니다. 시설 유형과 점검 유형의 구성에 따라 비율이 달라질 수 있어, 위험등급별 후속 비교는 같은 시설·점검 유형 안에서 판정 건수와 함께 봅니다. 원천의 `ALL`과 미분류 등급은 전체 집계에 포함하고 세 표준 등급 비교에서는 별도 범주로 관리합니다. [위험등급별 집계](../../data/gold/analysis/performance_by_risk.csv)

## 데이터 품질과 재현성

Bronze·Silver·Gold 점검 팩트는 각각 **318,627행**입니다. 완전 중복, 점검 키 충돌, 유효하지 않은 점검 키 또는 날짜로 제외된 행은 **0건**입니다. 시설 유형 결측 **5,358건**, 점검 유형 결측 **1건**, 위험등급 결측 **88건**, 검토 대상 위험등급 `ALL` **90건**을 기록했습니다. AI Ready는 월·시설 유형·점검 유형·위험등급 단위 **25,632행**입니다. 현재 원천 CSV가 Bronze 매니페스트의 SHA-256과 일치하고 각 레이어의 매니페스트 검증을 통과했습니다.

[품질 보고서](../../data/silver/reports/inspection_quality_report.json) · [AI Ready 데이터 정의](../../data/ai_ready_data/metadata/inspection_performance_contract.json)

재현 검증에 사용한 로컬 원천의 SHA-256은 `71bd98831bad3542fd7e2af6c0ada6469f2606347d1659fb61bd29c66e5fe7db`입니다.

## 취합할 데이터와 행 단위

| 단계 | 한 행의 의미 | 제공 결과 |
| --- | --- | --- |
| 원천 → Bronze | CSV의 원천 레코드 한 건 | 원천 17개 컬럼, `source_row_num`, 스냅샷 SHA-256 매니페스트 |
| Silver → 품질관리 | Silver는 원천 레코드 한 건, 품질 예외표는 원천 행과 규칙의 조합 | 공통 이름·타입·코드를 적용한 점검 데이터와 품질 보고서 |
| Gold | 팩트는 검증된 점검 한 건, 성과표는 집계 기준별 한 그룹 | 날짜·시설 유형·점검 유형·위험등급·결과 차원, 성과 집계와 불합격률 순위 |
| AI Ready Data | 연도 × 월 × 시설 유형 × 점검 유형 × 위험등급 조합당 한 행 | 과거 점검 성과 질의에 사용할 집계 데이터와 지표 정의 |

입력은 [식품 위생 점검 CSV](../../data/origin/food_Inspections.csv)입니다. 이 관점의 지표는 점검 원천에서 직접 계산합니다. [AI Ready 데이터 정의](../../data/ai_ready_data/metadata/inspection_performance_contract.json)

## 공용으로 맞출 이름과 타입

| 원천 컬럼 | 표준 컬럼 · 타입 | 01번 사용 목적 |
| --- | --- | --- |
| `Inspection ID` | `inspection_key` · string | 점검 한 건을 식별하고 다른 관점과 연결 |
| `License #` | `license_number_key` · string | 인허가 연결 후보. `0`과 `9999999`는 null 처리 |
| `Inspection Date` | `inspection_dtm` · date32 | 원천의 MM/DD/YYYY를 날짜로 변환하고 연도·월을 도출 |
| `Facility Type` / `Inspection Type` | `facility_type` / `inspection_type` · string | 시설과 점검 유형별 성과 비교 |
| `Risk` / `Results` | `risk_level_cd` / `result_cd` · string | 공용 위험등급과 결과 코드로 집계 |

Silver에서는 일반 텍스트의 양끝 공백을 제거하고 공란을 null로 저장합니다. 성과 집계에서는 시설·점검 유형의 대소문자와 연속 공백을 통일합니다. 의미가 같은 별칭의 통합은 팀 합의 항목입니다. [공용 코드표](../shared_code_map.csv)

## 연결 방식과 다른 관점에 제공할 컬럼

| 제공 컬럼 | 타입 | 해석 |
| --- | --- | --- |
| `inspection_key` | string | Gold 점검 팩트의 고유 키. 04번 인허가 매칭 등 점검 단위 결과와 연결 |
| `source_row_num` | int64 | Bronze 원천 레코드로 돌아가는 순번 |
| `inspection_count_num` | int64 | 전체 점검 건수 |
| `decision_count_num` | int64 | 통과·조건부 통과·불합격 건수의 합계 |
| `fail_count_num` | int64 | 불합격 건수 |
| `failure_rate` | float64, null 허용 | 불합격 건수 ÷ 판정 건수. 판정 건수가 0이면 null |

다른 관점과 연결할 때는 해당 결과를 점검 한 건당 한 행으로 맞추고 조인 전후 팩트 행 수를 대사합니다. 불합격률을 다시 집계할 때는 **불합격 건수와 판정 건수를 각각 합산한 뒤 나눕니다.** 시설·점검 유형 순위에는 판정 100건 이상이며 유형이 확인된 그룹을 사용합니다. [Gold 점검 팩트](../../data/gold/analysis/star_schema/fact_inspection.parquet)

## 원천 갱신 후 실행

프로젝트 루트에서 Python 3.11 이상을 사용합니다. 처음 실행할 때는 가상환경을 만들고 의존성을 설치합니다.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install pandas pyarrow
```

원천 CSV는 `data/origin/food_Inspections.csv`에 둡니다. Silver는 `docs/shared_code_map.csv`에서 위험등급과 점검 결과의 공용 코드를 읽습니다. 아래 명령은 Bronze부터 AI Ready까지 전체 기간을 다시 처리합니다.

```bash
.venv/bin/python src/domains/01_inspection/runner.py
```

단계별 결과를 확인하면서 실행할 때는 아래 순서를 따릅니다. 변환 로직이 들어 있는 각 Python 파일을 프로젝트 루트에서 직접 실행합니다.

```bash
.venv/bin/python src/domains/01_inspection/bronze.py
.venv/bin/python src/domains/01_inspection/silver.py
.venv/bin/python src/domains/01_inspection/quality.py
.venv/bin/python src/domains/01_inspection/gold.py
.venv/bin/python src/domains/01_inspection/ai_ready.py
```

품질 단계는 Silver의 행별 검사 결과를 읽고 `data/silver/validated_inspections.parquet`를 만듭니다. Gold는 이 파일에서 스타 스키마와 집계를 만들고, AI Ready는 Gold의 상세 집계를 읽습니다. 각 단계는 선행 단계의 매니페스트와 파일 해시를 검사합니다. 앞 단계가 다시 실행됐다면 해당 단계 이후를 순서대로 실행합니다.


각 레이어 바로 아래의 Parquet은 다음 단계가 읽는 입력 또는 최종 제공 데이터입니다. Gold의 순위·집계 CSV는 `data/gold/analysis/`, 스타 스키마는 그 아래 `star_schema/`에 있습니다. 품질 기록은 `data/silver/reports/`, 매니페스트와 AI Ready 정의는 각 레이어의 `metadata/`에서 확인할 수 있습니다.
