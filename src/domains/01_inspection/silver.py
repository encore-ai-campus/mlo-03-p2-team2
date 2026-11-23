"""Standardize inspection values and record row-level rule flags."""

import pandas as pd
import pyarrow as pa

from common import BRONZE, COLUMNS, INSPECTION_FIELDS, ROOT, RULE_FLAGS, SILVER, TABLE, TRANSFORMS, write_table
from src.silver.shared_dictionary import load_shared_codes


def standardize(raw):
    silver = raw.rename(columns=COLUMNS).copy()
    for name, transform in TRANSFORMS.items():
        values = silver[name]
        trimmed = values.str.strip()
        silver[name] = (values if transform == "nonblank_original" else trimmed).mask(trimmed.eq(""))
        if transform == "inspection_license_sentinels":
            silver[name] = silver[name].replace({"0": None, "9999999": None})
    exact = raw[list(COLUMNS)].duplicated()
    conflicts = silver["inspection_key"].where(~exact)
    issues = {
        "exact_duplicate": exact,
        "conflicting_inspection_key": silver["inspection_key"].isin(
            conflicts[conflicts.notna() & conflicts.duplicated(keep=False)]
        ),
        "invalid_inspection_key": ~silver["inspection_key"].str.fullmatch(r"[0-9]+", na=False),
    }
    for name, transform in TRANSFORMS.items():
        if transform == "inspection_date":
            dates = pd.to_datetime(silver[name], format="%m/%d/%Y", errors="coerce")
            issues["invalid_inspection_date"] = dates.isna()
            silver[name] = dates.astype(pd.ArrowDtype(pa.date32()))
        elif transform == "coordinate":
            parsed = pd.to_numeric(silver[name], errors="coerce")
            issues[f"invalid_{name}"] = silver[name].notna() & parsed.isna()
            silver[name] = parsed.astype("Float64")
    maps = load_shared_codes(ROOT, {"food_inspections": INSPECTION_FIELDS})
    by_target = {target: entries for (_, _, target), entries in maps.items()}
    # Keep flag columns in the published order.
    for name, entries in sorted(by_target.items()):
        lookup = {source: row["standard_code"] for source, row in entries.items()}
        values = silver[name]
        silver[name] = values.map(lookup).astype("string")
        issues[f"missing_{name}"] = values.isna()
        issues[f"unmapped_{name}"] = values.notna() & silver[name].isna()
        review = {source for source, row in entries.items() if row["mapping_status"] == "review"}
        if review:
            issues[f"review_{name}"] = values.isin(review)
    for name in ("facility_type", "inspection_type"):
        issues[f"missing_{name}"] = silver[name].isna()
    return silver, issues


def transform(data, output, _metadata):
    raw = pd.read_parquet(data / BRONZE / TABLE)
    clean, issues = standardize(raw)
    if not raw["source_row_num"].equals(clean["source_row_num"]):
        raise ValueError("Source row preservation failed")
    output = output / SILVER
    output.mkdir(parents=True)
    write_table(clean, output / TABLE)
    write_table(pd.DataFrame(issues).assign(source_row_num=raw["source_row_num"]),
                output / RULE_FLAGS)
    return {"silver_rows": len(clean)}


if __name__ == "__main__":
    from runner import ROOT, run_stage

    run_stage(ROOT, 1)
