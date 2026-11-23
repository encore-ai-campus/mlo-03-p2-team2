"""Build isolated shared Bronze and Silver from the tracked team snapshot."""

import argparse
from contextlib import contextmanager
from itertools import batched, zip_longest
import json
from pathlib import Path
import shutil
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from src.bronze.load_bronze import BATCH_SIZE, sha256, source_rows, utc_now
from src.ingestion import restore_origin


DOMAINS = Path(__file__).resolve().parents[1]
ROOT = DOMAINS.parents[1]
CATALOG = ROOT / "metadata/source_catalog/verification/download_manifest.csv"
BRONZE = Path("data/01_bronze/06_integration")
SILVER = Path("data/02_silver/06_integration")
SOURCES = {
    "food_inspections": ("csv", 318_627, "Inspection ID"),
    "business_licenses": ("csv", 1_212_132, "LICENSE ID"),
    "community_areas": ("geojson", 77, "area_numbe"),
}


def build_bronze(source, output, load_time, expected_rows, key):
    source_hash = sha256(source.path)
    stream = source_rows(source)
    columns, _ = next(stream)
    schema = pa.schema(
        [(name, pa.string()) for name in [*columns, "_SRC_FILE", "_LOAD_DTM"]]
        + [("source_row_num", pa.int64())],
        metadata={b"source_sha256": source_hash.encode("ascii")},
    )
    with pq.ParquetWriter(output, schema, compression="zstd") as writer:
        for start, items in enumerate(batched(stream, BATCH_SIZE)):
            records = [dict(row, _SRC_FILE=source.path.name, _LOAD_DTM=load_time,
                            source_row_num=start * BATCH_SIZE + index)
                       for index, (_, row) in enumerate(items, 1)]
            writer.write_table(pa.Table.from_pylist(records, schema=schema))
    verify_bronze(source, output, load_time, expected_rows, key, source_hash)
    return source_hash


def verify_bronze(source, output, load_time, expected_rows, key, source_hash):
    columns, _ = next(source_rows(source))
    source_records = (row for _, row in source_rows(source) if row is not None)
    keys = set()
    with pq.ParquetFile(output) as parquet:
        schema = parquet.schema_arrow
        expected = pa.schema([(name, pa.string()) for name in [*columns, "_SRC_FILE", "_LOAD_DTM"]]
                             + [("source_row_num", pa.int64())])
        if not schema.equals(expected) or (schema.metadata or {}).get(b"source_sha256") != source_hash.encode("ascii"):
            raise ValueError(f"{source.path.name}: Bronze schema or source SHA-256 differs")
        stored_records = (row for batch in parquet.iter_batches() for row in batch.to_pylist())
        for number, (raw, stored) in enumerate(zip_longest(source_records, stored_records), 1):
            expected = dict(raw or {}, _SRC_FILE=source.path.name, _LOAD_DTM=load_time, source_row_num=number)
            if not raw or stored != expected or not stored[key] or stored[key] in keys:
                raise ValueError(f"{source.path.name}: Bronze mismatch or duplicate key at row {number}")
            keys.add(stored[key])
    if len(keys) != expected_rows or sha256(source.path) != source_hash:
        raise ValueError(f"{source.path.name}: unexpected row count or source changed")


def inspection_silver(bronze, silver, quality):
    from pandas import DataFrame, read_parquet
    from silver import standardize

    raw = read_parquet(bronze)
    clean, flags = standardize(raw)
    clean.drop(columns=["_SRC_FILE", "_LOAD_DTM"]).to_parquet(silver, index=False)
    DataFrame(flags).assign(source_row_num=raw["source_row_num"]).to_parquet(quality, index=False)
    return {name: int(values.sum()) for name, values in flags.items()}


def license_silver(bronze, silver):
    from normalization import load_dictionary, normalize_batch, silver_schema

    fields = load_dictionary(DOMAINS / "04_license/데이터 사전.csv")["business_licenses"]
    schema = silver_schema(fields)
    with pq.ParquetFile(bronze) as source, pq.ParquetWriter(silver, schema) as writer:
        for batch in source.iter_batches():
            writer.write_batch(normalize_batch(batch, fields, schema))


def area_silver(bronze, silver):
    table = pq.read_table(bronze)
    areas = pa.table({
        "community_area_num": pc.cast(table["area_numbe"], pa.int64()),
        "community_area_name": pc.utf8_trim_whitespace(table["community"]),
        "geometry": table["geometry"],
        "source_row_num": table["source_row_num"],
    })
    pq.write_table(areas, silver)


def validate_silver(path, rows, key):
    table = pq.read_table(path, columns=[key, "source_row_num"])
    if (len(table) != rows or table[key].null_count or pc.count_distinct(table[key]).as_py() != rows
            or table["source_row_num"].to_pylist() != list(range(1, rows + 1))):
        raise ValueError(f"{path.name}: invalid Silver row count, key or lineage")


@contextmanager
def verified_origin(origin, parent):
    with TemporaryDirectory(dir=parent) as temporary:
        verified = Path(temporary)
        for name in [*restore_origin.SMALL_FILES, "SHA256SUMS",
                     *(part for csv_name in restore_origin.LARGE_FILES for part in restore_origin.parts(csv_name))]:
            shutil.copyfile(origin / name, verified / name)
        restore_origin.run(verified, CATALOG, True)
        yield verified


def build(origin, output):
    if output.exists():
        raise FileExistsError(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    for domain in ("01_inspection", "04_license"):
        sys.path.append(str(DOMAINS / domain))
    with TemporaryDirectory(dir=output.parent) as temporary, verified_origin(origin, output.parent) as verified:
        stage = Path(temporary) / "run"
        bronze_dir = stage / BRONZE
        silver_dir = stage / SILVER
        bronze_dir.mkdir(parents=True)
        silver_dir.mkdir(parents=True)
        quality = stage / "inspection_rule_flags.parquet"
        load_time = utc_now()
        summary = {"status": "PASS", "loaded_at": load_time, "datasets": {}}
        silver_keys = {"food_inspections": "inspection_key", "business_licenses": "license_event_key",
                       "community_areas": "community_area_num"}
        for name, (kind, rows, raw_key) in SOURCES.items():
            source = SimpleNamespace(path=verified / f"{name}.{kind}", format=kind)
            bronze = bronze_dir / f"{name}.parquet"
            silver = silver_dir / f"{name}.parquet"
            origin_hash = build_bronze(source, bronze, load_time, rows, raw_key)
            if name == "food_inspections":
                summary["inspection_quality_flags"] = inspection_silver(bronze, silver, quality)
            elif name == "business_licenses":
                license_silver(bronze, silver)
            else:
                area_silver(bronze, silver)
            validate_silver(silver, rows, silver_keys[name])
            summary["datasets"][name] = {
                "rows_per_stage": rows, "origin_sha256": origin_hash,
                "bronze_sha256": sha256(bronze), "silver_sha256": sha256(silver),
            }
            print(f"{name}: {rows:,} Origin = Bronze = Silver", flush=True)
        (stage / "verification.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        stage.rename(output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--origin", type=Path, default=ROOT / "data/00_origin")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    build(args.origin.resolve(), args.output.resolve())
