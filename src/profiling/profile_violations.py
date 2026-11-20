"""Profile the raw Food Inspections Violations text in the Bronze Parquet.

Run from the repository root with: python -m src.profiling.profile_violations
The script is read-only for Origin and Bronze and writes one JSON report.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

import pyarrow.parquet as pq

from src.bronze.paths import PROJECT_ROOT


BRONZE_RELATIVE = Path("data/01_bronze/food_inspections/food_inspections.parquet")
ORIGIN_RELATIVE = Path("data/00_origin/food_inspections/food_inspections.csv")
OUTPUT_RELATIVE = Path("reports/profiling/violations_profile.json")
FIELD_NAME = "Violations"
FRAGMENT_SEPARATOR = re.compile(r"\s+\|\s+")
CODE_HEADER = re.compile(r"^(?P<code>\d+[A-Z]?)\.\s+(?P<body>.+)$")
COMMENTS_MARKER = re.compile(r"\s+-\s+Comments:|\s+Comments:")
CANONICAL_COMMENTS_MARKER = re.compile(r"\s+-\s+Comments:")
DESCRIPTION_PATTERN = re.compile(
    r"^(?P<code>\d+[A-Z]?)\.\s+(?P<description>.*?)"
    r"(?:\s+-\s+Comments:|\s+Comments:)(?P<comments>.*)$"
)
MAX_EXAMPLES = 5
MAX_EXAMPLE_LENGTH = 500


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def shortened(value: str) -> str:
    return value if len(value) <= MAX_EXAMPLE_LENGTH else value[:MAX_EXAMPLE_LENGTH] + "…"


def parse_fragment(fragment: str) -> dict:
    """Return observable parsing properties without changing the raw fragment."""
    header = CODE_HEADER.match(fragment)
    description_match = DESCRIPTION_PATTERN.match(fragment)
    marker = COMMENTS_MARKER.search(fragment)
    body = header.group("body") if header else None
    description = (
        description_match.group("description").strip()
        if description_match
        else body.strip() if body and not marker
        else None
    )
    comments = description_match.group("comments").strip() if description_match else None
    return {
        "code": header.group("code") if header else None,
        "has_code_header": header is not None,
        "has_comments_marker": marker is not None,
        "has_canonical_comments_marker": bool(CANONICAL_COMMENTS_MARKER.search(fragment)),
        "has_standard_description_comments_pattern": description_match is not None,
        "description_nonempty": bool(description),
        "comments_nonempty": bool(comments),
        "body_nonempty_without_comments_marker": bool(body and not marker),
    }


def profile_violations(root: Path = PROJECT_ROOT, batch_size: int = 10_000) -> dict:
    """Stream Bronze and return row, separator, code and text-pattern metrics."""
    root = Path(root)
    bronze_path = root / BRONZE_RELATIVE
    origin_path = root / ORIGIN_RELATIVE
    if not bronze_path.is_file():
        raise FileNotFoundError(bronze_path)
    if not origin_path.is_file():
        raise FileNotFoundError(origin_path)

    parquet = pq.ParquetFile(bronze_path)
    if FIELD_NAME not in parquet.schema_arrow.names:
        raise ValueError(f"{bronze_path} has no {FIELD_NAME!r} column")

    counts: Counter[str] = Counter()
    code_counts: Counter[str] = Counter()
    examples: list[str] = []
    exception_examples: dict[str, list[str]] = {
        "missing_comments_marker": [],
        "no_code_header": [],
        "unrecognized_pipe_separator": [],
    }
    for batch in parquet.iter_batches(columns=[FIELD_NAME], batch_size=batch_size):
        for raw in batch.column(0).to_pylist():
            counts["total_rows"] += 1
            if raw is None:
                counts["null_rows"] += 1
                continue
            if raw == "":
                counts["empty_string_rows"] += 1
                continue
            if not raw.strip():
                counts["whitespace_only_rows"] += 1
                continue

            counts["nonempty_rows"] += 1
            if len(examples) < MAX_EXAMPLES:
                examples.append(shortened(raw))
            fragments = FRAGMENT_SEPARATOR.split(raw)
            separator_count = len(fragments) - 1
            literal_pipe_count = raw.count("|")
            counts["rows_with_multiple_fragments"] += int(len(fragments) > 1)
            counts["rows_with_literal_pipe"] += int(literal_pipe_count > 0)
            counts["recognized_pipe_separators"] += separator_count
            counts["literal_pipe_characters"] += literal_pipe_count
            if literal_pipe_count > separator_count:
                counts["rows_with_unrecognized_pipe_separator"] += 1
                if len(exception_examples["unrecognized_pipe_separator"]) < MAX_EXAMPLES:
                    exception_examples["unrecognized_pipe_separator"].append(shortened(raw))

            fragment_complete = 0
            for fragment in fragments:
                counts["candidate_fragments"] += 1
                parsed = parse_fragment(fragment)
                if parsed["has_code_header"]:
                    counts["code_header_matches"] += 1
                    code_counts[parsed["code"]] += 1
                else:
                    counts["code_header_failures"] += 1
                    if len(exception_examples["no_code_header"]) < MAX_EXAMPLES:
                        exception_examples["no_code_header"].append(shortened(fragment))
                if parsed["has_comments_marker"]:
                    counts["comments_marker_fragments"] += 1
                else:
                    counts["missing_comments_marker_fragments"] += 1
                    if len(exception_examples["missing_comments_marker"]) < MAX_EXAMPLES:
                        exception_examples["missing_comments_marker"].append(shortened(fragment))
                if parsed["has_canonical_comments_marker"]:
                    counts["canonical_description_comments_pattern"] += 1
                elif parsed["has_comments_marker"]:
                    counts["comments_marker_without_canonical_hyphen"] += 1
                if parsed["has_standard_description_comments_pattern"]:
                    counts["standard_description_comments_pattern_matches"] += 1
                if parsed["description_nonempty"]:
                    counts["nonempty_descriptions"] += 1
                else:
                    counts["empty_descriptions"] += 1
                if parsed["comments_nonempty"]:
                    counts["nonempty_comments"] += 1
                if parsed["has_code_header"] and parsed["has_comments_marker"] and parsed["description_nonempty"]:
                    counts["fully_parseable_fragments"] += 1
                    fragment_complete += 1
            if fragment_complete == len(fragments):
                counts["rows_with_all_fragments_parseable"] += 1
            elif fragment_complete:
                counts["rows_with_some_fragments_unparseable"] += 1
            else:
                counts["rows_with_no_fully_parseable_fragments"] += 1

    for metric in (
        "null_rows", "empty_string_rows", "whitespace_only_rows", "nonempty_rows",
        "rows_with_multiple_fragments", "rows_with_literal_pipe",
        "rows_with_unrecognized_pipe_separator", "candidate_fragments",
        "code_header_matches", "code_header_failures", "comments_marker_fragments",
        "missing_comments_marker_fragments", "fully_parseable_fragments",
        "nonempty_descriptions", "empty_descriptions",
    ):
        counts.setdefault(metric, 0)
    if counts["total_rows"] != parquet.metadata.num_rows:
        raise ValueError("Batch row count differs from Parquet metadata")
    if counts["total_rows"] != (
        counts["null_rows"] + counts["empty_string_rows"]
        + counts["whitespace_only_rows"] + counts["nonempty_rows"]
    ):
        raise ValueError("Null/empty/whitespace/nonempty row categories do not sum to total")
    if counts["literal_pipe_characters"] != counts["recognized_pipe_separators"]:
        raise ValueError("Some literal pipes are outside the observed padded separator format")
    result = {
        "profiled_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "dataset": "food_inspections",
        "field": FIELD_NAME,
        "source": {
            "origin_file": str(ORIGIN_RELATIVE.as_posix()),
            "origin_file_bytes": origin_path.stat().st_size,
            "origin_sha256": sha256(origin_path),
            "bronze_file": str(BRONZE_RELATIVE.as_posix()),
            "bronze_file_bytes": bronze_path.stat().st_size,
            "bronze_sha256": sha256(bronze_path),
            "bronze_rows": parquet.metadata.num_rows,
            "bronze_columns": len(parquet.schema_arrow.names),
            "bronze_field_type": str(parquet.schema_arrow.field(FIELD_NAME).type),
        },
        "method": {
            "batch_size": batch_size,
            "fragment_separator_regex": FRAGMENT_SEPARATOR.pattern,
            "code_header_regex": CODE_HEADER.pattern,
            "description_comments_regex": DESCRIPTION_PATTERN.pattern,
            "fully_parseable_definition": "code header + nonempty description + Comments marker",
        },
        "counts": dict(sorted(counts.items())),
        "code_pattern": {
            "distinct_codes": len(code_counts),
            "top_20_codes_by_fragment_count": [
                {"code": code, "fragments": count}
                for code, count in code_counts.most_common(20)
            ],
        },
        "examples": {
            "nonempty_original_values": examples,
            "exceptions": exception_examples,
        },
    }
    return result


def main() -> None:
    report = profile_violations()
    output = PROJECT_ROOT / OUTPUT_RELATIVE
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "report": str(OUTPUT_RELATIVE.as_posix()),
        "rows": report["counts"]["total_rows"],
        "nonnull_rows": report["counts"]["nonempty_rows"],
        "candidate_fragments": report["counts"]["candidate_fragments"],
        "fully_parseable_fragments": report["counts"]["fully_parseable_fragments"],
        "missing_comments_marker_fragments": report["counts"]["missing_comments_marker_fragments"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
