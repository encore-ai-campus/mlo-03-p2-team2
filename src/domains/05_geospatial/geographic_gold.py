"""Silver의 평가 완료 점검과 위반 기록을 지역·월·연도 기준으로 집계한다.

점검 지표, 위반 관측 범위, 코드별 기록률을 별도 테이블에 저장하고
집계 건수와 분모를 입력 Silver와 대조한다.
"""

import argparse
import calendar
from datetime import date, timedelta
from pathlib import Path
import platform

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from geographic_integration import load_shared_inputs, shared_files, shared_fingerprints
from geographic_medallion import (
    BRONZE_DIR, BRONZE_FORMAT_VERSION, GOLD_DIR, LOCAL_SOURCE_DIR, PROJECT, SILVER_ARTIFACTS, SILVER_DIR,
    SOURCE_DIR, check, contract_and_codes,
    digest_json, identity, publish, read_json, rules_identity, sha256_file, source_inventory,
    utc_now, verify_artifacts, write_json, write_table,
)
from silver_violations import FROM_CHANGE, PRE_CHANGE, PROCEDURE_CHANGE, SOURCE_START


AREA_KEYS = ["community_area_match_status", "community_area_num"]
PERIOD_KEYS = ["period_grain_cd", "period_start_dtm"]
ERA_KEYS = ["code_system_version"]
ALL_AREA_STATUSES = [
    "unique_area", "missing_coordinates", "invalid_coordinates",
    "outside_boundary", "multiple_boundaries",
]
INSPECTION_METRICS = [
    "inspection_count", "evaluated_count", "failed_count", "not_evaluated_count", "unknown_result_count",
]
COVERAGE_METRICS = [
    "evaluated_count", "violation_recorded_count", "violation_missing_count",
    "violation_code_ready_count", "violation_parsed_count",
    "violation_partial_count", "violation_unrecognized_count",
]
FILTER_FIELDS = ("facility_type", "inspection_type", "risk_level_cd", "community_area_num")
OBSERVATION_STATES = {"parsed", "raw_missing", "partial", "unrecognized"}
INSPECTION_COLUMNS = [
    "inspection_key", "inspection_dtm", "result_cd", "evaluation_status_cd",
    "evaluated_flag", "failed_flag", *AREA_KEYS, "boundary_version",
    "code_system_version", "violation_observation_status", "violation_code_occurrence_ready",
    *[name for name in FILTER_FIELDS if name not in AREA_KEYS],
]
AREA_SCHEMA = [
    ("community_area_match_status", pa.string()), ("community_area_num", pa.int64()),
    ("community_area_name", pa.string()), ("boundary_version", pa.string()),
]
PERIOD_SCHEMA = [
    ("period_grain_cd", pa.string()), ("period_start_dtm", pa.date32()), ("period_end_dtm", pa.date32()),
    ("covered_start_dtm", pa.date32()), ("covered_end_dtm", pa.date32()), ("partial_period_flag", pa.bool_()),
]
ERA_SCHEMA = [
    ("code_system_version", pa.string()), ("era_covered_start_dtm", pa.date32()), ("era_covered_end_dtm", pa.date32()),
]
CODE_SCHEMA = [
    ("violation_cd", pa.string()), ("violation_description_text", pa.string()),
    ("description_variant_count", pa.int64()), ("code_inspection_count", pa.int64()),
    ("evaluated_count", pa.int64()), ("violation_code_ready_count", pa.int64()),
    ("code_recorded_rate", pa.float64()), ("code_recorded_among_ready_rate", pa.float64()),
]
GOLD_ARTIFACTS = {
    "inspection_area_period.parquet", "violation_coverage_area_period.parquet",
    "violation_area_period.parquet", "metrics_summary.json",
}


def source_code_hashes():
    scripts = Path(__file__).resolve().parent
    names = ("geographic_gold.py", "geographic_integration.py", "geographic_medallion.py", "silver_violations.py")
    return {name: sha256_file(scripts / name) for name in names}


