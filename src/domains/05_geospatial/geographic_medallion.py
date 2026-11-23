"""두 원천 CSV를 보존하는 Bronze와 지역 분석용 Silver를 구축하고 검증한다.

Bronze는 원천 문자열과 논리 레코드 순번을 보존한다. Silver는 컬럼
표준화, 품질 사유, 점검별 지역 배정 및 위반 관측 데이터를 생성한다.
"""

import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import hashlib
from io import StringIO
import json
import os
from pathlib import Path
import re
import tempfile

import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq
import shapely

from geographic_boundary import BOUNDARY_FIELDS, boundary_records
from silver_spatial import assign_community_areas


PROJECT = Path(__file__).resolve().parents[3]
SOURCE_DIR = PROJECT / (os.getenv("CHICAGO_RAW_DIR") or "data/00_origin")
LOCAL_SOURCE_DIR = PROJECT / "origin/05_geospatial"
BRONZE_DIR = Path("01_bronze/05_geospatial")
SILVER_DIR = Path("02_silver/05_geospatial")
GOLD_DIR = Path("03_gold/05_geospatial")
AI_READY_DIR = Path("ai_ready/05_geospatial")
CONTRACT = PROJECT / "metadata/data_dictionary/05_geospatial/column_contract.json"
CODE_MAP = CONTRACT.parents[1] / "shared_code_map.csv"
OFFICIAL_METADATA = PROJECT / "metadata/source_catalog/05_geospatial/official_metadata_snapshot.json"
SCRIPTS = Path(__file__).resolve().parent
CSV_BATCH_ROWS = 12_000
BRONZE_FORMAT_VERSION = 3
BRONZE_TIMESTAMP = pa.timestamp("ms", tz="UTC")
EVALUATED_RESULTS = ("PASS", "PASS W/ CONDITIONS", "FAIL")
NOT_EVALUATED_RESULTS = ("NO ENTRY", "OUT OF BUSINESS", "NOT READY", "BUSINESS NOT LOCATED")
SILVER_ARTIFACTS = {
    "food_inspections.parquet", "community_areas.parquet", "quality_issues.parquet",
    "inspection_community_areas.parquet", "inspection_geography.parquet",
    "inspection_violation_observations.parquet", "inspection_violation_tokens.parquet",
    "inspection_violation_codes.parquet", "code_coverage.csv", "quality_summary.json",
}
TYPES = {
    "date32": pa.date32(),
    "int64": pa.int64(),
    "float64": pa.float64(),
    "string": pa.string(),
}
QUALITY_SCHEMA = pa.schema([
    ("source_dataset", pa.string()),
    ("batch_id", pa.string()),
    ("source_row_num", pa.int64()),
    ("standard_column", pa.string()),
    ("reason_cd", pa.string()),
    ("raw_value", pa.string()),
])


