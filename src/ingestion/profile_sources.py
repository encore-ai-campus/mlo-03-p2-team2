"""Read-only inventory of the configured Chicago source files."""

import argparse
import csv
import hashlib
import json
import os
import re
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.csv as arrow_csv
import yaml


PROJECT = Path(__file__).resolve().parents[2]
INTEGER = r"^[+-]?[0-9]+$"
NUMBER = r"^[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[Ee][+-]?[0-9]+)?$"
POINT = r"^\(\s*[+-]?[0-9]+(?:\.[0-9]+)?\s*,\s*[+-]?[0-9]+(?:\.[0-9]+)?\s*\)$"
US_DATE = r"^[0-9]{2}/[0-9]{2}/[0-9]{4}$"
ZIP = r"^[0-9]{5}(?:-[0-9]{4})?$"
ENUM_FIELDS = {"Risk", "Results", "APPLICATION TYPE", "LICENSE STATUS", "CONDITIONAL APPROVAL"}
COLUMN_PATTERNS = {
    "ID": {"digits_hyphen_eight_digits": r"^[0-9]+-[0-9]{8}$"},
    "Zip": {"zip_or_zip_plus_four": ZIP},
    "ZIP CODE": {"zip_or_zip_plus_four": ZIP},
    "WARD PRECINCT": {"integer": INTEGER, "two_numbers": r"^[0-9]+-[0-9]+$"},
    "SSA": {"integer": INTEGER},
    "BUSINESS ACTIVITY ID": {
        "single_id": INTEGER,
        "pipe_separated_ids": r"^[0-9]+(?:\s*\|\s*[0-9]+)+$",
    },
}
GEOJSON_PROPERTY_PATTERNS = {
    "area_numbe": INTEGER, "area_num_1": INTEGER,
    "shape_area": NUMBER, "shape_len": NUMBER,
}
JSON_TYPES = {
    str: "string", int: "integer", float: "number", list: "array",
    dict: "object", bool: "boolean", type(None): "null",
}


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def raw_path(root, relative):
    path = (root / relative).resolve()
    if not path.is_relative_to(root):
        raise ValueError(f"Source path lies outside the raw directory: {relative}")
    return path


def sha256(path, verification, suffix):
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    reference = verification / (path.name + suffix)
    expected = reference.read_text(encoding="utf-8-sig").strip().lower() if reference.is_file() else None
    return {"sha256": digest, "matches_reference": digest == expected if expected else None}


def field_types(records):
    counts = defaultdict(Counter)
    for record in records:
        for name, value in record.items():
            counts[name][JSON_TYPES[type(value)]] += 1
    return dict(counts)


def selected_metadata(row):
    return {"name": row["name"], "api_field": row["fieldName"], "provider_type": row["dataTypeName"]}


def count_true(mask):
    return pc.sum(pc.fill_null(mask, False)).as_py() or 0


def patterns_for(name, metadata):
    provider = metadata.get("provider_type")
    patterns = {}
    if provider == "number":
        patterns["numeric"] = NUMBER
        patterns["integer"] = INTEGER
    elif provider == "point":
        patterns["latitude_longitude_pair"] = POINT
    elif provider == "calendar_date":
        patterns["mm_dd_yyyy"] = US_DATE
    return patterns | COLUMN_PATTERNS.get(name, {})


def parse_csv_date(value):
    if not isinstance(value, str) or not re.fullmatch(US_DATE, value):
        return None
    try:
        month, day, year = map(int, value.split("/"))
        return date(year, month, day)
    except ValueError:
        return None


def summarize_dates(source_counts, parse):
    valid = []
    invalid = 0
    for value, count in source_counts.items():
        day = parse(value)
        if day is None:
            invalid += count
        else:
            valid.append((day, count))
    return {
        "nonblank": sum(source_counts.values()),
        "unparsed": invalid,
        "minimum": min((day for day, _ in valid), default=None),
        "maximum": max((day for day, _ in valid), default=None),
        "outside_1900_to_2100": {
            day.isoformat(): count for day, count in sorted(valid) if not 1900 <= day.year <= 2100
        },
    }


