import csv
import hashlib
import json
import math
import tempfile
from argparse import ArgumentParser
from collections import Counter
from datetime import datetime
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq


PROJECT = Path(__file__).resolve().parents[3]
DOMAIN = "03_repeat_inspection"
BRONZE_DIR = PROJECT / "data" / "bronze" / DOMAIN
SILVER_DIR = PROJECT / "data" / "silver" / DOMAIN
SNAPSHOT_MANIFEST = PROJECT / "metadata" / "lineage" / DOMAIN / "bronze_manifest.json"
DATASET = "food_inspections"
BATCH_SIZE = 10_000
TEXT_COLUMNS = {
    "DBA Name": "dba_name",
    "AKA Name": "aka_name",
    "Facility Type": "facility_type",
    "Address": "address",
    "City": "city",
    "State": "state",
    "Zip": "zip",
    "Inspection Type": "inspection_type",
    "Location": "location",
}
LOCAL_CODES = {
    "Results": {
        "Pass": "PASS",
        "Fail": "FAIL",
        "Pass w/ Conditions": "PASS W/ CONDITIONS",
        "Out of Business": "OUT OF BUSINESS",
        "No Entry": "NO ENTRY",
        "Not Ready": "NOT READY",
        "Business Not Located": "BUSINESS NOT LOCATED",
    },
    "Risk": {
        "Risk 1 (High)": "RISK_1",
        "Risk 2 (Medium)": "RISK_2",
        "Risk 3 (Low)": "RISK_3",
        "All": "ALL",
    },
}
REQUIRED_COLUMNS = set(TEXT_COLUMNS) | {
    "Inspection ID", "License #", "Inspection Date", "Results", "Risk",
    "Violations", "Latitude", "Longitude",
}
SCHEMA = pa.schema([
    pa.field("source_row_num", pa.int64(), nullable=False),
    pa.field("inspection_key", pa.string(), nullable=False),
    ("license_number_key", pa.string()),
    ("inspection_dtm", pa.date32()),
    ("result_cd", pa.string()),
    ("risk_level_cd", pa.string()),
    ("violations_text", pa.string()),
    *((target, pa.string()) for target in TEXT_COLUMNS.values()),
    ("latitude", pa.float64()),
    ("longitude", pa.float64()),
    ("quality_issues", pa.list_(pa.struct([
        ("source_column", pa.string()),
        ("source_value", pa.string()),
        ("reason", pa.string()),
    ]))),
])


