"""Create the final AI Ready inspection table and its data contract."""

import pandas as pd

from common import AI_READY, DECISIONS, GOLD, GRAIN, MIN_DECISIONS, PERFORMANCE_DETAIL, write_table


def transform(data, output, metadata):
    summary = pd.read_parquet(data / GOLD / PERFORMANCE_DETAIL)
    if summary.duplicated(GRAIN).any():
        raise ValueError("AI Ready grain is not unique")
    output = output / AI_READY
    output.mkdir(parents=True)
    write_table(summary, output / "01_inspection_performance.parquet")
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
    from runner import ROOT, run_stage

    run_stage(ROOT, 4)
