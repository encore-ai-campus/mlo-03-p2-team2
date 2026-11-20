"""Quality checks for the Violations Silver child table."""

import csv
import json
from importlib import import_module
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

profiling = import_module("src.domains.02_violation.profiling")
profile_violations = profiling.profile_violations
quality = import_module("src.domains.02_violation.quality")
silver = import_module("src.domains.02_violation.silver")
REPORT_RELATIVE, run_quality = quality.REPORT_RELATIVE, quality.run
SILVER_RELATIVE, SILVER_SCHEMA, run_silver = silver.SILVER_RELATIVE, silver.SILVER_SCHEMA, silver.run


def _prepared_root(root: Path) -> Path:
    bronze = root / profiling.BRONZE_RELATIVE
    origin = root / profiling.ORIGIN_RELATIVE
    bronze.parent.mkdir(parents=True)
    origin.parent.mkdir(parents=True)
    origin.write_bytes(b"quality fixture origin")
    rows = [
        {
            "Inspection ID": "0001",
            "Violations": "16. SURFACES CLEAN - Comments: CLEAN | 38. PESTS ABSENT - Comments: SEAL",
            "source_row_num": 1,
        },
        {
            "Inspection ID": "0002",
            "Violations": "1. PERSON IN CHARGE PRESENT",
            "source_row_num": 2,
        },
        {
            "Inspection ID": "0003",
            "Violations": "",
            "source_row_num": 3,
        },
    ]
    pq.write_table(pa.Table.from_pylist(rows), bronze)
    profile = profile_violations(root, batch_size=2)
    profile_path = root / "reports/runs/02_violation/violations_profile.json"
    profile_path.parent.mkdir(parents=True)
    profile_path.write_text(json.dumps(profile), encoding="utf-8")
    run_silver(root)
    return root / SILVER_RELATIVE


def _report_rows(root: Path) -> list[dict]:
    path = root / REPORT_RELATIVE
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def test_quality_passes_for_reconciled_silver_and_expected_nulls(tmp_path: Path):
    _prepared_root(tmp_path)

    result = run_quality(tmp_path)
    rules = {row["quality_rule"] + ":" + row["target_column"]: row for row in result["rules"]}

    assert result["status"] == "PASS"
    assert result["source_counts"]["bronze_rows"] == 3
    assert result["source_counts"]["empty_cells"] == 1
    assert result["source_counts"]["candidate_records"] == 3
    assert result["silver_rows"] == 3
    assert result["actual_status_counts"] == {
        "MISSING_COMMENTS_MARKER": 1,
        "PARSED": 2,
    }
    assert result["silver_null_counts"]["violation_description"] == 1
    assert result["silver_null_counts"]["violation_comments"] == 1
    assert rules["column_null_count:violation_description"]["status"] == "PASS"
    assert rules["column_null_count:violation_description"]["issue_rows"] == 0
    assert rules["bronze_lineage_and_fragment_match:source_row_num/item_sequence_num/inspection_id/source_violations_fragment"]["status"] == "PASS"
    assert (tmp_path / "logs/02_violation/violations_quality_runs.jsonl").is_file()
    assert (tmp_path / REPORT_RELATIVE).is_file()
    assert len(_report_rows(tmp_path)) >= len(SILVER_SCHEMA)


def test_quality_fails_on_wrong_grain_key_and_raw_fragment(tmp_path: Path):
    silver_path = _prepared_root(tmp_path)
    rows = pq.read_table(silver_path).to_pylist()
    rows[0]["item_sequence_num"] = 2
    rows[0]["source_violations_fragment"] = "changed fragment"
    pq.write_table(pa.Table.from_pylist(rows, schema=SILVER_SCHEMA), silver_path)

    result = run_quality(tmp_path)
    rules = {row["quality_rule"] + ":" + row["target_column"]: row for row in result["rules"]}

    assert result["status"] == "FAIL"
    assert result["duplicate_grain_keys"] == 1
    assert rules["silver_grain_key_unique:source_row_num + item_sequence_num"]["status"] == "FAIL"
    assert rules["bronze_lineage_and_fragment_match:source_row_num/item_sequence_num/inspection_id/source_violations_fragment"]["status"] == "FAIL"
