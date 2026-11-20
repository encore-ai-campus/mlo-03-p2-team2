"""Preserve source inspection records and provenance."""

from datetime import datetime, timezone

import pandas as pd

from common import BRONZE, COLUMNS, ROOT, SOURCE, TABLE, digest, write_table


def transform(_data, output, _metadata):
    source = ROOT / SOURCE
    if not source.is_file():
        raise FileNotFoundError(f"{source} is missing. Run python src/ingestion/restore_origin.py --restore")
    output = output / BRONZE
    output.mkdir(parents=True)
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
    from runner import ROOT, run_stage

    run_stage(ROOT, 0)
