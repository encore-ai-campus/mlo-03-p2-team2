"""Lossless-value Bronze full refresh. Run: python -m src.bronze.load_bronze."""

import csv
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import uuid

import pyarrow as pa
import pyarrow.parquet as pq

from .paths import RUN_LOG, SOURCES, Source


TECHNICAL_COLUMNS = ("_SRC_FILE", "_LOAD_DTM")
LOG_COLUMNS = ("PIPELINE_RUN_ID", "LAYER", "TARGET", "SOURCE_FILE", "START_DTM", "END_DTM", "INPUT_ROWS", "OUTPUT_ROWS", "STATUS")
BATCH_SIZE = 20_000


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def verify_source(source: Source) -> str:
    if not source.path.is_file():
        raise FileNotFoundError(source.path)
    sidecar = source.path.with_name(source.path.name + ".sha256")
    if not sidecar.is_file():
        raise FileNotFoundError(sidecar)
    expected = sidecar.read_text(encoding="ascii").strip().split()[0].upper()
    actual = sha256(source.path)
    if actual != expected:
        raise ValueError(f"SHA-256 mismatch: {source.path}")
    return actual


def csv_rows(source: Source):
    with source.path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream, dialect="excel", strict=True)
        columns = reader.fieldnames
        if not columns or len(columns) != len(set(columns)) or set(columns) & set(TECHNICAL_COLUMNS):
            raise ValueError(f"Invalid or conflicting CSV columns: {source.path}")
        yield columns, None
        for row in reader:
            if None in row or set(row) != set(columns) or any(row[key] is None for key in columns):
                raise ValueError(f"Malformed CSV row near physical line {reader.line_num}: {source.path}")
            yield columns, row


def geo_rows(source: Source):
    # Preserve the geometry coordinate tree exactly; GeoJSON source properties are strings.
    document = json.loads(source.path.read_text(encoding="utf-8-sig"))
    if document.get("type") != "FeatureCollection" or not isinstance(document.get("features"), list):
        raise ValueError("Expected GeoJSON FeatureCollection")
    features = document["features"]
    if not features:
        raise ValueError("Empty GeoJSON FeatureCollection")
    property_columns = list(features[0]["properties"])
    columns = ["type", "geometry", *property_columns]
    if len(columns) != len(set(columns)) or set(columns) & set(TECHNICAL_COLUMNS):
        raise ValueError("Conflicting GeoJSON columns")
    yield columns, None
    for feature in features:
        if feature.get("type") != "Feature" or set(feature.get("properties", {})) != set(property_columns):
            raise ValueError("Inconsistent GeoJSON feature")
        if not isinstance(feature.get("geometry"), dict):
            raise ValueError("Missing GeoJSON geometry")
        row = {"type": feature["type"], "geometry": json.dumps(feature["geometry"], ensure_ascii=False, separators=(",", ":"))}
        for key in property_columns:
            value = feature["properties"][key]
            if value is not None and not isinstance(value, str):
                raise ValueError(f"Unexpected non-string GeoJSON property: {key}")
            row[key] = value
        yield columns, row


def source_rows(source: Source):
    return csv_rows(source) if source.format == "csv" else geo_rows(source)


def write_batch(writer, columns, rows, src_file, load_dtm):
    data = {column: [row[column] for row in rows] for column in columns}
    data["_SRC_FILE"] = [src_file] * len(rows)
    data["_LOAD_DTM"] = [load_dtm] * len(rows)
    writer.write_table(pa.table(data, schema=writer.schema))


def verify_output(source: Source, output: Path, columns: list[str], count: int, load_dtm: str):
    parquet = pq.ParquetFile(output)
    if parquet.metadata.num_rows != count or count != source.expected_rows:
        raise ValueError(f"Row count mismatch for {source.name}: input={count}, output={parquet.metadata.num_rows}, expected={source.expected_rows}")
    if parquet.schema_arrow.names != [*columns, *TECHNICAL_COLUMNS]:
        raise ValueError(f"Column mismatch for {source.name}")
    if any(field.type != pa.string() for field in parquet.schema_arrow):
        raise ValueError(f"Unexpected Parquet type for {source.name}")

    original = (row for _, row in source_rows(source) if row is not None)
    observed = 0
    inspection_ids = set()
    license_ids = set()
    area_numbers = set()
    for batch in parquet.iter_batches(batch_size=BATCH_SIZE):
        for bronze in batch.to_pylist():
            raw = next(original)
            for column in columns:
                if column == "geometry":
                    if json.loads(bronze[column]) != json.loads(raw[column]):
                        raise ValueError(f"Geometry changed at {observed}")
                elif bronze[column] != raw[column]:
                    raise ValueError(f"Source value changed: {source.name}/{column}/{observed}")
            if bronze["_SRC_FILE"] != source.path.name or bronze["_LOAD_DTM"] != load_dtm:
                raise ValueError(f"Technical column mismatch at {observed}")
            if source.name == "food_inspections":
                inspection_ids.add(bronze["Inspection ID"])
            elif source.name == "business_licenses":
                license_ids.add(bronze["LICENSE ID"])
            else:
                area_key = "area_numbe" if "area_numbe" in bronze else "AREA_NUMBE"
                area_numbers.add(bronze[area_key])
            observed += 1
    if observed != count or next(original, None) is not None:
        raise ValueError(f"Row stream mismatch for {source.name}")
    if source.name == "food_inspections" and len(inspection_ids) != count:
        raise ValueError("Inspection ID is no longer unique")
    if source.name == "business_licenses" and len(license_ids) != count:
        raise ValueError("LICENSE ID is no longer unique")
    if source.name == "community_areas" and len(area_numbers) != 77:
        raise ValueError("Community area key count changed")


