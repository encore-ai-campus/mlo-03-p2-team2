"""Domain 04 Gold dimensions and facts."""

from collections import defaultdict
from dataclasses import dataclass, field
from itertools import islice

import pyarrow as pa

from config import DOMAIN, parquet_name
from pipeline_io import BATCH_SIZE, ROW, parquet_batches, write_parquet


UNKNOWN = "__unknown__"
EVENT = "fact_license_event"
MATCH = "fact_inspection_license_match"


def schema(keys, dates=(), counts=()):
    fields = [(name, pa.string()) for name in keys]
    fields += [(name, pa.date32()) for name in dates]
    fields += [(name, pa.int64()) for name in counts]
    return pa.schema(fields)


SCHEMAS = {
    "dim_license": schema(("license_number_key",)),
    "dim_establishment": schema(("establishment_key", "account_key", "site_key")),
    "dim_date": schema(("date_key",), ("calendar_dtm",)),
    EVENT: schema(
        ("license_event_key", "license_number_key", "establishment_key", "date_key",
         "application_cd", "recorded_status_cd"),
        ("term_start_dtm", "term_end_dtm", "status_change_dtm"), (ROW,),
    ),
    MATCH: schema(
        ("inspection_key", "license_number_key", "establishment_key", "date_key",
         "source_license_number", "matched_license_event_id", "match_status_cd", "result_cd"),
        counts=("candidate_count_num", ROW),
    ),
}
LICENSE_FIELDS = (
    "license_event_key", "license_number_key", "account_key", "site_key", "issued_dtm",
    "application_cd", "recorded_status_cd", "term_start_dtm", "term_end_dtm", "status_change_dtm", ROW,
)
INSPECTION_FIELDS = ("inspection_key", "license_number_key", "inspection_dtm", "result_cd", ROW)


@dataclass
class Indexes:
    licenses: set = field(default_factory=set)
    establishments: dict = field(default_factory=dict)
    dates: set = field(default_factory=set)
    periods: dict = field(default_factory=lambda: defaultdict(list))


def gold_path(root, table):
    return root / DOMAIN / parquet_name(table)


def record_batch(rows, table):
    return pa.RecordBatch.from_pylist(rows, schema=SCHEMAS[table])


def write_rows(path, table, rows):
    batches = iter(lambda: list(islice(rows, BATCH_SIZE)), [])
    write_parquet(gold_path(path, table), SCHEMAS[table],
                  (record_batch(batch, table) for batch in batches))


def require_key(key, seen, name, source_row):
    if not key or key in seen:
        raise ValueError(f"{name}: missing or duplicate PK at source row {source_row}: {key!r}.")
    seen.add(key)


def date_key(day, indexes):
    if day is None:
        return UNKNOWN
    indexes.dates.add(day)
    return day.isoformat()


def source_columns(batch, fields):
    return zip(*(batch[name].to_pylist() for name in fields))


def inspection_license_numbers(path):
    return {number for batch in parquet_batches(path, columns=["license_number_key"])
            for number in batch["license_number_key"].to_pylist() if number is not None}


def license_events(path, indexes, inspection_numbers):
    seen = set()
    for batch in parquet_batches(path, columns=LICENSE_FIELDS):
        rows = []
        for key, number, account, site, issued, application, status, start, end, change, row in source_columns(batch, LICENSE_FIELDS):
            require_key(key, seen, EVENT, row)
            establishment = UNKNOWN
            if account and site:
                establishment = f"{account}:{site}"
                indexes.establishments[establishment] = (account, site)
            if number:
                indexes.licenses.add(number)
            if number in inspection_numbers and start is not None and end is not None and start <= end:
                indexes.periods[number].append((start, end, key, establishment))
            rows.append({
                "license_event_key": key,
                "license_number_key": number or UNKNOWN,
                "establishment_key": establishment,
                "date_key": date_key(issued, indexes),
                "application_cd": application,
                "recorded_status_cd": status,
                "term_start_dtm": start,
                "term_end_dtm": end,
                "status_change_dtm": change,
                ROW: row,
            })
        yield record_batch(rows, EVENT)


def match_period(number, observed, indexes):
    if not number:
        return "MISSING_LICENSE_NUMBER", 0, None, UNKNOWN
    if not observed:
        return "MISSING_INSPECTION_DATE", 0, None, UNKNOWN
    if number not in indexes.licenses:
        return "NO_LICENSE_NUMBER_MATCH", 0, None, UNKNOWN

    candidates = [(key, establishment) for start, end, key, establishment in indexes.periods.get(number, ())
                  if start <= observed <= end]
    count = len(candidates)
    if count == 1:
        key, establishment = candidates[0]
        return "UNIQUE_MATCH", count, key, establishment
    status = "MULTIPLE_MATCHES" if count else "NO_VALID_PERIOD"
    return status, count, None, UNKNOWN


def inspection_matches(path, indexes):
    seen = set()
    for batch in parquet_batches(path, columns=INSPECTION_FIELDS):
        rows = []
        for key, number, observed, result, row in source_columns(batch, INSPECTION_FIELDS):
            require_key(key, seen, MATCH, row)
            status, count, event_id, establishment = match_period(number, observed, indexes)
            rows.append({
                "inspection_key": key,
                "license_number_key": number if number in indexes.licenses else UNKNOWN,
                "establishment_key": establishment,
                "date_key": date_key(observed, indexes),
                "source_license_number": number,
                "matched_license_event_id": event_id,
                "match_status_cd": status,
                "result_cd": result,
                "candidate_count_num": count,
                ROW: row,
            })
        yield record_batch(rows, MATCH)


def dimensions(root, indexes):
    write_rows(root, "dim_license", ({"license_number_key": number} for number in
                                    sorted(indexes.licenses | {UNKNOWN})))
    indexes.establishments[UNKNOWN] = (None, None)
    write_rows(root, "dim_establishment", (
        {"establishment_key": key, "account_key": account, "site_key": site}
        for key, (account, site) in sorted(indexes.establishments.items())
    ))

    def date_rows():
        yield {"date_key": UNKNOWN, "calendar_dtm": None}
        for day in sorted(indexes.dates):
            yield {"date_key": day.isoformat(), "calendar_dtm": day}

    write_rows(root, "dim_date", date_rows())


def build_gold(config, root):
    licenses = config.table("silver", "business_licenses")
    inspections = config.table("silver", "food_inspections")
    numbers = inspection_license_numbers(inspections)
    indexes = Indexes()
    write_parquet(gold_path(root, EVENT), SCHEMAS[EVENT], license_events(licenses, indexes, numbers))
    write_parquet(gold_path(root, MATCH), SCHEMAS[MATCH], inspection_matches(inspections, indexes))
    dimensions(root, indexes)
