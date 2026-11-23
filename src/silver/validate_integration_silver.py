"""Validate the published 06 Silver schemas, row lineage and quality flags."""

from importlib import import_module
import json

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq


from .shared_dictionary import PRIMARY_KEYS, load_shared_codes, load_shared_columns


TYPE_CHECKS = {
    "string": lambda dtype: pa.types.is_string(dtype) or pa.types.is_large_string(dtype),
    "date": pa.types.is_date32,
    "float64": pa.types.is_float64,
    "int64": pa.types.is_int64,
}


def verify_schema(path, fields):
    schema = pq.read_schema(path)
    types = {row["target_column"]: row["type"] for row in fields}
    types["source_row_num"] = "int64"
    if len(schema.names) != len(types) or set(schema.names) != types.keys():
        raise ValueError(f"{path.name}: columns differ from the shared dictionary")
    for field in schema:
        expected = types[field.name]
        if not TYPE_CHECKS[expected](field.type):
            raise ValueError(f"{path.name}: {field.name} must be {expected}, got {field.type}")


def verify_snapshot(root):
    build = import_module("src.domains.06_integration.build")
    publish = import_module("src.domains.06_integration.publish")
    columns = load_shared_columns(build.ROOT)
    load_shared_codes(build.ROOT, columns)
    manifest = json.loads((root / publish.MANIFEST).read_text(encoding="utf-8"))
    for name, fields in columns.items():
        relative = build.SILVER / f"{name}.parquet"
        publish.verify_artifact(root, relative, manifest)
        bronze = root / build.BRONZE / relative.name
        with pq.ParquetFile(bronze) as parquet:
            count = parquet.metadata.num_rows
        if count != manifest["origin"][name]["rows"]:
            raise ValueError(f"{name}: Bronze row count differs from manifest")
        verify_schema(root / relative, fields)
        build.validate_silver(root / relative, count, PRIMARY_KEYS[name])
        print(f"PASS {name}: {count:,} Bronze and Silver rows, dictionary columns and types, lineage and unique key")
    relative = build.SILVER / "inspection_rule_flags.parquet"
    publish.verify_artifact(root, relative, manifest)
    flags = pq.read_table(root / relative)
    inspections = pq.read_table(root / build.SILVER / "food_inspections.parquet", columns=["source_row_num"])
    if not flags["source_row_num"].equals(inspections["source_row_num"]):
        raise ValueError("Inspection quality flags differ from Silver row lineage")
    for rule in ("exact_duplicate", "conflicting_inspection_key"):
        print(f"{rule}: {pc.sum(flags[rule]).as_py()} flagged rows")


def main():
    verify_snapshot(import_module("src.domains.06_integration.build").ROOT)


if __name__ == "__main__":
    main()
