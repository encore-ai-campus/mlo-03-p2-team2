"""Compare the unified run with the published team snapshot and verify its files."""

from hashlib import file_digest
from itertools import zip_longest
import json
from pathlib import Path

import pyarrow.parquet as pq


VERIFICATION = "verification.json"
GOLD = Path("data/03_gold")
BASELINE_TRAINING = Path("data/ai_ready/inspection_training/ac0d0f3f4f33656e78a6")
PARQUET_REFERENCES = (
    Path("data/02_silver/02_violation/02_inspection_violations_quarantine.parquet"),
    Path("data/02_silver/03_repeat_inspection/03_inspection_history.parquet"),
    GOLD / "02_violation/02_violations_analysis_mart.parquet",
    Path("data/ai_ready/01_inspection/01_inspection_performance.parquet"),
)


def sha256(path):
    with path.open("rb") as stream:
        return file_digest(stream, "sha256").hexdigest()


def compare_parquet(generated, reference):
    """Check types and every ordered value, ignoring execution-specific metadata."""
    with pq.ParquetFile(generated) as current, pq.ParquetFile(reference) as baseline:
        rows = current.metadata.num_rows
        if rows != baseline.metadata.num_rows or not current.schema_arrow.equals(baseline.schema_arrow):
            raise ValueError(f"Schema or row count differs: {generated.name}")
        offset = 0
        for left, right in zip_longest(current.iter_batches(batch_size=16_384),
                                       baseline.iter_batches(batch_size=16_384)):
            if left is None or right is None or not left.equals(right):
                raise ValueError(f"Values differ: {generated.name} near row {offset + 1:,}")
            offset += left.num_rows
    return {"rows": rows, "sha256": sha256(generated), "reference_sha256": sha256(reference)}


def compare_results(repo, output, training):
    comparisons = {}
    for directory, expected in (("dimensions", 9), ("facts", 9)):
        files = sorted((output / GOLD / directory).glob("*.parquet"))
        if len(files) != expected:
            raise ValueError(f"Expected {expected} shared Gold {directory}, got {len(files)}")
        for path in files:
            relative = path.relative_to(output)
            comparisons[relative.as_posix()] = compare_parquet(path, repo / relative)
    for relative in PARQUET_REFERENCES:
        comparisons[relative.as_posix()] = compare_parquet(output / relative, repo / relative)
    baseline = repo / BASELINE_TRAINING
    references = sorted(baseline.glob("*.parquet"))
    if len(references) != 2:
        raise ValueError("Expected two published AI-ready training datasets")
    for reference in references:
        path = training / reference.name
        comparisons[path.relative_to(output).as_posix()] = compare_parquet(path, reference)
    summary = "validation_summary.json"
    if json.loads((training / summary).read_text(encoding="utf-8")) != json.loads(
        (baseline / summary).read_text(encoding="utf-8")
    ):
        raise ValueError("AI-ready split or label distribution differs from the published release")
    return comparisons


def verify_output(output):
    output = output.resolve()
    report = json.loads((output / VERIFICATION).read_text(encoding="utf-8"))
    if report["status"] != "PASS" or not report["artifacts"]:
        raise ValueError("No successful integration run to verify")
    for name, digest in report["artifacts"].items():
        path = output / name
        if Path(name).is_absolute() or not path.resolve().is_relative_to(output) or name == VERIFICATION:
            raise ValueError(f"Invalid artifact path: {name}")
        if not path.is_file() or sha256(path) != digest:
            raise ValueError(f"Artifact changed or is missing: {name}")
    return report
