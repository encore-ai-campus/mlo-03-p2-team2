"""Publish or restore the fixed team Bronze and Silver paths."""

import argparse
import json
import os
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory

from src.bronze.load_bronze import sha256
from .build import BRONZE, ROOT, SILVER, SOURCES


MANIFEST = SILVER / "snapshot_manifest.json"
GIT_FILE_LIMIT = 100_000_000
BLOCK = 1024 * 1024


def install(source, destination, digest):
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.exists():
        try:
            os.link(source, destination)
        except FileExistsError:
            pass
    if sha256(destination) != digest:
        raise ValueError(f"Existing file differs: {destination}")


def split(source, temporary):
    parts = []
    with source.open("rb") as stream:
        remaining = source.stat().st_size
        while remaining:
            size = min(remaining, GIT_FILE_LIMIT)
            part = temporary / f"{source.name}.part-{len(parts) + 1:03d}"
            with part.open("xb") as target:
                # Read only the bytes assigned to this part.
                for _ in range(size // BLOCK):
                    target.write(stream.read(BLOCK))
                target.write(stream.read(size % BLOCK))
            parts.append(part)
            remaining -= size
    return parts


def prepare(run, temporary):
    summary = json.loads((run / "verification.json").read_text(encoding="utf-8"))
    if summary["status"] != "PASS" or summary["datasets"].keys() != SOURCES.keys():
        raise ValueError("A verified integration run is required")
    files = {SILVER / "inspection_rule_flags.parquet": run / "inspection_rule_flags.parquet"}
    for name in SOURCES:
        for layer, folder in (("bronze", BRONZE), ("silver", SILVER)):
            relative = folder / f"{name}.parquet"
            files[relative] = run / relative
            if sha256(files[relative]) != summary["datasets"][name][f"{layer}_sha256"]:
                raise ValueError(f"{relative}: checksum differs from the run report")

    artifacts = {}
    staged = {}
    for relative, source in files.items():
        copy = temporary / f"{relative.parts[1]}-{source.name}"
        shutil.copyfile(source, copy)
        digest = sha256(copy)
        artifacts[relative.as_posix()] = {"sha256": digest, "bytes": copy.stat().st_size}
        staged[relative] = copy, digest
        if copy.stat().st_size > GIT_FILE_LIMIT:
            parts = {}
            for index, part in enumerate(split(copy, temporary), 1):
                part_path = relative.with_suffix(f".parquet.part-{index:03d}")
                parts[part_path.as_posix()] = sha256(part)
                staged[part_path] = part, parts[part_path.as_posix()]
            artifacts[relative.as_posix()]["parts"] = parts
    manifest = {"version": 1, "loaded_at": summary["loaded_at"],
                "origin": {name: {"sha256": result["origin_sha256"], "rows": result["rows_per_stage"]}
                           for name, result in summary["datasets"].items()}, "artifacts": artifacts}
    report = temporary / MANIFEST.name
    report.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    staged[MANIFEST] = report, sha256(report)
    return staged


def publish(run, root):
    with TemporaryDirectory(dir=root) as directory:
        staged = prepare(run, Path(directory))
        for relative, (_, digest) in staged.items():
            path = root / relative
            if path.exists() and sha256(path) != digest:
                raise ValueError(f"Published snapshot differs: {path}")
        # The manifest is installed last, after the complete snapshot is available.
        for relative, (source, digest) in staged.items():
            install(source, root / relative, digest)


def verify_artifact(root, relative, manifest):
    path = root / relative
    entry = manifest["artifacts"][relative.as_posix()]
    if path.stat().st_size != entry["bytes"] or sha256(path) != entry["sha256"]:
        raise ValueError(f"Invalid published artifact: {relative}")


def restore(root):
    manifest = json.loads((root / MANIFEST).read_text(encoding="utf-8"))
    with TemporaryDirectory(dir=root) as directory:
        for relative, entry in manifest["artifacts"].items():
            target = root / relative
            parts = entry.get("parts", {})
            for part, digest in parts.items():
                if sha256(root / part) != digest:
                    raise ValueError(f"Invalid split part: {part}")
            if parts and not target.exists():
                materialized = Path(directory) / (target.parent.parent.name + "-" + target.name)
                with materialized.open("xb") as output:
                    for part in sorted(parts):
                        with (root / part).open("rb") as stream:
                            shutil.copyfileobj(stream, output)
                if sha256(materialized) != entry["sha256"]:
                    raise ValueError(f"Invalid reconstructed artifact: {relative}")
                install(materialized, target, entry["sha256"])
            verify_artifact(root, Path(relative), manifest)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--run", type=Path, help="Publish an existing verified run")
    mode.add_argument("--restore", action="store_true", help="Restore and verify the published files")
    args = parser.parse_args()
    if args.run:
        publish(args.run.resolve(), ROOT)
    restore(ROOT)
    print(f"Verified fixed snapshot: {ROOT / MANIFEST}")
