"""Read-only source profiling. Run: python -m src.profiling.profile_sources."""

import csv
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import uuid

import pyarrow.compute as pc
import pyarrow.parquet as pq

from src.bronze.paths import ORIGIN_ROOT, PROJECT_ROOT, SOURCES
from src.bronze.load_bronze import sha256, verify_source


OUT = PROJECT_ROOT / "metadata" / "source_profiles.json"
LOG = PROJECT_ROOT / "logs" / "profiling_runs.csv"
RUN_ID = uuid.uuid4().hex
NULL_TOKENS = {"NULL", "N/A", "NA", "NONE"}
DATE_COLUMNS = {
    "food_inspections": ["Inspection Date"],
    "business_licenses": ["APPLICATION CREATED DATE", "APPLICATION REQUIREMENTS COMPLETE", "PAYMENT DATE", "LICENSE TERM START DATE", "LICENSE TERM EXPIRATION DATE", "LICENSE APPROVED FOR ISSUANCE", "DATE ISSUED", "LICENSE STATUS CHANGE DATE"],
}
KEY_COLUMNS = {
    "food_inspections": ["Inspection ID", "License #"],
    "business_licenses": ["ID", "LICENSE ID", "LICENSE NUMBER"],
    "community_areas": ["area_numbe", "area_num_1", "community"],
}
HEADER = re.compile(r"^\d+[A-Z]?\.\s+")
INTEGER = re.compile(r"^[+-]?\d+$")
DECIMAL = re.compile(r"^[+-]?(?:\d+\.\d*|\.\d+)$")
ZIP = re.compile(r"^\d{5}(?:-\d{4})?$")


def valid_multipolygon(geometry):
    if geometry.get("type") != "MultiPolygon":
        return False
    polygons = geometry.get("coordinates")
    if not isinstance(polygons, list) or not polygons:
        return False
    for polygon in polygons:
        if not isinstance(polygon, list) or not polygon:
            return False
        for ring in polygon:
            if not isinstance(ring, list) or len(ring) < 4 or ring[0] != ring[-1]:
                return False
            for point in ring:
                if not isinstance(point, list) or len(point) < 2:
                    return False
                if any(not isinstance(value, (int, float)) or not math.isfinite(value) for value in point[:2]):
                    return False
    return True


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def column_state(columns):
    return {name: {"empty": 0, "whitespace": 0, "null_token": 0, "numeric_integer": 0,
                   "numeric_decimal": 0, "other_text": 0, "sample": None,
                   "top_sample": Counter()} for name in columns}


def update_column(stats, value, row_index):
    if value is None:
        stats["empty"] += 1
        return
    if value == "":
        stats["empty"] += 1
        return
    if not value.strip():
        stats["whitespace"] += 1
        return
    if value.strip().upper() in NULL_TOKENS:
        stats["null_token"] += 1
    if stats["sample"] is None:
        stats["sample"] = value[:120].replace("\n", "\\n").replace("\r", "\\r")
    if row_index <= 50_000 and len(value) <= 80:
        stats["top_sample"][value] += 1
    if INTEGER.fullmatch(value):
        stats["numeric_integer"] += 1
    elif DECIMAL.fullmatch(value):
        stats["numeric_decimal"] += 1
    else:
        stats["other_text"] += 1


def distinct_from_bronze(source, columns):
    """Exact distinct counts, one column at a time to bound memory.

    The Bronze loader previously verifies every source value against its Parquet value.
    """
    if not source.output.is_file():
        raise FileNotFoundError(f"Verified Bronze required for exact distinct counts: {source.output}")
    parquet = pq.ParquetFile(source.output)
    if parquet.metadata.num_rows != source.expected_rows:
        raise ValueError(f"Bronze/source row mismatch: {source.name}")
    counts = {}
    for column in columns:
        table = pq.read_table(source.output, columns=[column])
        counts[column] = pc.count_distinct(table[column], mode="all").as_py()
        del table
    return counts


