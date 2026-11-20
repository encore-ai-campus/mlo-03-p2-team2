# 04 사업체 인허가 · AS-IS와 단계별 변환 기록

인허가 발급·갱신 기록과 위생점검을 연결해, 점검 당시 기록된 인허가 기간에 어떤 면허가 후보였는지 확인합니다. 점검 1건마다 후보 수와 상태를 남겨 반복 점검이나 불합격률 집계에서 행이 늘어나는 일을 방지합니다. [초기 프로젝트 기획서](../00_project_plan.md)

## AS-IS 원천 데이터 프로파일링

현재 공용 점검 **318,627행 × 17열**과 인허가 **1,212,132행 × 37열**을 기준으로 조사했습니다. 면허번호만으로 비교하면 점검의 **94.80%**, 점검일을 유효기간에 대조하면 **73.37%**에서 후보가 한 건 이상이었습니다. [원천 파일과 조사 기준](04_license/00_origin/README.md) · [현재 공용 원천 체크섬](../../metadata/source_catalog/verification/download_manifest.csv)

| 항목 | 관측 결과 | 분석에 미치는 영향 |
| --- | --- | --- |
| 점검 면허번호 결측·이상값 | 빈칸 19건, `0` 840건, `9999999` 1건. 총 **860건(0.27%)** | 해당 값으로는 인허가를 특정하기 어렵습니다. |
| 인허가 면허번호 결측 | `LICENSE NUMBER` 빈칸 **1건** | 해당 인허가 기록은 면허번호로 연결할 수 없습니다. |
| 인허가 유효기간 결측 | 시작일 **2,719건(0.2243%)**, 만료일 **170건(0.0140%)** | 날짜 한쪽이 없어 점검일이 유효기간에 포함되는지 판단하기 어렵습니다. |
| 인허가 기간 역전 | 만료일이 시작일보다 빠른 기록 **2,963건(0.2444%)** | 날짜 형식 검사는 통과해도 기간 비교에 사용할 수 없습니다. |
| 특이한 만료일 | `0206-08-17` 1건, `1901-01-01` 4건, `9999-01-01` 1건 | 앞의 5건은 기간 역전에도 포함됩니다. 6건 모두 실제 점검 후보에 들어가지 않았습니다. |
| 인허가 상태와 변경일 | 변경일 결측 **1,131,478건**이 모두 발급 상태 `AAI`. 검토가 필요한 상태 `INQ` **1건** | 공란은 상태에 따라 의미가 달라집니다. 취소·철회 등의 기준일 효과는 합의가 필요합니다. |
| 인허가 키 반복 | 비결측 면허번호 **350,803개** 중 **210,000개**가 반복됩니다. 원천 `ID`는 241개 값이 반복됐고, `LICENSE ID`는 전체 행에서 유일했습니다. | 한 점검에 인허가 기록이 여러 건 붙을 수 있어 후보 수를 별도로 기록해야 합니다. |

| 점검 한 건의 후보 수 | 면허번호만 비교 | 면허번호와 점검일 유효기간을 함께 비교 |
| --- | ---: | ---: |
| 0건 | 16,584 | 84,843 |
| 1건 | 35,899 | 232,383 |
| 2건 이상 | 266,144 | 1,401 |

빈 면허번호와 `0`, `9999999`는 두 비교에서 후보 0건으로 잡았습니다. 기간 비교는 시작일과 만료일 양쪽을 포함하며, 시작일·만료일이 비어 있거나 역전된 기록은 제외했습니다. [Gold 상태별 상세](04_license/03_gold/README.md) · [품질 규칙 검토](04_license/quality/README.md) · [기존 318,552행과 매칭 결과 비교](../../reports/04_license/match_comparison.md)

## 단계별 변환 기록

