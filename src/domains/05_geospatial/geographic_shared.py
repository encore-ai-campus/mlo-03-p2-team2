"""Build geospatial Silver, Gold, and query releases from shared 06/02 Parquet inputs."""

import argparse
from collections import Counter
import json
from pathlib import Path
import platform
import re

import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq
import shapely

import geographic_ai_ready
import geographic_gold
from geographic_boundary import geojson_wkt
from geographic_integration import (
    AREA_FIELDS, INSPECTION_FIELDS, OBSERVATION_FIELDS, SHARED_SILVER_ARTIFACTS, align_rows, attach_shared_violations,
    read_shared_violation_codes, read_typed, shared_files, shared_fingerprints,
)
from geographic_medallion import (
    SCRIPTS, SILVER_DIR, append_evaluation, check, digest_json, inspection_summary, publish, read_json,
    sha256_file, spatial_assignment, trimmed, utc_now, write_json, write_table,
)
from silver_violations import procedure_version


POINT_FIELDS = ("inspection_key", "latitude", "longitude")
INSPECTION_COLUMNS = (*POINT_FIELDS, "source_row_num", "inspection_dtm", "result_cd", "violations_text")
QUALITY_FIELDS = {"source_row_num": pa.int64(), "invalid_latitude": pa.bool_(), "invalid_longitude": pa.bool_()}


def origin_digest(value):
    if not re.fullmatch(r"[0-9a-fA-F]{64}", value):
        raise argparse.ArgumentTypeError("Expected a 64-character SHA-256 digest")
    return value.lower()


def verify_exports(files, fingerprints, inspection_origin):
    verification = read_json(files["violation_verification"])
    check(verification.get("status") == "PASS", "02 violation export verification must pass")
    check(verification.get("source_sha256", "").lower() == inspection_origin,
          "02 and 06 inspection origin SHA-256 differ")
    for role in ("violation_codes", "violation_observations"):
        path = files[role]
        entry = verification.get("artifacts", {}).get(path.name, {})
        check(entry.get("sha256", "").lower() == fingerprints[role]["sha256"]
              and entry.get("rows") == pq.read_metadata(path).num_rows,
              f"02 verification does not match {path.name}")


def silver_rules():
    names = (
        "geographic_shared.py", "geographic_integration.py", "geographic_medallion.py", "geographic_boundary.py",
        "silver_spatial.py", "silver_violations.py",
    )
    return {
        "input_code_sha256": {name: sha256_file(SCRIPTS / name) for name in names},
        "runtime": {"python": platform.python_version(), "pyarrow": pa.__version__, "pandas": pd.__version__,
                    "shapely": shapely.__version__, "geos": shapely.geos_version_string},
    }


