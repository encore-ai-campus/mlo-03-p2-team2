"""Validate the published 06 Silver schemas, row lineage and quality flags."""

import csv
from importlib import import_module
import json

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq


def verify_schema(path, fields, date_columns):
    schema = pq.read_schema(path)
    if len(schema.names) != len(fields) or set(schema.names) != set(fields):
        raise ValueError(f"{path.name}: columns differ from the standard mapping")
    actual_dates = {field.name for field in schema if pa.types.is_date32(field.type)}
    if actual_dates != date_columns:
        raise ValueError(f"{path.name}: date32 columns differ from the standard mapping")
    if schema.field("source_row_num").type != pa.int64():
        raise ValueError(f"{path.name}: source_row_num must be int64")


def main():
    build = import_module("src.domains.06_integration.build")
    publish = import_module("src.domains.06_integration.publish")
    # Import the existing 01 mapping without running that domain's pipeline.
    inspection_columns = import_module("src.domains.01_inspection.common").COLUMNS
    with (build.DOMAINS / "04_license/데이터 사전.csv").open(encoding="utf-8-sig", newline="") as file:
        license_fields = [row for row in csv.DictReader(file) if row["table"] == "business_licenses"]
    mappings = {
        "food_inspections": ("inspection_key", list(inspection_columns.values()), {"inspection_dtm"}),
        "business_licenses": ("license_event_key", [row["target_column"] for row in license_fields],
                              {row["target_column"] for row in license_fields if row["type"] == "date"}),
        "community_areas": ("community_area_num", ["community_area_num", "community_area_name", "geometry"], set()),
    }
    root = build.ROOT
    manifest = json.loads((root / publish.MANIFEST).read_text(encoding="utf-8"))
    for name, (key, columns, dates) in mappings.items():
        relative = build.SILVER / f"{name}.parquet"
        publish.verify_artifact(root, relative, manifest)
        bronze = root / build.BRONZE / relative.name
        with pq.ParquetFile(bronze) as parquet:
            count = parquet.metadata.num_rows
        if count != manifest["origin"][name]["rows"]:
            raise ValueError(f"{name}: Bronze row count differs from manifest")
        verify_schema(root / relative, [*columns, "source_row_num"], dates)
        build.validate_silver(root / relative, count, key)
        print(f"PASS {name}: {count:,} Bronze and Silver rows, standard columns, dates and unique key")
    relative = build.SILVER / "inspection_rule_flags.parquet"
    publish.verify_artifact(root, relative, manifest)
    flags = pq.read_table(root / relative)
    inspections = pq.read_table(root / build.SILVER / "food_inspections.parquet", columns=["source_row_num"])
    if not flags["source_row_num"].equals(inspections["source_row_num"]):
        raise ValueError("Inspection quality flags differ from Silver row lineage")
    for rule in ("exact_duplicate", "conflicting_inspection_key"):
        print(f"{rule}: {pc.sum(flags[rule]).as_py()} flagged rows")


if __name__ == "__main__":
    main()
