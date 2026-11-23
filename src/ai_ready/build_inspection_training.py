"""Build or verify a release of both point-in-time inspection datasets."""

import argparse
from collections import Counter, defaultdict
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import pyarrow as pa
import pyarrow.parquet as pq

from src.ai_ready import inspection_training as training
from src.bronze.paths import PROJECT_ROOT


OUTPUT = Path("data/ai_ready/inspection_training")
CONTRACT = Path("metadata/feature_dictionary/inspection_training/contract.json")
INSPECTIONS = Path("data/02_silver/04_license/04_food_inspections.parquet")
VIOLATIONS = Path("data/03_gold/02_violation/02_violations_analysis_mart.parquet")
QUARANTINE = Path("data/02_silver/02_violation/02_inspection_violations_quarantine.parquet")
RECURRENCE = Path("data/03_gold/03_repeat_inspection/03_repeat_violation_mart.parquet")
RECONCILIATION = Path("reports/quality/violations_reconciliation.json")
ORIGIN_03 = Path("metadata/lineage/03_repeat_inspection/bronze_manifest.json")
ORIGIN_04 = Path("metadata/lineage/04_license/bronze_manifest.json")
CHECKSUMS = {
    Path("reports/02_violation/parquet_sha256sums.txt"): (VIOLATIONS, QUARANTINE),
    Path("reports/03_repeat_inspection/parquet_sha256sums.txt"): (RECURRENCE,),
    Path("reports/04_license/parquet_sha256sums.txt"): (INSPECTIONS,),
}
SUMMARY = "validation_summary.json"
MANIFEST = "manifest.json"
BATCH_SIZE = 16_384


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def parquet_rows(path, columns=None):
    with pq.ParquetFile(path) as parquet:
        for batch in parquet.iter_batches(batch_size=BATCH_SIZE, columns=columns):
            yield from batch.to_pylist()


def verify_sources(root):
    evidence = (CONTRACT, RECONCILIATION, ORIGIN_03, ORIGIN_04, *CHECKSUMS)
    source_digests = {path.as_posix(): sha256(root / path) for path in evidence}
    for checksums, files in CHECKSUMS.items():
        lines = (root / checksums).read_text(encoding="ascii").splitlines()
        entries = (line.split(maxsplit=1) for line in lines if line.strip())
        manifest = {path: digest for digest, path in entries}
        for path in files:
            digest = sha256(root / path)
            if digest != manifest.get(path.as_posix()):
                raise ValueError(f"Published Parquet SHA-256 mismatch: {path}")
            source_digests[path.as_posix()] = digest

    report = read_json(root / RECONCILIATION)
    if report["status"] != "PASS" or any(report["issues"].values()):
        raise ValueError("Published 02 violation reconciliation did not pass")
    origin03 = read_json(root / ORIGIN_03)
    origin04, = (entry for entry in read_json(root / ORIGIN_04)["entries"]
                 if entry["table"] == "food_inspections")
    source_sha = origin04["source_sha256"]
    recurrence_metadata = pq.read_metadata(root / RECURRENCE).metadata
    if (source_sha != origin03["sha256"] or source_sha != report["origin_sha256"]
            or source_sha.encode("ascii") != recurrence_metadata.get(b"source_sha256")
            or recurrence_metadata.get(b"violation_source") != b"domain02"):
        raise ValueError("Published inputs must share an inspection source with Domain 02-based labels")

    expected_inspections = origin04["row_count"]
    counts = report["counts"]
    if (expected_inspections != origin03["logical_row_count"] or expected_inspections != counts["bronze_inspections"]
            or expected_inspections != pq.read_metadata(root / INSPECTIONS).num_rows
            or counts["accepted"] != pq.read_metadata(root / VIOLATIONS).num_rows
            or counts["quarantined"] != pq.read_metadata(root / QUARANTINE).num_rows):
        raise ValueError("Published inspection or violation row counts disagree with provenance")
    return source_sha, source_digests


def read_inspections(path):
    inspections = {}
    used_rows = set()
    columns = ["inspection_key", "license_number_key", "inspection_dtm", "result_cd", "source_row_num"]
    for record in parquet_rows(path, columns):
        key, license_number, day, result, source_row = (record[col] for col in columns)
        if not key or key in inspections or day is None or not source_row or source_row in used_rows:
            raise ValueError(f"Invalid or duplicate shared inspection: {key!r}, source row {source_row}")
        used_rows.add(source_row)
        inspections[key] = training.Inspection(key, license_number, day, result, source_row)
    if not inspections or min(used_rows) != 1 or max(used_rows) != len(inspections):
        raise ValueError("Shared inspections do not preserve the source row sequence")
    return inspections


def read_codes(accepted_path, quarantine_path, inspections):
    codes = defaultdict(set)
    for row in parquet_rows(accepted_path, ["inspection_id", "source_row_num", "violation_code"]):
        key, code = row["inspection_id"], row["violation_code"]
        source = inspections.get(key)
        if source is None or source.source_row != row["source_row_num"] or not code:
            raise ValueError(f"02 Gold violation disagrees with shared inspection: {key!r}")
        codes[key].add(code)

    rejected = set()
    for row in parquet_rows(quarantine_path, ["inspection_id", "source_row_num"]):
        key = row["inspection_id"]
        source = inspections.get(key)
        if source is None or source.source_row != row["source_row_num"]:
            raise ValueError(f"02 quarantine disagrees with shared inspection: {key!r}")
        rejected.add(key)
    return codes, rejected


def dataset_schema(contract, dataset):
    return pa.schema([
        pa.field(name, pa.type_for_alias(contract["columns"][name]["type"]),
                 nullable=contract["columns"][name].get("nullable", False))
        for name in dataset["columns"]
    ])


