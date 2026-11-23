"""검증된 Gold 집계와 의미 계약을 기반으로 지역별 AI 질의용 릴리스를 생성한다.

지역 키, 코드 관측 상태, 지표별 분모와 검증 요약을 제공한다.
"""

import argparse
import hashlib
import json
from pathlib import Path
import platform

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from geographic_gold import ALL_AREA_STATUSES, GOLD_ARTIFACTS, ratio
from geographic_medallion import (
    AI_READY_DIR, PROJECT, check, digest_json, publish, read_json, sha256_file,
    utc_now, verify_artifacts, write_json, write_table,
)


CONTRACT = PROJECT / "metadata/feature_dictionary/05_geospatial/semantic_contract.json"
INSPECTION_FILE = "ai_inspection_metrics.parquet"
COVERAGE_FILE = "ai_violation_coverage.parquet"
VIOLATION_FILE = "ai_violation_metrics.parquet"
RELEASE_ARTIFACTS = {
    INSPECTION_FILE, COVERAGE_FILE, VIOLATION_FILE, "semantic_contract.json", "validation_summary.json",
}
REGION_FIELDS = [("region_key", pa.string()), ("assigned_area_flag", pa.bool_())]
VIOLATION_EXTRA_FIELDS = [
    *REGION_FIELDS, ("violation_recorded_count", pa.int64()), ("violation_missing_count", pa.int64()),
    ("code_observation_status_cd", pa.string()),
]
REGION_PERIOD_KEY = ["period_grain_cd", "period_start_dtm", "region_key"]
COVERAGE_KEY = [*REGION_PERIOD_KEY, "code_system_version"]
CODE_KEY = [*COVERAGE_KEY, "violation_cd"]


def code_hashes():
    scripts = Path(__file__).resolve().parent
    names = ("geographic_ai_ready.py", "geographic_gold.py", "geographic_medallion.py")
    return {name: sha256_file(scripts / name) for name in names}


def add_region_key(table):
    # 지역 배정과 미배정 사유에 서로 다른 안정적인 키를 부여한다.
    numbers = table["community_area_num"].to_pylist()
    statuses = table["community_area_match_status"].to_pylist()
    keys = []
    assigned = []
    for number, status in zip(numbers, statuses, strict=True):
        check(status in ALL_AREA_STATUSES and (status == "unique_area") == (number is not None),
              "Gold region and assignment status disagree")
        if number is None:
            keys.append(f"unassigned:{status}")
            assigned.append(False)
        else:
            check(1 <= number <= 77, "Community Area number falls outside the supported range")
            keys.append(f"community_area:{number:02d}")
            assigned.append(True)
    return (table.append_column("region_key", pa.array(keys, type=pa.string()))
            .append_column("assigned_area_flag", pa.array(assigned, type=pa.bool_())))


def validate_inspections_and_coverage(inspections, coverage):
    dims = ["period_grain_cd", "period_start_dtm", "region_key", "community_area_name", "boundary_version"]
    relevant = [*dims, "evaluated_count"]
    inspections = inspections.select(relevant).to_pandas()
    covered = coverage.select([*relevant, "violation_recorded_count", "violation_missing_count",
                               "violation_code_ready_count"]).to_pandas()
    check(bool(covered["evaluated_count"].eq(
        covered["violation_recorded_count"] + covered["violation_missing_count"],
    ).all()) and bool(covered["violation_code_ready_count"].le(covered["violation_recorded_count"]).all()),
          "Gold evaluation and violation coverage counts disagree")
    combined = covered.groupby(dims, dropna=False)["evaluated_count"].sum().reset_index()
    compared = inspections.merge(combined, on=dims, how="outer", validate="one_to_one",
                                 suffixes=("_inspection", "_coverage"), indicator=True)
    check(bool(compared["_merge"].eq("both").all()) and
          bool(compared["evaluated_count_inspection"].eq(compared["evaluated_count_coverage"]).all()),
          "Era-specific denominator totals differ from the inspection table")


