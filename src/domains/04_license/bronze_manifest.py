"""Provenance for immutable Bronze files."""

import json
from datetime import datetime, timedelta, timezone

from pipeline_io import sha256


MANIFEST = "ingestion_manifest.json"
VERSION = 1


def now_utc():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def read_manifest(path, tables):
    payload = path.read_bytes()
    document = json.loads(payload)
    if not isinstance(document, dict) or document.get("version") != VERSION:
        raise ValueError("Unsupported Bronze ingestion manifest version.")
    rows = document.get("entries")
    if not isinstance(rows, list) or any(
        not isinstance(row, dict) or not isinstance(row.get("table"), str) for row in rows
    ):
        raise ValueError("Invalid entries in the Bronze ingestion manifest.")
    entries = {row["table"]: row for row in rows}
    if len(entries) != len(rows) or set(entries) != set(tables):
        raise ValueError("Bronze ingestion manifest must have one entry per configured table.")
    return payload, entries


def artifact_identity(table, source, source_digest, output, row_count):
    return {
        "table": table,
        "source_file": source.path.name,
        "source_sha256": source_digest,
        "source_format": source.format,
        "source_encoding": source.encoding,
        "source_sheet": source.sheet,
        "selected_columns": list(source.columns) if source.columns is not None else None,
        "bronze_file": output.name,
        "bronze_sha256": sha256(output),
        "row_count": row_count,
    }


def utc_timestamp(entry, field):
    value = entry.get(field)
    try:
        timestamp = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        raise ValueError(f"Invalid UTC timestamp: {field}.") from None
    if timestamp.utcoffset() != timedelta(0):
        raise ValueError(f"Expected a UTC timestamp: {field}.")
    return timestamp


def check_entry(entry, identity):
    for key, value in identity.items():
        if key not in entry or type(entry[key]) is not type(value) or entry[key] != value:
            raise ValueError(f"Manifest {key} differs from the input or Bronze file.")

    started = utc_timestamp(entry, "source_read_started_at_utc")
    recorded = utc_timestamp(entry, "recorded_at_utc")
    if started > recorded:
        raise ValueError("Manifest recording precedes source reading.")

    status = entry.get("status")
    if status == "created":
        created = utc_timestamp(entry, "bronze_created_at_utc")
        if not started <= created <= recorded:
            raise ValueError("Bronze creation time is outside the recorded execution window.")
    elif status == "verified_existing":
        if "bronze_created_at_utc" not in entry or entry["bronze_created_at_utc"] is not None:
            raise ValueError("The original creation time of a pre-existing file must be null.")
    else:
        raise ValueError("Unrecognized Bronze ingestion manifest status.")


def manifest_bytes(entries):
    payload = json.dumps({"version": VERSION, "entries": entries}, ensure_ascii=False, indent=2)
    return (payload + "\n").encode("utf-8")
