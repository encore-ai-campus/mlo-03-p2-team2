"""원천 CSV와 Bronze·Silver를 대조하여 지역 파이프라인을 독립 검증한다.

적재 모듈을 호출하지 않고 문자열 보존, 표준화, 위치 배정, 평가 상태와
위반 파싱을 재계산한 뒤 점검별 산출물과 비교한다.
"""

import argparse
import csv
import hashlib
import json
import math
import os
import re
from collections import Counter
from contextlib import closing
from datetime import date, datetime, timedelta
from functools import cache
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import shapely

from geographic_boundary import boundary_records, compare_boundaries


PROJECT = Path(__file__).resolve().parents[3]
SOURCE_DIR = PROJECT / (os.getenv("CHICAGO_RAW_DIR") or "data/00_origin")
CONTRACT_DIR = PROJECT / "metadata/data_dictionary/05_geospatial"
ARROW_TYPES = {
    "date32": pa.date32(),
    "float64": pa.float64(),
    "int64": pa.int64(),
    "string": pa.string(),
}
EVALUATED = {"PASS", "PASS W/ CONDITIONS", "FAIL"}
NOT_EVALUATED = {"OUT OF BUSINESS", "NO ENTRY", "NOT READY", "BUSINESS NOT LOCATED"}
SPATIAL_FIELDS = [
    "community_area_num",
    "community_area_match_status",
    "community_area_candidate_count",
    "community_area_candidate_nums",
    "community_area_on_boundary",
    "boundary_version",
]
GEOGRAPHY_CONTEXT = ["source_row_num", "batch_id", "facility_type", "inspection_type", "risk_level_cd"]
VIOLATION_LINEAGE = ["inspection_key", "source_row_num", "batch_id", "inspection_dtm", "code_system_version"]
VIOLATION_SUMMARY = [
    "violation_observation_status",
    "violation_token_count",
    "parsed_violation_token_count",
    "unrecognized_violation_token_count",
    "distinct_parsed_violation_code_count",
    "violation_code_occurrence_ready",
]
COMMENT_MARKER = re.compile(r"(?:^|\s+)-\s+Comments:\s*", re.IGNORECASE)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def parquet_rows(path, columns):
    with pq.ParquetFile(path) as file:
        missing = set(columns).difference(file.schema_arrow.names)
        require(not missing, f"{path.name}: missing fields {sorted(missing)}")
        for batch in file.iter_batches(batch_size=8192, columns=columns):
            values = [batch[name].to_pylist() for name in columns]
            yield from zip(*values, strict=True)