def dense_violation_metrics(gold_path, coverage):
    sparse = add_region_key(pq.read_table(gold_path))
    schema = pa.schema([*pq.read_schema(gold_path), *VIOLATION_EXTRA_FIELDS])
    assessed = coverage.to_pandas()
    if sparse.num_rows == 0:
        return pa.Table.from_batches([], schema=schema), {}

    sparse = sparse.to_pandas()
    era_code = ["code_system_version", "violation_cd"]
    labels = [*era_code, "violation_description_text", "description_variant_count"]
    codes = sparse[labels].drop_duplicates()
    check(not codes.duplicated(era_code).any() and bool(codes[era_code].notna().all().all()),
          "Gold describes an era/code with conflicting labels or a missing identity")
    check(bool(sparse["code_inspection_count"].gt(0).all()) and not sparse.duplicated(CODE_KEY).any(),
          "Gold violation counts include empty or duplicate keys")
    domain_sizes = codes.groupby("code_system_version").size().to_dict()
    coverage_sizes = assessed.groupby("code_system_version").size().to_dict()

    # 각 절차 구간에서 관측된 코드만 그 구간의 지역·기간으로 펼친다.
    dense = assessed.merge(codes, on="code_system_version", how="inner", validate="many_to_many")
    check(len(dense) == sum(count * coverage_sizes.get(era, 0) for era, count in domain_sizes.items()),
          "The dense violation table does not match its era-specific code domain")
    dense = dense.merge(sparse[CODE_KEY + ["code_inspection_count"]], on=CODE_KEY, how="left",
                        validate="one_to_one")
    dense["code_inspection_count"] = dense["code_inspection_count"].fillna(0).astype("int64")
    numerator = dense["code_inspection_count"]
    evaluated = dense["evaluated_count"]
    ready = dense["violation_code_ready_count"]
    check(bool(numerator.le(ready).all()) and bool(ready.le(evaluated).all()),
          "Violation numerator exceeds the code-ready or evaluated denominator")

    dense["code_recorded_rate"] = ratio(numerator, evaluated)
    dense["code_recorded_among_ready_rate"] = ratio(numerator, ready)
    # 코드 0건과 분모 0건을 관측 상태로 구분한다.
    state = pd.Series("RECORDED", index=dense.index, dtype="string")
    state = state.mask(numerator.eq(0), "NO_RECORDED_CODE")
    state = state.mask(ready.eq(0), "NO_CODE_READY_INSPECTIONS")
    dense["code_observation_status_cd"] = state.mask(evaluated.eq(0), "NO_EVALUATED_INSPECTIONS")
    check(bool(dense["code_recorded_rate"].isna().eq(evaluated.eq(0)).all()) and
          bool(dense["code_recorded_among_ready_rate"].isna().eq(ready.eq(0)).all()),
          "Violation rates do not preserve zero-denominator nulls")

    checked_measures = ["code_inspection_count", "evaluated_count", "violation_code_ready_count",
                        "code_recorded_rate", "code_recorded_among_ready_rate"]
    observed = dense.loc[numerator.gt(0), CODE_KEY + checked_measures]
    expected = sparse[CODE_KEY + checked_measures]
    pd.testing.assert_frame_equal(
        observed.sort_values(CODE_KEY, ignore_index=True),
        expected.sort_values(CODE_KEY, ignore_index=True),
        check_dtype=False,
    )

    ordered = dense.sort_values(CODE_KEY, ignore_index=True)
    result = pa.Table.from_pandas(ordered, schema=schema, preserve_index=False).replace_schema_metadata(None)
    return result, {era: int(count) for era, count in domain_sizes.items()}


def verify_contract(tables, contract):
    check(set(contract["tables"]) == set(tables), "Semantic contract list differs from release tables")
    keys = {INSPECTION_FILE: REGION_PERIOD_KEY, COVERAGE_FILE: COVERAGE_KEY, VIOLATION_FILE: CODE_KEY}
    for name, table in tables.items():
        target = contract["tables"][name]
        check(target["key"] == keys[name], f"{name}: unexpected semantic key")
        actual = {field.name: str(field.type) for field in table.schema}
        defined = {column: value["type"] for column, value in target["columns"].items()}
        check(actual == defined, f"{name}: semantic contract and physical schema differ")
        check(bool(target["grain_ko"]), f"{name}: missing grain definition")
        for column, specification in target["columns"].items():
            values = table[column]
            check(bool(specification["meaning_ko"]), f"{name}/{column}: missing semantic definition")
            check(specification["nullable"] or values.null_count == 0, f"{name}/{column}: unexpected NULL")
            if "values" in specification:
                distinct = set(values.unique().drop_null().to_pylist())
                check(distinct <= set(specification["values"]), f"{name}/{column}: unexpected category")
        check(not table.select(keys[name]).to_pandas().duplicated().any(), f"{name}: duplicate release keys")