| 단계 | 입력 → 출력 | 변환 내용 | 상세 기록 |
| --- | --- | --- | --- |
| 00 Origin | `data/00_origin/`의 점검·인허가 CSV와 컬럼 설명 JSON | 원천 컬럼, 제공 타입, 결측·형식·키, 스냅샷 체크섬 확인 | [00 Origin](04_license/00_origin/README.md) |
| 01 Bronze | 원천 CSV 2개 → `data/01_bronze/04_license/`의 Parquet 2개와 적재 기록 | 원천 컬럼·문자열 값 보존, `source_row_num` 추가 | [01 Bronze](04_license/01_bronze/README.md) |
| 02 Silver | Bronze Parquet 2개 → `data/02_silver/04_license/`의 Parquet 2개 | 필요한 업무 컬럼 선택, 이름·타입·결측·코드 표준화 | [02 Silver](04_license/02_silver/README.md) |
| 품질 검사 | Bronze·Silver Parquet → `reports/runs/04_license/`의 MD·CSV | 13개 결정 ID로 표준화 전후 위반 비교 | [품질 검사](04_license/quality/README.md) · [공유 보고서](../../reports/04_license/README.md) |
| 03 Gold | Silver Parquet 2개 → `data/03_gold/`의 사실 2개·차원 3개 | 점검일의 기간 후보 집계와 키 연결 | [03 Gold](04_license/03_gold/README.md) |

[컬럼 변환 목록 CSV](../../metadata/lineage/04_license/column_lineage.csv)에서 출력 컬럼 한 개당 한 행으로 입력 파일과 컬럼, 출력 파일과 컬럼, 타입, 처리 방식, 기존 결정 ID를 확인할 수 있습니다. 여러 입력은 `+`로 표시합니다. Bronze의 신규 순번처럼 원천 컬럼이 없는 경우 입력 컬럼은 비워 둡니다. 결정 ID는 기존 Silver 데이터 사전에 등록된 규칙에 표시합니다. [공유 스냅샷 Bronze 매니페스트](../../metadata/lineage/04_license/bronze_manifest.json)

표준화 규칙이 바뀌면 실행용 데이터 사전과 영향받는 단계 문서, 컬럼 변환 목록을 함께 맞춥니다. 수치를 다시 측정할 때는 사용한 원천 스냅샷과 집계 기준을 남깁니다.

## 실행

프로젝트 루트에서 [실행 환경 설정](../project_setup_and_sharing.md)에 따라 `pro_2`를 활성화한 뒤 실행합니다. 단계별 검증 스크립트는 실패하면 종료 코드 1을 반환하고, 검사별 판정을 CSV로 기록합니다.

```powershell
python src/ingestion/restore_origin.py --restore
$domain = 'src/domains/04_license'
$options = @('--raw-dir', 'data/00_origin', '--data-dir', 'data',
             '--report-dir', 'reports/runs/04_license')

python "$domain/01_bronze.py" @options
python "$domain/validate_bronze.py" @options
python "$domain/02_normalize.py" @options
python "$domain/validate_silver.py" @options
python "$domain/03_quality.py" @options
python "$domain/validate_quality.py" @options
python "$domain/04_modeling.py" @options
python "$domain/validate_gold.py" @options
```

[공용 원천 설정 예시](../../config/sources.example.yaml)의 `food_inspections`와 `business_licenses`를 사용합니다. `--sources-config`로 다른 YAML를 지정할 수 있습니다. 각 소스에 `file`, `format`, 선택 사항 `columns`를 지정합니다. `format: xlsx`는 `sheet`로 읽을 시트를 선택하며, 워크북에 저장된 셀 값을 읽습니다. 다른 헤더로 Silver를 만들 때는 `--dictionary`로 대응하는 컬럼 사전을 지정합니다.

