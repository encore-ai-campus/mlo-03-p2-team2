"""Reuse the standardized inspection values and quality flags from shared Silver."""

import json

import pyarrow.compute as pc
import pyarrow.parquet as pq

from pipeline_io import ROW, sha256


FLAGS_OUTPUT = "04_inspection_rule_flags.parquet"


def shared_inspections(config, schema):
    source = config.inspection_silver
    flags_path = source.with_name("inspection_rule_flags.parquet")
    manifest_path = source.with_name("snapshot_manifest.json")
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        entries = {path.rsplit("/", 1)[-1]: item for path, item in manifest["artifacts"].items()
                   if "/02_silver/" in path}
        for path in (source, flags_path):
            if sha256(path).lower() != entries[path.name]["sha256"].lower():
                raise ValueError(f"Shared snapshot checksum differs for {path.name}")
        if sha256(config.sources["food_inspections"].path).lower() != manifest["origin"]["food_inspections"]["sha256"].lower():
            raise ValueError("04 inspection Origin differs from the shared Silver snapshot")

    inspections = pq.read_table(source, columns=schema.names).cast(schema)
    flags = pq.read_table(flags_path)
    if not flags[ROW].equals(inspections[ROW]):
        raise ValueError("Shared inspection quality flags differ from Silver row lineage")
    bronze = pq.read_table(config.table("bronze", "food_inspections"), columns=["Inspection ID", "Results", ROW])
    if (not bronze[ROW].equals(inspections[ROW])
            or not pc.utf8_trim_whitespace(bronze["Inspection ID"]).equals(inspections["inspection_key"])):
        raise ValueError("04 Bronze inspection keys or row order differ from shared Silver")

    raw = pc.utf8_trim_whitespace(bronze["Results"])
    missing = pc.or_(pc.is_null(raw), pc.fill_null(pc.equal(raw, ""), False))
    unmapped = pc.and_(pc.invert(missing), pc.is_null(inspections["result_cd"]))
    if (not missing.equals(flags["missing_result_cd"])
            or not unmapped.equals(flags["unmapped_result_cd"])
            or pc.any(pc.and_(missing, pc.is_valid(inspections["result_cd"]))).as_py()):
        raise ValueError("Shared result codes or quality flags disagree with the 04 inspection source")
    return inspections, flags
