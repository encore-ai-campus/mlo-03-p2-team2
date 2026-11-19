# Domain 04 · 사업체 인허가 이력

인허가 발급·갱신 기록과 위생점검을 연결해, 점검 당시 기록된 인허가 기간에 어떤 면허가 후보였는지 확인합니다. 점검 1건마다 후보 수와 상태를 남겨 반복 점검이나 불합격률 집계에서 행이 늘어나는 일을 방지합니다. [초기 프로젝트 기획서](../00_project_plan.md)

## 실행

프로젝트 루트에서 아래 순서로 실행합니다. 단계별 검증 스크립트는 실패하면 종료 코드 1을 반환하고, 검사별 판정을 CSV로 기록합니다.

```powershell
$domain = 'src/domains/04_license'
python -m pip install -r "$domain/requirements.txt"

python "$domain/01_bronze.py"
python "$domain/validate_bronze.py"
python "$domain/02_normalize.py"
python "$domain/validate_silver.py"
python "$domain/03_quality.py"
python "$domain/validate_quality.py"
python "$domain/04_modeling.py"
python "$domain/validate_gold.py"
```

[공용 원천 설정 예시](../../config/sources.example.yaml)의 `food_inspections`와 `business_licenses`를 사용합니다. `--sources-config`로 다른 YAML를 지정할 수 있습니다. 각 소스에 `file`, `format`, 선택 사항 `columns`를 지정합니다. `format: xlsx`는 `sheet`로 읽을 시트를 선택하며, 워크북에 저장된 셀 값을 읽습니다. 다른 헤더로 Silver를 만들 때는 `--dictionary`로 대응하는 컬럼 사전을 지정합니다.

`--raw-dir`은 환경 변수와 로컬 설정보다 우선합니다. 다른 스냅샷을 처리할 때는 `--data-dir`과 `--report-dir`로 출력 위치를 지정할 수 있습니다. 동일한 입력과 라이브러리 버전으로 다시 돌리면 Parquet 내용이 같은지 확인합니다. 기존 Parquet와 다른 결과는 새 출력 위치에 저장합니다.

## 단계별 산출물

| 단계 | 하는 일 | 검증 |
| --- | --- | --- |
| Bronze | 두 입력을 읽어 기본 설정에서는 원천 컬럼 전체를 문자열로 보존합니다. `source_row_num`은 헤더를 뺀 논리 레코드의 1부터 시작하는 순번입니다. | 원천과 Bronze의 스키마, 값, 순서, 행 수 일치 |
| Silver | [데이터 사전](../../src/domains/04_license/%EB%8D%B0%EC%9D%B4%ED%84%B0%20%EC%82%AC%EC%A0%84.csv)에 지정된 04번 컬럼을 표준화합니다. 모든 Bronze 행의 순번을 보존합니다. | 행 수 대사, 표준 이름·타입, 사전대로 변환한 값과 행 순번 확인 |
| 데이터 품질 | `reports/runs/04_license/품질 관리.md`에 차원별·규칙별 비교표를, `quality_comparison.csv`에 규칙별 상세를 기록합니다. 예시는 원천 행 순번입니다. | 결정 ID 유일성, 같은 입력에서 보고서 재생성 결과 일치 |
| Gold | `data/gold/facts/04_license/`와 `data/gold/dimensions/04_license/`에 각각 사실과 차원 Parquet를 저장합니다. | 모든 테이블의 PK 유일성, FK 존재, Silver 키·행 순서와 행 수, 확정 후보의 기간 정합성 |

### 데이터 표준과 품질 결정

| 결정 ID | 기준 |
| --- | --- |
| `D04-N01` | 바깥 공백을 제거하고 공란은 null로 표현합니다. ZIP과 식별 값의 텍스트 표현을 보존합니다. |
| `D04-N02` · `D04-N05` | 양의 숫자 식별자를 문자열로 보존합니다. 점검 면허번호 `0`과 이번 스냅샷의 이상값 후보 `9999999`는 매칭 대상에서 제외합니다. |
| `D04-N03` · `D04-N04` | 범주를 대문자로 통일하고 날짜를 달력 날짜로 저장합니다. 변환에 실패한 값은 Bronze 행 순번으로 추적합니다. |
| `D04-DQ-01`~`D04-DQ-06` · `D04-DQ-10`~`D04-DQ-13` | 번호나 날짜의 결측과 형식 오류를 따로 집계합니다. Silver에서 형식 오류가 null로 바뀐 경우 결측 집계에 반영합니다. |
| `D04-DQ-07` | 만료일이 시작일보다 빠른 기간은 정합성 오류입니다. 인허가 행은 보존하고 기간 매칭 후보에서 제외합니다. |
| `D04-DQ-08` · `D04-DQ-09` | 인허가 신청 유형의 바깥 공백과 공식 설명에서 의미를 확인한 상태 코드의 범위를 검사합니다. 검토 대상 상태는 원천과 Silver에 보존합니다. [시카고시 인허가 설명](https://catalog.data.gov/dataset/business-licenses) |

## Gold 행 단위와 키

| 테이블 | 한 행의 의미 | PK |
| --- | --- | --- |
| `dim_license` | 면허번호 하나 | `license_number_key` |
| `dim_establishment` | 계정번호·사업장 번호 조합 하나 | `establishment_key` |
| `dim_date` | 점검일 또는 인허가 발급일 하나 | `date_key` |
| `fact_license_event` | 출처가 있는 인허가 기록 한 건 | `license_event_key`, 원천 `LICENSE ID` |
| `fact_inspection_license_match` | 점검 한 건 | `inspection_key`, 원천 `Inspection ID` |

두 사실 테이블의 면허번호, 사업장, 날짜 키는 차원에 연결됩니다. 원천 정보가 부족한 키는 차원의 `__unknown__` 항목으로 연결합니다.

면허번호가 같고 `시작일 ≤ 점검일 ≤ 만료일`이면 기간 후보로 계산합니다. 후보가 한 건이면 해당 인허가 기록 ID와 사업장 키를 기록합니다. 후보가 여러 건이면 후보 수만 남기고 연결 결정은 보류합니다. 이 규칙은 기록된 기간을 기준으로 합니다. 취소·철회 시점의 적용과 사업장 속성 변경 이력의 복원은 팀에서 정의할 항목입니다.