기본 원천 폴더는 `data/00_origin/`입니다. 원천 경로를 따로 지정하면 `--raw-dir`, `CHICAGO_RAW_DIR` 환경 변수, `.env` 순서로 적용됩니다. `data/01_bronze/`, `data/02_silver/`, `data/03_gold/`에는 이번 **318,627행** 공용본으로 만든 결과를 둡니다. 같은 입력과 라이브러리 버전으로 다시 돌리면 기존 Parquet와 체크섬을 대조합니다. 새 스냅샷을 검증할 때는 출력 위치를 따로 지정할 수 있습니다.

## 전체 실행, 검증, 추가 데이터 반영

위와 같은 `$domain`, `$options`로 아래 명령을 실행할 수 있습니다. 실행 중 검증에 실패하면 다음 단계로 넘어가기 전에 종료합니다.

```powershell
python "$domain/run_pipeline.py" @options                         # 전체 변환과 검증
python "$domain/run_pipeline.py" @options --start-at silver       # Bronze 검증 후 Silver부터 실행
python "$domain/run_pipeline.py" @options --validate-only         # 생성된 산출물을 단계별로 검증
```

새 파일이 **전체 스냅샷**이면 `--raw-dir`에 새 원천 폴더를 지정하고, `--data-dir`과 `--report-dir`에 새 버전의 경로를 지정해 실행합니다. **추가·수정 행만** 받은 경우에는 다음 순서로 실행합니다. `data/incoming/next`에 `food_inspections.csv`, `business_licenses.csv` 중 받은 파일을 둡니다. 각 행은 기존 CSV의 모든 컬럼을 포함해야 하며, 열 순서는 바뀌어도 됩니다.

```powershell
python "$domain/run_pipeline.py" --raw-dir data/00_origin `
  --delta-dir data/incoming/next --combined-raw-dir data/combined_04/next `
  --data-dir data/team_next --report-dir reports/runs/team_next/04_license
```

`Inspection ID` 또는 `LICENSE ID`가 이미 있으면 해당 위치의 행을 교체하고, 새 키는 파일 끝에 추가합니다. 같은 키에 서로 다른 추가 행이 오면 실행을 중단합니다. 원천과 추가분은 읽기 전용이며, 합친 파일은 `--combined-raw-dir`에 둡니다. 함께 생성되는 `merge_manifest.json`에 원천·추가분·합친 파일의 SHA-256과 추가·수정 건수를 기록합니다. 인허가 변경이 기존 점검에도 영향을 줄 수 있으므로 합친 스냅샷 전체에서 Gold 매칭을 다시 계산합니다.

## 산출물 재현

04번 Parquet는 `data/01_bronze/04_license/` 2개, `data/02_silver/04_license/` 2개, `data/03_gold/04_license/` 5개에 있습니다. 100 MB를 넘는 Bronze 인허가만 같은 폴더에 `.part-001`, `.part-002`로 나눴습니다. 전체 파일과 조각의 SHA-256은 아래 목록에서 확인합니다. [Parquet 체크섬](../../reports/04_license/parquet_sha256sums.txt)

원천 CSV를 복원한 뒤 `python src/domains/04_license/01_bronze.py`를 실행하면 동일한 Bronze 파일을 재생성합니다. 분할 파일에서 직접 복원하려면 저장소 루트에서 다음 코드를 실행합니다. `xb`는 기존 파일을 보호합니다.

```python
from pathlib import Path
from shutil import copyfileobj

bronze = Path("data/01_bronze/04_license/04_business_licenses.parquet")
first = bronze.with_name(bronze.name + ".part-001")
second = bronze.with_name(bronze.name + ".part-002")
with first.open("rb") as left, second.open("rb") as right, bronze.open("xb") as output:
    copyfileobj(left, output)
    copyfileobj(right, output)
```

공용본은 Python 3.14.10과 PyArrow 26.0.1로 검증했습니다. 동일한 환경에서 생성한 파일은 SHA-256으로 비교할 수 있습니다. 새 경로에 처음 적재하면 `ingestion_manifest.json`에 실제 적재 시각이 기록됩니다.
