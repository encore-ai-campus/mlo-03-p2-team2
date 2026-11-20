import importlib
import json

import pyarrow as pa
import pyarrow.parquet as pq
import pytest


analysis = importlib.import_module("src.domains.02_violation.build_analysis_mart")
gold = importlib.import_module("src.gold.violations")
silver = importlib.import_module("src.silver.violations_reconciliation")
profile = importlib.import_module("src.profiling.profile_violations")
silver_base = importlib.import_module("src.silver.violations")


def _write_fixture(tmp_path):
    root = tmp_path / "input"
    paths = {
        "origin": root / profile.ORIGIN_RELATIVE,
        "bronze": root / profile.BRONZE_RELATIVE,
        "silver": root / silver_base.SILVER_RELATIVE,
        "accepted": root / silver.ACCEPTED_RELATIVE,
        "quarantine": root / silver.QUARANTINE_RELATIVE,
        "report": root / silver.REPORT_RELATIVE,
        "dimension": root / gold.DIM_RELATIVE,
        "fact": root / gold.FACT_RELATIVE,
    }
    for path in paths.values():
        path.parent.mkdir(parents=True, exist_ok=True)
    paths["origin"].write_text("fixture", encoding="utf-8")
    bronze_schema = pa.schema([
        pa.field("Inspection ID", pa.string()), pa.field("Facility Type", pa.string()),
        pa.field("Results", pa.string()),
    ])
    bronze = [
        {"Inspection ID": "i1", "Facility Type": "Restaurant", "Results": "Fail"},
        {"Inspection ID": "i2", "Facility Type": "School", "Results": "Pass"},
    ]
    pq.write_table(pa.Table.from_pylist(bronze, schema=bronze_schema), paths["bronze"])
    accepted = [
        {"inspection_id": "i1", "bronze_row_number": 1, "item_sequence_num": 1,
         "_SRC_FILE": "x", "_LOAD_DTM": "t", "source_violations_fragment": "r1",
         "violation_code": "1", "violation_description": "A", "violation_comments": "c1", "parsing_status": "PARSED"},
        {"inspection_id": "i2", "bronze_row_number": 2, "item_sequence_num": 1,
         "_SRC_FILE": "x", "_LOAD_DTM": "t", "source_violations_fragment": "r2",
         "violation_code": "1", "violation_description": "B", "violation_comments": "c2", "parsing_status": "PARSED"},
    ]
    pq.write_table(pa.Table.from_pylist(accepted, schema=silver_base.SILVER_SCHEMA), paths["accepted"])
    pq.write_table(pa.Table.from_pylist(accepted, schema=silver_base.SILVER_SCHEMA), paths["silver"])
    quarantine = [{**accepted[0], "bronze_row_number": 3, "violation_description": None,
                   "violation_comments": None, "parsing_status": "MISSING_COMMENTS_MARKER",
                   "rejection_reason": "MISSING_COMMENTS_MARKER"}]
    pq.write_table(pa.Table.from_pylist(quarantine, schema=silver.QUARANTINE_SCHEMA), paths["quarantine"])
    paths["report"].write_text(json.dumps({
        "status": "PASS", "counts": {"candidate_fragments": 3, "accepted": 2, "quarantined": 1}
    }), encoding="utf-8")
    dim = [
        {"violation_key": 1, "violation_code": "1", "violation_description": "A"},
        {"violation_key": 2, "violation_code": "1", "violation_description": "B"},
    ]
    pq.write_table(pa.Table.from_pylist(dim, schema=gold.DIM_SCHEMA), paths["dimension"])
    facts = [
        {"bronze_row_number": 1, "item_sequence_num": 1, "inspection_id": "i1", "violation_key": 1,
         "violation_comments": "c1", "source_violations_fragment": "r1", "_SRC_FILE": "x", "_LOAD_DTM": "t"},
        {"bronze_row_number": 2, "item_sequence_num": 1, "inspection_id": "i2", "violation_key": 2,
         "violation_comments": "c2", "source_violations_fragment": "r2", "_SRC_FILE": "x", "_LOAD_DTM": "t"},
    ]
    pq.write_table(pa.Table.from_pylist(facts, schema=gold.FACT_SCHEMA), paths["fact"])
    return root, paths


def test_mart_join_analysis_and_repeat_are_deterministic(tmp_path):
    root, _ = _write_fixture(tmp_path)
    output = tmp_path / "output"
    first = analysis.build(root, output)
    second = analysis.build(root, output)
    assert first["mart_rows"] == first["fact_rows"] == first["accepted_rows"] == 2
    assert first["accepted_rows"] + first["quarantine_rows"] == first["candidate_fragments"] == 3
    assert first["fail_violation_rows"] == 1
    assert first["orphan_inspection"] == first["orphan_dimension"] == first["unexpected_row_change"] == 0
    assert first["mart_content_sha256"] == second["mart_content_sha256"]
    assert first["mart_sha256"] == second["mart_sha256"]
    assert first["html_sha256"] == second["html_sha256"]
    mart = pq.read_table(output / analysis.MART_RELATIVE)
    assert mart.schema == analysis.MART_SCHEMA
    assert mart.column("inspection_result").to_pylist() == ["Fail", "Pass"]
    html = (output / analysis.HTML_RELATIVE).read_text(encoding="utf-8")
    assert "전체 정상 위반 건수" in html and "Fail 점검" in html and "Restaurant" in html


def test_new_rows_are_calculated_without_production_counts(tmp_path):
    root, paths = _write_fixture(tmp_path)
    bronze = pq.read_table(paths["bronze"]).to_pylist()
    bronze.append({"Inspection ID": "i3", "Facility Type": "Bakery", "Results": "Fail"})
    pq.write_table(pa.Table.from_pylist(bronze, schema=pq.read_schema(paths["bronze"])), paths["bronze"])
    accepted = pq.read_table(paths["accepted"]).to_pylist()
    accepted.append({**accepted[0], "inspection_id": "i3", "bronze_row_number": 4, "violation_comments": "c3"})
    pq.write_table(pa.Table.from_pylist(accepted, schema=silver_base.SILVER_SCHEMA), paths["accepted"])
    pq.write_table(pa.Table.from_pylist(accepted, schema=silver_base.SILVER_SCHEMA), paths["silver"])
    facts = pq.read_table(paths["fact"]).to_pylist()
    facts.append({**facts[0], "inspection_id": "i3", "bronze_row_number": 4, "violation_comments": "c3"})
    pq.write_table(pa.Table.from_pylist(facts, schema=gold.FACT_SCHEMA), paths["fact"])
    report = json.loads(paths["report"].read_text(encoding="utf-8"))
    report["counts"] = {"candidate_fragments": 4, "accepted": 3, "quarantined": 1}
    paths["report"].write_text(json.dumps(report), encoding="utf-8")
    result = analysis.build(root, tmp_path / "new-output")
    assert result["mart_rows"] == 3
    assert result["fail_violation_rows"] == 2


def test_missing_inspection_parent_stops_without_output(tmp_path):
    root, paths = _write_fixture(tmp_path)
    fact = pq.read_table(paths["fact"]).to_pylist()
    fact[0]["inspection_id"] = "missing"
    pq.write_table(pa.Table.from_pylist(fact, schema=gold.FACT_SCHEMA), paths["fact"])
    output = tmp_path / "no-output"
    with pytest.raises(ValueError, match="Join mismatch"):
        analysis.build(root, output)
    assert not (output / analysis.MART_RELATIVE).exists()
    assert not (output / analysis.HTML_RELATIVE).exists()
