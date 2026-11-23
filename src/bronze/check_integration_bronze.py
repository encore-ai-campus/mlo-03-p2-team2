"""Check the published 06 Bronze against the verified team Origin."""

from importlib import import_module
import json
from types import SimpleNamespace


def verify_snapshot(root, origin):
    build = import_module("src.domains.06_integration.build")
    publish = import_module("src.domains.06_integration.publish")
    manifest = json.loads((root / publish.MANIFEST).read_text(encoding="utf-8"))
    reports = root / "reports/runs/06_integration"
    reports.mkdir(parents=True, exist_ok=True)
    with build.verified_origin(origin, reports) as verified:
        for name, (extension, count, key) in build.SOURCES.items():
            source = SimpleNamespace(path=verified / f"{name}.{extension}", format=extension)
            relative = build.BRONZE / f"{name}.parquet"
            origin = manifest["origin"][name]
            if origin["rows"] != count:
                raise ValueError(f"{name}: manifest row count differs from the snapshot contract")
            publish.verify_artifact(root, relative, manifest)
            build.verify_bronze(source, root / relative, manifest["loaded_at"], count, key, origin["sha256"])
            print(f"PASS {name}: {count:,} source and Bronze rows, lineage and load metadata", flush=True)


def main():
    root = import_module("src.domains.06_integration.build").ROOT
    verify_snapshot(root, root / "data/00_origin")


if __name__ == "__main__":
    main()