def release_summary(tables, domain_sizes):
    inspections = tables[INSPECTION_FILE].select([
        "period_grain_cd", "inspection_count", "evaluated_count", "failed_count",
    ]).to_pandas()
    coverage = tables[COVERAGE_FILE].select([
        "period_grain_cd", "violation_recorded_count", "violation_missing_count",
    ]).to_pandas()
    violation = tables[VIOLATION_FILE].select([
        "period_grain_cd", "code_inspection_count", "code_observation_status_cd",
    ]).to_pandas()
    by_grain = {}
    for grain, frame in inspections.groupby("period_grain_cd"):
        evaluated = int(frame["evaluated_count"].sum())
        failed = int(frame["failed_count"].sum())
        selected_coverage = coverage.loc[coverage["period_grain_cd"].eq(grain)]
        selected_codes = violation.loc[violation["period_grain_cd"].eq(grain)]
        by_grain[grain] = {
            "inspection_count": int(frame["inspection_count"].sum()),
            "evaluated_count": evaluated, "failed_count": failed,
            "failure_rate": failed / evaluated if evaluated else None,
            "evaluated_with_violation_record_count": int(selected_coverage["violation_recorded_count"].sum()),
            "evaluated_missing_violation_record_count": int(selected_coverage["violation_missing_count"].sum()),
            "evaluated_code_observation_count": int(selected_codes["code_inspection_count"].sum()),
        }
    check(by_grain.get("MONTH") == by_grain.get("YEAR"), "Month and year rollups cover different events")
    return {
        "table_rows": {name: table.num_rows for name, table in tables.items()},
        "observed_code_domain_size_by_era": domain_sizes,
        "code_observation_status_rows": {str(key): int(value) for key, value in
                                         violation["code_observation_status_cd"].value_counts().items()},
        "inspection_and_violation_totals_by_grain": by_grain,
        "validated_against_gold": True,
    }


def build(directory, gold_dir, lineage, contract, signature):
    inspections = add_region_key(pq.read_table(gold_dir / "inspection_area_period.parquet"))
    coverage = add_region_key(pq.read_table(gold_dir / "violation_coverage_area_period.parquet"))
    validate_inspections_and_coverage(inspections, coverage)
    violations, domains = dense_violation_metrics(gold_dir / "violation_area_period.parquet", coverage)
    tables = {INSPECTION_FILE: inspections, COVERAGE_FILE: coverage, VIOLATION_FILE: violations}
    verify_contract(tables, contract)
    for name, table in tables.items():
        write_table(directory / name, table)
    write_json(directory / "semantic_contract.json", contract)
    write_json(directory / "validation_summary.json", release_summary(tables, domains))
    verify_artifacts(gold_dir, "gold", lineage["gold_signature"], GOLD_ARTIFACTS, lineage["batch_id"])
    check(sha256_file(gold_dir / "manifest.json") == lineage["gold_manifest_sha256"],
          "Gold manifest changed while building AI-ready data")
    check(code_hashes() == lineage["ai_ready_code_sha256"], "AI-ready code changed while building")
    return {
        "layer": "ai_ready", "release_id": signature[:20], "rules_signature": signature,
        "built_at_utc": utc_now().isoformat(), "semantic_contract_version": contract["version"],
        **lineage,
    }


def run(action, gold_dir, data_dir):
    gold_manifest = gold_dir / "manifest.json"
    gold_hash = sha256_file(gold_manifest)
    gold = read_json(gold_manifest)
    batch_id = gold["batch_id"]
    verify_artifacts(gold_dir, "gold", gold["rules_signature"], GOLD_ARTIFACTS, batch_id)
    check(sha256_file(gold_manifest) == gold_hash, "Gold manifest changed during verification")
    contract_bytes = CONTRACT.read_bytes()
    contract = json.loads(contract_bytes)
    # 사용한 Gold 릴리스와 의미 계약을 지문으로 연결한다.
    lineage = {
        "batch_id": batch_id, "silver_rules_id": gold["silver_rules_id"],
        "gold_id": gold["gold_id"], "gold_signature": gold["rules_signature"],
        "gold_manifest_sha256": gold_hash, "scope": gold["scope"],
        "observed_window": read_json(gold_dir / "metrics_summary.json")["scope_check"],
        "semantic_contract_sha256": hashlib.sha256(contract_bytes).hexdigest(),
        "ai_ready_code_sha256": code_hashes(),
        "runtime": {"python": platform.python_version(), "pandas": pd.__version__, "pyarrow": pa.__version__},
    }
    signature = digest_json(lineage)
    target = data_dir / AI_READY_DIR / batch_id / signature[:20]
    if action == "verify":
        verify_artifacts(target, "ai_ready", signature, RELEASE_ARTIFACTS, batch_id)
        status = "verified existing"
    else:
        _, status = publish(target, "ai_ready", signature, RELEASE_ARTIFACTS,
                            lambda path: build(path, gold_dir, lineage, contract, signature),
                            batch_id)
    print(f"AI-ready {status}: {target}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("build", "verify"))
    parser.add_argument("--gold-dir", required=True, type=Path, help="Published Gold release directory")
    parser.add_argument("--data-dir", type=Path, default=PROJECT / "data")
    args = parser.parse_args()
    run(args.action, args.gold_dir.resolve(), args.data_dir.resolve())


if __name__ == "__main__":
    main()
