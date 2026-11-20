# Violations Gold Star Schema 작업 기록

## 목적과 입력

Silver는 원천 위반 문구를 분리하고 품질에 따라 정상·격리로 나눈다. Gold는 검증된 정상 조각을 분석 가능한 차원(Dimension: 위반 종류의 식별 정보)과 사실(Fact: 검사에서 발생한 위반 사건)로 연결하는 Star Schema다. 입력은 `data/02_silver/food_inspections/violations/inspection_violations_accepted.parquet`이며 quarantine은 Gold에 넣지 않는다. 실행: `python -m src.domains.02_violation.gold`.

기존 `data/03_gold/`에는 `dimensions/`, `facts/`, `marts/`의 `.gitkeep`만 있었고 `src/gold/` 및 inspection 부모 Gold 테이블은 없었다. 기존 팀 문서의 `inspection_key`는 확정된 부모 PK가 아닌 제안이다.

## 실제 grain과 연결

Accepted Silver에서 위반 코드 65종, 고유 `(violation_code, violation_description)` 110조합을 측정했다. 45개 코드는 둘 이상의 설명과 연결되므로 코드 하나를 차원 한 행으로 만들면 설명이 유실된다. `dim_violation`은 **코드·설명 조합 하나당 한 행**으로 정했다. 공식 코드 의미나 위험도는 추가하지 않았다. `violation_key`는 관측한 고유 조합을 `(code, description)` 문자열 순으로 정렬한 뒤 1부터 번호를 붙인다. 같은 입력이면 행 순서가 달라도 같은 조합에 같은 키가 붙는다. 새 조합이 들어오면 전체 정렬 번호가 바뀔 수 있으므로 기존 Gold와 새 버전을 혼용하지 말아야 한다.

`fact_inspection_violation`은 **Accepted Silver 위반 조각 한 건당 한 행**이다. grain 키는 `(bronze_row_number, item_sequence_num)`이고 `violation_key`가 차원 FK다. `violation_comments`는 종류의 고정 설명이 아니라 점검별 사건 내용이므로 Fact에 둔다. 현재 inspection Gold 부모 테이블이 없어 inspection surrogate FK는 연결하지 않았으며, 향후 부모 Gold와 연결할 수 있도록 source `inspection_id`를 보존한다. 원문 조각과 Bronze 원천 파일·적재 시각도 Fact에 보존한다.

```text
dim_violation (violation_key PK)
     │ violation_key
     ▼
fact_inspection_violation (bronze_row_number, item_sequence_num grain)
     └── inspection_id → 향후 inspection Gold 연결
```

## 실행 결과 및 검증

| 검사 | 실제 결과 |
| --- | ---: |
| 전체 violation 후보 | 1,030,806 |
| Accepted Silver / Gold Fact | 1,029,015 / 1,029,015 |
| Quarantine 제외 | 1,791 (`MISSING_COMMENTS_MARKER`) |
| Gold Dimension | 110 |
| Accepted → Fact 유실·증가 | 0 / 0 |
| Dimension PK NULL·중복 / 조합 중복 | 0 / 0 / 0 |
| Dimension code·description NULL | 0 / 0 |
| Fact grain 중복 / FK orphan | 0 / 0 |
| Fact 전체 컬럼 NULL / 역조인 값·lineage 불일치 | 0 / 0 |

`1,029,015 + 1,791 = 1,030,806`, `Accepted 1,029,015 = Fact 1,029,015`가 성립한다. Dimension 집합은 Accepted의 고유 조합 집합으로 만들었고, Fact와 Dimension을 역조인하여 Accepted의 코드·설명·comment·lineage와 행별 대조했다. 기존 Reconciliation 보고서의 PASS 상태·건수·Accepted/Quarantine content hash도 입력 검증에 사용했다.

최종 코드로 실제 실행을 두 번 했으며 두 실행 모두 위 건수·schema·PK/FK 검증이 같았다. 두 실행의 Dimension content SHA-256은 `cb1b940e5dcff69603252717aa13aa9d1476667badbd6e0347448d051b603830`, Fact content SHA-256은 `1ad308a036fc8c98e60238539cf5583d6d76585e80f817e2769ad08ab864fb26`로 일치했다. 파일 SHA-256도 각각 `cb84660a2e5048a9e23e8dcc17c03b4f39c2f45762acb4b3234a1a07f822a682`, `ff8c8749d4209ab91c985a18f0d090fc2af42afbc3ef38ba1e6153eef4bb1835`로 일치했다. 최종 두 실행의 UTC 시작 시각은 각각 `2026-11-20T05:49:39`, `2026-11-20T05:50:36`이며 실제 기록은 `logs/violations_gold_runs.jsonl`에 있다.

출력은 `data/03_gold/dimensions/dim_violation.parquet`과 `data/03_gold/facts/fact_inspection_violation.parquet`이다. 컬럼별 변환 및 적용 건수는 `metadata/standards/violations_gold_mapping.csv`에 기록했다. 코드는 `src/gold/violations.py`의 `validate_inputs → dimension_members → build → content_hash` 흐름이다. 기존 입력 파일은 읽기만 하고, 다른 내용의 Gold 출력이 이미 있으면 덮어쓰지 않는다.

`python -m pytest -q --basetemp C:/violations-gold-all-tests-final` 실행 결과 전체 20개 테스트가 통과했다. Gold 전용 테스트는 3개로 grain/PK/FK·건수 정합성·반복 실행·신규 입력 건수 계산·불일치 시 중단을 확인했다. `git diff --check`도 통과했다. Origin, Bronze, 기존 Silver, Accepted Silver, Quarantine의 SHA-256을 이전 기록과 대조해 모두 일치했다. 실제 Gold 실행 로그는 Git 제외 정책에 따라 커밋하지 않는다.

## 다음 연결

Inspection 부모 Gold의 grain·키·중복 기준이 확정되면 Fact의 `inspection_id`를 그 테이블과 검증한 뒤 FK를 추가할 수 있다. 현재는 inspection surrogate key를 만들지 않았다. 공식 violation 코드 사전이 확인되면 설명·분류의 업무 의미를 별도로 검토한다. 기존 Gold 사전검토의 65코드·110조합·45개 다대응 문제를 임의 해결하지 않았다.