def load_codes(path):
    if path is None:
        return LOCAL_CODES

    codes = {column: {} for column in LOCAL_CODES}
    with path.open(encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        required = {"dataset", "source_column", "source_value", "standard_code"}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError(f"{path} must contain {sorted(required)}")
        for row in reader:
            column = row["source_column"].strip()
            if row["dataset"].strip() != DATASET or column not in codes:
                continue
            value = row["source_value"].strip()
            code = row["standard_code"].strip()
            if not value or not code or value in codes[column]:
                raise ValueError(f"Invalid or duplicate code mapping at {path}:{reader.line_num}")
            codes[column][value] = code
    if not all(codes.values()):
        raise ValueError(f"{path} must map both Results and Risk for {DATASET}")
    return codes


def standardize(raw, source_row_num, codes):
    issues = []

    def issue(column, reason):
        issues.append({"source_column": column, "source_value": raw[column], "reason": reason})

    clean = {column: value.strip() or None for column, value in raw.items()}
    license_number = clean["License #"]
    if license_number in {None, "0", "9999999"}:
        issue("License #", "missing" if license_number is None else "placeholder")
        license_number = None

    inspection_date = None
    if clean["Inspection Date"] is None:
        issue("Inspection Date", "missing")
    else:
        try:
            inspection_date = datetime.strptime(clean["Inspection Date"], "%m/%d/%Y").date()
        except ValueError:
            issue("Inspection Date", "invalid_date")

    category_codes = {}
    for source in codes:
        value = clean[source]
        category_codes[source] = codes[source].get(value)
        if value is None:
            issue(source, "missing")
        elif category_codes[source] is None:
            issue(source, "unmapped")
        elif source == "Risk" and value == "All":
            issue(source, "review")

    coordinates = {}
    for source, bound in (("Latitude", 90), ("Longitude", 180)):
        value = clean[source]
        number = None
        if value is not None:
            try:
                number = float(value)
                if not math.isfinite(number) or not -bound <= number <= bound:
                    raise ValueError
            except ValueError:
                number = None
                issue(source, "invalid_coordinate")
        coordinates[source.lower()] = number

    return {
        "source_row_num": source_row_num,
        "inspection_key": clean["Inspection ID"],
        "license_number_key": license_number,
        "inspection_dtm": inspection_date,
        "result_cd": category_codes["Results"],
        "risk_level_cd": category_codes["Risk"],
        "violations_text": raw["Violations"] if clean["Violations"] is not None else None,
        **{target: clean[source] for source, target in TEXT_COLUMNS.items()},
        **coordinates,
        "quality_issues": issues or None,
    }


def write_snapshot(source, writer, manifest, schema, codes):
    reader = csv.reader(source, strict=True)
    header = next(reader)
    if header != manifest["header"] or len(header) != len(set(header)):
        raise ValueError("Bronze CSV header differs from the manifest or has duplicate columns")
    if missing := REQUIRED_COLUMNS.difference(header):
        raise ValueError(f"Missing Bronze columns {sorted(missing)}")

    row_count = 0
    seen_keys = {}
    batch = []
    issue_counts = Counter()
    for values in reader:
        if not any(values):
            continue
        row_count += 1
        if len(values) != len(header):
            raise ValueError(f"Wrong number of fields at source_row_num={row_count}")
        row = standardize(dict(zip(header, values)), row_count, codes)
        key = row["inspection_key"]
        if key is None:
            raise ValueError(f"Missing inspection_key at source_row_num={row_count}")
        if key in seen_keys:
            raise ValueError(f"Duplicate inspection_key {key} at source rows {seen_keys[key]} and {row_count}")
        seen_keys[key] = row_count
        for issue in row["quality_issues"] or []:
            issue_counts[issue["source_column"], issue["reason"]] += 1
        batch.append(row)
        if len(batch) >= BATCH_SIZE:
            writer.write_table(pa.Table.from_pylist(batch, schema=schema))
            batch.clear()

    if row_count != manifest["logical_row_count"]:
        raise ValueError(f"Expected {manifest['logical_row_count']} logical rows, found {row_count}")
    if batch:
        writer.write_table(pa.Table.from_pylist(batch, schema=schema))
    return row_count, issue_counts


def build_silver(bronze_dir, output, code_map, manifest_path=None):
    if manifest_path is None:
        manifest_path = bronze_dir / "metadata.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    source_path = bronze_dir / Path(manifest["bronze_file"]).name
    codes = load_codes(code_map)
    with source_path.open("rb") as source_bytes:
        source_hash = hashlib.file_digest(source_bytes, "sha256").hexdigest()
    if source_hash != manifest["sha256"]:
        raise ValueError(f"Bronze SHA-256 does not match the manifest for {source_path}")

    schema = SCHEMA.with_metadata({
        "source_sha256": source_hash,
        "snapshot_date": manifest["snapshot_date"],
        "code_map": "local" if code_map is None else code_map.name,
    })
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent) as staging_dir:
        staged_output = Path(staging_dir) / output.name
        with (
            source_path.open(encoding="utf-8-sig", newline="") as source,
            pq.ParquetWriter(staged_output, schema, compression="zstd") as writer,
        ):
            row_count, issues = write_snapshot(source, writer, manifest, schema, codes)
        staged_output.replace(output)

    print(f"{output} ({row_count:,} rows)")
    for (column, reason), count in sorted(issues.items()):
        print(f"  {column} [{reason}]: {count:,}")


def main():
    parser = ArgumentParser(description="Build a typed Food Inspections Silver Parquet from Bronze.")
    parser.add_argument("--bronze-dir", type=Path)
    parser.add_argument("--manifest", type=Path, help="Bronze snapshot manifest")
    parser.add_argument("--output", type=Path, default=SILVER_DIR / f"{DATASET}.parquet")
    parser.add_argument("--code-map", type=Path, help="CSV with dataset, source_column, source_value, standard_code")
    args = parser.parse_args()
    manifest_path = args.manifest
    if manifest_path is None and args.bronze_dir is None:
        manifest_path = SNAPSHOT_MANIFEST
    build_silver(args.bronze_dir or BRONZE_DIR, args.output, args.code_map, manifest_path)


if __name__ == "__main__":
    main()
