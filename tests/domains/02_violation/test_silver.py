"""Tests for the Violations-only Silver child table."""

import csv
import json
import hashlib
from importlib import import_module
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

profiling = import_module("src.domains.02_violation.profiling")
profile_violations = profiling.profile_violations
silver = import_module("src.domains.02_violation.silver")
SILVER_SCHEMA, parse_fragment, run = silver.SILVER_SCHEMA, silver.parse_fragment, silver.run


def test_parse_complete_record_and_missing_comments_exception():
    parsed = parse_fragment("16. SURFACES CLEAN - Comments: CLEAN THE MACHINE")
    assert parsed == {
        "violation_code": "16",
        "violation_description": "SURFACES CLEAN",
        "violation_comments": "CLEAN THE MACHINE",
        "parsing_status": "PARSED",
    }

    missing = parse_fragment("1. PERSON IN CHARGE PRESENT, DEMONSTRATES KNOWLEDGE")
    assert missing == {
        "violation_code": "1",
        "violation_description": None,
        "violation_comments": None,
        "parsing_status": "MISSING_COMMENTS_MARKER",
    }


def test_unparseable_header_is_preserved_as_status():
    assert parse_fragment("unknown format") == {
        "violation_code": None,
        "violation_description": None,
        "violation_comments": None,
        "parsing_status": "UNPARSED_CODE_HEADER",
    }


def test_pipeline_writes_only_nonempty_fragments_and_reconciles_profile(tmp_path: Path):
    bronze = tmp_path / profiling.BRONZE_RELATIVE
    origin = tmp_path / profiling.ORIGIN_RELATIVE
    bronze.parent.mkdir(parents=True)
    origin.parent.mkdir(parents=True)
    origin.write_bytes(b"fixture-origin")
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
    profile = profile_violations(tmp_path, batch_size=2)
    profile_path = tmp_path / "reports/runs/02_violation/violations_profile.json"
    profile_path.parent.mkdir(parents=True)
    profile_path.write_text(json.dumps(profile), encoding="utf-8")
    bronze_hash_before = hashlib.sha256(bronze.read_bytes()).hexdigest()
    origin_hash_before = hashlib.sha256(origin.read_bytes()).hexdigest()

    result = run(tmp_path)

    output = tmp_path / "data/02_silver/02_violation/02_inspection_violations.parquet"
    silver = pq.ParquetFile(output)
    assert silver.metadata.num_rows == 3
    assert silver.schema_arrow == SILVER_SCHEMA
    records = pq.read_table(output).to_pylist()
    assert [r["item_sequence_num"] for r in records] == [1, 2, 1]
    assert [r["inspection_id"] for r in records] == ["0001", "0001", "0002"]
    assert records[0]["violation_code"] == "16"
    assert records[0]["violation_description"] == "SURFACES CLEAN"
    assert records[0]["violation_comments"] == "CLEAN"
    assert records[2]["violation_code"] == "1"
    assert records[2]["violation_description"] is None
    assert records[2]["violation_comments"] is None
    assert result["output_rows"] == profile["counts"]["candidate_fragments"] == 3
    assert result["processing_status_counts"] == {
        "MISSING_COMMENTS_MARKER": 1,
        "PARSED": 2,
    }
    assert result["null_violation_description"] == 1
    assert result["source_bronze_sha256_before"] == result["source_bronze_sha256_after"] == bronze_hash_before
    assert result["source_origin_sha256_before"] == result["source_origin_sha256_after"] == origin_hash_before
    with (tmp_path / "metadata/standards/violations_mapping.csv").open(encoding="utf-8", newline="") as stream:
        mappings = list(csv.DictReader(stream))
    assert any(r["target_column"] == "violation_code" and r["affected_rows"] == "3" for r in mappings)
    assert (tmp_path / "logs/02_violation/violations_silver_runs.jsonl").is_file()
