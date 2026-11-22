# 02 위반유형 데이터 스냅샷

팀 공용 Food Inspections CSV에서 만든 Bronze, Silver, Gold 결과입니다. 원천 CSV의 SHA-256은 `b43beb7fae834a8698ca162004caf2929cb2eca7ff75c27b4db6bf07aa103c98`입니다.

아래 표와 체크섬은 당시 Git에 공개한 스냅샷에 해당합니다. 공용 Bronze의 적재 이력을 이어받는 현재 코드는 별도 실행 폴더에 결과를 생성합니다. [현재 실행 및 검증 방법](../../docs/domains/02_violation/folder_structure_alignment.md)

초기 02 실행의 [프로파일](legacy/violations_profile.json), [품질 보고서](legacy/violations_quality_report.csv), [분석 HTML](legacy/violations_analysis.html)은 이 폴더의 `legacy/`에 보관합니다. 당시 변환 기록은 [02 레거시 매핑 폴더](../../metadata/standards/02_violation/legacy/)에 있습니다. 초기 대사 보고서는 03의 예전 입력 경로와 호환되도록 [기존 위치](../quality/violations_reconciliation.json)에 보관합니다.

| 단계 | Parquet | 행 수 | Git에 저장한 형태 |
| --- | --- | ---: | --- |
| Bronze | `02_food_inspections.parquet` | 318,627 | 단일 파일 |
| Silver | `02_inspection_violations.parquet` | 1,031,073 | 2개 조각 |
| Silver | `02_inspection_violations_accepted.parquet` | 1,029,281 | 2개 조각 |
| Silver | `02_inspection_violations_quarantine.parquet` | 1,792 | 단일 파일 |
| Gold | `02_dim_violation.parquet` | 110 | 단일 파일 |
| Gold | `02_fact_inspection_violation.parquet` | 1,029,281 | 2개 조각 |
| Gold | `02_violations_analysis_mart.parquet` | 1,029,281 | 단일 파일 |

파일은 각 데이터 단계의 `02_violation/`에 있습니다. 100 MB가 넘는 Parquet은 앞부분과 뒷부분을 바이트 단위로 나눴습니다. 분할 파일과 이어 붙인 원본의 SHA-256은 [체크섬 목록](parquet_sha256sums.txt)에 있습니다.

## 분할 Parquet 복원

Git 저장소 루트에서 Python으로 아래 코드를 실행합니다. 이미 복원된 파일은 체크섬을 확인합니다.

```python
from hashlib import file_digest
from pathlib import Path
from shutil import copyfileobj
from tempfile import NamedTemporaryFile

manifest = Path("reports/02_violation/parquet_sha256sums.txt")
hashes = {
    Path(name): digest
    for digest, name in (line.split("  ", 1) for line in manifest.read_text().splitlines())
}

def verify(path, expected):
    with path.open("rb") as stream:
        if file_digest(stream, "sha256").hexdigest() != expected:
            raise ValueError(f"SHA-256 mismatch: {path}")

for path, expected in hashes.items():
    if path.is_file():
        verify(path, expected)

for target, expected in hashes.items():
    if target.suffix != ".parquet" or target.exists():
        continue
    parts = [target.with_name(f"{target.name}.part-{i:03d}") for i in (1, 2)]
    pending = None
    try:
        with NamedTemporaryFile(dir=target.parent, suffix=".tmp", delete=False) as output:
            pending = Path(output.name)
            for part in parts:
                with part.open("rb") as source:
                    copyfileobj(source, output, length=1024 * 1024)
        verify(pending, expected)
        target.hardlink_to(pending)
    finally:
        if pending is not None:
            pending.unlink(missing_ok=True)
```