def current_silver_dir(source_dir, data_dir, local_snapshot=False):
    """Resolve the same input version that the geographic Silver command verifies."""
    rules = rules_identity()
    contract, _ = contract_and_codes(rules["inputs_sha256"])
    inventory = source_inventory(source_dir, contract, local_snapshot)
    snapshot_signature = digest_json(identity(inventory))
    bronze_sig = digest_json({
        "source_snapshot_signature": snapshot_signature, "bronze_format_version": BRONZE_FORMAT_VERSION,
    })
    batch_id = bronze_sig[:20]
    bronze_manifest = data_dir / BRONZE_DIR / batch_id / "manifest.json"
    silver_sig = digest_json({"rules": rules, "bronze_manifest_sha256": sha256_file(bronze_manifest)})
    return data_dir / SILVER_DIR / batch_id / silver_sig[:20]


def read_named_parquet(directory, name, columns):
    return pq.read_table(directory / name, columns=columns).to_pandas()


def date_catalog(start, end):
    # 월·연도의 달력 구간과 실제 관측 구간을 함께 만든다.
    periods = []
    for grain in ("MONTH", "YEAR"):
        current = date(start.year, start.month if grain == "MONTH" else 1, 1)
        while current <= end:
            if grain == "MONTH":
                last = current.replace(day=calendar.monthrange(current.year, current.month)[1])
            else:
                last = date(current.year, 12, 31)
            periods.append((grain, current, last, max(start, current), min(end, last),
                            current < start or last > end))
            if last >= end:
                break
            current = last + timedelta(days=1)
    return pd.DataFrame.from_records(periods, columns=[name for name, _ in PERIOD_SCHEMA])


def era_catalog(periods):
    # 2018년 집계는 위반 절차 변경일을 기준으로 분모 구간을 나눈다.
    eras = (
        (None, date.min, SOURCE_START - timedelta(days=1)),
        (PRE_CHANGE, SOURCE_START, PROCEDURE_CHANGE - timedelta(days=1)),
        (FROM_CHANGE, PROCEDURE_CHANGE, date.max),
    )
    rows = []
    for period in periods.itertuples(index=False):
        for code, era_start, era_end in eras:
            start = max(period.covered_start_dtm, era_start)
            end = min(period.covered_end_dtm, era_end)
            if start <= end:
                rows.append((period.period_grain_cd, period.period_start_dtm, code, start, end))
    return pd.DataFrame.from_records(rows, columns=PERIOD_KEYS + [name for name, _ in ERA_SCHEMA])


def area_catalog(silver_dir, inspections, area_filter):
    fields = ["community_area_num", "community_area_name", "boundary_version"]
    areas = read_named_parquet(silver_dir, "community_areas.parquet", fields)
    check(len(areas) == 77 and set(areas["community_area_num"]) == set(range(1, 78)),
          "Community Area reference must contain every area 1–77")
    versions = areas["boundary_version"].unique()
    check(len(versions) == 1 and pd.notna(versions[0]), "Community Area reference has mixed boundary versions")
    version = versions[0]
    check(bool(inspections["boundary_version"].eq(version).fillna(False).all()),
          "Inspection boundary version differs from the area reference")
    statuses = inspections["community_area_match_status"]
    region = inspections["community_area_num"]
    check(bool(statuses.isin(ALL_AREA_STATUSES).all()) and
          bool(region.notna().eq(statuses.eq("unique_area")).all()) and
          bool(region.dropna().isin(areas["community_area_num"]).all()),
          "Inspection area status and assigned number disagree")

    areas["community_area_match_status"] = "unique_area"
    if area_filter is not None:
        areas = areas.loc[areas["community_area_num"].eq(area_filter)].copy()
    else:
        pending = pd.DataFrame({
            "community_area_match_status": ALL_AREA_STATUSES[1:],
            "community_area_num": pd.array([None] * 4, dtype="Int64"),
            "community_area_name": pd.array([None] * 4, dtype="string"),
            "boundary_version": version,
        })
        areas = pd.concat([areas, pending], ignore_index=True)
    areas["community_area_num"] = areas["community_area_num"].astype("Int64")
    return areas