def profile_csv(path, metadata):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        headings = next(csv.reader(stream), [])
    if not headings or any(not name.strip() for name in headings) or len(set(headings)) != len(headings):
        raise ValueError(f"Missing, blank or duplicate column header in {path.name}")
    definitions = {item["name"]: selected_metadata(item) for item in metadata}
    fields = [{"name": name, "raw_type": "string", "missing": 0, "formats": Counter(),
               "api_field": definitions.get(name, {}).get("api_field"),
               "provider_type": definitions.get(name, {}).get("provider_type")} for name in headings]
    patterns = [patterns_for(field["name"], field) for field in fields]
    dates = defaultdict(Counter)
    categories = defaultdict(Counter)
    total_rows = 0
    with arrow_csv.open_csv(
        path,
        read_options=arrow_csv.ReadOptions(block_size=8 * 1024 * 1024),
        parse_options=arrow_csv.ParseOptions(newlines_in_values=True, ignore_empty_lines=False),
        convert_options=arrow_csv.ConvertOptions(column_types={name: pa.string() for name in headings},
                                                 strings_can_be_null=False),
    ) as reader:
        for batch in reader:
            total_rows += batch.num_rows
            for col, field, checks in zip(batch.columns, fields, patterns):
                values = pc.utf8_trim_whitespace(col)
                present = pc.not_equal(values, "")
                field["missing"] += batch.num_rows - count_true(present)
                for label, pattern in checks.items():
                    field["formats"][label] += count_true(pc.match_substring_regex(values, pattern))
                name = field["name"]
                if field["provider_type"] == "calendar_date" or name in ENUM_FIELDS:
                    counter = dates[name] if field["provider_type"] == "calendar_date" else categories[name]
                    for pair in pc.value_counts(pc.filter(values, present)).to_pylist():
                        counter[pair["values"]] += pair["counts"]
    return {
        "rows": total_rows,
        "columns": fields,
        "dates": {name: summarize_dates(dates[name], parse_csv_date) for name in dates},
        "observed_categories": dict(categories),
        "provider_only": [item for name, item in definitions.items() if name not in headings],
    }


def parse_json_timestamp(value):
    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return None
    return timestamp.astimezone(timezone.utc) if timestamp.tzinfo is not None else None


def coordinate_values(items):
    for item in items:
        if isinstance(item, list):
            yield from coordinate_values(item)
        else:
            yield item


def profile_geojson(path, metadata):
    document = read_json(path)
    if document.get("type") != "FeatureCollection" or not isinstance(document.get("features"), list):
        raise ValueError(f"Expected a GeoJSON FeatureCollection in {path.name}")
    features = document["features"]
    geometries = [feature.get("geometry") or {} for feature in features]
    properties = [feature.get("properties") or {} for feature in features]
    date_fields = {}
    for name in (":created_at", ":updated_at"):
        values = [record[name] for record in properties if name in record and record[name] not in (None, "")]
        counts = Counter(value for value in values if isinstance(value, str))
        date_fields[name] = summarize_dates(counts, parse_json_timestamp) | {
            "utc_z": sum(count for value, count in counts.items() if value.endswith("Z")),
            "example": min(counts, default=None),
        }
        date_fields[name]["nonblank"] = len(values)
        date_fields[name]["unparsed"] += len(values) - sum(counts.values())
    return {
        "rows": len(features),
        "root_types": field_types([document]),
        "feature_types": field_types(features),
        "feature_kinds": Counter(feature.get("type") for feature in features if feature.get("type")),
        "geometry_types": field_types(geometries),
        "geometry_kinds": Counter(geometry.get("type") for geometry in geometries if geometry.get("type")),
        "coordinate_component_types": Counter(
            JSON_TYPES[type(value)] for geometry in geometries
            for value in coordinate_values(geometry.get("coordinates") or [])
        ),
        "property_types": field_types(properties),
        "numeric_string_properties": {
            name: sum(isinstance(record.get(name), str) and bool(re.fullmatch(pattern, record[name]))
                      for record in properties)
            for name, pattern in GEOJSON_PROPERTY_PATTERNS.items()
        },
        "dates": date_fields,
        "provider_fields": [selected_metadata(item) for item in metadata],
    }


def json_date(value):
    if isinstance(value, date):
        return value.isoformat()
    raise TypeError(f"Unsupported profile value: {type(value).__name__}")


def main():
    args = argparse.ArgumentParser(description="Profile all columns in the shared source snapshot.")
    args.add_argument("--raw-dir", type=Path, help="Directory containing the source files")
    args.add_argument("--sources-config", type=Path, default=PROJECT / "config" / "sources.example.yaml")
    options = args.parse_args()
    config = yaml.safe_load(options.sources_config.read_text(encoding="utf-8-sig"))
    root = (PROJECT / (options.raw_dir or os.getenv(config["raw_root_env"]) or "data/origin")).resolve()
    integrity = config["integrity"]
    verification = PROJECT / integrity["root"]
    outputs = {}
    for table, info in config["sources"].items():
        data_path = raw_path(root, info["file"])
        metadata_path = raw_path(root, info["columns_file"])
        metadata = read_json(metadata_path)
        profiler = {"csv": profile_csv, "geojson": profile_geojson}.get(info["format"])
        if profiler is None:
            raise ValueError(f"{table}: unsupported inventory format {info['format']!r}")
        outputs[table] = {
            "file": data_path.name,
            "metadata_file": metadata_path.name,
            "format": info["format"],
            "metadata_definition_count": len(metadata),
            "metadata_field_types": field_types(metadata),
            "integrity": {
                data_path.name: sha256(data_path, verification, integrity["checksum_suffix"]),
                metadata_path.name: sha256(metadata_path, verification, integrity["checksum_suffix"]),
            },
        } | profiler(data_path, metadata)
    print(json.dumps(outputs, indent=2, ensure_ascii=True, default=json_date))


if __name__ == "__main__":
    main()
