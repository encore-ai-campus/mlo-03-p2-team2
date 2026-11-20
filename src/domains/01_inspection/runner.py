"""Validate dependencies and publish artifacts for each stage."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory

import ai_ready
import bronze
import gold
import quality
import silver
from common import AI_READY, BRONZE, GOLD, REPORTS, ROOT, SILVER, digest


STAGES = (
    ("bronze", bronze.transform, BRONZE / "metadata/inspection_manifest.json"),
    ("silver", silver.transform, SILVER / "metadata/inspection_silver_manifest.json"),
    ("quality", quality.transform, REPORTS / "inspection_quality_report.json"),
    ("gold", gold.transform, GOLD / "metadata/inspection_gold_manifest.json"),
    ("ai_ready", ai_ready.transform, AI_READY / "metadata/inspection_performance_contract.json"),
)

VALIDATION_REPORTS = {
    "bronze": (("source_schema", "source_checksum_stability"), ("source_rows",)),
    "silver": (("source_row_preservation",), ("source_rows", "silver_rows")),
    "gold": (
        ("source_row_reconciliation", "unique_inspection_keys", "nonempty_fact",
         "dimension_references", "aggregate_count_reconciliation"),
        ("source_rows", "excluded_quality_rows", "gold_rows", "decision_rows"),
    ),
    "ai_ready": (("unique_aggregate_grain",), ("ai_ready_rows",)),
}


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def load_upstream(root, stages):
    metadata = {}
    parent = None
    for name, _, manifest in stages:
        path = root / manifest
        if not path.exists():
            raise ValueError(f"Run stage {name} first")
        previous = json.loads(path.read_text(encoding="utf-8"))
        if previous["parent_sha256"] != parent:
            raise ValueError(f"Stage {name} is stale; rerun from that stage")
        for filename, checksum in previous["artifacts"].items():
            if digest(root / filename) != checksum:
                raise ValueError(f"Stage {name} artifact changed: {filename}")
        metadata = previous
        parent = digest(path)
    return metadata, parent


def run_stage(root, index):
    name, build, manifest = STAGES[index]
    upstream, parent = load_upstream(root, STAGES[:index])
    metadata = {key: value for key, value in upstream.items()
                if key not in ("artifacts", "parent_sha256")}
    with TemporaryDirectory(dir=root) as directory:
        output = Path(directory)
        metadata.update(build(root, output, metadata))
        if name in VALIDATION_REPORTS:
            checks, count_fields = VALIDATION_REPORTS[name]
            report = output / REPORTS / f"validation_{name}.json"
            report.parent.mkdir(parents=True, exist_ok=True)
            write_json(report, {
                "stage": name,
                "status": "passed",
                "checks": [
                    *(["upstream_manifest_and_artifact_hashes"] if index else []),
                    *checks,
                ],
                "row_counts": {field: metadata[field] for field in count_fields},
                "source_sha256": metadata["source_sha256"],
                "manifest": manifest.as_posix(),
            })
        artifacts = sorted(path.relative_to(output) for path in output.rglob("*") if path.is_file())
        metadata["artifacts"] = {path.as_posix(): digest(output / path) for path in artifacts}
        metadata["parent_sha256"] = parent
        (output / manifest).parent.mkdir(parents=True, exist_ok=True)
        write_json(output / manifest, metadata)
        publish(output, root, [*artifacts, manifest])


def publish(source, target, files):
    for path in files:
        destination = target / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        (source / path).replace(destination)


def main():
    with TemporaryDirectory(dir=ROOT / "data") as directory:
        staging = Path(directory)
        for index in range(len(STAGES)):
            run_stage(staging, index)
        for _, _, manifest in STAGES:
            metadata = json.loads((staging / manifest).read_text(encoding="utf-8"))
            publish(staging, ROOT, [*map(Path, metadata["artifacts"]), manifest])
    print(f"Inspection pipeline complete: {ROOT / 'data'}")


if __name__ == "__main__":
    main()