def prepare_inspections(silver_dir, inspections, scope):
    inspections["community_area_num"] = inspections["community_area_num"].astype("Int64")
    check(bool(inspections["inspection_key"].notna().all()) and not inspections["inspection_key"].duplicated().any(),
          "Silver inspection keys must be present and unique")
    areas = area_catalog(silver_dir, inspections, scope["community_area_num"])

    status = inspections["evaluation_status_cd"]
    evaluated = inspections["evaluated_flag"]
    failed = inspections["failed_flag"]
    check(bool(status.isin(["EVALUATED", "NOT_EVALUATED", "UNKNOWN_RESULT"]).all()) and
          bool(evaluated.notna().all()) and bool(failed.notna().all()) and
          bool(evaluated.eq(status.eq("EVALUATED")).all()) and
          bool(failed.eq(inspections["result_cd"].eq("FAIL").fillna(False)).all()) and
          not bool((failed & ~evaluated).any()), "Silver evaluation status and flags disagree")
    observation = inspections["violation_observation_status"]
    ready = inspections["violation_code_occurrence_ready"]
    check(bool(observation.isin(OBSERVATION_STATES).all()) and bool(ready.notna().all()) and
          not bool((ready & ~observation.isin(["parsed", "partial"])).any()),
          "Silver violation readiness and observation status disagree")

    dates = inspections["inspection_dtm"].dropna()
    check(not dates.empty, "Silver contains no dated inspections")
    observed_start, observed_end = dates.min(), dates.max()
    start = max(observed_start, scope["start_date"] or observed_start)
    end = min(observed_end, scope["end_date"] or observed_end)
    check(start <= end, "Requested date window does not overlap the dated Silver snapshot")
    matching_scope = pd.Series(True, index=inspections.index)
    for field in FILTER_FIELDS:
        value = scope[field]
        if value is not None:
            matching_scope &= inspections[field].eq(value).fillna(False)
    undated = matching_scope & inspections["inspection_dtm"].isna()
    within_dates = inspections["inspection_dtm"].between(start, end)
    selected = inspections.loc[matching_scope & within_dates].copy()
    disposition = {
        "input_inspection_count": len(inspections), "included_inspection_count": len(selected),
        "excluded_by_category_or_area_count": int((~matching_scope).sum()),
        "excluded_undated_count": int(undated.sum()),
        "excluded_outside_date_window_count": int((matching_scope & ~within_dates & ~undated).sum()),
        "silver_first_observed_date": observed_start.isoformat(), "silver_last_observed_date": observed_end.isoformat(),
        "covered_start_date": start.isoformat(), "covered_end_date": end.isoformat(),
    }
    check(disposition["input_inspection_count"] == sum(disposition[name] for name in (
        "included_inspection_count", "excluded_by_category_or_area_count", "excluded_undated_count",
        "excluded_outside_date_window_count",
    )), "The selected scope does not reconcile to Silver")
    return selected, areas, date_catalog(start, end), disposition


