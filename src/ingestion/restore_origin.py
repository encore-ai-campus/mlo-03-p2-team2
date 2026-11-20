"""Verify the shared Origin files and optionally restore the two original CSVs."""

import argparse
import csv
import gzip
import hashlib
import os
import shutil
import sys
from contextlib import ExitStack, nullcontext
from pathlib import Path
from tempfile import TemporaryFile, mkstemp
from zlib import error as ZlibError


PROJECT = Path(__file__).resolve().parents[2]
BUFFER = 1024 * 1024
MAX_PART_BYTES = 100_000_000
LARGE_FILES = ("business_licenses.csv", "food_inspections.csv")
SMALL_FILES = ("community_areas.geojson", "area_columns.json", "food_columns.json", "license_columns.json")


def parts(name):
    return (f"{name}.gz.part-001", f"{name}.gz.part-002")


def checksum(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def verify_uploaded_files(root):
    expected = {*SMALL_FILES, *(part for name in LARGE_FILES for part in parts(name))}
    lines = (root / "SHA256SUMS").read_text(encoding="ascii").splitlines()
    hashes = dict((name, digest) for digest, name in (line.split("  ", 1) for line in lines))
    if len(lines) != len(expected) or set(hashes) != expected:
        raise ValueError("SHA256SUMS must list the four source files and four CSV parts.")
    for name, digest in hashes.items():
        path = root / name
        if path.stat().st_size > MAX_PART_BYTES or checksum(path) != digest.lower():
            raise ValueError(f"File size or SHA-256 differs: {name}")


def check_original(path, metadata):
    size, digest = metadata
    if path.stat().st_size != size or checksum(path) != digest:
        raise ValueError(f"Original source size or SHA-256 differs: {path.name}")


def check_csv_parts(root, name, metadata, output=None):
    remaining, expected = metadata
    digest = hashlib.sha256()
    with TemporaryFile() as encoded:
        for part in parts(name):
            with (root / part).open("rb") as stream:
                shutil.copyfileobj(stream, encoded, BUFFER)
        encoded.seek(0)
        with gzip.GzipFile(fileobj=encoded) as source:
            while remaining:
                block = source.read(min(remaining, BUFFER))
                if not block:
                    break
                remaining -= len(block)
                digest.update(block)
                if output is not None:
                    output.write(block)
            if remaining or source.read(1) or digest.hexdigest() != expected:
                raise ValueError(f"Restored size or SHA-256 differs: {name}")


def run(root, catalog, restore):
    verify_uploaded_files(root)
    with catalog.open(encoding="utf-8-sig", newline="") as stream:
        metadata = {row["File"]: (int(row["Bytes"]), row["SHA256"].lower())
                    for row in csv.DictReader(stream)}
    for name in SMALL_FILES:
        check_original(root / name, metadata[name])

    with ExitStack() as cleanup:
        pending = {}
        for name in LARGE_FILES:
            destination = root / name
            output = nullcontext()
            if destination.exists():
                check_original(destination, metadata[name])
            elif restore:
                descriptor, path = mkstemp(suffix=".tmp", dir=root)
                pending[name] = Path(path)
                cleanup.callback(pending[name].unlink)
                output = os.fdopen(descriptor, "wb")
            with output as stream:
                check_csv_parts(root, name, metadata[name], stream)
        for name, path in pending.items():
            destination = root / name
            try:
                os.link(path, destination)
            except FileExistsError:
                check_original(destination, metadata[name])

    print(f"Verified {len(SMALL_FILES) + len(LARGE_FILES)} sources and {2 * len(LARGE_FILES)} split parts.")
    if pending:
        print(f"Restored {len(pending)} CSV files to {root}.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--origin-dir", type=Path, default=PROJECT / "data" / "origin")
    parser.add_argument("--catalog", type=Path, default=PROJECT / "metadata/source_catalog/verification/download_manifest.csv")
    parser.add_argument("--restore", action="store_true", help="Write CSVs missing from the Origin directory")
    args = parser.parse_args()
    try:
        run(args.origin_dir.resolve(), args.catalog, args.restore)
    except (OSError, EOFError, ZlibError, KeyError, ValueError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
