"""Preserve source inspection records and provenance."""

from datetime import datetime, timezone

import pandas as pd

from common import COLUMNS, DATA, ROOT, TABLE, digest, write_table


def transform(_data, output, _metadata):
    source = DATA / "origin/food_Inspections.csv"
    checksum = digest(source)
    raw = pd.read_csv(source, dtype="string", keep_default_na=False, encoding="utf-8-sig")
    if list(raw.columns) != list(COLUMNS) or raw.isna().any().any():
        raise ValueError("Inspection source does not match the documented schema")
    if checksum != digest(source):
        raise ValueError("Source changed during ingestion")
    raw["source_row_num"] = range(1, len(raw) + 1)
    write_table(raw, output / TABLE)
    return {"source": str(source.relative_to(ROOT)), "source_sha256": checksum,
            "ingested_at": datetime.now(timezone.utc).isoformat(), "source_rows": len(raw)}


if __name__ == "__main__":
    from runner import DATA, run_stage

    run_stage(DATA, 0)