def inspection_measures(inspection):
    observation = inspection["violation_observation_status"]
    evaluated = inspection["evaluated_flag"]
    status = inspection["evaluation_status_cd"]
    return inspection.assign(
        inspection_count=1,
        evaluated_count=evaluated.astype("int64"), failed_count=inspection["failed_flag"].astype("int64"),
        not_evaluated_count=status.eq("NOT_EVALUATED").astype("int64"),
        unknown_result_count=status.eq("UNKNOWN_RESULT").astype("int64"),
        violation_missing_count=(evaluated & observation.eq("raw_missing")).astype("int64"),
        violation_recorded_count=(evaluated & ~observation.eq("raw_missing")).astype("int64"),
        violation_code_ready_count=(evaluated & inspection["violation_code_occurrence_ready"]).astype("int64"),
        violation_parsed_count=(evaluated & observation.eq("parsed")).astype("int64"),
        violation_partial_count=(evaluated & observation.eq("partial")).astype("int64"),
        violation_unrecognized_count=(evaluated & observation.eq("unrecognized")).astype("int64"),
    )


def period_rows(frame):
    frame = frame.reset_index(drop=True)
    dates = frame["inspection_dtm"]
    observed = dates.unique()
    per_month = dates.map({day: day.replace(day=1) for day in observed})
    per_year = dates.map({day: day.replace(month=1, day=1) for day in observed})
    return pd.concat([
        frame.assign(period_grain_cd="MONTH", period_start_dtm=per_month),
        frame.assign(period_grain_cd="YEAR", period_start_dtm=per_year),
    ], ignore_index=True)


def zero_filled_rollup(grid, counts, keys, measures):
    # 기준 격자를 유지해 점검이 없었던 지역·기간도 0건으로 나타낸다.
    check(bool(counts.merge(grid[keys], on=keys, how="left", indicator=True, validate="one_to_one")
               ["_merge"].eq("both").all()), "Observed group falls outside the Gold area or period grid")
    output = grid.merge(counts, on=keys, how="left", validate="one_to_one")
    for measure in measures:
        output[measure] = output[measure].fillna(0).astype("int64")
    return output


def ratio(numerator, denominator):
    return numerator.div(denominator.where(denominator.gt(0)))


def rollup_inspections(inspection, areas, periods):
    keys = PERIOD_KEYS + AREA_KEYS
    rows = period_rows(inspection)
    grid = periods.merge(areas, how="cross")
    totals = rows.groupby(keys, dropna=False)[INSPECTION_METRICS].sum().reset_index()
    result = zero_filled_rollup(grid, totals, keys, INSPECTION_METRICS)
    result["failure_rate"] = ratio(result["failed_count"], result["evaluated_count"])
    check(bool(result["inspection_count"].eq(
        result[["evaluated_count", "not_evaluated_count", "unknown_result_count"]].sum(axis=1)
    ).all()) and bool(result["failed_count"].le(result["evaluated_count"]).all()),
          "Inspection counts or failure rate denominator do not reconcile")

    coverage_keys = keys + ERA_KEYS
    coverage_totals = rows.groupby(coverage_keys, dropna=False)[COVERAGE_METRICS].sum().reset_index()
    coverage_grid = grid.merge(era_catalog(periods), on=PERIOD_KEYS, how="inner", validate="many_to_many")
    coverage = zero_filled_rollup(coverage_grid, coverage_totals, coverage_keys, COVERAGE_METRICS)
    check(bool(coverage["evaluated_count"].eq(coverage["violation_recorded_count"] +
                                             coverage["violation_missing_count"]).all()) and
          bool(coverage["violation_recorded_count"].eq(coverage[[
              "violation_parsed_count", "violation_partial_count", "violation_unrecognized_count",
          ]].sum(axis=1)).all()) and
          bool(coverage["violation_code_ready_count"].le(coverage["violation_recorded_count"]).all()),
          "Violation observation coverage counts do not reconcile")
    coverage["violation_recorded_rate"] = ratio(coverage["violation_recorded_count"], coverage["evaluated_count"])
    recombined = coverage.groupby(keys, dropna=False)["evaluated_count"].sum().reset_index()
    compared = result[keys + ["evaluated_count"]].merge(
        recombined, on=keys, how="left", validate="one_to_one", suffixes=("", "_coverage"),
    )
    check(bool(compared["evaluated_count"].eq(compared["evaluated_count_coverage"]).all()),
          "Era and inspection denominators differ")
    return result, coverage


