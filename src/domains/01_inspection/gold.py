"""Build the inspection star schema and performance aggregates."""

import pandas as pd
import pyarrow as pa

from common import DECISIONS, GRAIN, MIN_DECISIONS, write_table


def summarize(frame, group):
    summary = frame.groupby(group, dropna=False, sort=True).agg(
        inspection_count_num=("inspection_count_num", "sum"),
        decision_count_num=("decision_count_num", "sum"),
        pass_count_num=("pass_count_num", "sum"),
        conditional_pass_count_num=("conditional_pass_count_num", "sum"),
        fail_count_num=("fail_count_num", "sum"),
    ).reset_index()
    summary["other_result_count_num"] = summary["inspection_count_num"] - summary["decision_count_num"]
    denominator = summary["decision_count_num"].where(summary["decision_count_num"].gt(0))
    summary["failure_rate"] = summary["fail_count_num"] / denominator
    return summary


def build_gold(selected, output):
    analysis = output / "analysis"
    schema = analysis / "star_schema"
    schema.mkdir(parents=True)
    if not selected["inspection_key"].is_unique:
        raise ValueError("Gold inspection keys must be unique")
    if selected.empty:
        raise ValueError("No inspections passed quality checks")
    fact = selected[["inspection_key", "source_row_num", "inspection_dtm", "license_number_key"]].copy()
    for name in ("facility_type", "inspection_type", "risk_level_cd", "result_cd"):
        key = f"{name}_key"
        values = selected[name].astype("string")
        # Value-based keys stay stable across source refreshes.
        fact[key] = ("value:" + values).fillna("__unknown__")
        dimension = pd.DataFrame({key: fact[key], name: values}).drop_duplicates().sort_values(key)
        if not dimension[key].is_unique or not fact[key].isin(dimension[key]).all():
            raise ValueError(f"Invalid dimension references for {name}")
        write_table(dimension, schema / f"dim_{name.removesuffix('_cd')}.parquet")
    dates = pd.to_datetime(selected["inspection_dtm"])
    start, end = dates.min(), dates.max()
    calendar = pd.DataFrame({"inspection_dtm": pd.date_range(start, end)})
    calendar["inspection_year_num"] = calendar["inspection_dtm"].dt.year
    calendar["inspection_month_num"] = calendar["inspection_dtm"].dt.month
    calendar["inspection_dtm"] = calendar["inspection_dtm"].astype(pd.ArrowDtype(pa.date32()))
    if not fact["inspection_dtm"].isin(calendar["inspection_dtm"]).all():
        raise ValueError("Invalid inspection date reference")
    write_table(calendar, schema / "dim_date.parquet")
    fact["inspection_count_num"] = 1
    for code, name in zip(DECISIONS, ("pass", "conditional_pass", "fail"), strict=True):
        fact[f"{name}_count_num"] = selected["result_cd"].eq(code).fillna(False).astype("int64")
    fact["decision_count_num"] = fact[["pass_count_num", "conditional_pass_count_num", "fail_count_num"]].sum(axis=1)
    write_table(fact, schema / "fact_inspection.parquet")

    metrics = fact.assign(
        inspection_year_num=pd.to_datetime(fact["inspection_dtm"]).dt.year,
        inspection_month_num=pd.to_datetime(fact["inspection_dtm"]).dt.month,
        risk_level_cd=selected["risk_level_cd"].fillna("__unknown__"),
    )
    for name in ("facility_type", "inspection_type"):
        metrics[name] = selected[name].str.replace(r"\s+", " ", regex=True).str.upper().fillna("__unknown__")

    month = ["inspection_year_num", "inspection_month_num"]
    facility, inspection, risk = "facility_type", "inspection_type", "risk_level_cd"
    grains = {
        "year": month[:1], "month": month, "facility": [facility],
        "inspection_type": [inspection], "risk": [risk], "facility_inspection": [facility, inspection],
        "month_facility_inspection_risk": GRAIN,
    }
    for name, grain in grains.items():
        summary = summarize(metrics, grain)
        if summary["inspection_count_num"].sum() != len(fact) or summary["fail_count_num"].sum() != fact["fail_count_num"].sum():
            raise ValueError(f"Aggregate reconciliation failed for {name}")
        summary.to_csv(analysis / f"performance_by_{name}.csv", index=False)
        if name == "month_facility_inspection_risk":
            write_table(summary, output / "performance_detail.parquet")
        if name in ("facility", "inspection_type", "facility_inspection"):
            ranking = summary.loc[
                summary["decision_count_num"].ge(MIN_DECISIONS)
                & summary[grain].ne("__unknown__").all(axis=1)
            ].sort_values(["failure_rate", "decision_count_num", *grain], ascending=[False, False] + [True] * len(grain))
            ranking.to_csv(analysis / f"failure_ranking_by_{name}.csv", index=False)
    return {"reporting_start_inclusive": start.date().isoformat(),
            "reporting_end_inclusive": end.date().isoformat(),
            "gold_rows": len(fact), "decision_rows": int(fact["decision_count_num"].sum())}


def transform(data, output, metadata):
    selected = pd.read_parquet(data / "silver/validated_inspections.parquet")
    if metadata["source_rows"] != len(selected) + metadata["excluded_quality_rows"]:
        raise ValueError("Source-to-Gold reconciliation failed")
    return build_gold(selected, output)


if __name__ == "__main__":
    from runner import DATA, run_stage

    run_stage(DATA, 3)