def profile_csv(source):
    verify_source(source)
    with source.path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream, dialect="excel", strict=True)
        columns = reader.fieldnames
        stats = column_state(columns)
        keys = {name: set() for name in KEY_COLUMNS[source.name]}
        duplicates = Counter()
        dates = {name: {"invalid_calendar": 0, "outside_1900_2100": 0, "min": None, "max": None, "examples": []} for name in DATE_COLUMNS[source.name]}
        zip_column = "Zip" if source.name == "food_inspections" else "ZIP CODE"
        zip_bad = Counter()
        exact_rows = set()
        full_duplicates = 0
        violations = Counter()
        violation_examples = []
        license_numbers = Counter()
        city_values = Counter()
        business_name_variants = {}
        row_count = 0
        for row in reader:
            row_count += 1
            if None in row or any(value is None for value in row.values()):
                raise ValueError(f"Malformed CSV row: {source.name}, line {reader.line_num}")
            row_digest = hashlib.blake2b(repr(tuple(row.values())).encode("utf-8"), digest_size=16).digest()
            full_duplicates += row_digest in exact_rows
            exact_rows.add(row_digest)
            for name in columns:
                update_column(stats[name], row[name], row_count)
            for name in keys:
                value = row[name]
                if value in keys[name]:
                    duplicates[name] += 1
                keys[name].add(value)
            for name in dates:
                value = row[name]
                if not value.strip():
                    continue
                try:
                    parsed = datetime.strptime(value, "%m/%d/%Y").date()
                except ValueError:
                    dates[name]["invalid_calendar"] += 1
                    if len(dates[name]["examples"]) < 3:
                        dates[name]["examples"].append(value)
                    continue
                if parsed.year < 1900 or parsed.year > 2100:
                    dates[name]["outside_1900_2100"] += 1
                    if len(dates[name]["examples"]) < 3:
                        dates[name]["examples"].append(value)
                if dates[name]["min"] is None or parsed.isoformat() < dates[name]["min"]:
                    dates[name]["min"] = parsed.isoformat()
                if dates[name]["max"] is None or parsed.isoformat() > dates[name]["max"]:
                    dates[name]["max"] = parsed.isoformat()
            z = row[zip_column]
            if z and not ZIP.fullmatch(z):
                zip_bad[z] += 1
            city_values[row["City" if source.name == "food_inspections" else "CITY"]] += 1
            if source.name == "food_inspections":
                name = row["DBA Name"]
                if name:
                    business_name_variants.setdefault(name.casefold(), set()).add(name)
                value = row["Violations"]
                if value == "":
                    violations["empty"] += 1
                elif not value.strip():
                    violations["whitespace"] += 1
                else:
                    parts = re.split(r"\s+\|\s+", value)
                    violations["nonempty"] += 1
                    violations["candidate_items"] += len(parts)
                    violations["multi_item_rows"] += len(parts) > 1
                    malformed = [part for part in parts if not HEADER.match(part.strip())]
                    if malformed:
                        violations["rows_with_nonstandard_header"] += 1
                        if len(violation_examples) < 6:
                            violation_examples.append({"inspection_id": row["Inspection ID"], "fragment": malformed[0][:160]})
                    violations["rows_without_comments_marker"] += "Comments:" not in value
                    violations["rows_with_unspaced_pipe"] += bool(re.search(r"(?<!\s)\|(?!\s)", value))
                license_numbers[row["License #"]] += 1
            else:
                license_numbers[row["LICENSE NUMBER"]] += 1

    if row_count != source.expected_rows:
        raise ValueError(f"Unexpected source rows: {source.name}={row_count}")
    distinct = distinct_from_bronze(source, columns)
    for name in columns:
        stats[name]["unique_values"] = distinct[name]
        stats[name]["top_sample"] = stats[name]["top_sample"].most_common(5)
        stats[name]["missing_rate_percent"] = round(100 * (stats[name]["empty"] + stats[name]["whitespace"]) / row_count, 4)
    result = {"source_file": source.relative_path, "format": "CSV", "encoding": "UTF-8 (optional BOM)", "delimiter": ",",
              "rows": row_count, "columns": columns, "column_stats": stats,
              "key_duplicate_rows": dict(duplicates), "key_duplicate_rate_percent": {k: round(100 * duplicates[k] / row_count, 4) for k in keys},
              "full_row_duplicates_hash16": full_duplicates, "dates": dates,
              "zip_non_us_pattern_count": sum(zip_bad.values()), "zip_non_us_pattern_examples": zip_bad.most_common(10)}
    if source.name == "food_inspections":
        result["violations"] = {**violations, "nonstandard_header_examples": violation_examples}
        result["business_name_case_variants"] = [sorted(values)[:3] for values in business_name_variants.values() if len(values) > 1][:10]
    result["city_spelling_examples"] = {name: city_values[name] for name in ("CHICAGO", "Chicago", "chicago", "CCHICAGO") if city_values[name]}
    return result, license_numbers


