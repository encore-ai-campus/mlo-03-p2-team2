import csv
from datetime import date
import json
from importlib import import_module

import pyarrow as pa
import pyarrow.parquet as pq
import pytest


runner = import_module("src.domains.02_violation.runner")
export = import_module("src.domains.02_violation.export_shared_sample")


@pytest.fixture
def shared_inputs(tmp_path):
    origin = tmp_path / runner.profiling.ORIGIN_RELATIVE
    origin.parent.mkdir(parents=True)
    records = [
        {"Inspection ID": "101", "Facility Type": "Restaurant", "Results": "Pass",
         "Violations": "55. PHYSICAL FACILITIES INSTALLED, MAINTAINED & CLEAN - Comments: example"},
        {"Inspection ID": "102", "Facility Type": "Restaurant", "Results": "Pass", "Violations": ""},
    ]
    with origin.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)
    source_sha = runner.profiling.sha256(origin)
    bronze = tmp_path / "shared_bronze.parquet"
    pq.write_table(pa.Table.from_pylist([
        dict(record, _SRC_FILE=origin.name, _LOAD_DTM="2026-11-22T00:00:00Z", source_row_num=number)
        for number, record in enumerate(records, 1)
    ]).replace_schema_metadata({b"source_sha256": source_sha.upper().encode()}), bronze)
    return bronze, source_sha, records


def test_run_consumes_shared_bronze_without_republishing_it(tmp_path, shared_inputs):
    bronze, _, _ = shared_inputs
    output = tmp_path / "integrated"
    output.mkdir()
    (output / "run.json").write_text("integration report", encoding="utf-8")

    assert runner.run(tmp_path, shared_bronze=bronze, output_root=output) == output

    assert (output / "run.json").read_text(encoding="utf-8") == "integration report"
    assert not (output / runner.profiling.BRONZE_RELATIVE).exists()
    assert not (output / runner.profiling.ORIGIN_RELATIVE.parent).exists()
    assert pq.read_table(output / runner.gold.FACT_RELATIVE)["violation_key"].to_pylist() == [92]
    report = json.loads((output / runner.reconciliation.REPORT_RELATIVE).read_text(encoding="utf-8"))
    assert report["source_bronze_sha256"] == runner.profiling.sha256(bronze)
    assert report["source_bronze"] == bronze.as_posix()


@pytest.mark.parametrize(("column", "values", "expected"), [
    ("source_row_num", [2, 1], "logical row 1"),
    ("Inspection ID", ["102", "101"], "logical row 1"),
    ("_SRC_FILE", ["other.csv", "other.csv"], "logical row 1"),
    (None, None, "source SHA-256"),
])
def test_run_rejects_shared_bronze_with_incorrect_lineage(tmp_path, shared_inputs, column, values, expected):
    bronze, _, _ = shared_inputs
    table = pq.read_table(bronze)
    if column is None:
        table = table.replace_schema_metadata({b"source_sha256": b"0" * 64})
    else:
        index = table.schema.get_field_index(column)
        table = table.set_column(index, column, pa.array(values, type=table.schema.field(index).type))
    pq.write_table(table, bronze)

    output = tmp_path / "integrated"
    with pytest.raises(ValueError, match=expected):
        runner.run(tmp_path, shared_bronze=bronze, output_root=output)
    assert not (output / runner.gold.FACT_RELATIVE).exists()


def test_export_projects_direct_shared_silver_for_geospatial(tmp_path, shared_inputs):
    bronze, source_sha, records = shared_inputs
    root02 = runner.run(tmp_path, shared_bronze=bronze, output_root=tmp_path / "integrated")
    silver = tmp_path / "shared_silver.parquet"
    pq.write_table(pa.Table.from_pylist([
        {"inspection_key": record["Inspection ID"], "source_row_num": number,
         "inspection_dtm": date(2025, 1, 1), "violations_text": record["Violations"] or None}
        for number, record in enumerate(records, 1)
    ]), silver)
    manifest = tmp_path / "silver_manifest.json"
    manifest.write_text(json.dumps({
        "source_sha256": source_sha, "silver_rows": 2,
        "artifacts": {silver.name: runner.profiling.sha256(silver)},
    }), encoding="utf-8")

    output = tmp_path / "geospatial_inputs"
    verification = export.export_sample(
        root02, None, output, inspection_path=silver, inspection_manifest=manifest,
    )
    assert verification["inputs"]["inspection_silver"]["path"] == str(silver)
    assert pq.read_table(output / "inspection_violation_codes.parquet").to_pylist() == [
        {"inspection_key": "101", "code_system_version": "from_2018_07_01", "violation_cd": "55",
         "description_text": "PHYSICAL FACILITIES INSTALLED, MAINTAINED & CLEAN"},
    ]
    assert pq.read_table(output / "inspection_violation_observations.parquet").to_pylist() == [
        {"inspection_key": "101", "violation_observation_status": "parsed"},
        {"inspection_key": "102", "violation_observation_status": "raw_missing"},
    ]


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
