# 식품위생 점검 학습용 AI-ready

점검 전에는 불합격 위험을, 기준 점검 결과를 확인한 뒤에는 발견된 위반의 재발 가능성을 예측할 수 있도록 학습 테이블 두 개를 제공합니다. 같은 점검 이력을 재사용하고, 예측 기준 시각과 정답은 각 과제에서 정의합니다. [팀 기획의 AI-ready 완료 기준](../00_project_plan.md#파이프라인과-완료-기준)

| 테이블 | 한 행과 식별 키 | 기준 시점 | 정답 |
| --- | --- | --- | --- |
| `01_preinspection_failure.parquet` | 점검 1건, `inspection_key` | 해당 점검 직전 | `label_fail_flag`. `FAIL`은 `true`, `PASS`와 `PASS W/ CONDITIONS`는 `false` |
| `03_next_inspection_violation_recurrence.parquet` | 기준 점검의 고유 위반 코드 1건, `inspection_key` + `code_system_version` + `violation_cd` | 기준 점검 결과와 위반 기록을 확인한 직후 | `label_repeat_flag`. 03 Gold가 연결한 다음 비교 대상 점검에서 같은 버전의 코드가 관측되면 `true` |

## 입력과 연결

- **공용 점검** 현재 Git에 포함된 04 Silver 점검본에서 점검 키, 원천 행 번호, 면허번호, 점검일, 결과를 읽습니다. 이 테이블은 02·03이 사용한 것과 같은 공용 원천 318,627행을 담습니다. [04 데이터 모델](../domains/04_license.md)
- **위반 기록** 02 Gold 위반 마트에서 점검별 고유 승인 코드를 구합니다. 02 Silver 격리 파일로 부분 파싱 여부를 확인합니다. 두 입력의 `inspection_id`와 `source_row_num`이 모두 공용 점검과 일치해야 합니다. 승인 코드가 있는 횟수와 격리 조각 없이 파싱된 횟수를 별도 피처로 제공합니다. [02 분석 계약](../domains/02_violation/violation_types_analysis_contract.md)
- **다음 점검의 재발 여부** 03 Gold에서 2018-07-01 이후의 비교 가능 행을 사용합니다. 기준·후속 점검의 키, 날짜, 면허번호, 결과를 공용 점검과 대조하고, 두 점검의 02 코드로 재발 플래그를 검증합니다. 후속 점검 미관측, 같은 날 후보 중복, 위반 기록 공란·파싱 미확정은 정답을 확정할 수 없어 학습에서 제외합니다. [03 마트 연결 기준](../domains/03_repeat_inspection.md#4-연결-방식과-팀에-제공할-컬럼)

과거 피처는 `[기준일 - 365일, 기준일)`에 관측된 같은 면허번호의 기록으로 계산합니다. 같은 날짜의 모든 기록은 해당 날짜 행의 피처 계산을 마친 뒤에 이력에 반영합니다. 면허번호가 없으면 횟수도 결측으로 두고, 번호가 있으나 기간 내 점검 이력이 없으면 횟수를 0으로 둡니다. 두 테이블 모두 점검 횟수, 불합격 횟수, 위반 관측 횟수와 이력 상태를 제공합니다. 재발 테이블에는 기준 점검 결과, 당시 기록된 위반 코드와 개수, 같은 버전의 코드가 과거에 기록된 횟수가 추가됩니다.

원천은 점검일만 제공하므로 위반·결과 기록이 실제 공개된 시각까지 검증할 수 없습니다. 면허번호를 점검 이력 연결에 사용하므로 물리적 사업장과의 일대일 대응은 가정하지 않습니다. 이번 버전의 피처는 점검과 위반 이력으로 구성했습니다. 재발 학습 모집단은 후속 점검에서 위반을 비교할 수 있는 사례로 한정됩니다.

## 시간순 분할과 학습 컬럼

| `split_cd` | 기준일과 정답 관측일 |
| --- | --- |
| `train` | 2023-01-01 이전 |
| `validation` | 2023-01-01 이상, 2025-01-01 이전 |
| `test` | 2025-01-01 이상 |

두 날짜가 같은 구간에 들어가는 사례를 사용합니다. 예를 들어 2022년 12월에 기준 점검을 받고 2023년 1월에 재발 여부가 관측된 행은 훈련 구간을 넘어선 정답을 쓰게 되므로 제외합니다. 각 행의 365일 이력에는 분할 경계 이전에 관측된 기록도 포함될 수 있습니다. 학습 시 계약에서 `role: feature`인 컬럼을 입력으로 선택하고, `target`에 지정된 컬럼을 정답으로 사용합니다. `audit` 컬럼은 점검과 정답을 추적할 때 사용합니다. [컬럼별 타입·역할 계약](../../metadata/feature_dictionary/inspection_training/contract.json)

## 생성과 검증

저장소 루트에서 팀 환경의 Python 및 PyArrow로 실행합니다. Git에 있는 Silver·Gold 스냅샷을 입력으로 읽습니다.

```sh
python -m src.ai_ready.build_inspection_training
python -m src.ai_ready.build_inspection_training --verify
python -m pytest -q tests/ai_ready
```

출력은 `data/ai_ready/inspection_training/<release_id>/`에 생성합니다. 공유 릴리스는 Parquet 두 개, `manifest.json`, `validation_summary.json`을 함께 버전 관리합니다. 매니페스트에는 원천·입력·코드·결과 체크섬과 PyArrow 버전이 들어가고, 검증 결과에는 분할별 행 수와 정답 분포, 제외 사유가 들어갑니다. 같은 입력·코드·PyArrow 버전으로 재실행하면 해당 릴리스를 검증합니다. `--output-dir`로 출력 상위 폴더를 지정할 수 있습니다. [생성 코드](../../src/ai_ready/build_inspection_training.py) · [실행 결과](../../reports/ai_ready/inspection_training/README.md)
