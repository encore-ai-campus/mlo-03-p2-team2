"""Create Silver violation records from Food Inspections Bronze.

Run from the repository root with: python -m src.domains.02_violation.silver
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import csv
import hashlib
import json
import os
from pathlib import Path
import uuid

import pyarrow as pa
import pyarrow.parquet as pq

from src.bronze.paths import PROJECT_ROOT
from .profiling import (
    BRONZE_RELATIVE,
    CODE_HEADER,
    FRAGMENT_SEPARATOR,
    ORIGIN_RELATIVE,
    OUTPUT_RELATIVE as PROFILE_RELATIVE,
    COMMENTS_MARKER,
    origin_snapshot,
    sha256,
)


SILVER_RELATIVE = Path(
    "data/02_silver/02_violation/02_inspection_violations.parquet"
)
MAPPING_RELATIVE = Path("metadata/standards/02_violation/violations_mapping.csv")
RUN_LOG_RELATIVE = Path("logs/02_violation/violations_silver_runs.jsonl")
BATCH_SIZE = 5_000
WRITE_BATCH_SIZE = 25_000
SOURCE_DATASET = "food_inspections"
SOURCE_COLUMN = "Violations"
INSPECTION_ID_COLUMN = "Inspection ID"
SOURCE_ROW_COLUMN = "source_row_num"

SILVER_SCHEMA = pa.schema([
    pa.field("inspection_id", pa.string()),
    pa.field("source_row_num", pa.int64(), nullable=False),
    pa.field("item_sequence_num", pa.int32(), nullable=False),
    pa.field("source_violations_fragment", pa.string(), nullable=False),
    pa.field("violation_code", pa.string()),
    pa.field("violation_description", pa.string()),
    pa.field("violation_comments", pa.string()),
    pa.field("parsing_status", pa.string(), nullable=False),
])

MAPPING_FIELDS = [
    "source_dataset",
    "source_origin_file",
    "source_bronze_file",
    "source_column",
    "target_file",
    "target_column",
    "transformation",
    "before_pattern",
    "after",
    "affected_rows",
    "affected_unit",
    "status",
    "note",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def parse_fragment(fragment: str) -> dict:
    """Parse only fields with a visible boundary in the observed source pattern."""
    header = CODE_HEADER.match(fragment)
    if not header:
        return {
            "violation_code": None,
            "violation_description": None,
            "violation_comments": None,
            "parsing_status": "UNPARSED_CODE_HEADER",
        }
    body_start = header.start("body")
    marker = COMMENTS_MARKER.search(fragment, body_start)
    if not marker:
        # Without a Comments marker, the boundary between description and
        # comments cannot be inferred. Keep only the code and raw fragment.
        return {
            "violation_code": header.group("code"),
            "violation_description": None,
            "violation_comments": None,
            "parsing_status": "MISSING_COMMENTS_MARKER",
        }

    description = fragment[body_start:marker.start()].strip()
    comments = fragment[marker.end():].strip()
    if not description:
        status = "EMPTY_DESCRIPTION"
    elif not comments:
        status = "EMPTY_COMMENTS"
    else:
        status = "PARSED"
    return {
        "violation_code": header.group("code"),
        "violation_description": description or None,
        "violation_comments": comments or None,
        "parsing_status": status,
    }


def _mapping_rows(counts: Counter, actual: dict, silver_path: str) -> list[dict]:
    source = {
        "source_dataset": SOURCE_DATASET,
        "source_origin_file": ORIGIN_RELATIVE.as_posix(),
        "source_bronze_file": BRONZE_RELATIVE.as_posix(),
        "source_column": SOURCE_COLUMN,
        "target_file": silver_path,
        "status": "APPLIED",
    }
    common_note = (
        f"input_cells={counts['input_rows']}; nonempty_cells={counts['nonempty_cells']}; "
        f"candidate_records={actual['output_rows']}"
    )
    specifications = [
        (
            "source_violations_fragment",
            "Split each nonempty cell on the observed whitespace-padded pipe delimiter; retain each raw fragment.",
            r"\s+\|\s+",
            "One output row per fragment in original order.",
            actual["output_rows"],
            "Silver records",
            common_note,
        ),
        (
            "inspection_id",
            "Copy the Bronze Inspection ID as a string for traceability.",
            "Bronze Inspection ID",
            "Same identifier repeated for each fragment from that inspection.",
            actual["output_rows"],
            "Silver records",
            "Copied from the shared Bronze row and repeated for each fragment.",
        ),
        (
            "source_row_num",
            "Copy the source row number preserved in the shared Bronze Parquet.",
            "Positive integer source row number",
            "The original inspection record number is repeated for each violation fragment.",
            actual["output_rows"],
            "Silver records",
            "Used with item_sequence_num to identify a violation fragment within its source row.",
        ),
        (
            "violation_code",
            "Extract the prefix matching digits, optional uppercase suffix, period, and whitespace.",
            r"^(\d+[A-Z]?)\.\s+",
            "Captured code string; no numeric conversion or code meaning inference.",
            actual["code_rows"],
            "Silver records",
            f"Distinct codes observed={actual['distinct_codes']}; extraction failures={actual['unparsed_code_header']}.",
        ),
        (
            "violation_description",
            "Take text between the code header and the visible Comments marker.",
            "Description + ' - Comments: ' + comments",
            "Trim outer whitespace around the description; leave NULL if marker is absent.",
            actual["description_rows"],
            "Silver records",
            f"Missing marker records retain raw fragment and code; count={actual['missing_comments_marker']}.",
        ),
        (
            "violation_comments",
            "Take text following the first visible Comments marker.",
            "Comments: <comment text>",
            "Trim outer whitespace around the comments text.",
            actual["comments_rows"],
            "Silver records",
            f"Comments marker was present in {actual['comments_rows']} records.",
        ),
        (
            "parsing_status",
            "Set an explicit status from code/header and Comments boundary checks.",
            "Observed fragment shape",
            "PARSED or a specific exception status.",
            actual["output_rows"],
            "Silver records",
            json.dumps(actual["status_counts"], ensure_ascii=False, sort_keys=True),
        ),
        (
            "no child record",
            "Do not create violation records for NULL, empty, or whitespace-only cells.",
            "Blank cell",
            "No Silver violation row.",
            counts["null_cells"] + counts["empty_cells"] + counts["whitespace_cells"],
            "Bronze source cells",
            f"null={counts['null_cells']}; empty={counts['empty_cells']}; whitespace_only={counts['whitespace_cells']}.",
        ),
        (
            "multiple violation records",
            "Split a cell into multiple ordered records when the observed pipe delimiter occurs.",
            "At least one whitespace-padded pipe delimiter",
            "One Silver record per separated candidate.",
            counts["multi_violation_cells"],
            "Bronze source cells",
            "Every literal pipe was matched by the measured separator pattern.",
        ),
    ]
    return [
        {
            **source,
            "target_column": target_column,
            "transformation": transformation,
            "before_pattern": before_pattern,
            "after": after,
            "affected_rows": affected_rows,
            "affected_unit": affected_unit,
            "note": note,
        }
        for (
            target_column, transformation, before_pattern, after,
            affected_rows, affected_unit, note,
        ) in specifications
    ]


def _write_mapping(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=MAPPING_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def _publish_without_overwrite(temp_path: Path, final_path: Path) -> None:
    """Publish a new file, or allow only an identical deterministic rerun."""
    if final_path.exists():
        if sha256(temp_path) != sha256(final_path):
            raise FileExistsError(f"Refusing to overwrite different existing file: {final_path}")
        temp_path.unlink()
        return
    os.replace(temp_path, final_path)


def _readback(path: Path) -> dict:
    parquet = pq.ParquetFile(path)
    if parquet.schema_arrow != SILVER_SCHEMA:
        raise ValueError(f"Silver schema mismatch: {parquet.schema_arrow}")
    result = {
        "output_rows": 0,
        "status_counts": Counter(),
        "distinct_codes": set(),
        "code_rows": 0,
        "description_rows": 0,
        "comments_rows": 0,
        "unparsed_code_header": 0,
        "missing_comments_marker": 0,
    }
    for batch in parquet.iter_batches(
        columns=["violation_code", "violation_description", "violation_comments", "parsing_status"],
        batch_size=50_000,
    ):
        data = batch.to_pydict()
        for code, description, comments, status in zip(
            data["violation_code"], data["violation_description"],
            data["violation_comments"], data["parsing_status"],
        ):
            result["output_rows"] += 1
            result["status_counts"][status] += 1
            if code is not None:
                result["code_rows"] += 1
                result["distinct_codes"].add(code)
            result["description_rows"] += description is not None
            result["comments_rows"] += comments is not None
            result["unparsed_code_header"] += status == "UNPARSED_CODE_HEADER"
            result["missing_comments_marker"] += status == "MISSING_COMMENTS_MARKER"
    result["distinct_codes"] = len(result["distinct_codes"])
    result["status_counts"] = dict(sorted(result["status_counts"].items()))
    if result["output_rows"] != parquet.metadata.num_rows:
        raise ValueError("Silver readback row count differs from Parquet metadata")
    return result


def _append_run_log(root: Path, record: dict) -> None:
    path = root / RUN_LOG_RELATIVE
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="") as stream:
        stream.write(json.dumps(record, ensure_ascii=False) + "\n")


def run(root: Path = PROJECT_ROOT) -> dict:
    """Stream only Inspection ID and Violations into a dedicated Silver child table."""
    root = Path(root)
    bronze_path = root / BRONZE_RELATIVE
    origin_before = origin_snapshot(root)
    profile_path = root / PROFILE_RELATIVE
    final_path = root / SILVER_RELATIVE
    mapping_path = root / MAPPING_RELATIVE
    if not profile_path.is_file():
        raise FileNotFoundError(f"Run source profiling first: {profile_path}")

    started_at = utc_now()
    record: dict = {"started_at_utc": started_at, "status": "RUNNING"}
    temp_output = temp_mapping = None
    log_written = False
    try:
        profiling = json.loads(profile_path.read_text(encoding="utf-8"))
        expected = profiling["counts"]
        input_origin_sha = origin_before["source_sha256"]
        input_origin_guard_sha = origin_before["guard_sha256"]
        input_bronze_sha = sha256(bronze_path)
        profiling_bronze_sha = profiling["source"]["bronze_sha256"]
        if input_bronze_sha != profiling_bronze_sha:
            raise ValueError("Bronze SHA-256 differs from the committed profiling result")
        script_sha = sha256(Path(__file__))
        run_id = hashlib.sha256(
            f"{input_bronze_sha}:{script_sha}:{sha256(profile_path)}".encode()
        ).hexdigest()[:32]
        record.update({
            "pipeline_run_id": run_id,
            "dataset": SOURCE_DATASET,
            "source_origin_file": ORIGIN_RELATIVE.as_posix(),
            "source_origin_sha256_before": input_origin_sha,
            "source_bronze_file": BRONZE_RELATIVE.as_posix(),
            "source_bronze_sha256_before": input_bronze_sha,
            "source_column": SOURCE_COLUMN,
            "target_file": SILVER_RELATIVE.as_posix(),
            "mapping_file": MAPPING_RELATIVE.as_posix(),
        })

        parquet = pq.ParquetFile(bronze_path)
        required_columns = {
            INSPECTION_ID_COLUMN, SOURCE_COLUMN, SOURCE_ROW_COLUMN,
        }
        missing = required_columns - set(parquet.schema_arrow.names)
        if missing:
            raise ValueError(f"Bronze file is missing required columns: {sorted(missing)}")

        final_path.parent.mkdir(parents=True, exist_ok=True)
        mapping_path.parent.mkdir(parents=True, exist_ok=True)
        temp_output = final_path.with_name(f".{final_path.name}.{uuid.uuid4().hex}.tmp")
        temp_mapping = mapping_path.with_name(f".{mapping_path.name}.{uuid.uuid4().hex}.tmp")
        counters: Counter = Counter()
        pending: list[dict] = []
        code_values: set[str] = set()
        with pq.ParquetWriter(temp_output, SILVER_SCHEMA, compression="zstd") as writer:
            row_number = 0
            for batch in parquet.iter_batches(
                columns=[INSPECTION_ID_COLUMN, SOURCE_COLUMN, SOURCE_ROW_COLUMN],
                batch_size=BATCH_SIZE,
            ):
                for source_row in batch.to_pylist():
                    row_number += 1
                    counters["input_rows"] += 1
                    if source_row[SOURCE_ROW_COLUMN] != row_number:
                        raise ValueError(
                            f"Bronze source_row_num is not sequential at row {row_number}"
                        )
                    raw = source_row[SOURCE_COLUMN]
                    if raw is None:
                        counters["null_cells"] += 1
                        continue
                    if raw == "":
                        counters["empty_cells"] += 1
                        continue
                    if not raw.strip():
                        counters["whitespace_cells"] += 1
                        continue

                    counters["nonempty_cells"] += 1
                    fragments = FRAGMENT_SEPARATOR.split(raw)
                    literal_pipes = raw.count("|")
                    recognized_pipes = len(fragments) - 1
                    if len(fragments) > 1:
                        counters["multi_violation_cells"] += 1
                    if literal_pipes > recognized_pipes:
                        counters["unrecognized_separator_cells"] += 1
                        fragments = [raw]

                    for sequence, fragment in enumerate(fragments, 1):
                        counters["candidate_records"] += 1
                        parsed = (
                            {
                                "violation_code": None,
                                "violation_description": None,
                                "violation_comments": None,
                                "parsing_status": "UNRECOGNIZED_SEPARATOR",
                            }
                            if literal_pipes > recognized_pipes
                            else parse_fragment(fragment)
                        )
                        status = parsed["parsing_status"]
                        counters[f"status:{status}"] += 1
                        counters["code_rows"] += parsed["violation_code"] is not None
                        counters["description_rows"] += parsed["violation_description"] is not None
                        counters["comments_rows"] += parsed["violation_comments"] is not None
                        if parsed["violation_code"] is not None:
                            code_values.add(parsed["violation_code"])
                        pending.append({
                            "inspection_id": source_row[INSPECTION_ID_COLUMN],
                            "source_row_num": source_row[SOURCE_ROW_COLUMN],
                            "item_sequence_num": sequence,
                            "source_violations_fragment": fragment,
                            **parsed,
                        })
                        if len(pending) >= WRITE_BATCH_SIZE:
                            writer.write_table(pa.Table.from_pylist(pending, schema=SILVER_SCHEMA))
                            counters["written_records"] += len(pending)
                            pending.clear()
            if pending:
                writer.write_table(pa.Table.from_pylist(pending, schema=SILVER_SCHEMA))
                counters["written_records"] += len(pending)
                pending.clear()

        if counters["input_rows"] != parquet.metadata.num_rows:
            raise ValueError("Bronze batch row count differs from file metadata")
        input_totals = {
            "total_rows": "input_rows",
            "null_rows": "null_cells",
            "empty_string_rows": "empty_cells",
            "whitespace_only_rows": "whitespace_cells",
            "nonempty_rows": "nonempty_cells",
            "rows_with_multiple_fragments": "multi_violation_cells",
            "candidate_fragments": "candidate_records",
            "fully_parseable_fragments": "status:PARSED",
            "missing_comments_marker_fragments": "status:MISSING_COMMENTS_MARKER",
            "code_header_failures": "status:UNPARSED_CODE_HEADER",
            "rows_with_unrecognized_pipe_separator": "unrecognized_separator_cells",
        }
        comparisons = {
            profile_key: {"profile": expected[profile_key], "silver": counters[counter_key]}
            for profile_key, counter_key in input_totals.items()
            if expected[profile_key] != counters[counter_key]
        }
        if comparisons:
            raise ValueError(f"Silver source metrics differ from Profiling: {comparisons}")
        if counters["candidate_records"] != counters["written_records"]:
            raise ValueError("Candidate record count differs from records written")
        if len(code_values) != profiling["code_pattern"]["distinct_codes"]:
            raise ValueError("Distinct code count differs from Profiling")

        readback = _readback(temp_output)
        if readback["output_rows"] != counters["candidate_records"]:
            raise ValueError("Silver readback rows differ from parsed candidates")
        if readback["status_counts"] != {
            key.removeprefix("status:"): value
            for key, value in counters.items() if key.startswith("status:")
        }:
            raise ValueError("Silver readback parsing status counts differ from processing counts")
        if readback["distinct_codes"] != profiling["code_pattern"]["distinct_codes"]:
            raise ValueError("Silver readback distinct code count differs from Profiling")
        if readback["description_rows"] != expected["fully_parseable_fragments"]:
            raise ValueError("Silver description count differs from Profiling")
        if readback["comments_rows"] != expected["comments_marker_fragments"]:
            raise ValueError("Silver comments count differs from Profiling")

        mapping_rows = _mapping_rows(counters, readback, SILVER_RELATIVE.as_posix())
        _write_mapping(temp_mapping, mapping_rows)
        mapping_hash = sha256(temp_mapping)
        output_hash = sha256(temp_output)
        origin_after = origin_snapshot(root)
        origin_after_sha = origin_after["source_sha256"]
        bronze_after_sha = sha256(bronze_path)
        if (origin_after_sha != input_origin_sha
                or origin_after["guard_sha256"] != input_origin_guard_sha):
            raise RuntimeError("Origin SHA-256 changed during Silver processing")
        if bronze_after_sha != input_bronze_sha:
            raise RuntimeError("Bronze SHA-256 changed during Silver processing")

        # Check both existing paths before publishing either artifact.
        for temp_path, target_path in ((temp_output, final_path), (temp_mapping, mapping_path)):
            if target_path.exists() and sha256(target_path) != sha256(temp_path):
                raise FileExistsError(f"Refusing to overwrite different existing file: {target_path}")
        _publish_without_overwrite(temp_output, final_path)
        _publish_without_overwrite(temp_mapping, mapping_path)
        temp_output = temp_mapping = None

        record.update({
            "finished_at_utc": utc_now(),
            "status": "SUCCESS",
            "input_rows": counters["input_rows"],
            "null_source_cells": counters["null_cells"],
            "empty_source_cells": counters["empty_cells"],
            "whitespace_only_source_cells": counters["whitespace_cells"],
            "nonempty_source_cells": counters["nonempty_cells"],
            "multiple_violation_source_cells": counters["multi_violation_cells"],
            "candidate_records": counters["candidate_records"],
            "output_rows": readback["output_rows"],
            "output_columns": len(SILVER_SCHEMA),
            "output_schema": str(SILVER_SCHEMA),
            "output_file_bytes": final_path.stat().st_size,
            "output_sha256": output_hash,
            "mapping_sha256": mapping_hash,
            "processing_status_counts": dict(sorted(
                (key.removeprefix("status:"), value)
                for key, value in counters.items() if key.startswith("status:")
            )),
            "code_rows": readback["code_rows"],
            "distinct_codes": readback["distinct_codes"],
            "description_rows": readback["description_rows"],
            "comments_rows": readback["comments_rows"],
            "null_violation_code": readback["output_rows"] - readback["code_rows"],
            "null_violation_description": readback["output_rows"] - readback["description_rows"],
            "null_violation_comments": readback["output_rows"] - readback["comments_rows"],
            "source_origin_sha256_after": origin_after_sha,
            "source_origin_guard_sha256_before": input_origin_guard_sha,
            "source_origin_guard_sha256_after": origin_after["guard_sha256"],
            "source_bronze_sha256_after": bronze_after_sha,
        })
        _append_run_log(root, record)
        log_written = True
        return record
    except Exception as error:
        record.update({
            "finished_at_utc": utc_now(),
            "status": "FAILED",
            "error": repr(error),
        })
        if not log_written:
            _append_run_log(root, record)
            log_written = True
        raise
    finally:
        for temp_path in (temp_output, temp_mapping):
            if temp_path is not None and temp_path.exists():
                temp_path.unlink()


def main() -> None:
    result = run()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
