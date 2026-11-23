from datetime import date
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pyarrow as pa
import pyarrow.parquet as pq


SCRIPT = Path(__file__).resolve().parents[3] / "src/domains/05_geospatial/geographic_shared.py"


def test_shared_geography_uses_inputs_and_links_releases(tmp_path):
    inspections = tmp_path / "food_inspections.parquet"
    pq.write_table(pa.table({
        "inspection_key": ["1", "2", "3"], "source_row_num": [1, 2, 3],
        "inspection_dtm": pa.array([date(2020, 1, 1)] * 3, pa.date32()),
        "latitude": [0.5, None, None], "longitude": [0.5, None, None],
        "violations_text": ["1. Reported", None, None],
        "result_cd": ["FAIL", "PASS", "PASS"], "risk_level_cd": ["HIGH"] * 3,
        "facility_type": ["Restaurant"] * 3, "inspection_type": ["Canvass"] * 3,
    }), inspections)
    pq.write_table(pa.table({
        "source_row_num": [2, 3, 1], "invalid_latitude": [True, False, False],
        "invalid_longitude": [False] * 3,
    }), tmp_path / "inspection_rule_flags.parquet")
    areas = tmp_path / "community_areas.parquet"
    geometries = [json.dumps({"type": "Polygon", "coordinates": [[[x, 0], [x + 1, 0],
                    [x + 1, 1], [x, 1], [x, 0]]]}) for x in range(0, 154, 2)]
    pq.write_table(pa.table({"community_area_num": list(range(1, 78)), "geometry": geometries,
                             "community_area_name": [f"Area {x}" for x in range(1, 78)]}), areas)
    violations = tmp_path / "violations"
    violations.mkdir()
    codes = violations / "inspection_violation_codes.parquet"
    pq.write_table(pa.table({"inspection_key": ["1"], "code_system_version": ["from_2018_07_01"],
                             "violation_cd": ["1"], "description_text": ["Shared label"]}), codes)
    observations = violations / "inspection_violation_observations.parquet"
    pq.write_table(pa.table({"inspection_key": ["3", "1", "2"],
                             "violation_observation_status": ["raw_missing", "partial", "raw_missing"]}),
                   observations)
    source_hash = "a" * 64
    boundary_hash = "b" * 64
    verification = {
        "status": "PASS", "source_sha256": source_hash.upper(),
        "artifacts": {path.name: {"sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                                  "rows": pq.read_metadata(path).num_rows}
                      for path in (codes, observations)},
    }
    verification_path = violations / "verification.json"
    verification_path.write_text(json.dumps(verification), encoding="utf-8")
    data = tmp_path / "output"
    command = [sys.executable, str(SCRIPT), "--inspection-silver", str(inspections), "--area-silver", str(areas),
               "--violations-dir", str(violations), "--data-dir", str(data), "--inspection-sha256", source_hash,
               "--boundary-sha256", boundary_hash]
    result = subprocess.run(command, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr

    silver, gold, ai = [next(data.glob(f"{layer}/05_geospatial/*/*/manifest.json"))
                        for layer in ("02_silver", "03_gold", "ai_ready")]
    silver_manifest, gold_manifest, ai_manifest = [json.loads(path.read_text(encoding="utf-8"))
                                                   for path in (silver, gold, ai)]
    assert silver_manifest["source_mode"] == "shared"
    assert set(silver_manifest["artifacts"]) == {
        "inspection_community_areas.parquet", "inspection_geography.parquet", "quality_summary.json",
    }
    assigned = pq.read_table(silver.parent / "inspection_community_areas.parquet")
    assert assigned["community_area_match_status"].to_pylist() == ["unique_area", "invalid_coordinates",
                                                                  "missing_coordinates"]
    assert assigned["boundary_version"].to_pylist() == [boundary_hash] * 3
    assert gold_manifest["silver_manifest_sha256"] == hashlib.sha256(silver.read_bytes()).hexdigest()
    assert ai_manifest["gold_manifest_sha256"] == hashlib.sha256(gold.read_bytes()).hexdigest()
    summary = json.loads((gold.parent / "metrics_summary.json").read_text(encoding="utf-8"))
    assert summary["inspection"]["inspection_count"] == 3
    assert summary["violation_coverage"]["violation_partial_count"] == 1
    assert summary["violation_coverage"]["violation_code_ready_count"] == 1
    metrics = pq.read_table(gold.parent / "violation_area_period.parquet")
    assert metrics["violation_description_text"].unique().to_pylist() == ["Shared label"]

    verification["source_sha256"] = "c" * 64
    verification_path.write_text(json.dumps(verification), encoding="utf-8")
    result = subprocess.run(command, capture_output=True, text=True)
    assert result.returncode != 0
    assert "02 and 06 inspection origin SHA-256 differ" in result.stderr