def rollup_codes(codes, inspection, coverage):
    # 평가 점검에 기록된 고유 코드 건수를 집계한 뒤 관측 범위의 분모를 붙인다.
    keys = PERIOD_KEYS + AREA_KEYS + ERA_KEYS
    eligible = inspection.loc[inspection["evaluated_flag"], [
        "inspection_key", "inspection_dtm", *AREA_KEYS, *ERA_KEYS, "violation_code_occurrence_ready",
    ]]
    joined = codes.merge(eligible, on="inspection_key", how="inner", validate="many_to_one", suffixes=("", "_inspection"))
    code_key = ["inspection_key", *ERA_KEYS, "violation_cd"]
    era = joined["code_system_version"]
    check(bool(era.notna().all()) and bool(era.eq(joined["code_system_version_inspection"]).fillna(False).all())
          and bool(joined["violation_code_occurrence_ready"].all())
          and bool(joined["violation_cd"].notna().all()) and not joined.duplicated(code_key).any(),
          "Evaluated violation rows do not match a unique code-ready inspection and procedure era")
    check(set(joined["inspection_key"]) == set(eligible.loc[eligible["violation_code_occurrence_ready"], "inspection_key"]),
          "Code-ready evaluated inspection has no violation code occurrence")

    label_key = [*ERA_KEYS, "violation_cd"]
    descriptions = joined.groupby([*label_key, "description_text"], dropna=False).size().reset_index(name="row_count")
    descriptions["description_variant_count"] = descriptions.groupby(label_key)["description_text"].transform("count")
    descriptions["has_description"] = descriptions["description_text"].notna()
    labels = descriptions.sort_values([*label_key, "has_description", "row_count", "description_text"],
                                      ascending=[True, True, False, False, True])
    labels = labels.drop_duplicates(label_key).rename(columns={"description_text": "violation_description_text"})

    fact = period_rows(joined)
    code_counts = fact.groupby([*keys, "violation_cd"], dropna=False).size().reset_index(name="code_inspection_count")
    result = code_counts.merge(coverage.drop(columns=["violation_recorded_rate"]), on=keys,
                               how="left", validate="many_to_one", indicator=True)
    check(bool(result["_merge"].eq("both").all()) and
          bool(result["code_inspection_count"].le(result["violation_code_ready_count"]).all()),
          "Violation code count exceeds its code-ready denominator or misses the coverage grain")
    result = result.drop(columns=["_merge"]).merge(
        labels[label_key + ["violation_description_text", "description_variant_count"]],
        on=label_key, how="left", validate="many_to_one",
    )
    result["code_recorded_rate"] = ratio(result["code_inspection_count"], result["evaluated_count"])
    result["code_recorded_among_ready_rate"] = ratio(
        result["code_inspection_count"], result["violation_code_ready_count"],
    )
    return result, joined


def verify_counts(inspection, totals, coverage, codes, joined):
    # 월·연도별 합계를 각각 입력 점검 및 위반 기록과 대조한다.
    expected_violations = joined.groupby("code_system_version").size().to_dict()
    for grain in ("MONTH", "YEAR"):
        summarized = totals.loc[totals["period_grain_cd"].eq(grain), INSPECTION_METRICS].sum().to_dict()
        expected = {name: int(inspection[name].sum()) for name in INSPECTION_METRICS}
        check(summarized == expected, f"{grain}: Gold inspection counts differ from selected Silver")
        summarized_coverage = coverage.loc[coverage["period_grain_cd"].eq(grain), COVERAGE_METRICS].sum().to_dict()
        expected_coverage = {name: int(inspection[name].sum()) for name in COVERAGE_METRICS}
        check(summarized_coverage == expected_coverage, f"{grain}: Gold coverage counts differ from selected Silver")
        summarized_codes = codes.loc[codes["period_grain_cd"].eq(grain)].groupby(
            "code_system_version"
        )["code_inspection_count"].sum().to_dict()
        check(summarized_codes == expected_violations, f"{grain}: Gold code counts differ from selected Silver")


