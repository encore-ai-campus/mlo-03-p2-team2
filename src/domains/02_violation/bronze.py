"""Add logical row numbers to the team Food Inspections Bronze."""

import csv
from datetime import datetime
import os
from pathlib import Path
from tempfile import NamedTemporaryFile, TemporaryDirectory

import pyarrow as pa
import pyarrow.parquet as pq

from src.bronze.load_bronze import TECHNICAL_COLUMNS
from src.bronze.paths import PROJECT_ROOT
from src.ingestion.restore_origin import check_csv_parts
from .profiling import (
    BRONZE_RELATIVE, LEGACY_ORIGIN_RELATIVE, ORIGIN_RELATIVE,
    SOURCE_ROW_COLUMN, origin_snapshot, sha256,
)

SHARED_BRONZE_RELATIVE = Path("data/01_bronze/food_inspections/food_inspections.parquet")


def _add_source_rows(shared: Path, source: Path, pending: Path, origin_sha: str) -> str:
    with pq.ParquetFile(shared) as bronze, source.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.reader(stream, strict=True)
        columns = next(reader)
        if (not columns or len(columns) != len(set(columns))
                or set(columns).intersection((*TECHNICAL_COLUMNS, SOURCE_ROW_COLUMN))
                or bronze.schema_arrow.names != [*columns, *TECHNICAL_COLUMNS]
                or any(field.type != pa.string() for field in bronze.schema_arrow)):
            raise ValueError("Shared Bronze schema differs from the Origin header and technical columns")

        schema = bronze.schema_arrow.append(pa.field(SOURCE_ROW_COLUMN, pa.int64(), nullable=False))
        schema = schema.with_metadata({**(schema.metadata or {}), b"origin_sha256": origin_sha.encode("ascii")})
        load_dtm = None
        row_number = 0
        with pq.ParquetWriter(pending, schema, compression="zstd") as writer:
            for batch in bronze.iter_batches(batch_size=20_000):
                start = row_number + 1
                for values in zip(*(column.to_pylist() for column in batch.columns), strict=True):
                    row_number += 1
                    if tuple(next(reader, ())) != values[:-2] or values[-2] != ORIGIN_RELATIVE.name:
                        raise ValueError(f"Shared Bronze differs from Origin at logical row {row_number}")
                    if load_dtm is None:
                        load_dtm = values[-1]
                        if not load_dtm:
                            raise ValueError("Shared Bronze _LOAD_DTM is missing")
                        datetime.strptime(load_dtm, "%Y-%m-%dT%H:%M:%SZ")
                    if values[-1] != load_dtm:
                        raise ValueError(f"Shared Bronze _LOAD_DTM differs at logical row {row_number}")
                row_numbers = pa.array(range(start, row_number + 1), type=pa.int64())
                writer.write_batch(pa.RecordBatch.from_arrays([*batch.columns, row_numbers], schema=schema))
            if load_dtm is None or next(reader, None) is not None:
                raise ValueError("Shared Bronze and Origin row counts differ or are empty")
    return load_dtm


def build(root: Path = PROJECT_ROOT) -> Path:
    root = Path(root)
    destination = root / BRONZE_RELATIVE
    shared = root / SHARED_BRONZE_RELATIVE
    if not shared.is_file():
        raise FileNotFoundError(f"Shared Food Inspections Bronze is required: {shared}")
    shared_sha = sha256(shared)
    origin = origin_snapshot(root)
    expected = origin["source_file_bytes"], origin["source_sha256"]
    destination.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory() as scratch:
        source = next(
            (root / path for path in (ORIGIN_RELATIVE, LEGACY_ORIGIN_RELATIVE)
             if (root / path).is_file()), None,
        )
        if source is None:
            source = Path(scratch) / ORIGIN_RELATIVE.name
            with source.open("wb") as stream:
                check_csv_parts(root / ORIGIN_RELATIVE.parent, source.name, expected, stream)
        if (source.stat().st_size, sha256(source)) != expected:
            raise ValueError(f"Origin CSV differs from the shared snapshot: {source}")
        with NamedTemporaryFile(dir=destination.parent, suffix=".tmp", delete=False) as handle:
            pending = Path(handle.name)
        try:
            _add_source_rows(shared, source, pending, expected[1])
            if sha256(source) != expected[1] or sha256(shared) != shared_sha:
                raise ValueError("Origin or shared Bronze changed while adding source row numbers")
            try:
                os.link(pending, destination)
            except FileExistsError:
                if sha256(pending) != sha256(destination):
                    raise FileExistsError(f"Existing Domain 02 Bronze differs: {destination}") from None
        finally:
            pending.unlink(missing_ok=True)
    return destination


if __name__ == "__main__":
    print(build())
