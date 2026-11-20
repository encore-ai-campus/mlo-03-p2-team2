"""Read-only quality checks for the Food Inspections Violations Silver table.

Run from the repository root with: python -m src.domains.02_violation.quality
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
from .silver import SILVER_RELATIVE, MAPPING_RELATIVE, SILVER_SCHEMA


REPORT_RELATIVE = Path("reports/runs/02_violation/violations_quality_report.csv")
RUN_LOG_RELATIVE = Path("logs/02_violation/violations_quality_runs.jsonl")
INSPECTION_ID = "Inspection ID"
VIOLATIONS = "Violations"
LINEAGE_COLUMNS = (INSPECTION_ID, VIOLATIONS, "source_row_num")
SILVER_COLUMNS = list(SILVER_SCHEMA.names)
CODE_VALUE_PATTERN = re.compile(r"\d+[A-Z]?\Z")
EXPECTED_STATUSES = {
    "PARSED",
    "MISSING_COMMENTS_MARKER",
    "UNPARSED_CODE_HEADER",
    "UNRECOGNIZED_SEPARATOR",
    "EMPTY_DESCRIPTION",
    "EMPTY_COMMENTS",
}
INTENTIONAL_NULL_COLUMNS = {"violation_description", "violation_comments"}
MAPPING_EXPECTED_TARGETS = {
    "source_violations_fragment",
    "inspection_id",
    "source_row_num",
    "violation_code",
    "violation_description",
    "violation_comments",
    "parsing_status",
    "no child record",
    "multiple violation records",
}
REPORT_FIELDS = [
    "quality_rule", "target_column", "checked_rows", "issue_rows", "status", "note",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _source_records(parquet: pq.ParquetFile):
    for batch in parquet.iter_batches(columns=list(LINEAGE_COLUMNS), batch_size=5_000):
        yield from batch.to_pylist()


def _silver_records(parquet: pq.ParquetFile):
    for batch in parquet.iter_batches(columns=SILVER_COLUMNS, batch_size=25_000):
        yield from batch.to_pylist()


def _expected_fields(fragment: str, unrecognized_separator: bool = False) -> dict:
    if unrecognized_separator:
        return {
            "violation_code": None,
            "violation_description": None,
            "violation_comments": None,
            "parsing_status": "UNRECOGNIZED_SEPARATOR",
        }
    header = CODE_HEADER.match(fragment)
    if header is None:
        return {
            "violation_code": None,
            "violation_description": None,
            "violation_comments": None,
            "parsing_status": "UNPARSED_CODE_HEADER",
        }
    body_start = header.start("body")
    marker = COMMENTS_MARKER.search(fragment, body_start)
    if marker is None:
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


def _add_rule(
    rules: list[dict], rule: str, target: str, checked: int, issues: int, note: str,
) -> None:
    rules.append({
        "quality_rule": rule,
        "target_column": target,
        "checked_rows": int(checked),
        "issue_rows": int(issues),
        "status": "PASS" if issues == 0 else "FAIL",
        "note": note,
    })


def _mapping_validation(path: Path, expected_counts: dict[str, int]) -> tuple[list[dict], dict]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    counts = Counter(row["target_column"] for row in rows)
    duplicate_targets = sum(count - 1 for count in counts.values() if count > 1)
    missing_targets = MAPPING_EXPECTED_TARGETS - set(counts)
    unexpected_targets = set(counts) - MAPPING_EXPECTED_TARGETS
    mismatches = []
    for row in rows:
        target = row["target_column"]
        expected_identity = {
            "source_dataset": "food_inspections",
            "source_origin_file": ORIGIN_RELATIVE.as_posix(),
            "source_bronze_file": BRONZE_RELATIVE.as_posix(),
            "source_column": "Violations",
            "target_file": SILVER_RELATIVE.as_posix(),
        }
        for field, expected_value in expected_identity.items():
            if row.get(field) != expected_value:
                mismatches.append({
                    "target_column": target,
                    "reason": f"{field}_MISMATCH",
                    "mapping_value": row.get(field),
                    "measured_value": expected_value,
                })
        if any(not row.get(field, "").strip() for field in (
            "transformation", "before_pattern", "after", "affected_unit", "note",
        )):
            mismatches.append({
                "target_column": target,
                "reason": "MAPPING_DESCRIPTION_INCOMPLETE",
            })
        if target not in expected_counts:
            mismatches.append({"target_column": target, "reason": "UNEXPECTED_TARGET"})
            continue
        try:
            mapped_count = int(row["affected_rows"])
        except ValueError:
            mapped_count = -1
        if mapped_count != expected_counts[target]:
            mismatches.append({
                "target_column": target,
                "mapping_affected_rows": mapped_count,
                "measured_affected_rows": expected_counts[target],
            })
        if row["status"] != "APPLIED":
            mismatches.append({
                "target_column": target,
                "reason": f"STATUS_{row['status']}",
            })
    return mismatches, {
        "mapping_rows": len(rows),
        "duplicate_target_rows": duplicate_targets,
        "missing_targets": sorted(missing_targets),
        "unexpected_targets": sorted(unexpected_targets),
    }


def _write_report(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temp.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=REPORT_FIELDS)
            writer.writeheader()
            writer.writerows(rows)
        # This is a derived report and may be refreshed after the validator changes.
        # The Origin, Bronze and Silver inputs are never written by this module.
        os.replace(temp, path)
    finally:
        if temp.exists():
            temp.unlink()


def _append_log(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="") as stream:
        stream.write(json.dumps(record, ensure_ascii=False) + "\n")


def run(root: Path = PROJECT_ROOT) -> dict:
    """Recompute Bronze expectations and compare them with Silver and its Mapping."""
    root = Path(root)
    origin_before_snapshot = origin_snapshot(root)
    bronze_path = root / BRONZE_RELATIVE
    silver_path = root / SILVER_RELATIVE
    profile_path = root / PROFILE_RELATIVE
    mapping_path = root / MAPPING_RELATIVE
    report_path = root / REPORT_RELATIVE
    log_path = root / RUN_LOG_RELATIVE

    for path in (bronze_path, silver_path, profile_path, mapping_path):
        if not path.is_file():
            raise FileNotFoundError(path)
    started = utc_now()
    run_id = uuid.uuid4().hex
    log_record: dict = {
        "run_id": run_id,
        "started_at_utc": started,
        "scope": "Food Inspections / Violations Silver only",
        "status": "RUNNING",
    }
    try:
        origin_before = origin_before_snapshot["source_sha256"]
        bronze_before = sha256(bronze_path)
        silver_before = sha256(silver_path)
        mapping_hash = sha256(mapping_path)
        profile = json.loads(profile_path.read_text(encoding="utf-8"))
        prior_counts = profile["counts"]
        bronze = pq.ParquetFile(bronze_path)
        silver = pq.ParquetFile(silver_path)
        if silver.schema_arrow != SILVER_SCHEMA:
            raise ValueError("Silver schema differs from the committed Violations contract")
        if "Violations" not in bronze.schema_arrow.names:
            raise ValueError("Bronze file is missing the Violations column")

        source_counts: Counter = Counter()
        expected_status_counts: Counter = Counter()
        expected_code_set: set[str] = set()
        actual_status_counts: Counter = Counter()
        actual_code_set: set[str] = set()
        null_counts: Counter = Counter()
        code_format_failures = 0
        field_mismatch_counts: Counter = Counter()
        duplicate_grain_keys = 0
        lineage_issue_rows = 0
        sequence_invalid_rows = 0
        blank_source_output_rows = 0
        seen_grain_keys: set[int] = set()
        output_rows = 0
        previous_key = None
        actual_row_iter = iter(_silver_records(silver))
        actual_row = next(actual_row_iter, None)
        profile_candidate_count = prior_counts["candidate_fragments"]

        def inspect_actual(row: dict) -> None:
            nonlocal output_rows, code_format_failures, duplicate_grain_keys
            nonlocal sequence_invalid_rows
            output_rows += 1
            actual_status_counts[row["parsing_status"]] += 1
            for name in SILVER_COLUMNS:
                null_counts[name] += row[name] is None
            code = row["violation_code"]
            if code is not None:
                actual_code_set.add(code)
                code_format_failures += not bool(CODE_VALUE_PATTERN.fullmatch(code))
            source_row_num = row["source_row_num"]
            sequence = row["item_sequence_num"]
            if source_row_num is None or sequence is None or source_row_num < 1 or sequence < 1:
                sequence_invalid_rows += 1
            else:
                key = (int(source_row_num) << 32) | int(sequence)
                if key in seen_grain_keys:
                    duplicate_grain_keys += 1
                else:
                    seen_grain_keys.add(key)

        for row_number, source in enumerate(_source_records(bronze), start=1):
            source_counts["bronze_rows"] += 1
            if source["source_row_num"] != row_number:
                lineage_issue_rows += 1
            raw = source[VIOLATIONS]
            if raw is None:
                source_counts["null_cells"] += 1
                if actual_row is not None and actual_row["source_row_num"] == source["source_row_num"]:
                    blank_source_output_rows += 1
                    inspect_actual(actual_row)
                    actual_row = next(actual_row_iter, None)
                continue
            if raw == "":
                source_counts["empty_cells"] += 1
                if actual_row is not None and actual_row["source_row_num"] == source["source_row_num"]:
                    blank_source_output_rows += 1
                    inspect_actual(actual_row)
                    actual_row = next(actual_row_iter, None)
                continue
            if not raw.strip():
                source_counts["whitespace_cells"] += 1
                if actual_row is not None and actual_row["source_row_num"] == source["source_row_num"]:
                    blank_source_output_rows += 1
                    inspect_actual(actual_row)
                    actual_row = next(actual_row_iter, None)
                continue
            source_counts["nonempty_cells"] += 1

            fragments = FRAGMENT_SEPARATOR.split(raw)
            pipe_count = raw.count("|")
            recognized_pipe_count = len(fragments) - 1
            if len(fragments) > 1:
                source_counts["multiple_violation_cells"] += 1
            unrecognized = pipe_count > recognized_pipe_count
            if unrecognized:
                source_counts["unrecognized_separator_cells"] += 1
                fragments = [raw]
            for sequence, fragment in enumerate(fragments, start=1):
                source_counts["candidate_records"] += 1
                parsed = _expected_fields(fragment, unrecognized_separator=unrecognized)
                expected_status_counts[parsed["parsing_status"]] += 1
                if parsed["violation_code"] is not None:
                    expected_code_set.add(parsed["violation_code"])

                if actual_row is None:
                    source_counts["missing_silver_records"] += 1
                    continue
                inspect_actual(actual_row)
                current_key = (
                    actual_row["source_row_num"],
                    actual_row["item_sequence_num"],
                )
                row_lineage_mismatch = current_key != (source["source_row_num"], sequence) or (
                    actual_row["inspection_id"] != source[INSPECTION_ID]
                    or actual_row["source_row_num"] != source["source_row_num"]
                    or actual_row["item_sequence_num"] != sequence
                    or actual_row["source_violations_fragment"] != fragment
                )
                if row_lineage_mismatch:
                    lineage_issue_rows += 1
                for column in (
                    "violation_code", "violation_description",
                    "violation_comments", "parsing_status",
                ):
                    field_mismatch_counts[column] += actual_row[column] != parsed[column]
                actual_row = next(actual_row_iter, None)

        while actual_row is not None:
            source_counts["extra_silver_records"] += 1
            inspect_actual(actual_row)
            actual_row = next(actual_row_iter, None)

        source_total_mismatch = source_counts["bronze_rows"] != bronze.metadata.num_rows
        silver_metadata_mismatch = output_rows != silver.metadata.num_rows
        source_profile_mismatches = {
            profile_key: {
                "profiling": prior_counts[profile_key],
                "quality_recomputed": source_counts[counter_key],
            }
            for profile_key, counter_key in {
                "total_rows": "bronze_rows",
                "null_rows": "null_cells",
                "empty_string_rows": "empty_cells",
                "whitespace_only_rows": "whitespace_cells",
                "nonempty_rows": "nonempty_cells",
                "rows_with_multiple_fragments": "multiple_violation_cells",
                "candidate_fragments": "candidate_records",
                "rows_with_unrecognized_pipe_separator": "unrecognized_separator_cells",
            }.items()
            if prior_counts[profile_key] != source_counts[counter_key]
        }
        unexpected_status_rows = sum(
            count for status, count in actual_status_counts.items()
            if status not in EXPECTED_STATUSES
        )
        code_set_difference = expected_code_set.symmetric_difference(actual_code_set)
        expected_intentional_nulls = expected_status_counts["MISSING_COMMENTS_MARKER"]
        null_issue_counts = {
            column: max(
                0,
                null_counts[column] - (
                    expected_intentional_nulls
                    if column in INTENTIONAL_NULL_COLUMNS
                    else 0
                ),
            )
            for column in SILVER_COLUMNS
        }
        null_count_mismatch_rows = sum(
            abs(null_counts[column] - (
                expected_intentional_nulls
                if column in INTENTIONAL_NULL_COLUMNS
                else 0
            ))
            for column in SILVER_COLUMNS
        )

        mapping_expected = {
            "source_violations_fragment": output_rows,
            "inspection_id": output_rows,
            "source_row_num": output_rows,
            "violation_code": output_rows - null_counts["violation_code"],
            "violation_description": output_rows - null_counts["violation_description"],
            "violation_comments": output_rows - null_counts["violation_comments"],
            "parsing_status": output_rows,
            "no child record": source_counts["null_cells"] + source_counts["empty_cells"] + source_counts["whitespace_cells"],
            "multiple violation records": source_counts["multiple_violation_cells"],
        }
        mapping_mismatches, mapping_meta = _mapping_validation(mapping_path, mapping_expected)
        mapping_issues = (
            len(mapping_mismatches)
            + mapping_meta["duplicate_target_rows"]
            + len(mapping_meta["missing_targets"])
            + len(mapping_meta["unexpected_targets"])
        )

        rules: list[dict] = []
        candidate_diff = abs(source_counts["candidate_records"] - output_rows)
        _add_rule(
            rules, "bronze_silver_record_reconciliation", "Violations",
            source_counts["candidate_records"], candidate_diff,
            f"Bronze candidates={source_counts['candidate_records']}; Silver rows={output_rows}; "
            f"missing={source_counts['missing_silver_records']}; extra={source_counts['extra_silver_records']}.",
        )
        _add_rule(
            rules, "blank_source_cells_excluded", "Violations",
            source_counts["null_cells"] + source_counts["empty_cells"] + source_counts["whitespace_cells"],
            blank_source_output_rows,
            f"NULL={source_counts['null_cells']}; empty={source_counts['empty_cells']}; "
            f"whitespace-only={source_counts['whitespace_cells']}; "
            "blank cells must create no Silver row.",
        )
        _add_rule(
            rules, "unexpected_parsing_status", "parsing_status", output_rows,
            unexpected_status_rows,
            json.dumps(dict(sorted(actual_status_counts.items())), ensure_ascii=False),
        )
        _add_rule(
            rules, "violation_code_extraction", "violation_code",
            source_counts["candidate_records"],
            field_mismatch_counts["violation_code"] + null_counts["violation_code"],
            f"Bronze code header failures={expected_status_counts['UNPARSED_CODE_HEADER']}; "
            f"Silver NULL code={null_counts['violation_code']}.",
        )
        _add_rule(
            rules, "description_extraction", "violation_description",
            source_counts["candidate_records"], field_mismatch_counts["violation_description"],
            f"Description NULL is expected only for MISSING_COMMENTS_MARKER; "
            f"intended count={expected_intentional_nulls}.",
        )
        _add_rule(
            rules, "comments_extraction", "violation_comments",
            source_counts["candidate_records"], field_mismatch_counts["violation_comments"],
            f"Comments NULL is expected only for MISSING_COMMENTS_MARKER; "
            f"intended count={expected_intentional_nulls}.",
        )
        _add_rule(
            rules, "parsing_status_matches_source", "parsing_status",
            output_rows, field_mismatch_counts["parsing_status"],
            f"Expected status counts={dict(sorted(expected_status_counts.items()))}; "
            "fields were independently re-parsed from the Bronze fragment.",
        )
        _add_rule(
            rules, "missing_comments_marker_status", "parsing_status",
            expected_intentional_nulls,
            abs(actual_status_counts["MISSING_COMMENTS_MARKER"] - expected_intentional_nulls),
            "Comments boundary is not inferred when its marker is absent.",
        )
        _add_rule(
            rules, "violation_code_nonnull", "violation_code", output_rows,
            null_counts["violation_code"],
            f"Distinct Silver codes={len(actual_code_set)}.",
        )
        _add_rule(
            rules, "violation_code_format", "violation_code", output_rows,
            code_format_failures,
            "Accepted format: digits with optional uppercase suffix; code remains a string.",
        )
        _add_rule(
            rules, "bronze_silver_code_set_match", "violation_code",
            max(len(expected_code_set), len(actual_code_set)),
            len(code_set_difference),
            f"Bronze distinct={len(expected_code_set)}; Silver distinct={len(actual_code_set)}; "
            f"symmetric difference={sorted(code_set_difference)[:20]}.",
        )
        _add_rule(
            rules, "bronze_lineage_and_fragment_match",
            "source_row_num/item_sequence_num/inspection_id/source_violations_fragment",
            source_counts["candidate_records"], lineage_issue_rows,
            "Compared every Silver record with its Bronze source row number, source ID, and raw fragment.",
        )
        _add_rule(
            rules, "silver_grain_key_unique",
            "source_row_num + item_sequence_num", output_rows,
            duplicate_grain_keys + sequence_invalid_rows,
            "Grain key identifies one violation fragment within its source inspection row; repeated codes are allowed.",
        )
        for column in SILVER_COLUMNS:
            allowed_nulls = (
                expected_intentional_nulls if column in INTENTIONAL_NULL_COLUMNS else 0
            )
            issue_rows = null_issue_counts[column]
            note = f"Observed NULL={null_counts[column]}; expected NULL={allowed_nulls}."
            if column in INTENTIONAL_NULL_COLUMNS:
                note += " NULL is intentional only for MISSING_COMMENTS_MARKER records."
            _add_rule(rules, "column_null_count", column, output_rows, issue_rows, note)
        _add_rule(
            rules, "mapping_affected_counts", "metadata/standards/violations_mapping.csv",
            len(mapping_expected), mapping_issues,
            f"Mapping rows={mapping_meta['mapping_rows']}; mismatches={mapping_mismatches}; "
            f"missing targets={mapping_meta['missing_targets']}; "
            f"duplicate targets={mapping_meta['duplicate_target_rows']}.",
        )
        _add_rule(
            rules, "profiling_count_reconciliation", "Bronze / Violations",
            8, len(source_profile_mismatches),
            f"Profiling differences={source_profile_mismatches}.",
        )
        _add_rule(
            rules, "origin_bronze_silver_readonly_hashes", "Origin/Bronze/Silver",
            3, 0,
            f"Origin={origin_before}; Bronze={bronze_before}; Silver={silver_before}.",
        )
        if source_total_mismatch or silver_metadata_mismatch:
            # Record metadata inconsistencies explicitly in addition to reconciliation.
            _add_rule(
                rules, "parquet_metadata_row_counts", "Bronze/Silver",
                bronze.metadata.num_rows + silver.metadata.num_rows,
                int(source_total_mismatch) + int(silver_metadata_mismatch),
                f"Bronze batch rows={source_counts['bronze_rows']}, metadata={bronze.metadata.num_rows}; "
                f"Silver readback rows={output_rows}, metadata={silver.metadata.num_rows}.",
            )

        origin_after_snapshot = origin_snapshot(root)
        origin_after = origin_after_snapshot["source_sha256"]
        bronze_after = sha256(bronze_path)
        silver_after = sha256(silver_path)
        hashes_unchanged = (
            origin_before == origin_after
            and origin_before_snapshot["guard_sha256"] == origin_after_snapshot["guard_sha256"]
            and bronze_before == bronze_after
            and silver_before == silver_after
        )
        hash_rule = next(row for row in rules if row["quality_rule"] == "origin_bronze_silver_readonly_hashes")
        hash_rule["issue_rows"] = 0 if hashes_unchanged else 1
        hash_rule["status"] = "PASS" if hashes_unchanged else "FAIL"
        hash_rule["note"] = (
            f"Origin before/after={origin_before}/{origin_after}; "
            f"Origin guard before/after={origin_before_snapshot['guard_sha256']}/"
            f"{origin_after_snapshot['guard_sha256']}; "
            f"Bronze before/after={bronze_before}/{bronze_after}; "
            f"Silver before/after={silver_before}/{silver_after}."
        )
        overall_status = "PASS" if all(rule["status"] == "PASS" for rule in rules) else "FAIL"
        _write_report(report_path, rules)
        field_mismatch_rows = sum(field_mismatch_counts.values())

        result = {
            "run_id": run_id,
            "started_at_utc": started,
            "finished_at_utc": utc_now(),
            "status": overall_status,
            "origin_file": ORIGIN_RELATIVE.as_posix(),
            "bronze_file": BRONZE_RELATIVE.as_posix(),
            "silver_file": SILVER_RELATIVE.as_posix(),
            "mapping_file": MAPPING_RELATIVE.as_posix(),
            "report_file": REPORT_RELATIVE.as_posix(),
            "bronze_sha256_before": bronze_before,
            "bronze_sha256_after": bronze_after,
            "origin_sha256_before": origin_before,
            "origin_sha256_after": origin_after,
            "origin_guard_sha256_before": origin_before_snapshot["guard_sha256"],
            "origin_guard_sha256_after": origin_after_snapshot["guard_sha256"],
            "origin_storage_files": origin_before_snapshot["storage_files"],
            "silver_sha256_before": silver_before,
            "silver_sha256_after": silver_after,
            "mapping_sha256": mapping_hash,
            "profile_candidate_count": prior_counts["candidate_fragments"],
            "source_counts": dict(sorted(source_counts.items())),
            "silver_rows": output_rows,
            "silver_schema": str(silver.schema_arrow),
            "silver_null_counts": dict(sorted(null_counts.items())),
            "actual_status_counts": dict(sorted(actual_status_counts.items())),
            "expected_status_counts": dict(sorted(expected_status_counts.items())),
            "bronze_code_count": len(expected_code_set),
            "silver_code_count": len(actual_code_set),
            "code_set_difference": sorted(code_set_difference),
            "duplicate_grain_keys": duplicate_grain_keys,
            "lineage_issue_rows": lineage_issue_rows,
            "field_mismatch_rows": field_mismatch_rows,
            "mapping_metadata": mapping_meta,
            "rules": rules,
        }
        _append_log(log_path, result)
        return result
    except Exception as error:
        log_record.update({
            "finished_at_utc": utc_now(),
            "status": "FAILED",
            "error": repr(error),
        })
        _append_log(log_path, log_record)
        raise


def main() -> None:
    result = run()
    print(json.dumps({
        "run_id": result["run_id"],
        "status": result["status"],
        "report": result["report_file"],
        "silver_rows": result["silver_rows"],
        "rule_statuses": Counter(rule["status"] for rule in result["rules"]),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
