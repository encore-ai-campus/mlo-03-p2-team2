# 식품위생 점검 AI-ready 생성·검증 결과

2026-11-23에 공용 점검 스냅샷 318,627행으로 릴리스 `ac0d0f3f4f33656e78a6`을 생성했습니다. 점검 관측 종료일은 2026-11-18이며 원천 CSV SHA-256은 `b43beb7fae834a8698ca162004caf2929cb2eca7ff75c27b4db6bf07aa103c98`입니다. Python 3.14와 PyArrow 26.0.1을 사용했습니다. [공용 원천 매니페스트](../../../metadata/lineage/03_repeat_inspection/bronze_manifest.json) · [생성·검증 명령](../../../docs/ai_ready/inspection_training.md#생성과-검증)

| 데이터셋 | Train 행 / 양성 | Validation 행 / 양성 | Test 행 / 양성 | 전체 행 / 양성 |
| --- | ---: | ---: | ---: | ---: |
| 점검 직전 불합격 | 213,919 / 48,048 | 31,408 / 7,316 | 28,161 / 5,980 | 273,488 / 61,344 |
| 다음 점검의 동일 위반 재발 | 179,964 / 72,169 | 60,099 / 24,697 | 47,472 / 19,808 | 287,535 / 116,674 |

- 점검 직전 불합격 테이블은 `PASS`, `PASS W/ CONDITIONS`, `FAIL` 결과가 있는 점검을 담습니다. 평가 결과가 없는 기타 상태 45,139건을 제외했습니다. 면허번호가 없는 평가 완료 점검 745건은 이력 피처를 결측으로 두고 포함했습니다.
- 위반 재발 테이블의 03 Gold 비교 가능 후보는 333,856행입니다. 후속 결과가 기준 점검의 시간 분할 이후에 관측된 46,321행을 제외했습니다. 비교 가능 후보 집계에는 후속 점검 미관측 59,919행, 후속 위반 미확정 45,634행, 기준 위반 미확정 4,153행, 같은 날짜 후보 모호 1,206행이 포함되지 않습니다. [03 Gold 검증](../../../docs/domains/03_repeat_inspection.md#통합-규칙-적용-검증)

## 확인한 항목

- 입력 Parquet의 SHA-256, 원천 스냅샷 지문, 02 위반 상세·격리 기록과 04 점검의 키 및 원천 행 번호를 대조했습니다. 03 재발 정답은 기준·후속 점검 키와 02 승인 코드로 재검증했습니다.
- 생성한 Parquet를 DuckDB로 독립 대조했습니다. 두 테이블의 중복 키, 정답 누락·불일치, 시간 분할 위반은 0건이었습니다. 전체 점검 직전 데이터의 365일 이력과 전체 재발 데이터의 동일 코드 이력도 원천 조인 결과와 일치했습니다.
- 별도 출력 경로에서 새로 생성한 두 Parquet와 검증 JSON의 SHA-256이 일치했습니다. 기존 AI-ready 파일 12개의 SHA-256도 작업 전과 일치했습니다.
- 신규 테스트 3건이 통과했습니다. 전체 테스트는 46건 통과, 기존 04 인허가 테스트 4건 실패였습니다. 변경 전 `main`에서도 04 테스트가 동일하게 실패했고, 테스트용 CSV와 파이프라인이 기대하는 입력 경로가 달랐습니다.

## 결과 파일 SHA-256

| 파일 | SHA-256 |
| --- | --- |
| `01_preinspection_failure.parquet` | `347daa64e1ed72df8cb06ad0b7f3afe5986f474bdf544df8ca2b484f6aefb3d0` |
| `03_next_inspection_violation_recurrence.parquet` | `6ef5fe6bf00e5249c0edbc80cacefb42cded9e2c6f9b259579abc5b57833fd44` |
| `validation_summary.json` | `ccb696e69bfef6ec1a4373c2b1790248eff1b1434f6487ddc6e5cad0106d6480` |

전체 입력·결과 체크섬과 상세 분포는 공유 릴리스에 있습니다. [실행 매니페스트](../../../data/ai_ready/inspection_training/ac0d0f3f4f33656e78a6/manifest.json) · [검증 결과 JSON](../../../data/ai_ready/inspection_training/ac0d0f3f4f33656e78a6/validation_summary.json)