def source_hash(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def read_code_map(path):
    with path.open(encoding="utf-8-sig", newline="") as source:
        rows = csv.DictReader(source)
        return {
            (row["dataset"], row["source_column"], row["source_value"]): (row["standard_code"], row["mapping_status"])
            for row in rows
        }


def normalize(value, transform, codes, dataset, column):
    stripped = value.strip()
    if not stripped:
        return None
    if transform == "preserve":
        return value
    if transform == "text":
        return stripped
    if transform == "inspection_license":
        return None if stripped in {"0", "9999999"} else stripped
    if transform == "code":
        return codes.get((dataset, column, stripped), (None, "unmapped"))[0]
    try:
        if transform == "date":
            month, day, year = stripped.split("/")
            if [len(month), len(day), len(year)] != [2, 2, 4]:
                return None
            return date(int(year), int(month), int(day))
        if transform == "integer":
            digits = stripped[1:] if stripped[0] in "+-" else stripped
            if not digits.isascii() or not digits.isdecimal():
                return None
            number = int(stripped)
            return number if -(2**63) <= number < 2**63 else None
        if transform == "number":
            body = stripped[1:] if stripped[0] in "+-" else stripped
            whole, point, fraction = body.partition(".")
            groups = whole.split(",")
            if any(not group.isascii() or not group.isdecimal() for group in groups):
                return None
            if len(groups) > 1 and (len(groups[0]) > 3 or any(len(group) != 3 for group in groups[1:])):
                return None
            if point and (not fraction.isascii() or not fraction.isdecimal()):
                return None
            number = float(stripped.replace(",", ""))
            return number if math.isfinite(number) else None
    except (ValueError, OverflowError):
        return None
    raise ValueError(f"Unsupported audit transform: {transform}")


def check_schema(bronze_path, silver_path, fields):
    bronze_schema = pq.read_schema(bronze_path)
    silver_schema = pq.read_schema(silver_path)
    source_columns = [field["source_column"] for field in fields]
    require(bronze_schema.names[:len(source_columns)] == source_columns,
            f"{bronze_path.name}: Bronze source column order differs from the contract")
    for field in fields:
        source = field["source_column"]
        target = field["standard_column"]
        require(bronze_schema.field(source).type == pa.string(), f"{source}: expected Bronze string")
        expected_type = ARROW_TYPES[field["silver_type"]]
        require(silver_schema.field(target).type == expected_type,
                f"{target}: expected Silver {expected_type}")
    for schema in (bronze_schema, silver_schema):
        require(schema.field("source_row_num").type == pa.int64(), "source_row_num: expected int64")
        require(schema.field("batch_id").type == pa.string(), "batch_id: expected string")
    if "inspection_key" in silver_schema.names:
        require(silver_schema.field("coordinate_invalid_flag").type == pa.bool_(),
                "coordinate_invalid_flag: expected bool")
    timestamp = bronze_schema.field("loaded_at_utc").type
    require(pa.types.is_timestamp(timestamp) and timestamp.tz == "UTC",
            "loaded_at_utc: expected UTC timestamp")
    if "source_ingest_started_at_utc" in bronze_schema.names:
        expected_timestamp = pa.timestamp("ms", tz="UTC")
        for name in ("loaded_at_utc", "source_ingest_started_at_utc"):
            require(bronze_schema.field(name).type == expected_timestamp, f"{name}: expected millisecond UTC")


def ingestion_times(manifest, dataset, filename, digest):
    source = manifest["sources"][dataset]
    require((source["file"], source["sha256"]) == (filename, digest), f"{dataset}: manifest source mismatch")
    loaded = datetime.fromisoformat(manifest["loaded_at_utc"])
    require(loaded.utcoffset() == timedelta(0), f"{dataset}: batch timestamp is not UTC")
    if manifest.get("bronze_format_version", 1) == 1:
        return loaded, None
    require(Path(source["source_path"]).name == filename, f"{dataset}: incorrect manifest input path")
    require("source_acquired_at_utc" in source and "extracted_at" in source,
            f"{dataset}: missing acquisition or extraction provenance")
    started = datetime.fromisoformat(source["ingestion_started_at_utc"])
    finished = datetime.fromisoformat(source["ingestion_finished_at_utc"])
    batch_finished = datetime.fromisoformat(manifest["ingestion_finished_at_utc"])
    require(all(item.utcoffset() == timedelta(0) for item in (started, finished, batch_finished)),
            f"{dataset}: ingestion timestamps are not UTC")
    require(loaded <= started <= finished <= batch_finished, f"{dataset}: ingestion timestamps are out of order")
    return loaded, started


def quality_reason(column, transform, value, normalized, mapping_status):
    if transform == "code" and mapping_status in {"unmapped", "review", "missing"}:
        return f"CODE_{mapping_status.upper()}"
    if transform == "inspection_license":
        if not value.strip():
            return "MISSING_LICENSE_NUMBER"
        if value.strip() in {"0", "9999999"}:
            return "SENTINEL_LICENSE_NUMBER"
    if transform in {"date", "number", "integer"} and value.strip() and normalized is None:
        return "PARSE_FAILED"
    if column == "inspection_dtm" and not value.strip():
        return "MISSING_INSPECTION_DATE"
    if normalized is None:
        return None
    if column == "latitude" and abs(normalized) > 90 or column == "longitude" and abs(normalized) > 180:
        return "COORDINATE_OUT_OF_RANGE"
    if column == "community_area_num" and not 1 <= normalized <= 77:
        return "AREA_OUT_OF_RANGE"
    if column == "zip_code" and not re.fullmatch(r"[0-9]{5}(?:-[0-9]{4})?", normalized):
        return "ZIP_FORMAT_REVIEW"
    return None


def checked_source_rows(dataset, spec, source_dir, bronze_dir, silver_dir, digest, codes, issues, manifest):
    source_path = source_dir / spec["file"]
    bronze_path = bronze_dir / f"{dataset}.parquet"
    silver_path = silver_dir / f"{dataset}.parquet"
    fields = spec["columns"]
    check_schema(bronze_path, silver_path, fields)
    raw_names = [field["source_column"] for field in fields]
    silver_names = [field["standard_column"] for field in fields]
    transforms = [field["transform"] for field in fields]
    bronze_meta = ["source_row_num", "batch_id", "source_dataset", "source_file", "source_sha256", "loaded_at_utc"]
    expected_load_time, expected_source_start = ingestion_times(manifest, dataset, source_path.name, digest)
    if expected_source_start is not None:
        bronze_meta.append("source_ingest_started_at_utc")
    silver_meta = ["source_row_num", "batch_id", "quality_status_cd"]
    code_fields = [(raw, target) for raw, target, mode in zip(raw_names, silver_names, transforms, strict=True)
                   if mode == "code"]
    code_metadata = [name for _, target in code_fields for name in (f"{target}_raw", f"{target}_mapping_status")]
    bronze_rows = parquet_rows(bronze_path, raw_names + bronze_meta)
    silver_rows = parquet_rows(silver_path, silver_names + silver_meta + code_metadata)
    # 빈 레코드는 따로 세고 검증할 순번은 값이 있는 논리 레코드에만 부여한다.
    def logical_records():
        nonlocal empty_records
        if source_path.suffix == ".geojson":
            yield from boundary_records(source_path)
            return
        with source_path.open(encoding="utf-8-sig", newline="") as source:
            reader = csv.reader(source, strict=True)
            require(next(reader, None) == raw_names, f"{dataset}: raw header differs from the contract")
            for record in reader:
                if any(record):
                    yield record
                else:
                    empty_records += 1

    empty_records = 0
    with closing(logical_records()) as raw_rows:
        row_num = 0
        for row_num, (raw, bronze, silver) in enumerate(zip(raw_rows, bronze_rows, silver_rows, strict=True), 1):
            if tuple(raw) != bronze[:len(raw_names)]:
                raise ValueError(f"{dataset}: raw and Bronze cells differ at source row {row_num}")
            bronze_line, bronze_batch, bronze_dataset, bronze_file, bronze_hash, loaded, *source_times = bronze[len(raw_names):]
            silver_line, silver_batch, quality_status, *extras = silver[len(silver_names):]
            require(bronze_line == silver_line == row_num and bronze_batch == silver_batch == manifest["batch_id"],
                    f"{dataset}: wrong batch or source row number at source row {row_num}")
            require((bronze_dataset, bronze_file, bronze_hash) == (dataset, source_path.name, digest),
                    f"{dataset}: incorrect Bronze file lineage at source row {row_num}")
            require(loaded == expected_load_time and
                    (expected_source_start is None or source_times == [expected_source_start]),
                    f"{dataset}: Bronze row timestamp does not match its ingestion manifest")
            raw_record = dict(zip(raw_names, raw, strict=True))
            expected_code_metadata = []
            mapping_statuses = {}
            for raw_name, target in code_fields:
                value = raw_record[raw_name]
                if value.strip():
                    _, mapping_status = codes.get((dataset, raw_name, value.strip()), (None, "unmapped"))
                else:
                    mapping_status = "missing"
                mapping_statuses[target] = mapping_status
                expected_code_metadata.extend((value, mapping_status))
            require(extras == expected_code_metadata, f"{dataset}: changed code source or status at row {row_num}")
            silver_values = silver[:len(silver_names)]
            row_issues = []
            for raw_name, value, target, actual, transform in zip(
                raw_names, raw, silver_names, silver_values, transforms, strict=True
            ):
                expected = normalize(value, transform, codes, dataset, raw_name)
                if actual != expected:
                    raise ValueError(f"{dataset}: Silver {target} differs from the rule at source row {row_num}")
                reason = quality_reason(target, transform, value, expected, mapping_statuses.get(target))
                if reason:
                    row_issues.append((dataset, bronze_batch, row_num, target, reason, value))
            issues.update(row_issues)
            require(quality_status == ("review" if row_issues else "standardized"),
                    f"{dataset}: incorrect row review state at row {row_num}")
            standard = dict(zip(silver_names, silver_values, strict=True))
            standard.update(source_row_num=row_num, batch_id=bronze_batch)
            yield raw_record, standard, bronze_batch
        require(row_num == manifest["sources"][dataset]["rows"], f"{dataset}: recorded row count differs")
        require(empty_records == manifest["sources"][dataset].get("empty_records", 0),
                f"{dataset}: empty record count differs")


def prepared_boundaries(rows):
    boundaries = {}
    batch_id = None
    for _, area, batch_id in rows:
        area_num = area["community_area_num"]
        require(area_num not in boundaries, f"Duplicate community area number: {area_num}")
        geometry = shapely.from_wkt(area["geometry"])
        require(geometry.geom_type in {"Polygon", "MultiPolygon"} and geometry.is_valid and not geometry.is_empty,
                f"Invalid geometry in community area {area_num}")
        shapely.prepare(geometry)
        boundaries[area_num] = (geometry.bounds, geometry)
    require(set(boundaries) == set(range(1, 78)), "Boundary keys must cover all 77 Chicago community areas")
    return boundaries, batch_id


def spatial_lookup(boundaries, boundary_hash):
    # 공간 결합의 독립 검증은 경계 상자와 폴리곤을 직접 검사한다.
    @cache
    def lookup(longitude, latitude):
        point = shapely.Point(longitude, latitude)
        hits = []
        for number, (bounds, polygon) in sorted(boundaries.items()):
            xmin, ymin, xmax, ymax = bounds
            if xmin <= longitude <= xmax and ymin <= latitude <= ymax and polygon.intersects(point):
                hits.append(number)
        if len(hits) == 1:
            number = hits[0]
            return number, "unique_area", 1, tuple(hits), not boundaries[number][1].contains(point), boundary_hash
        status = "multiple_boundaries" if hits else "outside_boundary"
        return None, status, len(hits), tuple(hits), None, boundary_hash

    def locate(raw, inspection):
        lon, lat = inspection["longitude"], inspection["latitude"]
        has_invalid_lon = raw["Longitude"].strip() and (lon is None or abs(lon) > 180)
        has_invalid_lat = raw["Latitude"].strip() and (lat is None or abs(lat) > 90)
        if has_invalid_lon or has_invalid_lat:
            return None, "invalid_coordinates", None, None, None, boundary_hash
        if lon is None or lat is None:
            return None, "missing_coordinates", None, None, None, boundary_hash
        return lookup(lon, lat)

    return locate


def evaluation(result):
    if result in EVALUATED:
        return "EVALUATED", True, result == "FAIL"
    if result in NOT_EVALUATED:
        return "NOT_EVALUATED", False, False
    return "UNKNOWN_RESULT", False, False


def spatial_tuple(values):
    number, status, count, candidate_numbers, on_boundary, version = values
    if candidate_numbers is not None:
        candidate_numbers = tuple(candidate_numbers)
    return number, status, count, candidate_numbers, on_boundary, version


def check_derived_rows(silver_dir, expected, violation_summaries, bronze_format_version):
    spatial_columns = ["inspection_key", *SPATIAL_FIELDS]
    geography_columns = [
        "inspection_key", "inspection_dtm", "result_cd", "evaluation_status_cd", "evaluated_flag", "failed_flag",
        *SPATIAL_FIELDS, *GEOGRAPHY_CONTEXT, "code_system_version", *VIOLATION_SUMMARY,
    ]
    spatial_path = silver_dir / "inspection_community_areas.parquet"
    geography_path = silver_dir / "inspection_geography.parquet"
    geography_schema = pq.read_schema(geography_path)
    require(set(geography_columns) <= set(geography_schema.names), "Geography lacks required fields")
    for name in ("evaluated_flag", "failed_flag", "violation_code_occurrence_ready", "community_area_on_boundary"):
        require(geography_schema.field(name).type == pa.bool_(), f"{name}: expected bool")
    if bronze_format_version >= 2:
        spatial_schema = pq.read_schema(spatial_path)
        for schema in (spatial_schema, geography_schema):
            for name in ("inspection_key", "community_area_match_status", "boundary_version"):
                require(schema.field(name).type == pa.string(), f"{name}: expected string")

    seen = set()
    for key, *values in parquet_rows(spatial_path, spatial_columns):
        require(key in expected and key not in seen, f"Invalid or duplicate spatial inspection key: {key}")
        require(spatial_tuple(values) == expected[key][2], f"Independent spatial match differs at {key}")
        seen.add(key)
    require(seen == expected.keys(), "Spatial result misses inspections")

    seen.clear()
    for key, dtm, result, status, assessed, failed, *details in parquet_rows(geography_path, geography_columns):
        require(key in expected and key not in seen, f"Invalid or duplicate geography inspection key: {key}")
        expected_date, expected_result, expected_spatial, expected_context = expected[key]
        spatial = spatial_tuple(details[:len(SPATIAL_FIELDS)])
        require(dtm == expected_date and result == expected_result and spatial == expected_spatial,
                f"Geography lineage or spatial result differs at {key}")
        require((status, assessed, failed) == evaluation(expected_result),
                f"Incorrect evaluated/fail flags at {key}")
        context_end = len(SPATIAL_FIELDS) + len(GEOGRAPHY_CONTEXT)
        require(tuple(details[len(SPATIAL_FIELDS):context_end]) == expected_context,
                f"Geography source or analysis context differs at {key}")
        require(details[context_end] == violation_era(dtm), f"Incorrect geography procedure era at {key}")
        require(tuple(details[context_end + 1:]) == violation_summaries[key],
                f"Incorrect geography violation summary at {key}")
        seen.add(key)
    require(seen == expected.keys(), "Geography result misses inspections")


def decode_violation(segment):
    stripped = segment.strip()
    if not stripped:
        return None, None, None, "empty_segment"
    code, separator, remaining = stripped.partition(".")
    if (not separator or len(code) not in (1, 2, 3) or not code.isascii() or not code.isdecimal()
            or not remaining or not remaining[0].isspace()):
        return None, None, None, "unrecognized"
    body = remaining.lstrip()
    marker = COMMENT_MARKER.search(body)
    description = (body[:marker.start()] if marker else body).strip()
    if not any(character.isalpha() for character in description):
        return None, None, None, "unrecognized"
    comment = body[marker.end():].strip() or None if marker else None
    return code, description, comment, "parsed"


def violation_era(inspection_date):
    if inspection_date is None or inspection_date < date(2010, 1, 1):
        return None
    return "pre_2018_07_01" if inspection_date < date(2018, 7, 1) else "from_2018_07_01"


def check_violations(silver_dir, source_path, batch_id, expected):
    observation = parquet_rows(silver_dir / "inspection_violation_observations.parquet", [
        *VIOLATION_LINEAGE, "violations_text", *VIOLATION_SUMMARY,
    ])
    tokens = parquet_rows(silver_dir / "inspection_violation_tokens.parquet", [
        *VIOLATION_LINEAGE, "violation_sequence", "raw_segment", "violation_cd", "description_text", "comment_text",
        "parse_status",
    ])
    codes = parquet_rows(silver_dir / "inspection_violation_codes.parquet", [
        *VIOLATION_LINEAGE, "violation_cd", "first_violation_sequence", "violation_token_count", "description_text",
        "violation_observation_status",
    ])
    totals = Counter()
    observation_counts = Counter()
    token_statuses = Counter()
    assessed_codes_by_region = {}
    summaries = {}
    with source_path.open(encoding="utf-8-sig", newline="") as source:
        records = (row for row in csv.DictReader(source, strict=True) if any(row.values()))
        for row_num, raw in enumerate(records, 1):
            key = raw["Inspection ID"].strip()
            inspection_date, result, spatial, _ = expected[key]
            era = violation_era(inspection_date)
            lineage = (key, row_num, batch_id, inspection_date, era)
            raw_text = raw["Violations"]
            if raw_text.strip():
                segments = raw_text.split("|")
                first_token = {}
                counts = Counter()
                for sequence, segment in enumerate(segments, 1):
                    code, description, comment, status = decode_violation(segment)
                    expected_token = (*lineage, sequence, segment, code, description, comment, status)
                    require(next(tokens, None) == expected_token,
                            f"Violation token or raw text differs at source row {row_num}, segment {sequence}")
                    token_statuses[status] += 1
                    if code is not None:
                        first_token.setdefault(code, (sequence, description))
                        counts[code] += 1
                parsed = counts.total()
                status = "parsed" if parsed == len(segments) else ("partial" if parsed else "unrecognized")
                ready = bool(era and parsed)
                summary = (status, len(segments), parsed, len(segments) - parsed, len(counts), ready)
                if ready:
                    for code, count in counts.items():
                        first_sequence, description = first_token[code]
                        expected_fact = (*lineage, code, first_sequence, count, description, status)
                        require(next(codes, None) == expected_fact,
                                f"Deduplicated violation code occurrence differs at source row {row_num}, code {code}")
                        totals["distinct_inspection_code_pairs"] += 1
                        if result in EVALUATED:
                            region = (spatial[0], era)
                            assessed_codes_by_region.setdefault(region, Counter())[code] += 1
            else:
                raw_text = None
                summary = ("raw_missing", None, None, None, None, False)
            require(next(observation, None) == (*lineage, raw_text, *summary),
                    f"Violation observation or raw text differs at source row {row_num}")
            observation_counts[summary[0]] += 1
            summaries[key] = summary
    for name, stream in (("observations", observation), ("tokens", tokens), ("codes", codes)):
        require(next(stream, None) is None, f"Unexpected extra violation {name} rows")
    return summaries, {
        "observation_statuses": dict(observation_counts),
        "token_statuses": dict(token_statuses),
        "distinct_inspection_code_pairs": totals["distinct_inspection_code_pairs"],
        "evaluated_inspection_codes_by_area_and_era_for_audit": [
            {
                "community_area_num": number,
                "code_system_version": era,
                "inspection_code_pairs": counts.total(),
                "distinct_codes": len(counts),
                "most_observed_codes": dict(counts.most_common(5)),
            }
            for (number, era), counts in sorted(assessed_codes_by_region.items(), key=lambda item: (item[0][0] or 0, item[0][1]))
        ],
    }


def audit(source_dir, bronze_dir, silver_dir):
    contract = json.loads((CONTRACT_DIR / "column_contract.json").read_text(encoding="utf-8"))
    codes = read_code_map(CONTRACT_DIR.parent / "shared_code_map.csv")
    bronze_manifest_path = bronze_dir / "manifest.json"
    manifest = json.loads(bronze_manifest_path.read_text(encoding="utf-8"))
    silver_manifest = json.loads((silver_dir / "manifest.json").read_text(encoding="utf-8"))
    require(manifest["layer"] == "bronze" and silver_manifest["layer"] == "silver" and
            manifest["batch_id"] == silver_manifest["batch_id"] and
            source_hash(bronze_manifest_path) == silver_manifest["bronze_manifest_sha256"],
            "Silver manifest does not reference the specified Bronze batch")
    # 검증할 파일명은 해당 Bronze 배치의 계보에서 읽는다.
    datasets = {}
    for key in ("food_inspections", "community_areas"):
        filename = manifest["sources"][key]["file"]
        require(bool(filename) and Path(filename).name == filename, f"{key}: expected a source file name")
        datasets[key] = {**contract["datasets"][key], "file": filename}
    hashes = {key: source_hash(source_dir / spec["file"]) for key, spec in datasets.items()}
    issues = Counter()
    checked = {
        key: checked_source_rows(key, spec, source_dir, bronze_dir, silver_dir, hashes[key], codes, issues, manifest)
        for key, spec in datasets.items()
    }
    boundaries, batch_id = prepared_boundaries(checked["community_areas"])
    locate = spatial_lookup(boundaries, hashes["community_areas"])
    expected = {}
    raw_results = Counter()
    spatial_statuses = Counter()
    evaluation_statuses = Counter()
    geographic_counts = {**{key: Counter() for key in sorted(boundaries)}, None: Counter()}
    for raw, inspection, row_batch in checked["food_inspections"]:
        key = inspection["inspection_key"]
        require(key and key not in expected, f"Missing or duplicate inspection key: {key}")
        require(row_batch == batch_id, f"Area/inspection batch mismatch at inspection {key}")
        spatial = locate(raw, inspection)
        result = inspection["result_cd"]
        context = tuple(inspection[name] for name in GEOGRAPHY_CONTEXT)
        expected[key] = (inspection["inspection_dtm"], result, spatial, context)
        raw_results[raw["Results"]] += 1
        spatial_statuses[spatial[1]] += 1
        status, assessed, failed = evaluation(result)
        evaluation_statuses[status] += 1
        area_counts = geographic_counts[spatial[0]]
        area_counts["inspection_rows"] += 1
        area_counts["evaluated_rows"] += assessed
        area_counts["failed_rows"] += failed
    quality_columns = ["source_dataset", "batch_id", "source_row_num", "standard_column", "reason_cd", "raw_value"]
    actual_issues = Counter(parquet_rows(silver_dir / "quality_issues.parquet", quality_columns))
    require(issues == actual_issues, "The Silver quality issues do not reconcile to the audited source rows")
    source_inspection = source_dir / datasets["food_inspections"]["file"]
    # 점검 ID로 원천·파생 레코드를 맞춰 위반 파싱과 지역·평가 상태를 대조한다.
    violation_summaries, violation_counts = check_violations(silver_dir, source_inspection, batch_id, expected)
    check_derived_rows(silver_dir, expected, violation_summaries, manifest.get("bronze_format_version", 1))
    return {
        "batch_id": batch_id,
        "source_sha256": hashes,
        "bronze_silver_source_rows": {"food_inspections": len(expected), "community_areas": len(boundaries)},
        "raw_inspection_results": dict(raw_results),
        "spatial_statuses": dict(spatial_statuses),
        "evaluation_statuses": dict(evaluation_statuses),
        "quality_issue_rows": issues.total(),
        "quality_review_source_rows": len({issue[:3] for issue in issues}),
        "failed_evaluated_rows": sum(counts["failed_rows"] for counts in geographic_counts.values()),
        "geographic_counts_for_audit": [
            {"community_area_num": number, **dict(counts)} for number, counts in geographic_counts.items()
        ],
        "violation_counts_for_audit": violation_counts,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=SOURCE_DIR)
    parser.add_argument("--bronze-dir", type=Path, required=True)
    parser.add_argument("--silver-dir", type=Path, required=True)
    parser.add_argument("--compare-wkt", type=Path, help="Compare the published GeoJSON batch against a WKT CSV")
    args = parser.parse_args()
    result = audit(args.source_dir, args.bronze_dir, args.silver_dir)
    if args.compare_wkt:
        manifest = json.loads((args.bronze_dir / "manifest.json").read_text(encoding="utf-8"))
        geojson_path = args.source_dir / manifest["sources"]["community_areas"]["file"]
        require(geojson_path.suffix == ".geojson", "WKT comparison requires a GeoJSON Bronze batch")
        points = pq.read_table(args.silver_dir / "food_inspections.parquet", columns=[
            "inspection_key", "latitude", "longitude", "coordinate_invalid_flag",
        ]).to_pandas()
        result["boundary_comparison"] = compare_boundaries(geojson_path, args.compare_wkt, points)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
