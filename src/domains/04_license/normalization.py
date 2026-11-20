"""Data dictionary driven Silver transforms."""

import csv
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from functools import lru_cache

import pyarrow as pa
import pyarrow.compute as pc

from config import TABLES
from pipeline_io import ROW


POSITIVE_ID = r"^0*[1-9][0-9]*$"
US_DATE = re.compile(r"\d{1,2}/\d{1,2}/\d{4}\Z")
TRANSFORM_TYPES = {
    "trim": "string", "upper": "string", "positive_id": "string",
    "inspection_license": "string", "calendar_date": "date",
}
ARROW_TYPES = {"string": pa.string(), "date": pa.date32()}


@dataclass(frozen=True)
class Field:
    table: str
    source_column: str
    target_column: str
    type: str
    transform: str
    decision_id: str


def load_dictionary(path):
    entries = defaultdict(list)
    with path.open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            field = Field(**row)
            if TRANSFORM_TYPES.get(field.transform) != field.type or not field.decision_id.strip():
                raise ValueError(f"Invalid transform or decision ID for {field.target_column}.")
            if not re.fullmatch(r"[a-z][a-z0-9_]*", field.target_column):
                raise ValueError(f"Invalid Silver column name: {field.target_column}")
            entries[field.table].append(field)
    if set(entries) != set(TABLES):
        raise ValueError(f"Data dictionary must define exactly {TABLES}.")
    for table, fields in entries.items():
        targets = [field.target_column for field in fields]
        if len(targets) != len(set(targets)) or ROW in targets:
            raise ValueError(f"{table}: duplicate or reserved target column.")
    return entries


def silver_schema(fields):
    return pa.schema([(field.target_column, ARROW_TYPES[field.type]) for field in fields]
                     + [(ROW, pa.int64())])


@lru_cache(maxsize=65_536)
def calendar_date(value):
    if not value:
        return None
    try:
        if US_DATE.fullmatch(value):
            month, day, year = map(int, value.split("/"))
            return date(year, month, day)
        if "T" in value or " " in value:
            return datetime.fromisoformat(value).date()
        return date.fromisoformat(value)
    except ValueError:
        return None


def trimmed(values):
    text = pc.utf8_trim_whitespace(values)
    return pc.if_else(pc.equal(text, ""), pa.scalar(None, pa.string()), text)


def valid_identifier(text, inspection=False):
    valid = pc.match_substring_regex(text, POSITIVE_ID)
    if inspection:
        valid = pc.and_kleene(valid, pc.not_equal(text, "9999999"))
    return valid


def typed_dates(text):
    encoded = pc.dictionary_encode(text)
    dictionary = pa.array([calendar_date(value) for value in encoded.dictionary.to_pylist()],
                          type=pa.date32())
    return pc.take(dictionary, encoded.indices)


def transform(values, mode):
    text = trimmed(values)
    if mode == "trim":
        return text
    if mode == "upper":
        return pc.utf8_upper(text)
    if mode == "calendar_date":
        return typed_dates(text)
    valid = valid_identifier(text, inspection=(mode == "inspection_license"))
    return pc.if_else(valid, text, pa.scalar(None, pa.string()))


def normalize_batch(batch, fields, schema=None):
    columns = [transform(batch[field.source_column], field.transform) for field in fields]
    return pa.record_batch(columns + [batch[ROW]], schema=schema or silver_schema(fields))
