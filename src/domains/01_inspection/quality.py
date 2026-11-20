"""Report quality issues and select eligible inspection records."""

import pandas as pd

from common import TABLE, write_table


REJECT_RULES = ["exact_duplicate", "conflicting_inspection_key", "invalid_inspection_key", "invalid_inspection_date"]


def transform(data, output, _metadata):
    clean = pd.read_parquet(data / "silver" / TABLE)
    flags = pd.read_parquet(data / "silver/inspection_rule_flags.parquet")
    if not clean["source_row_num"].equals(flags.pop("source_row_num")):
        raise ValueError("Quality flags do not align with Silver")
    exceptions = pd.concat([
        clean.loc[flags[rule], ["source_row_num", "inspection_key"]].assign(rule_cd=rule)
        for rule in flags
    ], ignore_index=True).sort_values(["source_row_num", "rule_cd"])
    reports = output / "reports"
    reports.mkdir()
    exceptions.to_csv(reports / "inspection_quality_issues.csv", index=False)
    rejected = flags[REJECT_RULES].any(axis=1)
    write_table(clean.loc[~rejected], output / "validated_inspections.parquet")
    return {"excluded_quality_rows": int(rejected.sum()),
            "quality_rule_counts": {rule: int(flags[rule].sum()) for rule in flags}}


if __name__ == "__main__":
    from runner import DATA, run_stage

    run_stage(DATA, 2)