def sha256_file(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def digest_json(value):
    data = json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def utc_now():
    now = datetime.now(timezone.utc)
    return now.replace(microsecond=now.microsecond // 1000 * 1000)


def write_table(path, table):
    pq.write_table(table, path, compression="zstd", row_group_size=CSV_BATCH_ROWS)


def check(condition, message):
    if not condition:
        raise ValueError(message)


def contract_and_codes(fingerprints):
    # 해시를 확인한 바이트를 파싱해 기록과 실제 적용 규칙을 일치시킨다.
    def load_rule(path):
        contents = path.read_bytes()
        check(hashlib.sha256(contents).hexdigest() == fingerprints[str(path.relative_to(PROJECT))],
              f"{path.name}: rule file changed while loading")
        return contents.decode("utf-8")

    contract = json.loads(load_rule(CONTRACT))
    groups = {}
    for dataset, spec in contract["datasets"].items():
        source = [col["source_column"] for col in spec["columns"]]
        standard = [col["standard_column"] for col in spec["columns"]]
        check(len(source) == len(set(source)), f"{dataset}: duplicate source headings")
        check(len(standard) == len(set(standard)) and all(
            re.fullmatch(r"[a-z][a-z0-9_]*", name) for name in standard
        ), f"{dataset}: invalid or duplicate standard headings")
        check(spec["primary_key"] in standard, f"{dataset}: missing contracted primary key")
        for col in spec["columns"]:
            check(col["bronze_type"] == "string" and col["silver_type"] in TYPES,
                  f"{dataset}: invalid storage type for {col['source_column']}")
        mapped = {col["source_column"] for col in spec["columns"] if col["transform"] == "code"}
        check(mapped == set(spec["expected_code_columns"]), f"{dataset}: invalid code group contract")
        groups.update({(dataset, col["source_column"]): col["standard_column"]
                       for col in spec["columns"] if col["source_column"] in mapped})

    maps = {}
    for row in csv.DictReader(StringIO(load_rule(CODE_MAP).removeprefix("\ufeff"), newline="")):
        key = row["dataset"], row["source_column"]
        if key not in groups:
            continue
        codes = maps.setdefault(key, {})
        raw = row["source_value"]
        check(bool(raw) and raw == raw.strip() and raw not in codes,
              f"{key}: invalid or duplicate code map key {raw!r}")
        check(bool(row["standard_code"]) and row["mapping_status"] in {"proposed", "review"}
              and row["target_column"] == groups[key],
              f"{key}: invalid code value, status, or target column")
        codes[raw] = row["standard_code"], row["mapping_status"]
    check(set(maps) == set(groups), "Code map groups differ from the contract")
    result_codes = {code for code, _ in maps["food_inspections", "Results"].values()}
    check(set(EVALUATED_RESULTS + NOT_EVALUATED_RESULTS) <= result_codes,
          "Code map is missing a result with a defined evaluation state")
    return contract, maps


def source_records(path, header, stats=None):
    """Read logical records with no null inference or whitespace normalization."""
    if path.suffix == ".geojson":
        check(tuple(header) == BOUNDARY_FIELDS, f"{path.name}: invalid boundary projection")
        yield from boundary_records(path)
        return
    with path.open(encoding="utf-8-sig", newline="") as file:
        reader = csv.reader(file, strict=True)
        actual = next(reader, None)
        check(actual == header, f"{path.name}: source header differs from the contract")
        for position, record in enumerate(reader, start=1):
            if not any(record):
                if stats is not None:
                    stats["empty_records"] += 1
                continue
            check(len(record) == len(header), f"{path.name}: wrong width at input record {position}")
            yield record


def source_inventory(source_dir, contract, local_snapshot=False):
    inventory = {}
    for dataset, spec in contract["datasets"].items():
        path = source_dir / spec["local_file" if local_snapshot else "file"]
        source_path = path.relative_to(PROJECT) if path.is_relative_to(PROJECT) else path
        header = [col["source_column"] for col in spec["columns"]]
        digest = sha256_file(path)
        if not local_snapshot:
            check(digest == spec["team_sha256"],
                  f"{path.name}: team SHA-256 mismatch (expected {spec['team_sha256']}, got {digest})")
        if path.suffix == ".csv":
            with path.open(encoding="utf-8-sig", newline="") as file:
                check(next(csv.reader(file, strict=True), None) == header, f"{path.name}: source header drift")
        inventory[dataset] = {
            "file": path.name, "source_path": str(source_path),
            "sha256": digest, "size_bytes": path.stat().st_size, "format": path.suffix[1:],
            "header": header, "schema_sha256": digest_json(header), "source_dataset_id": spec["source_id"],
            "source_landing_url": spec["url"], "source_identification": spec.get("identification_status", "metadata_reference"),
            "download_url": None, "extracted_at": None, "source_acquired_at_utc": None,
            "query_filter": None, "sort_order": None,
            "snapshot_as_of": None, "historical_extraction_status": "unknown",
        }
    return inventory


def identity(inventory):
    return {name: {key: item[key] for key in ("file", "sha256", "size_bytes", "header")}
            for name, item in inventory.items()}


def rules_identity():
    inputs = (CONTRACT, CODE_MAP, OFFICIAL_METADATA, SCRIPTS / "geographic_medallion.py",
              SCRIPTS / "geographic_boundary.py", SCRIPTS / "silver_spatial.py", SCRIPTS / "silver_violations.py")
    return {
        "inputs_sha256": {str(path.relative_to(PROJECT)): sha256_file(path) for path in inputs},
        "runtime": {"pyarrow": pa.__version__, "pandas": pd.__version__, "shapely": shapely.__version__,
                    "geos": shapely.geos_version_string},
    }


def verify_artifacts(directory, layer, signature, required_artifacts, batch_id=None):
    manifest = read_json(directory / "manifest.json")
    id_field = "batch_signature" if layer == "bronze" else "rules_signature"
    check(manifest["layer"] == layer and manifest[id_field] == signature,
          f"Different {layer} signature at {directory}")
    if batch_id:
        check(manifest["batch_id"] == batch_id, f"Different Bronze batch for {directory}")
    actual = {path.name for path in directory.iterdir() if path.name != "manifest.json"}
    check(actual == set(manifest["artifacts"]) == required_artifacts,
          f"{layer}: directory or manifest differs from required artifacts")
    for name, expected in manifest["artifacts"].items():
        path = directory / name
        check(sha256_file(path) == expected["sha256"], f"{layer}: checksum mismatch for {name}")
        if path.suffix == ".parquet":
            with pq.ParquetFile(path) as parquet:
                schema = {field.name: str(field.type) for field in parquet.schema_arrow}
                check(parquet.metadata.num_rows == expected["rows"], f"{layer}: row count differs for {name}")
                check(schema == expected["schema"], f"{layer}: schema differs for {name}")
    return manifest


def publish(directory, layer, signature, required_artifacts, build, batch_id=None):
    if directory.exists():
        return verify_artifacts(directory, layer, signature, required_artifacts, batch_id), "verified existing"

    directory.parent.mkdir(parents=True, exist_ok=True)
    # 임시 디렉터리에서 파일을 모두 검증한 후 최종 경로로 게시한다.
    with tempfile.TemporaryDirectory(dir=directory.parent, prefix=".staging-") as tmp:
        staging = Path(tmp) / "output"
        staging.mkdir()
        manifest = build(staging)
        manifest["artifacts"] = {}
        for path in sorted(staging.iterdir()):
            entry = {"sha256": sha256_file(path), "size_bytes": path.stat().st_size}
            if path.suffix == ".parquet":
                with pq.ParquetFile(path) as parquet:
                    entry["rows"] = parquet.metadata.num_rows
                    entry["schema"] = {field.name: str(field.type) for field in parquet.schema_arrow}
            manifest["artifacts"][path.name] = entry
        write_json(staging / "manifest.json", manifest)
        verify_artifacts(staging, layer, signature, required_artifacts, batch_id)
        try:
            staging.rename(directory)
        except OSError:
            if not directory.is_dir():
                raise
            return verify_artifacts(directory, layer, signature, required_artifacts, batch_id), "verified concurrent"
    return manifest, "published"


def bronze_table(path, header, schema, defaults):
    with pq.ParquetWriter(path, schema, compression="zstd") as writer:
        count = 0
        for rows in defaults["records"]:
            arrays = [pa.array(column, type=pa.string()) for column in zip(*rows, strict=True)]
            # 줄바꿈이 포함된 CSV 필드도 논리 레코드 하나로 센다.
            arrays.append(pa.array(range(count + 1, count + len(rows) + 1), type=pa.int64()))
            arrays.extend(pa.repeat(defaults[field.name], len(rows)).cast(field.type)
                          for field in list(schema)[len(header) + 1:])
            writer.write_batch(pa.RecordBatch.from_arrays(arrays, schema=schema))
            count += len(rows)
    return count


def batches(records, size):
    from itertools import batched
    yield from batched(records, size)


def build_bronze(directory, source_dir, inventory, signature, batch_id, source_snapshot_signature, source_mode):
    loaded_at = utc_now()
    sources = {}
    for dataset, item in inventory.items():
        src = source_dir / item["file"]
        header = item["header"]
        schema = pa.schema([(name, pa.string()) for name in header] + [
            ("source_row_num", pa.int64()), ("batch_id", pa.string()), ("source_dataset", pa.string()),
            ("source_file", pa.string()), ("source_sha256", pa.string()),
            ("loaded_at_utc", BRONZE_TIMESTAMP), ("source_ingest_started_at_utc", BRONZE_TIMESTAMP),
        ])
        dest = directory / f"{dataset}.parquet"
        started_at = utc_now()
        stats = Counter()
        count = bronze_table(dest, header, schema, {
            "records": batches(source_records(src, header, stats), CSV_BATCH_ROWS),
            "batch_id": batch_id, "source_dataset": dataset, "source_file": src.name,
            "source_sha256": item["sha256"], "loaded_at_utc": loaded_at,
            "source_ingest_started_at_utc": started_at,
        })
        check(pq.ParquetFile(dest).schema_arrow.equals(schema), f"{dataset}: Bronze schema mismatch")
        check(pq.ParquetFile(dest).metadata.num_rows == count, f"{dataset}: Bronze row count mismatch")
        check(sha256_file(src) == item["sha256"], f"{src.name}: source changed during ingestion")
        sources[dataset] = {
            **item, "rows": count, "empty_records": stats["empty_records"], "local_ingestion_status": "success",
            "ingestion_started_at_utc": started_at.isoformat(timespec="milliseconds"),
            "ingestion_finished_at_utc": utc_now().isoformat(timespec="milliseconds"),
        }
    return {
        "layer": "bronze", "batch_id": batch_id, "batch_signature": signature,
        "bronze_format_version": BRONZE_FORMAT_VERSION, "source_snapshot_signature": source_snapshot_signature,
        "source_mode": source_mode,
        "loaded_at_utc": loaded_at.isoformat(timespec="milliseconds"),
        "ingestion_finished_at_utc": utc_now().isoformat(timespec="milliseconds"),
        "ingestion_code_sha256": sha256_file(Path(__file__)),
        "sources": sources,
    }


def trimmed(raw):
    value = pc.utf8_trim_whitespace(raw)
    return pc.if_else(pc.equal(value, ""), pa.scalar(None, type=pa.string()), value)


def parse_date(value):
    shape = pc.match_substring_regex(value, r"^[0-9]{2}/[0-9]{2}/[0-9]{4}$")
    parsed = pc.strptime(pc.if_else(shape, value, None), "%m/%d/%Y", "s", error_is_null=True)
    roundtrip = pc.equal(pc.strftime(parsed, format="%m/%d/%Y"), value)
    no_year_zero = pc.invert(pc.ends_with(value, "/0000"))
    return pc.if_else(pc.and_kleene(roundtrip, no_year_zero), parsed.cast(pa.date32()), None)


def parse_number(value, integer):
    if integer:
        accepted = pc.match_substring_regex(value, r"^[+-]?[0-9]+$")
        candidate = pc.if_else(accepted, pc.replace_substring_regex(value, r"^\+", ""), None)
        try:
            return candidate.cast(pa.int64())
        except pa.ArrowInvalid:
            def bounded(text):
                if text is None:
                    return None
                sign = -1 if text.startswith("-") else 1
                digits = text.lstrip("-").lstrip("0")
                if len(digits) > 19:
                    return None
                number = sign * int(digits or "0")
                return number if -(2**63) <= number < 2**63 else None
            return pa.array([bounded(item) for item in candidate.to_pylist()], type=pa.int64())
    accepted = pc.match_substring_regex(
        value, r"^[+-]?(?:[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+)(?:\.[0-9]+)?$"
    )
    candidate = pc.replace_substring(pc.if_else(accepted, value, None), ",", "").cast(pa.float64())
    return pc.if_else(pc.is_finite(candidate), candidate, None)


def map_codes(value, mapping):
    indices = pc.index_in(value, value_set=pa.array(list(mapping), type=pa.string()))
    code = pc.take(pa.array([item[0] for item in mapping.values()]), indices)
    status = pc.take(pa.array([item[1] for item in mapping.values()]), indices)
    status = pc.if_else(pc.is_null(value), "missing", pc.fill_null(status, "unmapped"))
    return code, status


def standardize_batch(dataset, spec, raw, maps, issue_tables, code_counts):
    fields = {}
    has_issue = pa.repeat(False, len(raw))
    invalid_coordinates = pa.repeat(False, len(raw))

    def record_issue(column, reason, original, predicate):
        nonlocal has_issue
        mask = pc.fill_null(predicate, False)
        if pc.any(mask).as_py():
            has_issue = pc.or_(has_issue, mask)
            index = pc.indices_nonzero(mask)
            issue_tables.append(pa.Table.from_arrays([
                pa.repeat(dataset, len(index)), pc.take(raw["batch_id"], index),
                pc.take(raw["source_row_num"], index), pa.repeat(column, len(index)),
                pa.repeat(reason, len(index)), pc.take(original, index),
            ], schema=QUALITY_SCHEMA))
        return mask

    # 컬럼 변환과 품질 사유 기록을 같은 배치에서 수행한다.
    for col in spec["columns"]:
        source, name = col["source_column"], col["standard_column"]
        original = raw[source]
        value = trimmed(original)
        mode = col["transform"]
        if mode == "code":
            code, status = map_codes(value, maps[dataset, source])
            fields[name] = code
            fields[f"{name}_raw"] = original
            fields[f"{name}_mapping_status"] = status
            code_counts.update(zip([source] * len(raw), original.to_pylist(), code.to_pylist(), status.to_pylist(), strict=True))
            for flag in ("unmapped", "review", "missing"):
                record_issue(name, f"CODE_{flag.upper()}", original, pc.equal(status, flag))
            continue

        if mode in {"date", "integer", "number"}:
            result = parse_date(value) if mode == "date" else parse_number(value, mode == "integer")
            invalid = record_issue(name, "PARSE_FAILED", original, pc.and_(pc.is_valid(value), pc.is_null(result)))
            if name in {"latitude", "longitude"}:
                limit = 90 if name == "latitude" else 180
                beyond = record_issue(name, "COORDINATE_OUT_OF_RANGE", original, pc.greater(pc.abs(result), limit))
                invalid_coordinates = pc.or_(invalid_coordinates, pc.or_(invalid, beyond))
            if name == "inspection_dtm":
                record_issue(name, "MISSING_INSPECTION_DATE", original, pc.is_null(value))
            if name == "community_area_num":
                record_issue(name, "AREA_OUT_OF_RANGE", original,
                             pc.or_(pc.less(result, 1), pc.greater(result, 77)))
        elif mode == "inspection_license":
            sentinel = pc.is_in(value, value_set=pa.array(["0", "9999999"]))
            record_issue(name, "SENTINEL_LICENSE_NUMBER", original, sentinel)
            record_issue(name, "MISSING_LICENSE_NUMBER", original, pc.is_null(value))
            result = pc.if_else(sentinel, None, value)
        elif mode == "preserve":
            result = pc.if_else(pc.is_valid(value), original, None)
        else:
            check(mode == "text", f"Unsupported transform: {mode}")
            result = value
            if name == "zip_code":
                valid_postal = pc.match_substring_regex(value, r"^[0-9]{5}(?:-[0-9]{4})?$")
                record_issue(name, "ZIP_FORMAT_REVIEW", original, pc.invert(valid_postal))
        fields[name] = result

    if dataset == "food_inspections":
        fields["coordinate_invalid_flag"] = invalid_coordinates
    fields.update(source_row_num=raw["source_row_num"], batch_id=raw["batch_id"],
                  quality_status_cd=pc.if_else(has_issue, "review", "standardized"))
    return pa.table(fields)


def standardize(directory, bronze_dir, contract, maps, boundary_sha):
    issue_tables = []
    code_counts = Counter()
    for dataset, spec in contract["datasets"].items():
        bronze = pq.ParquetFile(bronze_dir / f"{dataset}.parquet")
        parts = [standardize_batch(dataset, spec, batch, maps, issue_tables, code_counts)
                 for batch in bronze.iter_batches(batch_size=CSV_BATCH_ROWS)]
        check(bool(parts), f"{dataset}: source snapshot has no rows")
        table = pa.concat_tables(parts)
        key = table[spec["primary_key"]]
        check(len(table) == bronze.metadata.num_rows and key.null_count == 0
              and pc.count_distinct(key).as_py() == len(table), f"{dataset}: row count/key grain violated")
        for col in spec["columns"]:
            check(table[col["standard_column"]].type == TYPES[col["silver_type"]],
                  f"{dataset}: Silver type differs for {col['standard_column']}")
        if dataset == "community_areas":
            table = table.append_column("boundary_version", pa.repeat(boundary_sha, len(table)))
        write_table(directory / f"{dataset}.parquet", table)
    issues = pa.concat_tables(issue_tables) if issue_tables else pa.Table.from_batches([], schema=QUALITY_SCHEMA)
    write_table(directory / "quality_issues.parquet", issues)
    with (directory / "code_coverage.csv").open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(["source_column", "raw_value", "standard_code", "mapping_status", "row_count"])
        for (column, raw, code, status), count in sorted(code_counts.items()):
            writer.writerow([column, raw, code, status, count])
    return {column: dict(Counter(issues[column].to_pylist())) for column in ("reason_cd", "source_dataset")}


def spatial_assignment(points, areas, boundary, invalid_coordinates):
    assigned, summary = assign_community_areas(points, areas, boundary["sha256"], invalid_coordinates)
    summary["boundary"].update(
        source_file=boundary["file"], source_format=boundary["format"],
        axis_assumption=("GeoJSON positions are longitude/latitude" if boundary["format"] == "geojson"
                         else "WKT x/y treated as longitude/latitude in decimal degrees"),
    )
    spatial = pa.Table.from_pandas(assigned, preserve_index=False).replace_schema_metadata(None)
    for name in ("inspection_key", "community_area_match_status", "boundary_version"):
        index = spatial.schema.get_field_index(name)
        spatial = spatial.set_column(index, name, spatial[name].cast(pa.string()))
    check(len(spatial) == len(points), "Spatial assignment changed the inspection row count")
    return spatial, summary


def derive_geography(directory, boundary):
    inspect_path = directory / "food_inspections.parquet"
    points = pq.read_table(
        inspect_path, columns=["inspection_key", "latitude", "longitude", "coordinate_invalid_flag"]
    ).to_pandas()
    areas = pq.read_table(directory / "community_areas.parquet", columns=["community_area_num", "geometry"]).to_pandas()
    spatial, summary = spatial_assignment(points, areas, boundary, points["coordinate_invalid_flag"])
    write_table(directory / "inspection_community_areas.parquet", spatial)
    return spatial, summary


def append_evaluation(geography, result):
    evaluated = pc.is_in(result, value_set=pa.array(EVALUATED_RESULTS))
    failed = pc.fill_null(pc.equal(result, "FAIL"), False)
    not_evaluated = pc.is_in(result, value_set=pa.array(NOT_EVALUATED_RESULTS))
    evaluation = pc.if_else(evaluated, "EVALUATED", pc.if_else(not_evaluated, "NOT_EVALUATED", "UNKNOWN_RESULT"))
    for name, values in (("evaluated_flag", evaluated), ("failed_flag", failed), ("evaluation_status_cd", evaluation)):
        geography = geography.append_column(name, values)
    return geography


def inspection_summary(geography, inspection_dates):
    date_range = pc.min_max(inspection_dates).as_py()
    return {
        "inspection_count": len(geography), "assigned_count": len(geography) - geography["community_area_num"].null_count,
        "evaluated_count": pc.sum(geography["evaluated_flag"]).as_py(),
        "failed_count": pc.sum(geography["failed_flag"]).as_py(),
        "evaluation_status": dict(Counter(geography["evaluation_status_cd"].to_pylist())),
        "date_range": {key: str(value) if value is not None else None for key, value in date_range.items()},
    }


def derive_analysis_tables(directory, spatial):
    from silver_violations import parse_violations

    selected = pq.read_table(directory / "food_inspections.parquet", columns=[
        "inspection_key", "inspection_dtm", "source_row_num", "batch_id", "violations_text",
        "result_cd", "facility_type", "inspection_type", "risk_level_cd",
    ])
    observations, tokens, codes, violation_summary = parse_violations(selected)
    for name, table in (("observations", observations), ("tokens", tokens), ("codes", codes)):
        write_table(directory / f"inspection_violation_{name}.parquet", table)

    # 점검 키와 순서가 일치할 때 지역·위반 파생 컬럼을 붙인다.
    key = selected["inspection_key"].combine_chunks()
    for reference in (spatial, observations):
        check(reference["inspection_key"].cast(pa.string()).combine_chunks().equals(key),
              "One-to-one inspection join changed keys or row order")
    geography = selected.drop_columns(["violations_text"])
    for field in spatial.schema:
        if field.name != "inspection_key":
            geography = geography.append_column(field, spatial[field.name])
    for field in observations.schema:
        if field.name not in {*geography.column_names, "violations_text"}:
            geography = geography.append_column(field, observations[field.name])
    geography = append_evaluation(geography, geography["result_cd"])
    write_table(directory / "inspection_geography.parquet", geography)
    return violation_summary, inspection_summary(geography, selected["inspection_dtm"])


def build_silver(directory, bronze_dir, bronze, contract, maps, rules, signature):
    boundary = bronze["sources"]["community_areas"]
    issues = standardize(directory, bronze_dir, contract, maps, boundary["sha256"])
    spatial, spatial_summary = derive_geography(directory, boundary)
    violations, inspection = derive_analysis_tables(directory, spatial)
    check(rules_identity() == rules, "Rules or reference files changed during the Silver build")
    check(sha256_file(bronze_dir / "manifest.json") == bronze["manifest_sha256"],
          "Bronze manifest changed during the Silver build")
    write_json(directory / "quality_summary.json", {
        "inspection": inspection, "spatial": spatial_summary, "violations": violations, "field_issues": issues,
    })
    return {
        "layer": "silver", "batch_id": bronze["batch_id"], "rules_id": signature[:20],
        "rules_signature": signature, "bronze_manifest_sha256": bronze["manifest_sha256"],
        "built_at_utc": utc_now().isoformat(), "contract_version": contract["version"],
        "mapping_version": contract["mapping_version"], "source_mode": bronze["source_mode"], **rules,
    }


def run(action, source_dir, data_dir, local_snapshot=False):
    rules = rules_identity()
    contract, maps = contract_and_codes(rules["inputs_sha256"])
    inventory = source_inventory(source_dir, contract, local_snapshot)
    source_snapshot_signature = digest_json(identity(inventory))
    batch_signature = digest_json({"source_snapshot_signature": source_snapshot_signature,
                                   "bronze_format_version": BRONZE_FORMAT_VERSION})
    batch_id = batch_signature[:20]
    bronze_dir = data_dir / BRONZE_DIR / batch_id
    bronze_artifacts = {f"{dataset}.parquet" for dataset in inventory}
    if action in {"all", "bronze"}:
        bronze, status = publish(
            bronze_dir, "bronze", batch_signature, bronze_artifacts,
            lambda path: build_bronze(path, source_dir, inventory, batch_signature, batch_id,
                                      source_snapshot_signature, "local" if local_snapshot else "team"),
        )
    else:
        bronze, status = verify_artifacts(
            bronze_dir, "bronze", batch_signature, bronze_artifacts,
        ), "verified existing"
    print(f"Bronze {status}: {bronze_dir}", flush=True)
    if action == "bronze":
        return

    bronze["manifest_sha256"] = sha256_file(bronze_dir / "manifest.json")
    signature = digest_json({"rules": rules, "bronze_manifest_sha256": bronze["manifest_sha256"]})
    silver_dir = data_dir / SILVER_DIR / batch_id / signature[:20]
    if action == "verify":
        silver, status = verify_artifacts(
            silver_dir, "silver", signature, SILVER_ARTIFACTS, batch_id,
        ), "verified existing"
    else:
        silver, status = publish(silver_dir, "silver", signature, SILVER_ARTIFACTS,
                                 lambda path: build_silver(path, bronze_dir, bronze, contract, maps, rules, signature),
                                 batch_id)
    check(silver["bronze_manifest_sha256"] == bronze["manifest_sha256"], "Silver has a different Bronze manifest")
    print(f"Silver {status}: {silver_dir}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("bronze", "silver", "all", "verify"))
    parser.add_argument("--source-dir", type=Path)
    parser.add_argument("--local-snapshot", action="store_true", help="Use the local 05 CSVs for comparison")
    parser.add_argument("--data-dir", type=Path, default=PROJECT / "data")
    args = parser.parse_args()
    csv.field_size_limit(16 * 1024 * 1024)
    source_dir = args.source_dir or (LOCAL_SOURCE_DIR if args.local_snapshot else SOURCE_DIR)
    run(args.action, source_dir.resolve(), args.data_dir.resolve(), args.local_snapshot)
