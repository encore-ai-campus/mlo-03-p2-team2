"""Share Domain 04 files in one folder and restore their exact file bytes."""

import argparse
import csv
import gzip
import hashlib
import json
import sys
from contextlib import nullcontext
from pathlib import Path
from tempfile import TemporaryFile
from zlib import error as ZlibError

import pyarrow as pa
import pyarrow.parquet as pq

from bronze_manifest import MANIFEST as BRONZE_MANIFEST, read_manifest
from config import DOMAIN, STAGE_DIRS, TABLES, directories_overlap
from modeling import SCHEMAS, gold_path
from pipeline_io import json_bytes, sha256, staging


MANIFEST = "04_manifest.json"
CHECKSUMS = "04_sha256sums.txt"
MAX_BYTES = 100_000_000
BUFFER_SIZE = 1024 * 1024
RAW_FILES = ("food_inspections.csv", "business_licenses.csv", "community_areas.geojson",
             "food_columns.json", "license_columns.json", "area_columns.json")
VALIDATION_REPORTS = tuple(f"validation_{stage}.csv" for stage in ("bronze", "silver", "quality", "gold"))
REPORT_FILES = (*VALIDATION_REPORTS, "quality_comparison.csv", "품질 관리.md")
UPLOAD_STAGE = {"00_origin": "origin", "01_bronze": "bronze", "02_silver": "silver", "03_gold": "gold"}


def layout():
    for name in RAW_FILES:
        yield Path("data/00_origin") / name
    for stage in ("bronze", "silver"):
        folder = Path("data") / STAGE_DIRS[stage] / DOMAIN
        for name in TABLES:
            yield folder / f"{name}.parquet"
        if stage == "bronze":
            yield folder / BRONZE_MANIFEST
    for name in SCHEMAS:
        yield gold_path(Path("data") / STAGE_DIRS["gold"], name)
    for report in REPORT_FILES:
        yield Path("reports") / report