def write_datasets(stage, contract, examples, rules):
    datasets = contract["datasets"]
    schemas = {name: dataset_schema(contract, spec) for name, spec in datasets.items()}
    columns = {name: set(schema.names) for name, schema in schemas.items()}
    buffers = {name: [] for name in datasets}
    splits = {name: {split: Counter() for split in ("train", "validation", "test")} for name in datasets}
    history_statuses = {name: Counter() for name in datasets}
    with ExitStack() as stack:
        writers = {
            name: stack.enter_context(pq.ParquetWriter(stage / spec["file"], schemas[name], compression="zstd"))
            for name, spec in datasets.items()
        }
        for name, row in examples:
            day, label_day = row["prediction_dtm"], row["label_observed_dtm"]
            prior = row["latest_prior_inspection_dtm"]
            split = row["split_cd"]
            if (row.keys() != columns[name] or (prior is not None and not 1 <= (day - prior).days <= rules.history_days)
                    or day > label_day or rules.split(day) != split or rules.split(label_day) != split):
                raise ValueError(f"Invalid training row schema or temporal boundary: {name}, {row['inspection_key']}")
            target = row[datasets[name]["target"]]
            splits[name][split]["positive" if target else "negative"] += 1
            history_statuses[name][row["history_status_cd"]] += 1
            buffers[name].append(row)
            if len(buffers[name]) == BATCH_SIZE:
                writers[name].write_table(pa.Table.from_pylist(buffers[name], schema=schemas[name]))
                buffers[name].clear()
        for name, rows in buffers.items():
            if rows:
                writers[name].write_table(pa.Table.from_pylist(rows, schema=schemas[name]))

    return {
        name: {
            "rows": sum(history_statuses[name].values()),
            "splits": {split: {"negative": counts["negative"], "positive": counts["positive"]}
                       for split, counts in splits[name].items()},
            "history_status_counts": dict(history_statuses[name]),
        }
        for name in datasets
    }


def verify_release(target, lineage, contract):
    manifest = read_json(target / MANIFEST)
    if manifest["release_id"] != target.name or manifest["lineage"] != lineage:
        raise ValueError(f"AI-ready release lineage mismatch: {target}")
    artifacts = manifest["artifacts"]
    if set(artifacts) != {SUMMARY, *(spec["file"] for spec in contract["datasets"].values())}:
        raise ValueError(f"AI-ready release artifact inventory mismatch: {target}")
    for name, digest in artifacts.items():
        if sha256(target / name) != digest:
            raise ValueError(f"AI-ready artifact SHA-256 mismatch: {target / name}")
    report = read_json(target / SUMMARY)
    for name, spec in contract["datasets"].items():
        with pq.ParquetFile(target / spec["file"]) as parquet:
            if (parquet.schema_arrow != dataset_schema(contract, spec)
                    or parquet.metadata.num_rows != report["datasets"][name]["rows"]):
                raise ValueError(f"AI-ready artifact row count or schema mismatch: {target / spec['file']}")


def build(root=PROJECT_ROOT, output_dir=None, *, verify_only=False):
    source_sha, inputs = verify_sources(root)
    contract = read_json(root / CONTRACT)
    rules = training.Rules.from_contract(contract)
    lineage = {
        "source_sha256": source_sha,
        "input_sha256": inputs,
        "code_sha256": {Path(path).name: sha256(Path(path)) for path in (__file__, training.__file__)},
        "pyarrow_version": pa.__version__,
    }
    release_id = hashlib.sha256(json_bytes(lineage)).hexdigest()[:20]
    parent = output_dir if output_dir is not None else root / OUTPUT
    target = parent / release_id
    if verify_only or target.exists():
        verify_release(target, lineage, contract)
        return target

    inspections = read_inspections(root / INSPECTIONS)
    codes, rejected = read_codes(root / VIOLATIONS, root / QUARANTINE, inspections)
    labels, label_counts = training.load_recurrence_labels(
        parquet_rows(root / RECURRENCE), inspections, codes, rejected, rules,
    )
    examples = training.training_examples(inspections.values(), codes, rejected, labels, rules)

    parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".build-", dir=parent) as pending:
        stage = Path(pending) / release_id
        stage.mkdir()
        summary = {
            "source_inspection_rows": len(inspections),
            "source_observation_end": max(row.day for row in inspections.values()).isoformat(),
            "inspection_results": dict(Counter(row.result or "unknown" for row in inspections.values())),
            "recurrence_input_status_counts": label_counts,
            "datasets": write_datasets(stage, contract, examples, rules),
        }
        (stage / SUMMARY).write_bytes(json_bytes(summary))
        manifest = {
            "release_id": release_id,
            "lineage": lineage,
            "artifacts": {path.name: sha256(path) for path in stage.iterdir()},
        }
        (stage / MANIFEST).write_bytes(json_bytes(manifest))
        verify_release(stage, lineage, contract)
        if any(sha256(root / path) != digest for path, digest in inputs.items()):
            raise ValueError("An AI-ready input changed during the build")
        try:
            stage.rename(target)
        except OSError:
            if not target.exists():
                raise
            verify_release(target, lineage, contract)
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=PROJECT_ROOT, help="Repository containing the published inputs")
    parser.add_argument("--output-dir", type=Path, help="Parent directory for the generated release")
    parser.add_argument("--verify", action="store_true", help="Verify the release for the current inputs and writer")
    args = parser.parse_args()
    print(build(args.root, args.output_dir, verify_only=args.verify))


if __name__ == "__main__":
    main()
