"""Run published shared Bronze and Silver through all five Gold views and AI-ready."""

from argparse import ArgumentParser
from importlib import import_module
import json
from pathlib import Path
from shutil import copyfile
import subprocess
import sys
from tempfile import TemporaryDirectory

from src.ai_ready import build_inspection_training as training
from src.bronze import check_integration_bronze
from src.gold import build_dimensions
from src.silver import validate_integration_silver

from . import publish
from .build import BRONZE, DOMAINS, ROOT, SILVER
from .validate_pipeline import GOLD, VERIFICATION, compare_results, sha256, verify_output


DEFAULT_OUTPUT = Path("reports/runs/06_integration/end-to-end")
REPEAT = "03_repeat_inspection"
REGIONAL = "05_geospatial"


def write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def stage_snapshot(repo, stage):
    manifest = json.loads((repo / publish.MANIFEST).read_text(encoding="utf-8"))
    files = [publish.MANIFEST]
    for name, entry in manifest["artifacts"].items():
        files.extend(Path(part) for part in entry.get("parts") or (name,))
    for path in files:
        (stage / path).parent.mkdir(parents=True, exist_ok=True)
        copyfile(repo / path, stage / path)
    publish.restore(stage)
    check_integration_bronze.verify_snapshot(stage, repo / "data/00_origin")
    validate_integration_silver.verify_snapshot(stage)
    return manifest


def inspection_gold(stage, inspections, flags, source_rows):
    common = import_module("src.domains.01_inspection.common")
    quality = import_module("src.domains.01_inspection.quality")
    gold = import_module("src.domains.01_inspection.gold")
    ai_ready = import_module("src.domains.01_inspection.ai_ready")
    metadata = quality.transform(stage, stage, {}, inspections=inspections, rule_flags=flags)
    metadata.update(gold.transform(stage, stage, {**metadata, "source_rows": source_rows}))
    contract = ai_ready.transform(stage, stage, metadata)
    write_json(stage / common.AI_READY / "metadata/inspection_performance_contract.json", contract)
    write_json(stage / common.REPORTS / "inspection_quality_report.json", metadata)
    return stage / common.GOLD / "analysis/star_schema"


def inspection_manifest(stage, inspections, source):
    path = stage / "reports/06_integration/inspection_silver_manifest.json"
    write_json(path, {"source_sha256": source["sha256"].lower(), "silver_rows": source["rows"],
                      "artifacts": {inspections.name: sha256(inspections)}})
    return path


def regional_outputs(stage, inspections, areas, violations, source_sha, boundary_sha):
    subprocess.run([
        sys.executable, str(DOMAINS / REGIONAL / "geographic_shared.py"),
        "--inspection-silver", str(inspections), "--area-silver", str(areas),
        "--violations-dir", str(violations), "--data-dir", str(stage / "data"),
        "--inspection-sha256", source_sha, "--boundary-sha256", boundary_sha,
    ], check=True)
    manifests = list((stage / GOLD / REGIONAL).glob("*/*/manifest.json"))
    if len(manifests) != 1:
        raise ValueError("Expected one generated 05 Gold release")
    return manifests[0].parent


def training_outputs(repo, stage, inspections, reconciliation):
    # Keep the existing training writer and its standalone release verification
    # unchanged. The adapter lives only during this run and supplies fresh hashes
    # for the exact 06, 02 and 03 files under the writer's established input names.
    with TemporaryDirectory(dir=stage) as temporary:
        inputs = Path(temporary)
        paths = {
            training.INSPECTIONS: inspections,
            training.VIOLATIONS: stage / training.VIOLATIONS,
            training.QUARANTINE: stage / training.QUARANTINE,
            training.RECURRENCE: stage / training.RECURRENCE,
            training.RECONCILIATION: reconciliation,
            **{relative: repo / relative for relative in (training.CONTRACT, training.ORIGIN_03, training.ORIGIN_04)},
        }
        for relative, source in paths.items():
            target = inputs / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            if source.is_relative_to(stage):
                target.hardlink_to(source)
            else:
                copyfile(source, target)
        for relative, files in training.CHECKSUMS.items():
            target = inputs / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("".join(f"{sha256(inputs / path)}  {path.as_posix()}\n" for path in files),
                              encoding="ascii")
        release = training.build(inputs, stage / training.OUTPUT)
        training.build(inputs, stage / training.OUTPUT, verify_only=True)
    return release


