"""Create the final AI Ready inspection table and its data contract."""

import pandas as pd

from common import DECISIONS, GRAIN, MIN_DECISIONS, write_table


def transform(data, output, metadata):
    summary = pd.read_parquet(data / "gold/performance_detail.parquet")
    if summary.duplicated(GRAIN).any():
        raise ValueError("AI Ready grain is not unique")
    write_table(summary, output / "inspection_performance.parquet")
    return {
        "ai_ready_rows": len(summary),
        "purpose": "Descriptive analytics and grounded Q&A on historical inspection performance",
        "grain": GRAIN,
        "period": {"start_inclusive": metadata["reporting_start_inclusive"],
                   "end_inclusive": metadata["reporting_end_inclusive"]},
        "unknown_dimension_value": "__unknown__",
        "type_normalization": "Trim, collapse whitespace and uppercase. Semantic aliases remain distinct.",
        "decision_codes": DECISIONS,
        "failure_rate": "fail_count_num / decision_count_num; null when denominator is zero",
        "rollup": "Sum numerator and denominator separately, then divide. Counts are additive.",
        "ranking_min_decisions": MIN_DECISIONS,
        "zero_denominator": None,
    }


if __name__ == "__main__":
    from runner import DATA, run_stage

    run_stage(DATA, 4)
