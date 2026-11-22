import csv
import json
from importlib import import_module

import pyarrow as pa
import pyarrow.parquet as pq
import pytest


runner = import_module("src.domains.02_violation.runner")


@pytest.mark.parametrize(("values", "reasons", "fact_keys"), [
    (["", "  "], [], []),
    (["NO CODE OR MARKER"], ["UNPARSED_CODE_HEADER"], []),
    (
        ["NO CODE OR MARKER", "1. BODY|2. BODY", "4. BODY - Comments:",
         "5. BODY", "55. PHYSICAL FACILITIES INSTALLED, MAINTAINED & CLEAN - Comments: example"],
        ["UNPARSED_CODE_HEADER", "UNRECOGNIZED_SEPARATOR", "EMPTY_COMMENTS", "MISSING_COMMENTS_MARKER"],
        [92],
    ),
])
def test_run_reconciles_empty_and_unrecognized_violations(tmp_path, values, reasons, fact_keys):
    origin = tmp_path / runner.profiling.ORIGIN_RELATIVE
    shared = tmp_path / runner.bronze.SHARED_BRONZE_RELATIVE
    for path in (origin, shared):
        path.parent.mkdir(parents=True)
    records = [
        {"Inspection ID": str(index), "Facility Type": "Restaurant", "Results": "Pass", "Violations": value}
        for index, value in enumerate(values, 1)
    ]
    with origin.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)
    pq.write_table(pa.Table.from_pylist([
        {**record, "_SRC_FILE": "food_inspections.csv", "_LOAD_DTM": "2026-11-22T00:00:00Z"}
        for record in records
    ]), shared)

    output = runner.run(tmp_path)

    run = json.loads((output / "run.json").read_text(encoding="utf-8"))
    assert run["status"] == "PASS"
    assert run["counts"]["bronze_inspections"] == len(values)
    assert run["counts"]["accepted"] == len(fact_keys)
    assert run["counts"]["quarantined"] == len(reasons)
    assert run["counts"]["candidate_fragments"] == len(reasons) + len(fact_keys)
    quarantine = pq.read_table(output / runner.reconciliation.QUARANTINE_RELATIVE).to_pylist()
    assert [row["rejection_reason"] for row in quarantine] == reasons
    assert [row["source_violations_fragment"] for row in quarantine] == values[:len(reasons)]
    fact = pq.read_table(output / runner.gold.FACT_RELATIVE)
    assert fact.schema == runner.gold.FACT_SCHEMA
    assert fact["violation_key"].to_pylist() == fact_keys
    dimension = pq.read_table(output / runner.gold.DIM_RELATIVE)
    assert dimension.schema == runner.gold.DIM_SCHEMA
    assert dimension["violation_key"].to_pylist() == fact_keys
    mart = pq.read_table(output / runner.build_analysis_mart.MART_RELATIVE)
    assert mart.num_rows == len(fact_keys)
