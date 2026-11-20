import json
from importlib import import_module

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

gold = import_module("src.domains.02_violation.gold")
reconciliation = import_module("src.domains.02_violation.reconciliation")
silver = import_module("src.domains.02_violation.silver")
DIM_RELATIVE, FACT_RELATIVE = gold.DIM_RELATIVE, gold.FACT_RELATIVE
build, content_hash, dimension_members, rows = gold.build, gold.content_hash, gold.dimension_members, gold.rows
ACCEPTED_RELATIVE, QUARANTINE_RELATIVE = reconciliation.ACCEPTED_RELATIVE, reconciliation.QUARANTINE_RELATIVE
REPORT_RELATIVE, QUARANTINE_SCHEMA = reconciliation.REPORT_RELATIVE, reconciliation.QUARANTINE_SCHEMA
SILVER_SCHEMA = silver.SILVER_SCHEMA


def sample_root(tmp_path):
    root = tmp_path / "input"
    accepted = root / ACCEPTED_RELATIVE
    quarantine = root / QUARANTINE_RELATIVE
    report = root / REPORT_RELATIVE
    for path in (accepted, quarantine, report):
        path.parent.mkdir(parents=True, exist_ok=True)
    source = {
        "inspection_id": "001", "source_row_num": 1, "item_sequence_num": 1,
        "source_violations_fragment": "raw",
        "violation_code": "1", "violation_description": "A", "violation_comments": "comment",
        "parsing_status": "PARSED",
    }
    valid = [source, {**source, "source_row_num": 2, "violation_description": "B"},
             {**source, "source_row_num": 3, "violation_code": "2"}]
    invalid = {**source, "source_row_num": 4, "violation_description": None,
               "violation_comments": None, "parsing_status": "MISSING_COMMENTS_MARKER",
               "rejection_reason": "MISSING_COMMENTS_MARKER"}
    pq.write_table(pa.Table.from_pylist(valid, schema=SILVER_SCHEMA), accepted)
    pq.write_table(pa.Table.from_pylist([invalid], schema=QUARANTINE_SCHEMA), quarantine)
    report.write_text(json.dumps({
        "status": "PASS", "issues": {}, "counts": {"candidate_fragments": 4, "accepted": 3, "quarantined": 1},
        "accepted_content_sha256": content_hash(accepted),
        "quarantine_content_sha256": content_hash(quarantine),
    }), encoding="utf-8")
    return root, accepted, valid


def test_gold_grain_keys_fk_reconciliation_and_repeat(tmp_path):
    root, accepted, valid = sample_root(tmp_path)
    out = tmp_path / "output"
    first = build(root, out)
    second = build(root, out)
    assert first["dimension_rows"] == second["dimension_rows"] == 3
    assert first["fact_rows"] == second["fact_rows"] == len(valid)
    assert first["candidate_fragments"] == first["accepted"] + first["quarantined"]
    assert first["orphan_fk"] == first["reverse_join_mismatch"] == first["duplicate_fact_grain"] == 0
    assert first["dimension_content_sha256"] == second["dimension_content_sha256"]
    assert first["fact_content_sha256"] == second["fact_content_sha256"]
    dim = list(rows(out / DIM_RELATIVE))
    fact = list(rows(out / FACT_RELATIVE))
    assert len({d["violation_key"] for d in dim}) == len(dim)
    assert len({(d["violation_code"], d["violation_description"]) for d in dim}) == len(dim)
    assert len({(f["source_row_num"], f["item_sequence_num"]) for f in fact}) == len(fact)
    assert {f["violation_key"] for f in fact} <= {d["violation_key"] for d in dim}
    pq.write_table(pa.Table.from_pylist(list(reversed(valid)), schema=SILVER_SCHEMA), accepted)
    assert dimension_members(accepted) == dim


def test_new_input_counts_are_calculated(tmp_path):
    root, accepted, valid = sample_root(tmp_path)
    extra = {**valid[0], "source_row_num": 5, "violation_code": "3"}
    pq.write_table(pa.Table.from_pylist(valid + [extra], schema=SILVER_SCHEMA), accepted)
    report = root / REPORT_RELATIVE
    payload = json.loads(report.read_text(encoding="utf-8"))
    payload["counts"] = {"candidate_fragments": 5, "accepted": 4, "quarantined": 1}
    payload["accepted_content_sha256"] = content_hash(accepted)
    report.write_text(json.dumps(payload), encoding="utf-8")
    result = build(root, tmp_path / "new_output")
    assert result["fact_rows"] == 4
    assert result["dimension_rows"] == 4


def test_reconciliation_mismatch_stops_before_gold(tmp_path):
    root, _, _ = sample_root(tmp_path)
    report = root / REPORT_RELATIVE
    payload = json.loads(report.read_text(encoding="utf-8"))
    payload["counts"]["candidate_fragments"] += 1
    report.write_text(json.dumps(payload), encoding="utf-8")
    out = tmp_path / "no_output"
    with pytest.raises(ValueError, match="candidate fragments"):
        build(root, out)
    assert not (out / DIM_RELATIVE).exists()
    assert not (out / FACT_RELATIVE).exists()
