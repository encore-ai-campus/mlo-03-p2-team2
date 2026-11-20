"""Materialize a new CSV snapshot from a base version and incoming full rows."""

import csv
import re
import shutil
from contextlib import contextmanager

from config import directories_overlap
from normalization import POSITIVE_ID
from pipeline_io import json_bytes, sha256, staging


SOURCE_KEYS = {"business_licenses": "LICENSE ID", "food_inspections": "Inspection ID"}


@contextmanager
def csv_rows(path, encoding, key_column):
    with path.open(encoding=encoding, newline="") as stream:
        reader = csv.reader(stream, strict=True)
        header = next(reader, [])
        if header:
            header[0] = header[0].removeprefix("\ufeff")
        if key_column not in header or len(header) != len(set(header)) or any(not c.strip() for c in header):
            raise ValueError(f"{path}: missing key or invalid CSV header ({key_column}).")
        key_index = header.index(key_column)

        def keyed_rows():
            for row in reader:
                if len(row) != len(header):
                    raise ValueError(f"{path}, line {reader.line_num}: unexpected column count.")
                key = row[key_index].strip()
                if not re.fullmatch(POSITIVE_ID, key):
                    raise ValueError(f"{path}, line {reader.line_num}: invalid {key_column}: {key!r}.")
                yield key, row

        yield header, keyed_rows()


def merge_csv(base, delta, output, key_column, encoding):
    csv.field_size_limit(8 * 1024 * 1024)
    with csv_rows(base, encoding, key_column) as (header, base_rows):
        with csv_rows(delta, encoding, key_column) as (delta_header, delta_rows):
            if set(header) != set(delta_header):
                raise ValueError(f"{delta}: incoming rows must have the same columns as {base.name}.")
            positions = [delta_header.index(name) for name in header]
            incoming = {}
            for key, row in delta_rows:
                aligned = [row[index] for index in positions]
                if incoming.setdefault(key, aligned) != aligned:
                    raise ValueError(f"{delta}: conflicting incoming rows for {key_column} {key!r}.")

        seen = set()
        changed = 0
        with output.open("w", encoding=encoding, newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(header)
            for key, row in base_rows:
                if key in seen:
                    raise ValueError(f"{base}: duplicate {key_column} {key!r}.")
                seen.add(key)
                resolved = incoming.pop(key, row)
                changed += resolved != row
                writer.writerow(resolved)
            writer.writerows(incoming.values())
    return {"key_column": key_column, "base_rows": len(seen), "updated_rows": changed,
            "inserted_rows": len(incoming), "result_rows": len(seen) + len(incoming)}


def merge_sources(config, raw, delta, combined):
    destinations = [config.stage_dir(stage).resolve() for stage in ("bronze", "silver", "gold")]
    protected = [raw, config.reports, *destinations]
    if (directories_overlap(delta, combined)
            or any(directories_overlap(directory, other)
                   for directory in (delta, combined) for other in protected)):
        raise ValueError("Incoming and combined directories must be separate from all input and output directories.")
    if not delta.is_dir():
        raise ValueError(f"Incoming directory does not exist: {delta}")

    files = {name: source.path.relative_to(raw) for name, source in config.sources.items()}
    if any(source.format != "csv" for source in config.sources.values()):
        raise ValueError("Incoming-row mode requires CSV source files.")
    if not any((delta / relative).is_file() for relative in files.values()):
        raise ValueError(f"No incoming CSV found. Expected one or more of: {', '.join(map(str, files.values()))}.")
    if any((delta / relative).is_file() and (delta / relative).resolve() != delta / relative
           for relative in files.values()):
        raise ValueError("Incoming CSV paths must stay inside the incoming directory.")

    entries = []
    with staging(combined) as target:
        for name, relative in files.items():
            source = config.sources[name]
            incoming, output = delta / relative, target / relative
            output.parent.mkdir(parents=True, exist_ok=True)
            base_hash = sha256(source.path)
            incoming_hash = sha256(incoming) if incoming.is_file() else None
            if incoming_hash is None:
                shutil.copyfile(source.path, output)
                counts = {"updated_rows": 0, "inserted_rows": 0}
            else:
                counts = merge_csv(source.path, incoming, output, SOURCE_KEYS[name], source.encoding)
            result_hash = sha256(output)
            if (sha256(source.path) != base_hash or (incoming_hash is None and result_hash != base_hash)
                    or (incoming_hash is not None and sha256(incoming) != incoming_hash)):
                raise ValueError(f"An input changed while merging {name}.")
            entries.append({"table": name, "file": relative.as_posix(), "base_sha256": base_hash,
                            "incoming_sha256": incoming_hash, "result_sha256": result_hash, **counts})
        (target / "merge_manifest.json").write_bytes(json_bytes({"version": 1, "entries": entries}))
    print(f"Combined raw snapshot and merge manifest: {combined}")
