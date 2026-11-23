"""Run Domain 02 using the shared Food Inspections Bronze."""

from argparse import ArgumentParser
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from tempfile import mkdtemp

import pyarrow.parquet as pq

from src.bronze.load_bronze import TECHNICAL_COLUMNS

from src.bronze.paths import PROJECT_ROOT
from . import bronze, build_analysis_mart, gold, profiling, quality, reconciliation, silver


RUN_RELATIVE = Path("reports/runs/02_violation/run.json")


def _link_legacy_inputs(repo: Path, root: Path, origin: dict) -> None:
    inputs = [bronze.SHARED_BRONZE_RELATIVE, *map(Path, origin["storage_files"])]
    if origin["catalog_verified"]:
        inputs.extend((profiling.ORIGIN_CHECKSUMS_RELATIVE, profiling.SOURCE_CATALOG_RELATIVE))
        local_csv = next((path for path in (profiling.ORIGIN_RELATIVE, profiling.LEGACY_ORIGIN_RELATIVE)
                          if (repo / path).is_file()), None)
        if local_csv is not None:
            inputs.append(local_csv)
    for relative in inputs:
        source = repo / relative
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.link(source, target)
        except FileExistsError:
            if not target.samefile(source):
                raise


def run(
    repo: Path = PROJECT_ROOT, *, registry_path: Path | None = None,
    shared_bronze: Path | None = None, output_root: Path | None = None,
) -> Path:
    repo = Path(repo).resolve()
    shared = Path(shared_bronze).resolve() if shared_bronze is not None else repo / bronze.SHARED_BRONZE_RELATIVE
    if not shared.is_file():
        raise FileNotFoundError(f"Build or restore the shared Food Inspections Bronze first: {shared}")

    origin = profiling.origin_snapshot(repo)
    if output_root is None:
        run_dir = repo / RUN_RELATIVE.parent
        run_dir.mkdir(parents=True, exist_ok=True)
        root = Path(mkdtemp(prefix="lineage-", dir=run_dir))
        log = root / "run.json"
    else:
        root = Path(output_root).resolve()
        log = root / RUN_RELATIVE
        log.parent.mkdir(parents=True, exist_ok=True)
    print(f"Domain 02 output: {root}", flush=True)
    started = datetime.now(timezone.utc).isoformat()
    record = {"status": "RUNNING", "started_at": started, "origin_sha256": origin["source_sha256"]}
    stage = "prepare_inputs"
    try:
        source_options = {}
        if shared_bronze is None:
            _link_legacy_inputs(repo, root, origin)
        stage = "bronze"
        if shared_bronze is None:
            input_bronze = bronze.build(root)
            record["shared_bronze_sha256"] = profiling.sha256(root / bronze.SHARED_BRONZE_RELATIVE)
            record["domain_bronze_sha256"] = profiling.sha256(input_bronze)
        else:
            input_bronze = shared
            record["shared_bronze_sha256"] = bronze.validate_shared(repo, shared, origin)
            source_options = {"bronze_path": shared, "origin_root": repo}
        record["source_origin_file"] = origin["source_file"]
        record["shared_bronze_file"] = (str(shared) if shared_bronze is None
                                         else profiling.bronze_reference(root, shared))
        with pq.ParquetFile(input_bronze) as parquet:
            batch = next(parquet.iter_batches(batch_size=1, columns=list(TECHNICAL_COLUMNS)))
            record["bronze_lineage"] = batch.to_pylist()[0]
        stage = "profiling"
        profile = profiling.profile_violations(root, **source_options)
        profile_path = root / profiling.OUTPUT_RELATIVE
        profile_path.parent.mkdir(parents=True, exist_ok=True)
        profile_path.write_text(json.dumps(profile, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        stage = "silver"
        silver.run(root, **source_options)
        stage = "quality"
        quality_report = quality.run(root, **source_options)
        if quality_report["status"] != "PASS":
            raise ValueError("Silver quality checks failed")
        stage = "reconciliation"
        record["counts"] = reconciliation.run(root, **source_options)["counts"]
        stage = "gold"
        gold_report = gold.build(root, registry_path=registry_path or repo / gold.REGISTRY_RELATIVE)
        record["violation_key_registry"] = gold_report["violation_key_registry"]
        stage = "analysis_mart"
        build_analysis_mart.build(root, **source_options)
        if shared_bronze is not None:
            stage = "verify_inputs"
            if (profiling.sha256(shared) != record["shared_bronze_sha256"]
                    or profiling.origin_snapshot(repo)["guard_sha256"] != origin["guard_sha256"]):
                raise ValueError("Origin or shared Bronze changed during the run")
        record["status"] = "PASS"
        return root
    except Exception as exc:
        record.update(status="FAIL", failed_stage=stage, error=str(exc))
        raise
    finally:
        record["finished_at"] = datetime.now(timezone.utc).isoformat()
        log.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, help="Persistent Domain 02 violation key CSV")
    parser.add_argument("--shared-bronze", type=Path, help="Domain 06 Food Inspections Bronze")
    parser.add_argument("--output-root", type=Path, help="Destination for Domain 02 artifacts")
    args = parser.parse_args()
    run(registry_path=args.registry, shared_bronze=args.shared_bronze, output_root=args.output_root)
