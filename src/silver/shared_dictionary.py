"""Column and type contract for the three shared Silver tables."""

import csv
from collections import defaultdict
import re
from pathlib import Path


SHARED_COLUMNS = Path("metadata/data_dictionary/shared_silver_columns.csv")
CODE_MAP = SHARED_COLUMNS.with_name("shared_code_map.csv")
PRIMARY_KEYS = {
    "food_inspections": "inspection_key",
    "business_licenses": "license_event_key",
    "community_areas": "community_area_num",
}
TRANSFORM_TYPES = {
    "trim": "string",
    "upper": "string",
    "positive_id": "string",
    "inspection_license_sentinels": "string",
    "code_map": "string",
    "nonblank_original": "string",
    "trim_whitespace": "string",
    "preserve": "string",
    "inspection_date": "date",
    "calendar_date": "date",
    "coordinate": "float64",
    "area_integer": "int64",
}


def load_shared_columns(root):
    tables = defaultdict(list)
    with (root / SHARED_COLUMNS).open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            if (TRANSFORM_TYPES.get(row["transform"]) != row["type"]
                    or not re.fullmatch(r"[a-z][a-z0-9_]*", row["target_column"])
                    or not row["source_column"]):
                raise ValueError(f"Invalid shared Silver mapping: {row}")
            tables[row["table"]].append(row)
    if tables.keys() != PRIMARY_KEYS.keys():
        raise ValueError("Shared Silver dictionary must cover inspections, licenses and community areas")

    for table, rows in tables.items():
        sources = {row["source_column"] for row in rows}
        targets = {row["target_column"] for row in rows}
        if len(sources) != len(rows) or len(targets) != len(rows) or "source_row_num" in targets:
            raise ValueError(f"{table}: duplicate source/target or reserved column")
        if PRIMARY_KEYS[table] not in targets:
            raise ValueError(f"{table}: missing primary key mapping")
    return dict(tables)


def load_shared_codes(root, columns):
    expected = {(table, row["source_column"], row["target_column"])
                for table, fields in columns.items() for row in fields if row["transform"] == "code_map"}
    lookups = {}
    with (root / CODE_MAP).open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            key = (row["dataset"], row["source_column"], row["target_column"])
            # The same file also documents codes not used by the shared Silver transforms.
            if key not in expected:
                continue
            values = lookups.setdefault(key, {})
            source = row["source_value"]
            if not source or not row["standard_code"] or source in values:
                raise ValueError(f"Invalid or duplicate shared code for {key}: {source!r}")
            values[source] = row
    if lookups.keys() != expected:
        raise ValueError(f"Missing shared code mappings: {expected.difference(lookups)}")
    return lookups