def profile_geo(source):
    verify_source(source)
    document = json.loads(source.path.read_text(encoding="utf-8-sig"))
    features = document["features"]
    if document.get("type") != "FeatureCollection":
        raise ValueError("Not a FeatureCollection")
    columns = ["type", "geometry", *features[0]["properties"]]
    stats = column_state(columns)
    kinds = Counter()
    structural_errors = Counter()
    numbers = Counter()
    bronze = pq.read_table(source.output).to_pylist()
    if len(bronze) != len(features) or len(features) != source.expected_rows:
        raise ValueError("GeoJSON/Bronze feature count mismatch")
    for index, (feature, saved) in enumerate(zip(features, bronze), 1):
        properties = feature.get("properties")
        geometry = feature.get("geometry")
        if not isinstance(properties, dict) or set(properties) != set(columns[2:]):
            structural_errors["properties"] += 1
            continue
        if not isinstance(geometry, dict) or not isinstance(geometry.get("coordinates"), list):
            structural_errors["geometry"] += 1
            continue
        kinds[geometry.get("type")] += 1
        if not valid_multipolygon(geometry):
            structural_errors["invalid_multipolygon_structure"] += 1
        numbers[properties["area_numbe"]] += 1
        row = {"type": feature.get("type"), "geometry": json.dumps(geometry, ensure_ascii=False, separators=(",", ":")), **properties}
        for name in columns:
            update_column(stats[name], row[name], index)
            if name == "geometry":
                if json.loads(saved[name]) != geometry:
                    structural_errors["bronze_geometry_mismatch"] += 1
            elif saved[name] != row[name]:
                structural_errors["bronze_value_mismatch"] += 1
    distinct = distinct_from_bronze(source, columns)
    for name in columns:
        stats[name]["unique_values"] = distinct[name]
        stats[name]["top_sample"] = stats[name]["top_sample"].most_common(5)
        stats[name]["missing_rate_percent"] = round(100 * (stats[name]["empty"] + stats[name]["whitespace"]) / len(features), 4)
    return {"source_file": source.relative_path, "format": "GeoJSON FeatureCollection", "encoding": "UTF-8",
            "rows": len(features), "columns": columns, "column_stats": stats,
            "top_level_keys": list(document), "feature_keys": list(features[0]), "property_keys": list(features[0]["properties"]),
            "geometry_types": dict(kinds), "structural_errors": dict(structural_errors),
            "key_duplicate_rows": {"area_numbe": sum(n - 1 for n in numbers.values() if n > 1)},
            "key_duplicate_rate_percent": {"area_numbe": 0.0}, "full_row_duplicates_hash16": 0}, numbers


def log_run(run_id, target, rows, status, error):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    exists = LOG.exists()
    with LOG.open("a", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["RUN_ID", "EXECUTED_AT_UTC", "TARGET", "PROCESSED_ROWS", "STATUS", "ERROR"])
        if not exists:
            writer.writeheader()
        writer.writerow({"RUN_ID": run_id, "EXECUTED_AT_UTC": now(), "TARGET": target,
                         "PROCESSED_ROWS": rows, "STATUS": status, "ERROR": error})


def main():
    run_id = RUN_ID
    result = {"run_id": run_id, "executed_at_utc": now(), "null_policy": {
        "empty": "CSV field exactly '' or JSON null", "whitespace": "nonempty text for which str.strip() == ''",
        "null_token": "trimmed, case-insensitive NULL/N/A/NA/NONE; counted separately, not automatically missing",
        "missing_rate": "(empty + whitespace) / rows; NULL-like tokens excluded"}, "sources": {}}
    license_counts = {}
    for source in SOURCES:
        try:
            if source.format == "csv":
                profile, keys = profile_csv(source)
                license_counts[source.name] = keys
            else:
                profile, keys = profile_geo(source)
                license_counts[source.name] = keys
            result["sources"][source.name] = profile
            log_run(run_id, source.name, profile["rows"], "SUCCESS", "")
            print(f"{source.name}: {profile['rows']} rows, {len(profile['columns'])} columns")
        except Exception as exc:
            log_run(run_id, source.name, 0, "FAILED", f"{type(exc).__name__}: {exc}")
            raise
    food = license_counts["food_inspections"]
    licenses = license_counts["business_licenses"]
    result["joins"] = {"inspection_license_number": {
        "distinct_shared_nonblank": len((set(food) - {""}) & set(licenses)),
        "inspection_rows_blank": food[""],
        "inspection_rows_no_match_nonblank": sum(n for key, n in food.items() if key and key not in licenses),
        "inspection_rows_one_candidate": sum(n for key, n in food.items() if key and licenses[key] == 1),
        "inspection_rows_multiple_candidates": sum(n for key, n in food.items() if key and licenses[key] > 1),
        "max_license_history_candidates": max(licenses.values())}}
    area_numbers = set(license_counts["community_areas"])
    area_values = Counter()
    with SOURCES[1].path.open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            area_values[row["COMMUNITY AREA"]] += 1
    result["joins"]["license_area_number"] = {
        "distinct_matching_areas": len(area_numbers & set(area_values)),
        "blank_rows": area_values[""],
        "nonblank_unmatched_rows": sum(n for key, n in area_values.items() if key and key not in area_numbers),
        "unmatched_values": {key: n for key, n in area_values.items() if key and key not in area_numbers}}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    log_run(run_id, "__overall__", sum(item["rows"] for item in result["sources"].values()), "SUCCESS", "")
    print(f"profile={OUT}; run_id={run_id}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        log_run(RUN_ID, "__overall__", 0, "FAILED", f"{type(exc).__name__}: {exc}")
        raise
