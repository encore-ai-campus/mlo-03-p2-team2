# 팀 실행 환경과 저장소 구조

## Conda 환경

프로젝트 루트를 연 Anaconda Prompt에서 아래 명령을 실행합니다. 환경 이름은 `pro_2`이고 Python은 3.14입니다. [환경 정의](../environment.yml)

```powershell
conda env create --file environment.yml
conda activate pro_2
python --version
python -m pytest -q tests/domains/04_license
```

프로젝트 코드의 실행에는 PyArrow, PyYAML, openpyxl이 필요합니다. pytest는 테스트에 사용합니다. Python 3.14 환경은 PyArrow 26.0.1을 사용하고, 기존 Python 3.13 환경에서는 PyArrow 21.0.0으로 만든 스냅샷을 같은 환경으로 재현할 수 있습니다. [04번 의존성](../src/domains/04_license/requirements.txt) · [PyArrow Python 3.14 배포 파일](https://pypi.org/project/pyarrow/26.0.1/)

기존 팀 스냅샷의 Parquet는 새 환경에서 열거나 검증할 수 있습니다. **새 Python 3.14 환경으로 다시 생성할 때는 별도 출력 위치를 사용합니다.** Parquet 기록기 버전이 바뀌면 테이블 값이 같아도 파일 체크섬이 달라질 수 있습니다. 04번 단계 실행 방법은 [04번 문서](domains/04_license.md)에 있습니다.

## VS Code에서 Parquet 보기

VS Code에서 이 프로젝트 폴더를 열고, 명령 팔레트에서 **Python: Select Interpreter → pro_2**를 선택합니다. 이 설정은 VS Code에서 Python과 테스트를 실행할 환경을 지정합니다. [VS Code의 Python 환경 안내](https://code.visualstudio.com/docs/python/environments)

04번 Parquet는 ZSTD 압축을 사용합니다. VS Code에서 파일 탭을 우클릭하고 **Reopen Editor With... → Parquet Grid Viewer**를 선택하면 표로 볼 수 있습니다. Database Client의 Parquet Viewer에서 `unsupported compression codec: ZSTD`가 나오면 ZSTD를 지원하는 뷰어로 다시 엽니다. [Parquet Grid Viewer 확장](https://marketplace.visualstudio.com/items?itemName=zovo.zovo-parquet-viewer)

`EPERM: operation not permitted`가 나오면 Windows에서 현재 계정의 파일 읽기 권한을 확인합니다. 터미널에서는 아래 코드로 처음 5행을 읽을 수 있습니다.

```python
import pyarrow.parquet as pq

with pq.ParquetFile("data/02_silver/04_license/04_food_inspections.parquet") as parquet:
    print(parquet.schema_arrow)
    for batch in parquet.iter_batches(
        batch_size=5, columns=["inspection_key", "inspection_dtm", "result_cd"]
    ):
        print(batch.to_pydict())
        break
```

## 로컬 폴더 구조

| 로컬 위치 | 내용 |
| --- | --- |
| `data/origin/` | 팀 공용 원천 분할 파일, GeoJSON, 컬럼 설명 JSON, 체크섬과 복원된 CSV |
| `data/01_bronze/04_license/` · `data/02_silver/04_license/` | 공용본으로 실행한 04번 원천 보존본과 표준화본 |
| `data/03_gold/04_license/` | 공용본으로 생성한 04번 사실·차원 Parquet |
| `src/domains/04_license/` · `src/ingestion/` | 04번 변환·검증 코드와 원천 프로파일링 코드 |
| `metadata/lineage/04_license/` | 팀 공유 스냅샷의 적재 매니페스트와 컬럼 변환 목록 |
| `reports/04_license/` | 팀 공유 스냅샷의 품질 검사와 단계별 검증 보고서 |
| `reports/runs/04_license/` | 공용본 실행에서 생성한 로컬 보고서 |

`.env`나 환경 변수에서 원천 경로를 지정한 경우 `CHICAGO_RAW_DIR=data/origin`으로 맞춥니다.

공용 점검 CSV는 03번의 `Food_Inspections_20261119.zip`에서 가져온 **318,627행** 버전입니다. 나머지 원천 5개는 기존 파일을 체크섬으로 대조했습니다. 기본 단계 폴더와 공유 보고서는 이 공용본의 결과입니다. [현재 공용 원천 체크섬](../metadata/source_catalog/verification/download_manifest.csv) · [기존·공용본 매칭 비교](../reports/04_license/match_comparison.md)

Bronze·Silver·Gold는 각각 동일한 01~05 관점 폴더를 사용합니다. 예를 들어 04번 Silver 점검 파일은 `data/02_silver/04_license/04_food_inspections.parquet`입니다. [01~05 폴더 구조 Wiki](https://github.com/encore-ai-campus/mlo-03-p2-team2/wiki/Repository-Structure)

## 팀 공용 원천

Git의 `data/origin/`에는 점검·인허가 CSV의 gzip 조각 각 2개, GeoJSON, 설명 JSON 3개와 `SHA256SUMS`가 있습니다. 팀원은 저장소를 받은 뒤 아래 명령으로 같은 폴더에 CSV를 복원합니다. 이미 복원된 파일은 SHA-256을 대조하며, 검증만 할 때는 `--restore`를 빼면 됩니다.

```powershell
python src/ingestion/restore_origin.py --restore
```

분할 조각은 각각 100 MB 이하입니다. 복원한 CSV와 각 파트의 생성 Parquet는 로컬에서 사용하고, Git에는 원천 분할 파일과 변환·검증 코드를 유지합니다. [업로드 파일 SHA-256](../data/origin/SHA256SUMS) · [원천 6개 SHA-256](../metadata/source_catalog/verification/download_manifest.csv)
