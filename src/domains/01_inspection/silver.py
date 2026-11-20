"""Standardize inspection values and record row-level rule flags."""

import csv

import pandas as pd
import pyarrow as pa

from common import COLUMNS, ROOT, TABLE, write_table


def standardize(raw):
    silver = raw.rename(columns=COLUMNS).copy()
    for name in COLUMNS.values():
        values = silver[name]
        trimmed = values.str.strip()
        silver[name] = (values if name == "violations_text" else trimmed).mask(trimmed.eq(""))
    silver["license_number_key"] = silver["license_number_key"].replace(
        {"0": None, "9999999": None}
    )
    exact = raw[list(COLUMNS)].duplicated()
    conflicts = silver["inspection_key"].where(~exact)
    issues = {
        "exact_duplicate": exact,
        "conflicting_inspection_key": silver["inspection_key"].isin(
            conflicts[conflicts.notna() & conflicts.duplicated(keep=False)]
        ),
        "invalid_inspection_key": ~silver["inspection_key"].str.fullmatch(r"[0-9]+", na=False),
    }
    dates = pd.to_datetime(silver["inspection_dtm"], format="%m/%d/%Y", errors="coerce")
    issues["invalid_inspection_date"] = dates.isna()
    silver["inspection_dtm"] = dates.astype(pd.ArrowDtype(pa.date32()))
    for name in ("latitude", "longitude"):
        parsed = pd.to_numeric(silver[name], errors="coerce")
        issues[f"invalid_{name}"] = silver[name].notna() & parsed.isna()
        silver[name] = parsed.astype("Float64")
    with (ROOT / "docs/shared_code_map.csv").open(encoding="utf-8-sig", newline="") as file:
        mappings = [row for row in csv.DictReader(file) if row["dataset"] == "food_inspections"]
    for name in ("result_cd", "risk_level_cd"):
        entries = [row for row in mappings if row["target_column"] == name]
        lookup = {row["source_value"]: row["standard_code"] for row in entries}
        values = silver[name]
        silver[name] = values.map(lookup).astype("string")
        issues[f"missing_{name}"] = values.isna()
        issues[f"unmapped_{name}"] = values.notna() & silver[name].isna()
        review = {row["source_value"] for row in entries if row["mapping_status"] == "review"}
        if review:
            issues[f"review_{name}"] = values.isin(review)
    for name in ("facility_type", "inspection_type"):
        issues[f"missing_{name}"] = silver[name].isna()
    return silver, issues


def transform(data, output, _metadata):
    raw = pd.read_parquet(data / "bronze" / TABLE)
    clean, issues = standardize(raw)
    if not raw["source_row_num"].equals(clean["source_row_num"]):
        raise ValueError("Source row preservation failed")
    write_table(clean, output / TABLE)
    write_table(pd.DataFrame(issues).assign(source_row_num=raw["source_row_num"]),
                output / "inspection_rule_flags.parquet")
    return {"silver_rows": len(clean)}


if __name__ == "__main__":
    from runner import DATA, run_stage

    run_stage(DATA, 1)