def build_silver(directory, files, lineage, rules, batch_id, signature):
    inspections = read_typed(files["inspection_silver"], {name: INSPECTION_FIELDS[name] for name in INSPECTION_COLUMNS})
    keys = inspections["inspection_key"]
    check(len(inspections) > 0 and not trimmed(keys).null_count
          and pc.count_distinct(keys).as_py() == len(inspections), "06 inspection keys must be complete and unique")
    flags = align_rows(read_typed(files["inspection_quality"], QUALITY_FIELDS), "source_row_num",
                       inspections["source_row_num"])
    invalid = pc.or_(flags["invalid_latitude"], flags["invalid_longitude"])
    check(not invalid.null_count, "06 coordinate parse flags must be complete")
    areas = read_typed(files["area_silver"], {**AREA_FIELDS, "geometry": pa.string()})
    check(not areas["geometry"].null_count and not trimmed(areas["community_area_name"]).null_count,
          "06 community areas must have names and geometries")
    polygons = areas.select(["community_area_num", "geometry"]).to_pandas()
    polygons["geometry"] = polygons["geometry"].map(lambda value: geojson_wkt(json.loads(value)))
    boundary = {"sha256": lineage["origin_sha256"]["community_areas"],
                "file": "community_areas.geojson", "format": "geojson"}
    spatial, spatial_summary = spatial_assignment(inspections.select(POINT_FIELDS).to_pandas(), polygons,
                                                  boundary, invalid.to_pandas())
    write_table(directory / "inspection_community_areas.parquet", spatial)

    # Determine the procedure era and raw-text coverage, then attach the approved 02 classifications by key.
    dates = inspections["inspection_dtm"]
    code_versions = pa.array([procedure_version(day) for day in dates.to_pylist()], type=pa.string())
    expected = pa.table({"inspection_key": keys, "code_system_version": code_versions,
                         "violation_observation_status": pc.if_else(pc.is_null(trimmed(inspections["violations_text"])),
                                                                   "raw_missing", "raw_present")})
    codes = read_shared_violation_codes(files["violation_codes"])
    observations = read_typed(files["violation_observations"], OBSERVATION_FIELDS).to_pandas()
    assessed = attach_shared_violations(expected.to_pandas(), codes, observations)
    observations = pa.array(assessed["violation_observation_status"], type=pa.string())
    geography = spatial.select(["inspection_key", "community_area_num", "community_area_match_status", "boundary_version"])
    geography = (append_evaluation(geography, inspections["result_cd"])
                 .append_column("code_system_version", code_versions)
                 .append_column("violation_observation_status", observations)
                 .append_column("violation_code_occurrence_ready", pa.array(assessed["violation_code_occurrence_ready"])))
    write_table(directory / "inspection_geography.parquet", geography)
    write_json(directory / "quality_summary.json", {
        "inspection": inspection_summary(geography, dates), "spatial": spatial_summary,
        "violation_observation_status": dict(Counter(observations.to_pylist())),
        "violation_code_rows": len(codes),
    })
    check(shared_fingerprints(files) == lineage["shared_inputs"], "Shared inputs changed while building 05 Silver")
    check(silver_rules() == rules, "05 Silver rules changed during the build")
    return {
        "layer": "silver", "source_mode": "shared", "batch_id": batch_id, "rules_id": signature[:20],
        "rules_signature": signature, "built_at_utc": utc_now().isoformat(), **lineage, **rules,
    }


def run(inspection, areas, quality, violations, data, inspection_origin, boundary_origin):
    files = {**shared_files(inspection, violations), "area_silver": areas, "inspection_quality": quality,
             "violation_verification": violations / "verification.json"}
    fingerprints = shared_fingerprints(files)
    verify_exports(files, fingerprints, inspection_origin)
    lineage = {"origin_sha256": {"food_inspections": inspection_origin, "community_areas": boundary_origin},
               "shared_inputs": fingerprints}
    rules = silver_rules()
    batch_id = digest_json(lineage)[:20]
    signature = digest_json({"lineage": lineage, "rules": rules})
    silver_dir = data / SILVER_DIR / batch_id / signature[:20]
    _, status = publish(silver_dir, "silver", signature, SHARED_SILVER_ARTIFACTS,
                        lambda path: build_silver(path, files, lineage, rules, batch_id, signature), batch_id)
    print(f"Silver {status}: {silver_dir}", flush=True)
    scope = dict.fromkeys(("start_date", "end_date", *geographic_gold.FILTER_FIELDS))
    gold_dir = geographic_gold.run("build", silver_dir, data, scope, files)
    geographic_ai_ready.run("build", gold_dir, data)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inspection-silver", type=Path, required=True)
    parser.add_argument("--area-silver", type=Path, required=True)
    parser.add_argument("--inspection-quality", type=Path, help="Defaults to inspection_rule_flags.parquet beside Silver")
    parser.add_argument("--violations-dir", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--inspection-sha256", type=origin_digest, required=True, help="Shared food-inspection origin SHA-256")
    parser.add_argument("--boundary-sha256", type=origin_digest, required=True, help="Shared community-area origin SHA-256")
    args = parser.parse_args()
    quality = args.inspection_quality or args.inspection_silver.with_name("inspection_rule_flags.parquet")
    run(args.inspection_silver, args.area_silver, quality, args.violations_dir, args.data_dir,
        args.inspection_sha256, args.boundary_sha256)


if __name__ == "__main__":
    main()
