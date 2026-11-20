"""Build the Domain 02 Food Inspections Bronze from the shared Origin."""

import csv
import os
from pathlib import Path
from tempfile import NamedTemporaryFile, TemporaryDirectory

import pyarrow as pa
import pyarrow.parquet as pq

from src.ingestion.restore_origin import check_csv_parts
from .profiling import (
    BRONZE_RELATIVE, LEGACY_ORIGIN_RELATIVE, ORIGIN_RELATIVE, PROJECT_ROOT,
    SOURCE_ROW_COLUMN, origin_snapshot, sha256,
)


def build(root: Path = PROJECT_ROOT) -> Path:
    root = Path(root)
    destination = root / BRONZE_RELATIVE
    if destination.exists():
        raise FileExistsError(destination)
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
            with source.open(encoding="utf-8-sig", newline="") as stream:
                reader = csv.reader(stream, strict=True)
                columns = next(reader)
                if len(columns) != len(set(columns)) or SOURCE_ROW_COLUMN in columns:
                    raise ValueError("Invalid Food Inspections CSV header")
                fields = [pa.field(name, pa.string()) for name in columns]
                fields.append(pa.field(SOURCE_ROW_COLUMN, pa.int64(), nullable=False))
                schema = pa.schema(fields, metadata={b"origin_sha256": expected[1].encode("ascii")})
                batch = []
                with pq.ParquetWriter(pending, schema, compression="zstd") as writer:
                    for row_num, values in enumerate(reader, start=1):
                        row = dict(zip(columns, values, strict=True))
                        row[SOURCE_ROW_COLUMN] = row_num
                        batch.append(row)
                        if len(batch) == 10_000:
                            writer.write_table(pa.Table.from_pylist(batch, schema=schema))
                            batch.clear()
                    if batch:
                        writer.write_table(pa.Table.from_pylist(batch, schema=schema))
            if sha256(source) != expected[1]:
                raise ValueError("Origin CSV changed during Bronze processing")
            os.link(pending, destination)
        finally:
            pending.unlink(missing_ok=True)
    return destination


if __name__ == "__main__":
    print(build())
