"""Validate dependencies and publish artifacts for each stage."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory

import ai_ready
import bronze
import gold
import quality
import silver
from common import DATA, digest


STAGES = (
    ("bronze", bronze.transform, "bronze", "metadata/inspection_manifest.json"),
    ("silver", silver.transform, "silver", "metadata/inspection_silver_manifest.json"),
    ("quality", quality.transform, "silver", "reports/inspection_quality_report.json"),
    ("gold", gold.transform, "gold", "metadata/inspection_gold_manifest.json"),
    ("ai_ready", ai_ready.transform, "ai_ready_data", "metadata/inspection_performance_contract.json"),
)


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def load_upstream(data, stages):
    metadata = {}
    parent = None
    for name, _, layer, manifest in stages:
        folder = data / layer
        path = folder / manifest
        if not path.exists():
            raise ValueError(f"Run stage {name} first")
        previous = json.loads(path.read_text(encoding="utf-8"))
        if previous["parent_sha256"] != parent:
            raise ValueError(f"Stage {name} is stale; rerun from that stage")
        for filename, checksum in previous["artifacts"].items():
            if digest(folder / filename) != checksum:
                raise ValueError(f"Stage {name} artifact changed: {filename}")
        metadata = previous
        parent = digest(path)
    return metadata, parent


def run_stage(data, index):
    name, build, layer, manifest = STAGES[index]
    upstream, parent = load_upstream(data, STAGES[:index])
    metadata = {key: value for key, value in upstream.items()
                if key not in ("artifacts", "parent_sha256")}
    target = data / layer
    target.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=data) as directory:
        output = Path(directory)
        metadata.update(build(data, output, metadata))
        artifacts = sorted(path.relative_to(output) for path in output.rglob("*") if path.is_file())
        metadata["artifacts"] = {path.as_posix(): digest(output / path) for path in artifacts}
        metadata["parent_sha256"] = parent
        (output / manifest).parent.mkdir(parents=True, exist_ok=True)
        write_json(output / manifest, metadata)
        publish(output, target, [*artifacts, Path(manifest)])


def publish(source, target, files):
    for path in files:
        destination = target / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        (source / path).replace(destination)


def main():
    with TemporaryDirectory(dir=DATA) as directory:
        staging = Path(directory)
        for index in range(len(STAGES)):
            run_stage(staging, index)
        for _, _, layer, manifest in STAGES:
            source = staging / layer
            metadata = json.loads((source / manifest).read_text(encoding="utf-8"))
            publish(source, DATA / layer, [*map(Path, metadata["artifacts"]), Path(manifest)])
    print(f"Inspection pipeline complete: {DATA}")


if __name__ == "__main__":
    main()