def log_run(values: dict):
    RUN_LOG.parent.mkdir(parents=True, exist_ok=True)
    exists = RUN_LOG.exists()
    with RUN_LOG.open("a", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=LOG_COLUMNS)
        if not exists:
            writer.writeheader()
        writer.writerow(values)


def source_url(source: Source) -> str | None:
    """Look up the downloaded source URL without changing the origin manifest."""
    manifest = source.path.parent.parent / "download_manifest.csv"
    if not manifest.is_file():
        return None
    with manifest.open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            if row.get("File") == source.path.name:
                return row.get("Source") or None
    return None


def log_run_details(source: Source, run_id: str, load_dtm: str,
                    source_sha256: str | None, input_rows: int,
                    output_rows: int, status: str, error: str):
    """Append provenance fields separately, preserving the existing CSV log schema."""
    details = RUN_LOG.parent / "bronze_run_details.jsonl"
    details.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "pipeline_run_id": run_id,
        "source_file": source.path.name,
        "source_path": str(source.path.resolve()),
        "source_url": source_url(source),
        "load_dtm": load_dtm,
        "bronze_file": source.output.name,
        "bronze_path": str(source.output.resolve()),
        "input_rows": input_rows,
        "output_rows": output_rows,
        "source_sha256": source_sha256,
        "status": status,
        "error": error,
    }
    with details.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, ensure_ascii=False) + "\n")


def load_source(source: Source, run_id: str, load_dtm: str) -> int:
    started = utc_now()
    count = 0
    before = None
    error = ""
    temp = source.output.with_suffix(".parquet.tmp")
    try:
        before = verify_source(source)
        source.output.parent.mkdir(parents=True, exist_ok=True)
        stream = source_rows(source)
        columns, _ = next(stream)
        schema = pa.schema([pa.field(name, pa.string()) for name in [*columns, *TECHNICAL_COLUMNS]])
        with pq.ParquetWriter(temp, schema, compression="zstd") as writer:
            batch = []
            for _, row in stream:
                batch.append(row)
                count += 1
                if len(batch) == BATCH_SIZE:
                    write_batch(writer, columns, batch, source.path.name, load_dtm)
                    batch.clear()
            if batch:
                write_batch(writer, columns, batch, source.path.name, load_dtm)
        verify_output(source, temp, columns, count, load_dtm)
        if sha256(source.path) != before:
            raise ValueError(f"Source changed during load: {source.path}")
        os.replace(temp, source.output)  # Full refresh; previous successful output survives failed validation.
        status = "SUCCESS"
        return count
    except Exception as exc:
        status = "FAILED"
        error = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        if temp.exists():
            temp.unlink()
        log_run({"PIPELINE_RUN_ID": run_id, "LAYER": "BRONZE", "TARGET": source.name,
                 "SOURCE_FILE": source.relative_path, "START_DTM": started,
                 "END_DTM": utc_now(), "INPUT_ROWS": count, "OUTPUT_ROWS": count if status == "SUCCESS" else 0,
                 "STATUS": status})
        log_run_details(source, run_id, load_dtm, before, count,
                        count if status == "SUCCESS" else 0, status, error)


def main():
    run_id = uuid.uuid4().hex
    load_dtm = utc_now()  # One UTC instant shared by every row in this invocation.
    for source in SOURCES:
        rows = load_source(source, run_id, load_dtm)
        print(f"{source.name}: {rows} input rows = {rows} Bronze rows; {source.output}")
    print(f"run_id={run_id}, _LOAD_DTM={load_dtm}")


if __name__ == "__main__":
    main()
