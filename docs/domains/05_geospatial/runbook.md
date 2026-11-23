# 로컬 실행 및 팀 통합 검증

저장소 루트에서 실행한다. 검증 환경은 Python 3.14.7이다. [05 의존성](../../../src/domains/05_geospatial/requirements.txt)

```bash
python3.14 -m venv .venv
source .venv/bin/activate
python -m pip install -r src/domains/05_geospatial/requirements.txt
```

## 팀 통합 입력

팀이 제공한 `food_inspections.csv`와 `community_areas.geojson`을 `data/00_origin/`에 둔다. 파이프라인은 파일 내용을 팀 기준 SHA-256과 대조한다. 다른 원천 경로는 `--source-dir` 또는 셸 환경 변수 `CHICAGO_RAW_DIR`로 지정한다. [원천 지문과 현재 확인 상태](../../../reports/05_geospatial/README.md#팀-통합-입력)

Gold에 01 점검 Silver Parquet 경로와 02 공유 Parquet 두 개가 있는 디렉터리를 전달한다.

| 생산자 | 입력 | 필수 컬럼 |
| --- | --- | --- |
| 01 | 공용 점검 Silver | 문자열 `inspection_key`, `license_number_key`, `result_cd`, `risk_level_cd`, `facility_type`, `inspection_type`, `violations_text`. 날짜 `inspection_dtm`은 `date32`, 좌표 `latitude`·`longitude`는 `float64`, `source_row_num`은 `int64` |
| 02 | `inspection_violation_codes.parquet` | 문자열 `inspection_key`, `code_system_version`, `violation_cd`. 선택 문자열 `description_text` |
| 02 | `inspection_violation_observations.parquet` | 점검당 한 행의 문자열 `inspection_key`, `violation_observation_status`. 상태는 `parsed`, `partial`, `unrecognized`, `raw_missing` |

팀 기준의 Bronze 공유는 원천 단위로 관리한다. 아래 Bronze·Silver 명령은 05 관점의 지역 배정 및 독립 대조용 산출물을 생성한다. 집계용 점검 정보와 위반 관측은 각각 01·02 산출물에서 받는다.

## 구축

먼저 관점별 지역 배정을 생성한다.

```bash
domain=src/domains/05_geospatial
layers="$(python "$domain/geographic_medallion.py" all)"
printf '%s\n' "$layers"
bronze_dir="$(printf '%s\n' "$layers" | sed -n 's/^Bronze [^:]*: //p')"
silver_dir="$(printf '%s\n' "$layers" | sed -n 's/^Silver [^:]*: //p')"
```

`inspection_silver`와 `violations_dir`에 01·02가 공유한 실제 경로를 지정하고 실행한다.

```bash
gold="$(python "$domain/geographic_gold.py" build --silver-dir "$silver_dir" \
  --inspection-silver "$inspection_silver" --shared-violations-dir "$violations_dir")"
printf '%s\n' "$gold"
gold_dir="${gold##*: }"
python "$domain/geographic_ai_ready.py" build --gold-dir "$gold_dir"
```

관점별 결과는 `data/01_bronze/05_geospatial/`, `data/02_silver/05_geospatial/`, `data/03_gold/05_geospatial/`, `data/ai_ready/05_geospatial/` 아래의 버전 경로에 저장된다. 같은 입력과 규칙으로 재실행하면 해당 버전의 산출물을 검사한다. 공유 스냅샷은 체크섬을 포함해 Git으로 관리한다.

## 검증

구축 명령을 실행한 셸에서 같은 입력 경로를 사용한다. 기존 WKT 파일과 비교하려면 독립 검증에서 `--compare-wkt`를 지정한다.

```bash
python "$domain/geographic_medallion.py" verify
python "$domain/geographic_gold.py" verify --silver-dir "$silver_dir" \
  --inspection-silver "$inspection_silver" --shared-violations-dir "$violations_dir"
python "$domain/geographic_ai_ready.py" verify --gold-dir "$gold_dir"

mkdir -p reports/runs/05_geospatial
python "$domain/audit_geographic_silver.py" --bronze-dir "$bronze_dir" --silver-dir "$silver_dir" \
  --compare-wkt origin/05_geospatial/export.csv > reports/runs/05_geospatial/team_audit.json

python -m unittest discover -s tests/domains/05_geospatial -v
```

독립 검증은 원천 논리 레코드와 Bronze·Silver를 대조하고 지역 배정·평가 상태·위반 파싱을 재계산한다. WKT 비교는 두 파일의 해시, 지역 번호와 도형, 배정 상태와 후보 목록의 차이를 기록한다. WKT의 원래 좌표계는 별도 증빙이 필요하다. 팀 Gold는 01·02의 입력 파일 지문과 점검·위반 키를 확인하고, 집계 건수와 분모를 대조한다.

## 기존 05 결과 재현

`origin/05_geospatial/`의 `Food_Inspections_20261120.csv`와 `export.csv`로 로컬 배치를 재현한다. 이 배치의 매니페스트에는 `source_mode=local`이 기록된다.

```bash
domain=src/domains/05_geospatial
python "$domain/geographic_medallion.py" all --local-snapshot
gold="$(python "$domain/geographic_gold.py" build --local-snapshot)"
printf '%s\n' "$gold"
python "$domain/geographic_ai_ready.py" build --gold-dir "${gold##*: }"
```

로컬 독립 검증에는 위 Bronze·Silver 출력 경로 및 `--source-dir origin/05_geospatial`을 전달한다. Gold는 기간, 시설 유형, 점검 유형, 위험 등급, 지역 번호 필터를 지원한다. 조건별 릴리스의 검증에는 구축과 동일한 옵션을 사용한다.

## 공유 스냅샷의 분할 Parquet 복원

공유된 두 로컬 비교 배치의 `inspection_violation_tokens.parquet`는 각각 100 MB를 넘으므로 바이트 단위로 분할했다. 분할본은 `data/02_silver/05_geospatial/snapshot_parts/`에 있다. 아래 명령은 저장소 루트에서 분할본과 원본의 SHA-256을 확인하고, 복원본이 없으면 Silver 매니페스트가 참조하는 위치에 생성한다. [분할·원본 체크섬](../../../reports/05_geospatial/split_snapshot_parts.json)

```bash
python - <<'PY'
import json
from pathlib import Path
from shutil import copyfileobj
from tempfile import TemporaryDirectory

from src.ingestion.restore_origin import checksum

index = Path("reports/05_geospatial/split_snapshot_parts.json")
for relative, spec in json.loads(index.read_text(encoding="ascii")).items():
    target = Path(relative)
    parts = [Path(part["path"]) for part in spec["parts"]]
    for part, info in zip(parts, spec["parts"], strict=True):
        if checksum(part) != info["sha256"]:
            raise ValueError(f"SHA-256 mismatch: {part}")
    if target.exists():
        if checksum(target) != spec["sha256"]:
            raise ValueError(f"SHA-256 mismatch: {target}")
        continue
    with TemporaryDirectory(dir=target.parent.parent) as pending:
        restored = Path(pending) / target.name
        with restored.open("wb") as output:
            for part in parts:
                with part.open("rb") as source:
                    copyfileobj(source, output, length=1024 * 1024)
        if checksum(restored) != spec["sha256"]:
            raise ValueError(f"Restored SHA-256 mismatch: {target}")
        target.hardlink_to(restored)
PY
```

## Python 파일별 역할

| 파일 | 역할 |
| --- | --- |
| [`geographic_medallion.py`](../../../src/domains/05_geospatial/geographic_medallion.py) | 원천 지문 검사, 논리 레코드 계보, Bronze·Silver 구축 |
| [`geographic_boundary.py`](../../../src/domains/05_geospatial/geographic_boundary.py) | 팀 GeoJSON 속성·좌표 읽기, 이전 WKT와 비교 |
| [`silver_spatial.py`](../../../src/domains/05_geospatial/silver_spatial.py) | 경계 도형 검증, 좌표 교차, Community Area 배정 |
| [`silver_violations.py`](../../../src/domains/05_geospatial/silver_violations.py) | 로컬 비교용 위반 원문·관측 상태·고유 코드 구조화 |
| [`geographic_integration.py`](../../../src/domains/05_geospatial/geographic_integration.py) | 01 점검 Silver와 02 공용 위반 입력의 타입·키·관측 상태 대조 |
| [`geographic_gold.py`](../../../src/domains/05_geospatial/geographic_gold.py) | 비교 조건 적용, 지역·기간별 지표 산정 및 대사 |
| [`geographic_ai_ready.py`](../../../src/domains/05_geospatial/geographic_ai_ready.py) | 지역 키와 코드 관측 상태 추가, 의미 계약 검증 |
| [`audit_geographic_silver.py`](../../../src/domains/05_geospatial/audit_geographic_silver.py) | 원천·Bronze·Silver 전수 대조, 공간·위반 독립 검증 |
