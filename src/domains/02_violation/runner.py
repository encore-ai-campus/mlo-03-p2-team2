"""Run Domain 02 into a fresh local directory using the existing shared Bronze."""

from datetime import datetime, timezone
import json
import os
from pathlib import Path
from tempfile import mkdtemp

import pyarrow.parquet as pq

from src.bronze.load_bronze import TECHNICAL_COLUMNS

from src.bronze.paths import PROJECT_ROOT
from . import bronze, build_analysis_mart, gold, profiling, quality, reconciliation, silver


def run(repo: Path = PROJECT_ROOT) -> Path:
    repo = repo.resolve()
    shared = repo / bronze.SHARED_BRONZE_RELATIVE
    if not shared.is_file():
        raise FileNotFoundError(f"Build or restore the shared Food Inspections Bronze first: {shared}")

    origin = profiling.origin_snapshot(repo)
    run_dir = repo / "reports/runs/02_violation"
    run_dir.mkdir(parents=True, exist_ok=True)
    root = Path(mkdtemp(prefix="lineage-", dir=run_dir))
    print(f"Domain 02 output: {root}", flush=True)

    # Use read-only input links on the same drive. Stage writers publish separate files.
    inputs = [bronze.SHARED_BRONZE_RELATIVE, *map(Path, origin["storage_files"])]
    if origin["catalog_verified"]:
        inputs.extend((profiling.ORIGIN_CHECKSUMS_RELATIVE, profiling.SOURCE_CATALOG_RELATIVE))
        local_csv = next((path for path in (profiling.ORIGIN_RELATIVE, profiling.LEGACY_ORIGIN_RELATIVE)
                          if (repo / path).is_file()), None)
        if local_csv is not None:
            inputs.append(local_csv)
    log = root / "run.json"
    started = datetime.now(timezone.utc).isoformat()
    record = {"status": "RUNNING", "started_at": started, "origin_sha256": origin["source_sha256"]}
    stage = "prepare_inputs"
    try:
        for relative in inputs:
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            os.link(repo / relative, target)

        stage = "bronze"
        projected = bronze.build(root)
        record["shared_bronze_sha256"] = profiling.sha256(root / bronze.SHARED_BRONZE_RELATIVE)
        record["domain_bronze_sha256"] = profiling.sha256(projected)
        record["source_origin_file"] = origin["source_file"]
        record["shared_bronze_file"] = str(shared)
        with pq.ParquetFile(projected) as parquet:
            batch = next(parquet.iter_batches(batch_size=1, columns=list(TECHNICAL_COLUMNS)))
            record["bronze_lineage"] = batch.to_pylist()[0]
        stage = "profiling"
        profile = profiling.profile_violations(root)
        profile_path = root / profiling.OUTPUT_RELATIVE
        profile_path.parent.mkdir(parents=True, exist_ok=True)
        profile_path.write_text(json.dumps(profile, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        stage = "silver"
        silver.run(root)
        stage = "quality"
        quality_report = quality.run(root)
        if quality_report["status"] != "PASS":
            raise ValueError("Silver quality checks failed")
        stage = "reconciliation"
        record["counts"] = reconciliation.run(root)["counts"]
        stage = "gold"
        gold.build(root)
        stage = "analysis_mart"
        build_analysis_mart.build(root)
        record["status"] = "PASS"
        return root
    except Exception as exc:
        record.update(status="FAIL", failed_stage=stage, error=str(exc))
        raise
    finally:
        record["finished_at"] = datetime.now(timezone.utc).isoformat()
        log.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    run()