def build(repo, output):
    if output.exists():
        raise FileExistsError(f"Use a new output directory or --verify: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    # The individual domain CLIs use sibling imports when run as scripts.
    for domain in ("01_inspection", REPEAT, "04_license"):
        sys.path.append(str(DOMAINS / domain))
    with TemporaryDirectory(dir=output.parent) as temporary:
        stage = Path(temporary) / "run"
        stage.mkdir()
        manifest = stage_snapshot(repo, stage)
        source = manifest["origin"]["food_inspections"]
        inspection_bronze = stage / BRONZE / "food_inspections.parquet"
        inspections = stage / SILVER / "food_inspections.parquet"
        licenses = stage / SILVER / "business_licenses.parquet"
        areas = stage / SILVER / "community_areas.parquet"
        flags = stage / SILVER / "inspection_rule_flags.parquet"
        provenance = inspection_manifest(stage, inspections, source)

        print("01: building inspection Gold and descriptive AI-ready", flush=True)
        inspection_star = inspection_gold(stage, inspections, flags, source["rows"])
        print("02: parsing and reconciling violations from shared Bronze", flush=True)
        domain02 = import_module("src.domains.02_violation.runner")
        domain02.run(repo, shared_bronze=inspection_bronze, output_root=stage)
        shared_violations = stage / "data/02_silver/02_violation/shared"
        exporter = import_module("src.domains.02_violation.export_shared_sample")
        exporter.export_sample(stage, repo, shared_violations, inspection_path=inspections,
                               inspection_manifest=provenance)
        print("03: building reinspection and recurrence Gold from shared Silver and 02", flush=True)
        mart = import_module("src.domains.03_repeat_inspection.build_inspection_marts")
        mart.build(inspections, stage / "data/02_silver" / REPEAT, stage / GOLD / REPEAT,
                   stage / "reports" / REPEAT, domain02_root=stage, inspection_manifest=provenance)
        print("04: building license Gold from shared inspection and license Silver", flush=True)
        modeling = import_module("src.domains.04_license.modeling")
        modeling.build_gold_from_silver(licenses, inspections, stage / GOLD)
        print("05: assigning community areas and building Gold and query AI-ready", flush=True)
        regional = regional_outputs(stage, inspections, areas, shared_violations, source["sha256"].lower(),
                                    manifest["origin"]["community_areas"]["sha256"].lower())

        gold = stage / GOLD
        print("Building and validating shared Gold", flush=True)
        build_dimensions.build(gold, inspection_star, regional, gold)
        print("Building and verifying both training datasets", flush=True)
        release = training_outputs(repo, stage, inspections, stage / exporter.REPORT_RELATIVE)
        print("Comparing generated tables with the published snapshot", flush=True)
        comparisons = compare_results(repo, stage, release)
        artifacts = {path.relative_to(stage).as_posix(): sha256(path)
                     for folder in ("data", "reports") for path in (stage / folder).rglob("*")
                     if path.is_file()}
        write_json(stage / VERIFICATION, {
            "status": "PASS",
            "source_snapshot": manifest["origin"],
            "shared_snapshot_sha256": sha256(stage / publish.MANIFEST),
            "training_release": release.relative_to(stage).as_posix(),
            "comparisons": comparisons,
            "artifacts": artifacts,
        })
        verify_output(stage)
        stage.rename(output)
    return output


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / DEFAULT_OUTPUT)
    parser.add_argument("--verify", action="store_true", help="Verify a completed run and its checksums")
    args = parser.parse_args()
    output = args.output.resolve()
    if args.verify:
        report = verify_output(output)
        print(f"PASS: {len(report['artifacts'])} artifacts verified in {output}")
    else:
        print(f"PASS: {build(ROOT, output)}")


if __name__ == "__main__":
    main()