def part_plan(path, size, limit, minimum_parts=1):
    count = max(minimum_parts, (size + limit - 1) // limit)
    if count == 1:
        return [(path, size)]
    size_per_part, extra = divmod(size, count)
    return [(path.with_name(f"{path.name}.part-{index + 1:03d}"), size_per_part + (index < extra))
            for index in range(count)]


def upload_name(relative, compressed):
    if relative.parts[0] == "data":
        name = f"04_{UPLOAD_STAGE[relative.parts[1]]}_{relative.name}"
    elif relative.name == "품질 관리.md":
        name = "04_quality.md"
    else:
        name = f"04_{relative.name}"
    return Path(name + (".gz" if compressed else ""))


def compressed_source(relative, size, limit):
    return relative.parent == Path("data/00_origin") and relative.suffix == ".csv" and size > limit


def stream_chunk(input_stream, size, digests, output_stream=None):
    remaining = size
    while remaining:
        block = input_stream.read(min(remaining, BUFFER_SIZE))
        if not block:
            raise ValueError("File ended before its expected byte size.")
        for digest in digests:
            digest.update(block)
        if output_stream is not None:
            output_stream.write(block)
        remaining -= len(block)


def parquet_rows(path):
    with pq.ParquetFile(path) as artifact:
        return artifact.metadata.num_rows


def write_parts(stream, target, plan):
    whole_hash = hashlib.sha256()
    parts = []
    for part, part_size in plan:
        digest = hashlib.sha256()
        with (target / part).open("wb") as output:
            stream_chunk(stream, part_size, (whole_hash, digest), output)
        parts.append({"path": part.as_posix(), "bytes": part_size, "sha256": digest.hexdigest()})
    if stream.read(1):
        raise ValueError("File grew while packaging.")
    return whole_hash.hexdigest(), parts


def copy_artifact(source, target, relative, limit):
    size = source.stat().st_size
    compressed = compressed_source(relative, size, limit)
    name = upload_name(relative, compressed)
    encoding = {}
    with source.open("rb") as stream:
        if compressed:
            raw_hash = hashlib.sha256()
            with TemporaryFile() as encoded:
                with gzip.GzipFile(filename="", fileobj=encoded, mode="wb", mtime=0, compresslevel=6) as output:
                    stream_chunk(stream, size, (raw_hash,), output)
                if stream.read(1):
                    raise ValueError(f"Raw file grew while packaging: {source}")
                encoded_size = encoded.tell()
                encoded.seek(0)
                encoded_hash, parts = write_parts(encoded, target, part_plan(name, encoded_size, limit, 2))
            digest = raw_hash.hexdigest()
            encoding = {"gzip_bytes": encoded_size, "gzip_sha256": encoded_hash}
        else:
            digest, parts = write_parts(stream, target, part_plan(name, size, limit))
    rows = parquet_rows(source) if relative.suffix == ".parquet" else None
    return {"path": relative.as_posix(), "bytes": size, "sha256": digest,
            "rows": rows, "parts": parts, **encoding}


def checksum_bytes(root, entries):
    lines = [f"{sha256(root / MANIFEST)}  {MANIFEST}\n"]
    lines.extend(f"{part['sha256']}  {part['path']}\n" for entry in entries for part in entry["parts"])
    return "".join(lines).encode("utf-8")


def passed_reports(report_dir):
    for report in VALIDATION_REPORTS:
        with (report_dir / report).open(encoding="utf-8", newline="") as stream:
            checks = list(csv.DictReader(stream))
        if not checks or any(row["violations"] != "0" for row in checks):
            raise ValueError(f"Cannot package a failing validation report: {report}")


def check_bronze_identity(entries, provenance):
    files = {Path(entry["path"]): entry for entry in entries}
    for table, payload in provenance.items():
        parquet = Path("data") / STAGE_DIRS["bronze"] / DOMAIN / f"{table}.parquet"
        record = files[parquet]
        if record["sha256"] != payload["bronze_sha256"] or record["rows"] != payload["row_count"]:
            raise ValueError(f"Bronze Parquet differs from its ingestion manifest: {table}")
        raw = Path("data/00_origin") / f"{table}.csv"
        if files[raw]["sha256"] != payload["source_sha256"]:
            raise ValueError(f"Origin CSV differs from the source used for Bronze: {table}")


def build(raw_dir, data_dir, report_dir, output_dir, limit):
    if not 0 < limit <= MAX_BYTES:
        raise ValueError(f"The limit must be between 1 and {MAX_BYTES} bytes.")
    if any(directories_overlap(output_dir, directory) for directory in (raw_dir, data_dir, report_dir)):
        raise ValueError("The sharing directory must be separate from the origin, data and reports.")
    passed_reports(report_dir)
    _, provenance = read_manifest(data_dir / STAGE_DIRS["bronze"] / DOMAIN / BRONZE_MANIFEST, TABLES)
    with staging(output_dir) as target:
        entries = []
        for relative in layout():
            root, *path = relative.parts
            if root == "reports":
                source = report_dir / relative.name
            elif path[0] == "00_origin":
                source = raw_dir / relative.name
            else:
                source = data_dir.joinpath(*path)
            entries.append(copy_artifact(source, target, relative, limit))
        check_bronze_identity(entries, provenance)
        metadata = {"version": 2, "max_file_bytes": limit, "artifacts": entries}
        (target / MANIFEST).write_bytes(json_bytes(metadata))
        (target / CHECKSUMS).write_bytes(checksum_bytes(target, entries))
        verify(target)
    print(f"Package written: {output_dir}")


def package_file(root, relative):
    path = root / relative
    if path.resolve() != path or not path.is_file():
        raise ValueError(f"Missing or linked package file: {relative}")
    return path


def check_parts(root, entry, plan, output):
    if len(plan) != len(entry["parts"]):
        raise ValueError(f"Invalid part count: {entry['path']}")
    entire = hashlib.sha256()
    for (expected_path, size), part in zip(plan, entry["parts"], strict=True):
        if part["path"] != expected_path.as_posix() or part["bytes"] != size:
            raise ValueError(f"Invalid part entry: {expected_path}")
        path = package_file(root, expected_path)
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            stream_chunk(stream, size, (digest, entire), output)
            if stream.read(1) or digest.hexdigest() != part["sha256"]:
                raise ValueError(f"Package part size or SHA-256 differs: {expected_path}")
    if entire.hexdigest() != entry.get("gzip_sha256", entry["sha256"]):
        raise ValueError(f"Whole-file SHA-256 differs: {entry['path']}")


def check_artifact(root, target, relative, entry, limit):
    size = entry["bytes"]
    if type(size) is not int or size < 0 or entry["path"] != relative.as_posix():
        raise ValueError(f"Invalid artifact entry: {relative}")
    compressed = compressed_source(relative, size, limit)
    name = upload_name(relative, compressed)
    destination = target / relative if target is not None else None
    if destination is not None:
        destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("wb") if destination is not None else nullcontext() as output:
        if compressed:
            with TemporaryFile() as encoded:
                check_parts(root, entry, part_plan(name, entry["gzip_bytes"], limit, 2), encoded)
                encoded.seek(0)
                digest = hashlib.sha256()
                with gzip.GzipFile(fileobj=encoded) as stream:
                    stream_chunk(stream, size, (digest,), output)
                    if stream.read(1) or digest.hexdigest() != entry["sha256"]:
                        raise ValueError(f"Uncompressed size or SHA-256 differs: {relative}")
        else:
            check_parts(root, entry, part_plan(name, size, limit), output)
    if destination is not None and sha256(destination) != entry["sha256"]:
        raise ValueError(f"Restored file SHA-256 differs: {relative}")
    if relative.suffix == ".parquet" and (destination is not None or size <= limit):
        if parquet_rows(destination or package_file(root, name)) != entry["rows"]:
            raise ValueError(f"Parquet row count differs: {relative}")


def verify(package_dir, restore_dir=None):
    if restore_dir is not None and directories_overlap(package_dir, restore_dir):
        raise ValueError("The restore directory must be separate from the package.")
    metadata = json.loads(package_file(package_dir, Path(MANIFEST)).read_bytes())
    limit = metadata["max_file_bytes"]
    entries = metadata["artifacts"]
    if (metadata["version"] != 2 or type(limit) is not int or not 0 < limit <= MAX_BYTES
            or len(entries) != len(list(layout()))):
        raise ValueError("Invalid package manifest.")
    if package_file(package_dir, Path(CHECKSUMS)).read_bytes() != checksum_bytes(package_dir, entries):
        raise ValueError(f"{CHECKSUMS} differs from the manifest or its part hashes.")
    with staging(restore_dir) if restore_dir is not None else nullcontext() as target:
        for relative, entry in zip(layout(), entries, strict=True):
            check_artifact(package_dir, target, relative, entry, limit)
    print(f"Verified {len(entries)} files and {sum(len(entry['parts']) for entry in entries)} package parts.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    package = commands.add_parser("build", help="Build from generated and validated outputs")
    for flag in ("raw-dir", "data-dir", "report-dir", "output-dir"):
        package.add_argument(f"--{flag}", required=True, type=Path)
    package.add_argument("--limit-bytes", type=int, default=MAX_BYTES)
    check = commands.add_parser("verify", help="Verify every part and optionally restore exact Parquet files")
    check.add_argument("--package-dir", required=True, type=Path)
    check.add_argument("--restore-dir", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "build":
            build(args.raw_dir.resolve(), args.data_dir.resolve(), args.report_dir.resolve(),
                  args.output_dir.resolve(), args.limit_bytes)
        else:
            verify(args.package_dir.resolve(), args.restore_dir.resolve() if args.restore_dir else None)
    except (OSError, KeyError, ValueError, TypeError, EOFError, ZlibError, pa.ArrowException) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
