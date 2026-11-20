"""Partition Bronze Violations fragments into accepted and quarantine Parquet.

Run from the repository root: python -m src.silver.violations_reconciliation
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import uuid

import pyarrow as pa
import pyarrow.parquet as pq

from src.bronze.paths import PROJECT_ROOT
from src.profiling.profile_violations import BRONZE_RELATIVE, FRAGMENT_SEPARATOR, ORIGIN_RELATIVE, sha256
from src.silver.violations import SILVER_SCHEMA, parse_fragment


ACCEPTED_RELATIVE = Path("data/02_silver/food_inspections/violations/inspection_violations_accepted.parquet")
QUARANTINE_RELATIVE = Path("data/quarantine/food_inspections/violations/inspection_violations_quarantine.parquet")
REPORT_RELATIVE = Path("reports/quality/violations_reconciliation.json")
MAPPING_RELATIVE = Path("metadata/standards/violations_reconciliation_mapping.csv")
LOG_RELATIVE = Path("logs/violations_reconciliation_runs.jsonl")
QUARANTINE_SCHEMA = SILVER_SCHEMA.append(pa.field("rejection_reason", pa.string(), nullable=False))
CODE_PATTERN = re.compile(r"\d+[A-Z]?\Z")
SOURCE_COLUMNS = ["Inspection ID", "Violations", "_SRC_FILE", "_LOAD_DTM"]
CHUNK = 10_000


def _record_bytes(row: dict) -> bytes:
    return (json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _rows(path: Path, columns: list[str]):
    parquet = pq.ParquetFile(path)
    for batch in parquet.iter_batches(columns=columns, batch_size=CHUNK):
        yield from batch.to_pylist()


def _reason(row: dict) -> str | None:
    """Only fully parsed, traceable fragments enter the accepted table."""
    if not row["inspection_id"]:
        return "MISSING_INSPECTION_ID"
    if not row["_SRC_FILE"] or not row["_LOAD_DTM"]:
        return "MISSING_LINEAGE_METADATA"
    if row["parsing_status"] != "PARSED":
        return row["parsing_status"]
    if row["violation_code"] is None or not CODE_PATTERN.fullmatch(row["violation_code"]):
        return "INVALID_VIOLATION_CODE"
    if not row["violation_description"]:
        return "MISSING_DESCRIPTION"
    if not row["violation_comments"]:
        return "MISSING_COMMENTS"
    return None


def _content(path: Path, schema: pa.Schema) -> tuple[int, str, Counter, Counter]:
    parquet = pq.ParquetFile(path)
    if parquet.schema_arrow != schema:
        raise ValueError(f"Unexpected schema: {path}")
    digest = hashlib.sha256()
    statuses, nulls = Counter(), Counter()
    count = 0
    for row in _rows(path, schema.names):
        digest.update(_record_bytes(row))
        count += 1
        statuses[row["parsing_status"]] += 1
        for name in schema.names:
            nulls[name] += row[name] is None
    if count != parquet.metadata.num_rows:
        raise ValueError(f"Parquet metadata row mismatch: {path}")
    return count, digest.hexdigest(), statuses, nulls


def _publish(temp: Path, final: Path) -> None:
    if final.exists():
        if sha256(temp) != sha256(final):
            raise FileExistsError(f"Existing output differs; refusing overwrite: {final}")
        temp.unlink()
    else:
        os.replace(temp, final)


def run(root: Path = PROJECT_ROOT, output_root: Path | None = None) -> dict:
    """Recompute both reconciliation levels from Bronze; never alter input data."""
    root = Path(root)
    output_root = Path(output_root) if output_root is not None else root
    bronze_path = root / BRONZE_RELATIVE
    origin_path = root / ORIGIN_RELATIVE
    for path in (bronze_path, origin_path):
        if not path.is_file():
            raise FileNotFoundError(path)
    bronze_before, origin_before = sha256(bronze_path), sha256(origin_path)
    started = datetime.now(timezone.utc).isoformat()
    counts, reasons = Counter(), Counter()
    expected_lineage = hashlib.sha256()
    accepted_path = output_root / ACCEPTED_RELATIVE
    quarantine_path = output_root / QUARANTINE_RELATIVE
    for path in (accepted_path, quarantine_path):
        path.parent.mkdir(parents=True, exist_ok=True)
    temps = [path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp") for path in (accepted_path, quarantine_path)]
    result = None
    completed = False
    failure = None
    try:
        source = pq.ParquetFile(bronze_path)
        if not set(SOURCE_COLUMNS) <= set(source.schema_arrow.names):
            raise ValueError("Bronze required columns are missing")
        pending = [[], []]
        with pq.ParquetWriter(temps[0], SILVER_SCHEMA, compression="zstd") as accepted_writer, pq.ParquetWriter(temps[1], QUARANTINE_SCHEMA, compression="zstd") as quarantine_writer:
            writers = [accepted_writer, quarantine_writer]
            for row_number, source_row in enumerate(_rows(bronze_path, SOURCE_COLUMNS), 1):
                counts["bronze_inspections"] += 1
                raw = source_row["Violations"]
                if raw is None or not raw.strip():
                    counts["empty_inspections"] += 1
                    counts["null_cells" if raw is None else "empty_strings" if raw == "" else "whitespace_strings"] += 1
                    continue
                counts["nonblank_inspections"] += 1
                fragments = FRAGMENT_SEPARATOR.split(raw)
                bad_separator = raw.count("|") != len(fragments) - 1
                if bad_separator:
                    fragments = [raw]
                    counts["unexpected_delimiter_inspections"] += 1
                for sequence, fragment in enumerate(fragments, 1):
                    counts["candidate_fragments"] += 1
                    parsed = ({"violation_code": None, "violation_description": None,
                               "violation_comments": None, "parsing_status": "UNRECOGNIZED_SEPARATOR"}
                              if bad_separator else parse_fragment(fragment))
                    item = {"inspection_id": source_row["Inspection ID"],
                            "bronze_row_number": row_number, "item_sequence_num": sequence,
                            "_SRC_FILE": source_row["_SRC_FILE"], "_LOAD_DTM": source_row["_LOAD_DTM"],
                            "source_violations_fragment": fragment, **parsed}
                    expected_lineage.update(_record_bytes({"bronze_row_number": row_number,
                                                           "item_sequence_num": sequence,
                                                           "inspection_id": item["inspection_id"],
                                                           "_SRC_FILE": item["_SRC_FILE"],
                                                           "_LOAD_DTM": item["_LOAD_DTM"],
                                                           "source_violations_fragment": fragment}))
                    reason = _reason(item)
                    partition = 1 if reason else 0
                    if reason:
                        item["rejection_reason"] = reason
                        reasons[reason] += 1
                        counts["quarantined"] += 1
                    else:
                        counts["accepted"] += 1
                    pending[partition].append(item)
                    if len(pending[partition]) >= CHUNK:
                        writers[partition].write_table(pa.Table.from_pylist(pending[partition], schema=(SILVER_SCHEMA, QUARANTINE_SCHEMA)[partition]))
                        pending[partition].clear()
            for partition in (0, 1):
                if pending[partition]:
                    writers[partition].write_table(pa.Table.from_pylist(pending[partition], schema=(SILVER_SCHEMA, QUARANTINE_SCHEMA)[partition]))

        accepted_rows, accepted_hash, accepted_statuses, accepted_nulls = _content(temps[0], SILVER_SCHEMA)
        quarantined_rows, quarantine_hash, quarantine_statuses, quarantine_nulls = _content(temps[1], QUARANTINE_SCHEMA)
        issues = {"duplicate_grain": 0, "misclassified_accepted": 0,
                  "misclassified_quarantine": 0}
        issues["inspection_reconciliation"] = abs(counts["bronze_inspections"] - counts["empty_inspections"] - counts["nonblank_inspections"])
        issues["fragment_reconciliation"] = abs(counts["candidate_fragments"] - accepted_rows - quarantined_rows)
        issues["accepted_count"] = abs(counts["accepted"] - accepted_rows)
        issues["quarantine_count"] = abs(counts["quarantined"] - quarantined_rows)
        issues["unexpected_accepted_status"] = accepted_rows - accepted_statuses["PARSED"]
        issues["quarantine_reason_count"] = abs(quarantined_rows - sum(reasons.values()))
        issues["bronze_metadata_count"] = abs(counts["bronze_inspections"] - source.metadata.num_rows)
        seen, lineage = set(), hashlib.sha256()
        accepted_iter = iter(_rows(temps[0], SILVER_SCHEMA.names))
        quarantine_iter = iter(_rows(temps[1], QUARANTINE_SCHEMA.names))
        a, q = next(accepted_iter, None), next(quarantine_iter, None)
        while a is not None or q is not None:
            use_accepted = q is None or (a is not None and (a["bronze_row_number"], a["item_sequence_num"]) < (q["bronze_row_number"], q["item_sequence_num"]))
            row = a if use_accepted else q
            key = (row["bronze_row_number"], row["item_sequence_num"])
            if key in seen:
                issues["duplicate_grain"] += 1
            seen.add(key)
            lineage.update(_record_bytes({name: row[name] for name in ("bronze_row_number", "item_sequence_num", "inspection_id", "_SRC_FILE", "_LOAD_DTM", "source_violations_fragment")}))
            if use_accepted:
                if _reason(row) is not None:
                    issues["misclassified_accepted"] += 1
                a = next(accepted_iter, None)
            else:
                if row["rejection_reason"] != _reason(row):
                    issues["misclassified_quarantine"] += 1
                q = next(quarantine_iter, None)
        issues["lineage_or_missing_fragment"] = int(lineage.hexdigest() != expected_lineage.hexdigest())
        issues["input_hash_changed"] = int(sha256(bronze_path) != bronze_before or sha256(origin_path) != origin_before)
        status = "PASS" if not any(issues.values()) else "FAIL"
        unexpected_reasons = {reason: count for reason, count in reasons.items()
                              if reason != "MISSING_COMMENTS_MARKER"}
        result = {"status": status, "source_bronze": BRONZE_RELATIVE.as_posix(),
                  "source_bronze_sha256": bronze_before, "origin_sha256": origin_before,
                  "accepted_file": ACCEPTED_RELATIVE.as_posix(), "quarantine_file": QUARANTINE_RELATIVE.as_posix(),
                  "counts": dict(counts), "quarantine_reasons": dict(reasons),
                  "unexpected_quarantine_reasons": unexpected_reasons,
                  "unexpected_quarantine_count": sum(unexpected_reasons.values()),
                  "issues": issues,
                  "accepted_schema": str(SILVER_SCHEMA), "quarantine_schema": str(QUARANTINE_SCHEMA),
                  "accepted_content_sha256": accepted_hash, "quarantine_content_sha256": quarantine_hash,
                  "accepted_statuses": dict(accepted_statuses), "quarantine_statuses": dict(quarantine_statuses),
                  "accepted_nulls": dict(accepted_nulls), "quarantine_nulls": dict(quarantine_nulls),
                  "lineage_sha256": lineage.hexdigest()}
        if status != "PASS":
            raise ValueError(f"Reconciliation failed: {issues}")
        # Reject a conflicting destination before publishing either partition.
        for temp, final in zip(temps, (accepted_path, quarantine_path)):
            if final.exists() and sha256(temp) != sha256(final):
                raise FileExistsError(f"Existing output differs; refusing overwrite: {final}")
        _publish(temps[0], accepted_path)
        _publish(temps[1], quarantine_path)
        report_path = output_root / REPORT_RELATIVE
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        mapping_path = output_root / MAPPING_RELATIVE
        mapping_path.parent.mkdir(parents=True, exist_ok=True)
        with mapping_path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=["source_file", "source_column", "target_file", "transformation", "affected_rows", "status"])
            writer.writeheader()
            writer.writerows([
                {"source_file": BRONZE_RELATIVE.as_posix(), "source_column": "Violations", "target_file": ACCEPTED_RELATIVE.as_posix(), "transformation": "Split fragments; accept complete PARSED records", "affected_rows": accepted_rows, "status": "APPLIED"},
                {"source_file": BRONZE_RELATIVE.as_posix(), "source_column": "Violations", "target_file": QUARANTINE_RELATIVE.as_posix(), "transformation": "Preserve incomplete or invalid fragments with reason", "affected_rows": quarantined_rows, "status": "APPLIED"},
            ])
        completed = True
        return result
    except Exception as error:
        failure = repr(error)
        raise
    finally:
        for temp in temps:
            if temp.exists():
                temp.unlink()
        log_path = output_root / LOG_RELATIVE
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"started_at_utc": started, "finished_at_utc": datetime.now(timezone.utc).isoformat(),
                                     "status": result["status"] if completed else "FAILED",
                                     "error": failure, "counts": result["counts"] if result else dict(counts),
                                     "quarantine_reasons": dict(reasons)}, ensure_ascii=False) + "\n")


def main() -> None:
    print(json.dumps(run(), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
