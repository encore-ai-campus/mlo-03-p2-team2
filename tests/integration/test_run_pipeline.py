import json
from importlib import import_module

import pyarrow as pa
import pyarrow.parquet as pq
import pytest


pipeline = import_module("src.domains.06_integration.validate_pipeline")


def test_parquet_comparison_checks_values_and_ignores_build_metadata(tmp_path):
    reference = tmp_path / "reference.parquet"
    generated = tmp_path / "generated.parquet"
    table = pa.table({"key": ["a", "b", "c"], "count": [1, None, 3]})
    pq.write_table(table, reference, row_group_size=1)
    pq.write_table(table.replace_schema_metadata({"input": "new"}), generated)
    result = pipeline.compare_parquet(generated, reference)
    assert result["rows"] == 3
    assert result["sha256"] != result["reference_sha256"]

    pq.write_table(pa.table({"key": ["a", "b", "c"], "count": [1, None, 4]}), generated)
    with pytest.raises(ValueError, match="Values differ"):
        pipeline.compare_parquet(generated, reference)


def test_verify_detects_changed_output_and_manifest_paths(tmp_path):
    artifact = tmp_path / "result.parquet"
    pq.write_table(pa.table({"key": ["one"]}), artifact)
    report = tmp_path / pipeline.VERIFICATION
    receipt = {"status": "PASS", "artifacts": {artifact.name: pipeline.sha256(artifact)}}
    report.write_text(json.dumps(receipt), encoding="utf-8")
    assert pipeline.verify_output(tmp_path) == receipt
    pq.write_table(pa.table({"key": ["two"]}), artifact)
    with pytest.raises(ValueError, match="Artifact changed"):
        pipeline.verify_output(tmp_path)

    receipt["artifacts"] = {"../result.parquet": "invalid"}
    report.write_text(json.dumps(receipt), encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid artifact path"):
        pipeline.verify_output(tmp_path)
