import csv
import json
from argparse import ArgumentParser
from hashlib import file_digest
from itertools import islice, zip_longest
from pathlib import Path
from tempfile import TemporaryDirectory

import pyarrow as pa
import pyarrow.parquet as pq


PROJECT = Path(__file__).resolve().parents[3]
DOMAIN = "03_repeat_inspection"
BRONZE_DIR = PROJECT / "data" / "01_bronze" / DOMAIN
SNAPSHOT_MANIFEST = PROJECT / "metadata" / "lineage" / DOMAIN / "bronze_manifest.json"
BATCH_SIZE = 10_000


def sha256(path):
    with path.open("rb") as stream:
        return file_digest(stream, "sha256").hexdigest()


def csv_records(path, header):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.reader(stream, strict=True)
        actual = next(reader, None)
        if actual != header or len(header) != len(set(header)) or "source_row_num" in header:
            raise ValueError(f"Invalid CSV header for {path}")
        row_number = 0
        for values in reader:
            if not any(values):
                continue
            row_number += 1
            if len(values) != len(header):
                raise ValueError(f"Wrong number of fields at source_row_num={row_number}")
            yield {**dict(zip(header, values)), "source_row_num": row_number}


def bronze_schema(header):
    return pa.schema([
        *(pa.field(name, pa.string(), nullable=False) for name in header),
        pa.field("source_row_num", pa.int64(), nullable=False),
    ])


def parquet_records(parquet):
    for batch in parquet.iter_batches(batch_size=BATCH_SIZE):
        yield from batch.to_pylist()


def build_bronze(source, output, manifest_path):
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    source = source or PROJECT / manifest["source_file"]
    output = output or PROJECT / manifest["bronze_file"]
    source_hash = manifest["sha256"]
    if sha256(source) != source_hash:
        raise ValueError(f"Origin SHA-256 does not match the manifest for {source}")
    header = manifest["header"]
    schema = bronze_schema(header).with_metadata({"source_sha256": source_hash})
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=output.parent) as directory:
        staged = Path(directory) / output.name
        records = csv_records(source, header)
        with pq.ParquetWriter(staged, schema, compression="zstd") as writer:
            while batch := list(islice(records, BATCH_SIZE)):
                writer.write_table(pa.Table.from_pylist(batch, schema=schema))
        with pq.ParquetFile(staged) as parquet:
            if parquet.metadata.num_rows != manifest["logical_row_count"]:
                raise ValueError("Bronze row count differs from the manifest")
            for row_number, (raw, actual) in enumerate(
                zip_longest(csv_records(source, header), parquet_records(parquet)), 1,
            ):
                if raw != actual:
                    raise ValueError(f"Bronze values or order changed at source_row_num={row_number}")
        if sha256(source) != source_hash:
            raise ValueError("Origin changed while building Bronze")
        staged.replace(output)
    print(f"{output} ({manifest['logical_row_count']:,} rows; source values and order verified)")


def main():
    parser = ArgumentParser(description="Build lossless Bronze inspection Parquet from the shared Origin CSV.")
    parser.add_argument("--manifest", type=Path, default=SNAPSHOT_MANIFEST)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    build_bronze(args.source, args.output, args.manifest)


if __name__ == "__main__":
    main()