def write_output(path, frame, fields, keys):
    schema = pa.schema(fields)
    check(not frame.duplicated(keys).any(), f"{path.name}: duplicate Gold keys")
    if frame.empty:
        table = pa.Table.from_batches([], schema=schema)
    else:
        ordered = frame.sort_values(keys, na_position="last", ignore_index=True)
        table = pa.Table.from_pandas(ordered, schema=schema, preserve_index=False).replace_schema_metadata(None)
    write_table(path, table)


def build(directory, silver_dir, source, settings, signature, shared_inputs):
    geography = read_named_parquet(silver_dir, "inspection_geography.parquet", INSPECTION_COLUMNS)
    if shared_inputs:
        geography, violation_codes = load_shared_inputs(silver_dir, geography, shared_inputs)
    else:
        violation_codes = read_named_parquet(silver_dir, "inspection_violation_codes.parquet",
                                            ["inspection_key", *ERA_KEYS, "violation_cd", "description_text"])
    inspection, areas, periods, disposition = prepare_inspections(silver_dir, geography, settings)
    inspection = inspection_measures(inspection)
    totals, coverage = rollup_inspections(inspection, areas, periods)
    codes, joined = rollup_codes(violation_codes, inspection, coverage)
    verify_counts(inspection, totals, coverage, codes, joined)

    base = PERIOD_SCHEMA + AREA_SCHEMA
    totals_fields = base + [(name, pa.int64()) for name in INSPECTION_METRICS] + [("failure_rate", pa.float64())]
    coverage_fields = (base + ERA_SCHEMA + [(name, pa.int64()) for name in COVERAGE_METRICS] +
                       [("violation_recorded_rate", pa.float64())])
    period_area_key = PERIOD_KEYS + AREA_KEYS
    write_output(directory / "inspection_area_period.parquet", totals, totals_fields, period_area_key)
    write_output(directory / "violation_coverage_area_period.parquet", coverage, coverage_fields,
                 period_area_key + ERA_KEYS)
    write_output(directory / "violation_area_period.parquet", codes, base + ERA_SCHEMA + CODE_SCHEMA,
                 period_area_key + ERA_KEYS + ["violation_cd"])

    summary = {
        "scope_check": disposition,
        "inspection": {metric: int(inspection[metric].sum()) for metric in INSPECTION_METRICS},
        "spatial_status_counts": inspection["community_area_match_status"].value_counts().to_dict(),
        "violation_coverage": {metric: int(inspection[metric].sum()) for metric in COVERAGE_METRICS},
        "evaluated_inspection_code_rows_by_era": joined.groupby("code_system_version").size().to_dict(),
        "periods": periods.groupby("period_grain_cd").size().to_dict(),
        "partial_periods": [f"{row.period_grain_cd} {row.period_start_dtm}" for row in
                            periods.loc[periods["partial_period_flag"]].itertuples(index=False)],
        "area_catalog_rows": len(areas), "validated_against_selected_silver": True,
    }
    write_json(directory / "metrics_summary.json", summary)
    verify_artifacts(silver_dir, "silver", source["silver_rules_signature"], SILVER_ARTIFACTS, source["batch_id"])
    check(sha256_file(silver_dir / "manifest.json") == source["silver_manifest_sha256"],
          "Silver manifest changed while building Gold")
    check(source_code_hashes() == source["gold_source_code_sha256"], "Gold code changed while building")
    check(shared_fingerprints(shared_inputs) == source["shared_inputs"], "01/02 inputs changed while building Gold")
    return {
        "layer": "gold", "batch_id": source["batch_id"], "gold_id": signature[:20],
        "rules_signature": signature, "built_at_utc": utc_now().isoformat(), **source,
    }


