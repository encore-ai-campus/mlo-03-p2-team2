"""The partition stays lossless and deterministic as Bronze gains rows."""

from pathlib import Path
import hashlib
import json

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from src.silver.violations_reconciliation import (
    ACCEPTED_RELATIVE, QUARANTINE_RELATIVE, run,
)


def _fixture(root: Path, extra: bool = False) -> None:
    bronze = root / "data/01_bronze/food_inspections/food_inspections.parquet"
    origin = root / "data/00_origin/food_inspections/food_inspections.csv"
    bronze.parent.mkdir(parents=True)
    origin.parent.mkdir(parents=True)
    origin.write_bytes(b"fixture original")
    values = [
        ("01", "1. FIRST - Comments: GOOD | 2. SECOND - Comments: OK"),
        ("02", "3. UNKNOWN BOUNDARY"),
        ("03", ""),
    ]
    if extra:
        values.append(("04", "4. NEW - Comments: NEW DATA"))
    pq.write_table(pa.Table.from_pylist([
        {"Inspection ID": key, "Violations": value, "_SRC_FILE": "fixture.csv", "_LOAD_DTM": "fixed"}
        for key, value in values
    ]), bronze)


def test_lossless_partition_and_determinism(tmp_path: Path):
    _fixture(tmp_path)
    before = hashlib.sha256((tmp_path / "data/01_bronze/food_inspections/food_inspections.parquet").read_bytes()).hexdigest()
    first = run(tmp_path, tmp_path / "out1")
    second = run(tmp_path, tmp_path / "out2")
    assert first == second
    assert first["status"] == "PASS"
    assert first["counts"]["bronze_inspections"] == 3
    assert first["counts"]["empty_inspections"] == 1
    assert first["counts"]["candidate_fragments"] == 3
    assert first["counts"]["accepted"] == 2
    assert first["counts"]["quarantined"] == 1
    assert first["quarantine_reasons"] == {"MISSING_COMMENTS_MARKER": 1}
    assert first["unexpected_quarantine_count"] == 0
    assert first["issues"]["duplicate_grain"] == 0
    assert pq.read_table(tmp_path / "out1" / ACCEPTED_RELATIVE).num_rows == 2
    quarantined = pq.read_table(tmp_path / "out1" / QUARANTINE_RELATIVE).to_pylist()
    assert quarantined[0]["source_violations_fragment"] == "3. UNKNOWN BOUNDARY"
    assert quarantined[0]["rejection_reason"] == "MISSING_COMMENTS_MARKER"
    assert json.loads((tmp_path / "out1/reports/quality/violations_reconciliation.json").read_text())["status"] == "PASS"
    assert before == hashlib.sha256((tmp_path / "data/01_bronze/food_inspections/food_inspections.parquet").read_bytes()).hexdigest()


def test_new_bronze_row_recomputes_counts(tmp_path: Path):
    _fixture(tmp_path, extra=True)
    result = run(tmp_path, tmp_path / "out")
    assert result["status"] == "PASS"
    assert result["counts"]["bronze_inspections"] == 4
    assert result["counts"]["candidate_fragments"] == 4
    assert result["counts"]["accepted"] == 3
    assert result["counts"]["quarantined"] == 1


def test_conflicting_output_prevents_partial_publication(tmp_path: Path):
    _fixture(tmp_path)
    output = tmp_path / "out"
    run(tmp_path, output)
    accepted = output / ACCEPTED_RELATIVE
    quarantined = output / QUARANTINE_RELATIVE
    accepted.unlink()
    quarantined.write_bytes(b"conflicting file")
    with pytest.raises(FileExistsError):
        run(tmp_path, output)
    assert not accepted.exists()
    assert quarantined.read_bytes() == b"conflicting file"
