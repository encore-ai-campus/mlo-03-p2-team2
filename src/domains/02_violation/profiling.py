"""Profile the raw Food Inspections Violations text in the Bronze Parquet.

Run from the repository root with: python -m src.domains.02_violation.profiling
The script is read-only for Origin and Bronze and writes one JSON report.
"""

from __future__ import annotations

from collections import Counter
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

import pyarrow.parquet as pq

from src.bronze.paths import PROJECT_ROOT


BRONZE_RELATIVE = Path("data/01_bronze/02_violation/02_food_inspections.parquet")
ORIGIN_RELATIVE = Path("data/00_origin/food_inspections.csv")
LEGACY_ORIGIN_RELATIVE = Path("data/00_origin/food_inspections/food_inspections.csv")
ORIGIN_CHECKSUMS_RELATIVE = Path("data/00_origin/SHA256SUMS")
SOURCE_CATALOG_RELATIVE = Path("metadata/source_catalog/verification/download_manifest.csv")
ORIGIN_PARTS = (
    "food_inspections.csv.gz.part-001",
    "food_inspections.csv.gz.part-002",
)
OUTPUT_RELATIVE = Path("reports/runs/02_violation/violations_profile.json")
FIELD_NAME = "Violations"
SOURCE_ROW_COLUMN = "source_row_num"
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


def origin_snapshot(root: Path = PROJECT_ROOT) -> dict:
    """Return the source identity and a read-only guard for either Origin layout."""
    root = Path(root)
    checksums_path = root / ORIGIN_CHECKSUMS_RELATIVE
    if not checksums_path.is_file():
        for relative in (LEGACY_ORIGIN_RELATIVE, ORIGIN_RELATIVE):
            path = root / relative
            if path.is_file():
                digest = sha256(path)
                return {
                    "source_file": relative.as_posix(),
                    "source_sha256": digest,
                    "source_file_bytes": path.stat().st_size,
                    "storage_files": [relative.as_posix()],
                    "guard_sha256": digest,
                    "catalog_verified": False,
                }
        raise FileNotFoundError(checksums_path)

    catalog_path = root / SOURCE_CATALOG_RELATIVE
    source_name = ORIGIN_RELATIVE.name
    with catalog_path.open(encoding="utf-8-sig", newline="") as stream:
        catalog_rows = [row for row in csv.DictReader(stream) if row.get("File") == source_name]
    if len(catalog_rows) != 1:
        raise ValueError("Source catalog must contain one Food Inspections entry")
    source_sha = catalog_rows[0]["SHA256"].lower()
    source_bytes = int(catalog_rows[0]["Bytes"])

    expected = {}
    for line in checksums_path.read_text(encoding="ascii").splitlines():
        digest, name = line.split("  ", 1)
        expected[name] = digest.lower()
    storage_paths = [root / "data" / "00_origin" / name for name in ORIGIN_PARTS]
    part_hashes = []
    for name, path in zip(ORIGIN_PARTS, storage_paths):
        if not path.is_file():
            raise FileNotFoundError(path)
        actual = sha256(path)
        if expected.get(name) != actual:
            raise ValueError(f"Origin part SHA-256 differs: {name}")

        part_hashes.append(actual)

    guard = hashlib.sha256()
    for digest in (sha256(catalog_path), sha256(checksums_path), *part_hashes):
        guard.update(bytes.fromhex(digest))
    return {
        "source_file": (Path("data/00_origin") / source_name).as_posix(),
        "source_sha256": source_sha,
        "source_file_bytes": source_bytes,
        "storage_files": [path.relative_to(root).as_posix() for path in storage_paths],
        "guard_sha256": guard.hexdigest(),
        "catalog_verified": True,
    }


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
    origin = origin_snapshot(root)
    if not bronze_path.is_file():
        raise FileNotFoundError(bronze_path)
    bronze_sha = sha256(bronze_path)
    parquet = pq.ParquetFile(bronze_path)
    metadata = parquet.schema_arrow.metadata or {}
    if origin["catalog_verified"] and metadata.get(b"origin_sha256") != origin["source_sha256"].encode("ascii"):
        raise ValueError("02 Bronze does not match the shared Origin checksum")
    missing = {FIELD_NAME, SOURCE_ROW_COLUMN} - set(parquet.schema_arrow.names)
    if missing:
        raise ValueError(f"{bronze_path} is missing required columns: {sorted(missing)}")

    counts: Counter[str] = Counter()
    code_counts: Counter[str] = Counter()
    examples: list[str] = []
    exception_examples: dict[str, list[str]] = {
        "missing_comments_marker": [],
        "no_code_header": [],
        "unrecognized_pipe_separator": [],
    }
    for batch in parquet.iter_batches(columns=[FIELD_NAME, SOURCE_ROW_COLUMN], batch_size=batch_size):
        for raw, source_row_num in zip(batch.column(0).to_pylist(), batch.column(1).to_pylist()):
            counts["total_rows"] += 1
            if source_row_num != counts["total_rows"]:
                raise ValueError(
                    f"Bronze source_row_num is not sequential at row {counts['total_rows']}"
                )
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
            "origin_file": origin["source_file"],
            "origin_file_bytes": origin["source_file_bytes"],
            "origin_sha256": origin["source_sha256"],
            "origin_storage_files": origin["storage_files"],
            "origin_guard_sha256": origin["guard_sha256"],
            "bronze_file": str(BRONZE_RELATIVE.as_posix()),
            "bronze_file_bytes": bronze_path.stat().st_size,
            "bronze_sha256": bronze_sha,
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