def run(action, silver_dir, data_dir, scope, shared_inputs):
    manifest_path = silver_dir / "manifest.json"
    silver_hash = sha256_file(manifest_path)
    manifest = read_json(manifest_path)
    batch_id = manifest["batch_id"]
    verify_artifacts(silver_dir, "silver", manifest["rules_signature"], SILVER_ARTIFACTS, batch_id)
    check(sha256_file(manifest_path) == silver_hash, "Silver manifest changed during verification")

    source_mode = manifest.get("source_mode")
    check(source_mode in {"local", "team"}, "Build Silver with the current team integration contract first")
    check(source_mode == "local" or shared_inputs,
          "Team Gold requires --inspection-silver and --shared-violations-dir")
    source = {
        "batch_id": batch_id, "silver_rules_id": manifest["rules_id"], "silver_manifest_sha256": silver_hash,
        "silver_rules_signature": manifest["rules_signature"], "gold_source_code_sha256": source_code_hashes(),
        "source_mode": source_mode, "shared_inputs": shared_fingerprints(shared_inputs),
        "runtime": {"python": platform.python_version(), "pandas": pd.__version__, "pyarrow": pa.__version__},
        "scope": {name: value.isoformat() if isinstance(value, date) else value for name, value in scope.items()},
    }
    signature = digest_json(source)
    gold_dir = data_dir / GOLD_DIR / batch_id / signature[:20]
    if action == "verify":
        outcome = verify_artifacts(gold_dir, "gold", signature, GOLD_ARTIFACTS, batch_id)
        status = "verified existing"
    else:
        outcome, status = publish(gold_dir, "gold", signature, GOLD_ARTIFACTS,
                                  lambda path: build(path, silver_dir, source, scope, signature, shared_inputs), batch_id)
    check(outcome["silver_manifest_sha256"] == silver_hash, "Gold links to a different Silver version")
    print(f"Gold {status}: {gold_dir}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("build", "verify"))
    parser.add_argument("--silver-dir", type=Path, help="Use this published Silver folder instead of the current batch")
    parser.add_argument("--source-dir", type=Path)
    parser.add_argument("--local-snapshot", action="store_true", help="Use the local 05 CSVs for comparison")
    parser.add_argument("--inspection-silver", type=Path, help="Shared 01 inspection Silver Parquet")
    parser.add_argument("--shared-violations-dir", type=Path, help="Directory containing the two shared 02 Parquets")
    parser.add_argument("--data-dir", type=Path, default=PROJECT / "data")
    parser.add_argument("--start-date", type=date.fromisoformat)
    parser.add_argument("--end-date", type=date.fromisoformat)
    parser.add_argument("--facility-type", help="Exact Silver facility_type value")
    parser.add_argument("--inspection-type", help="Exact Silver inspection_type value")
    parser.add_argument("--risk-level-cd", help="Exact Silver risk_level_cd value")
    parser.add_argument("--community-area-num", type=int, choices=range(1, 78), metavar="1–77")
    args = parser.parse_args()
    data_dir = args.data_dir.resolve()
    if bool(args.inspection_silver) != bool(args.shared_violations_dir):
        parser.error("--inspection-silver and --shared-violations-dir must be supplied together")
    shared_inputs = shared_files(args.inspection_silver, args.shared_violations_dir) if args.inspection_silver else {}
    source_dir = args.source_dir or (LOCAL_SOURCE_DIR if args.local_snapshot else SOURCE_DIR)
    silver_dir = (args.silver_dir.resolve() if args.silver_dir else
                  current_silver_dir(source_dir.resolve(), data_dir, args.local_snapshot))
    scope = {name: getattr(args, name) for name in ("start_date", "end_date", *FILTER_FIELDS)}
    run(args.action, silver_dir, data_dir, scope, shared_inputs)


if __name__ == "__main__":
    main()
