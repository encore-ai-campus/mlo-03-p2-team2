"""Validate shared Food Inspections Bronze and add row numbers for legacy runs."""

from contextlib import contextmanager
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


@contextmanager
def _verified_source(root: Path, expected: tuple[int, str]):
    source = next(
        (root / path for path in (ORIGIN_RELATIVE, LEGACY_ORIGIN_RELATIVE)
         if (root / path).is_file()), None,
    )
    with TemporaryDirectory() as scratch:
        if source is None:
            source = Path(scratch) / ORIGIN_RELATIVE.name
            with source.open("wb") as stream:
                check_csv_parts(root / ORIGIN_RELATIVE.parent, source.name, expected, stream)
        if (source.stat().st_size, sha256(source)) != expected:
            raise ValueError(f"Origin CSV differs from the shared snapshot: {source}")
        yield source


def _validate_schema(schema: pa.Schema, columns: list[str], *, numbered: bool) -> None:
    raw_columns = [*columns, *TECHNICAL_COLUMNS]
    expected = [*raw_columns, SOURCE_ROW_COLUMN] if numbered else raw_columns
    if (not columns or len(columns) != len(set(columns))
            or set(columns).intersection((*TECHNICAL_COLUMNS, SOURCE_ROW_COLUMN))
            or schema.names != expected
            or any(field.type != pa.string() for field in list(schema)[:len(raw_columns)])
            or (numbered and schema.field(SOURCE_ROW_COLUMN).type != pa.int64())):
        raise ValueError("Shared Bronze schema differs from the Origin header and lineage columns")


def _matching_batches(bronze, reader, columns, *, numbered):
    row_number = 0
    load_dtm = None
    source_index = len(columns)
    if numbered and "Inspection ID" not in columns:
        raise ValueError("Shared Bronze is missing Inspection ID")
    id_index = columns.index("Inspection ID") if numbered else None
    ids = set()
    for batch in bronze.iter_batches(batch_size=20_000):
        for values in zip(*(column.to_pylist() for column in batch.columns), strict=True):
            row_number += 1
            if (tuple(next(reader, ())) != values[:source_index]
                    or values[source_index] != ORIGIN_RELATIVE.name
                    or (numbered and values[-1] != row_number)):
                raise ValueError(f"Shared Bronze differs from Origin at logical row {row_number}")
            timestamp = values[source_index + 1]
            if load_dtm is None:
                if not timestamp:
                    raise ValueError("Shared Bronze _LOAD_DTM is missing")
                datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%SZ")
                load_dtm = timestamp
            if timestamp != load_dtm:
                raise ValueError(f"Shared Bronze _LOAD_DTM differs at logical row {row_number}")
            if id_index is not None:
                inspection_id = values[id_index]
                if not inspection_id or not inspection_id.strip() or inspection_id in ids:
                    raise ValueError(f"Shared Bronze Inspection ID is blank or duplicate at logical row {row_number}")
                ids.add(inspection_id)
        yield batch
    if load_dtm is None or next(reader, None) is not None:
        raise ValueError("Shared Bronze and Origin row counts differ or are empty")


def validate_shared(root: Path, shared: Path, origin: dict) -> str:
    """Verify Domain 06 Bronze against Origin without writing a second Bronze."""
    expected = origin["source_file_bytes"], origin["source_sha256"]
    shared_sha = sha256(shared)
    with _verified_source(root, expected) as source:
        with pq.ParquetFile(shared) as bronze, source.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.reader(stream, strict=True)
            columns = next(reader, [])
            schema = bronze.schema_arrow
            _validate_schema(schema, columns, numbered=True)
            if (schema.metadata or {}).get(b"source_sha256", b"").lower() != expected[1].encode("ascii"):
                raise ValueError("Shared Bronze source SHA-256 differs from Origin")
            for _ in _matching_batches(bronze, reader, columns, numbered=True):
                pass
        if sha256(source) != expected[1] or sha256(shared) != shared_sha:
            raise ValueError("Origin or shared Bronze changed during validation")
    return shared_sha


def _add_source_rows(shared: Path, source: Path, pending: Path, origin_sha: str) -> None:
    with pq.ParquetFile(shared) as bronze, source.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.reader(stream, strict=True)
        columns = next(reader, [])
        _validate_schema(bronze.schema_arrow, columns, numbered=False)

        schema = bronze.schema_arrow.append(pa.field(SOURCE_ROW_COLUMN, pa.int64(), nullable=False))
        schema = schema.with_metadata({**(schema.metadata or {}), b"origin_sha256": origin_sha.encode("ascii")})
        row_number = 0
        with pq.ParquetWriter(pending, schema, compression="zstd") as writer:
            for batch in _matching_batches(bronze, reader, columns, numbered=False):
                start = row_number + 1
                row_number += batch.num_rows
                row_numbers = pa.array(range(start, row_number + 1), type=pa.int64())
                writer.write_batch(pa.RecordBatch.from_arrays([*batch.columns, row_numbers], schema=schema))


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
    with _verified_source(root, expected) as source:
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
