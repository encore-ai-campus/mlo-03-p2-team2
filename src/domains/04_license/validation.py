"""One validation row per check, with a failing process status."""

import csv
from collections import deque
from dataclasses import asdict, dataclass
from io import StringIO

import pyarrow.compute as pc
import pyarrow.parquet as pq

from bronze_manifest import MANIFEST, artifact_identity, check_entry, read_manifest
from config import TABLES
from modeling import (EVENT, MATCH, SCHEMAS, UNKNOWN, Indexes, gold_path,
                      inspection_license_numbers, inspection_matches, license_events)
from normalization import load_dictionary, normalize_batch, silver_schema
from pipeline_io import ROW, bronze_batches, sha256, staging
from quality import compare, render_reports
from shared_inspections import FLAGS_OUTPUT, shared_inspections


@dataclass(frozen=True)
class Check:
    table: str
    name: str
    violations: int
    detail: str = ""


def equal_batches(expected, actual):
    left, right = next(expected, None), next(actual, None)
    while left is not None and right is not None:
        length = min(left.num_rows, right.num_rows)
        if not left.slice(0, length).equals(right.slice(0, length)):
            return False
        left = left.slice(length) if left.num_rows > length else next(expected, None)
        right = right.slice(length) if right.num_rows > length else next(actual, None)
    return left is None and right is None


def bronze_checks(config):
    checks = []
    manifest = config.table("bronze", TABLES[0]).with_name(MANIFEST)
    try:
        _, entries = read_manifest(manifest, TABLES)
        checks.append(Check("bronze", "ingestion manifest structure", 0))
    except (OSError, ValueError) as error:
        entries = {}
        checks.append(Check("bronze", "ingestion manifest structure", 1, str(error)))

    for name in TABLES:
        target = config.table("bronze", name)
        source = config.sources[name]
        batches = bronze_batches(source)
        expected = next(batches)
        with pq.ParquetFile(target) as artifact:
            checks.append(Check(name, "schema", int(not artifact.schema_arrow.equals(expected))))
            matches = equal_batches(batches, artifact.iter_batches())
            row_count = artifact.metadata.num_rows
            checks.append(Check(name, "source values, order and row count", int(not matches),
                                f"Bronze rows: {row_count}"))
        if name in entries:
            identity = artifact_identity(name, source, sha256(source.path), target, row_count)
            try:
                check_entry(entries[name], identity)
                checks.append(Check(name, "ingestion manifest file hashes, row count and UTC timestamps", 0))
            except ValueError as error:
                checks.append(Check(name, "ingestion manifest file hashes, row count and UTC timestamps", 1, str(error)))
    return checks


def silver_checks(config):
    mapping = load_dictionary(config.dictionary)
    checks = []
    for name in TABLES:
        source, target = config.table("bronze", name), config.table("silver", name)
        schema = silver_schema(mapping[name])
        with pq.ParquetFile(source) as bronze, pq.ParquetFile(target) as silver:
            expected, actual = bronze.metadata.num_rows, silver.metadata.num_rows
            checks.append(Check(name, "row count", abs(expected - actual),
                                f"Bronze: {expected}, Silver: {actual}"))
            checks.append(Check(name, "dictionary schema", int(not silver.schema_arrow.equals(schema))))
            if name == "food_inspections" and config.inspection_silver:
                shared, flags = shared_inspections(config, schema)
                batches = iter(shared.to_batches())
                actual_flags = pq.read_table(target.with_name(FLAGS_OUTPUT))
                checks.append(Check(name, "shared inspection quality flags", int(not flags.equals(actual_flags))))
                rule = "shared inspection values and source row lineage"
            else:
                batches = (normalize_batch(batch, mapping[name], schema) for batch in bronze.iter_batches())
                rule = "dictionary values and source row lineage"
            matches = equal_batches(batches, silver.iter_batches())
            checks.append(Check(name, rule, int(not matches)))
    return checks


def quality_checks(config):
    results = compare(config)
    expected = render_reports(results)
    checks = [Check("quality", "unique decision IDs", len(results) - len({r["decision_id"] for r in results}))]
    for name, data in expected.items():
        path = config.reports / name
        checks.append(Check("quality", name + " matches recomputed comparisons",
                            int(not path.is_file() or path.read_bytes() != data)))
    return checks


PRIMARY_KEYS = {
    "dim_license": "license_number_key",
    "dim_establishment": "establishment_key",
    "dim_date": "date_key",
    EVENT: "license_event_key",
    MATCH: "inspection_key",
}


def violation_count(mask):
    return pc.sum(pc.fill_null(mask, True)).as_py() or 0


def membership_violations(values, permitted):
    return violation_count(pc.invert(pc.is_in(values, value_set=permitted)))


def gold_checks(config, root=None):
    root = root or config.stage_dir("gold")
    tables = {}
    checks = []
    for name, schema in SCHEMAS.items():
        with pq.ParquetFile(gold_path(root, name)) as artifact:
            checks.append(Check(name, "schema", int(not artifact.schema_arrow.equals(schema))))
            tables[name] = artifact.read()
        key = tables[name][PRIMARY_KEYS[name]]
        checks.append(Check(name, "PK duplicates or nulls", len(key) - pc.count_distinct(key).as_py()))

    for fact in (EVENT, MATCH):
        for dim in ("dim_license", "dim_establishment", "dim_date"):
            col = PRIMARY_KEYS[dim]
            checks.append(Check(fact, f"FK {col} -> {dim}",
                                membership_violations(tables[fact][col], tables[dim][col])))

    for fact, source in ((EVENT, "business_licenses"), (MATCH, "food_inspections")):
        cols = [PRIMARY_KEYS[fact], ROW]
        with pq.ParquetFile(config.table("silver", source)) as artifact:
            unchanged = artifact.read(columns=cols).equals(tables[fact].select(cols))
        checks.append(Check(fact, "source key, row order and count", int(not unchanged)))

    licenses = config.table("silver", "business_licenses")
    inspections = config.table("silver", "food_inspections")
    indexes = Indexes()
    expected_events = license_events(licenses, indexes, inspection_license_numbers(inspections))
    events_match = equal_batches(expected_events, iter(tables[EVENT].to_batches()))
    if not events_match:
        # A comparison can stop early. Index the remaining Silver events before checking matches.
        deque(expected_events, maxlen=0)
    checks.append(Check(EVENT, "fact values recomputed from Silver", int(not events_match)))
    matches_match = equal_batches(inspection_matches(inspections, indexes), iter(tables[MATCH].to_batches()))
    checks.append(Check(MATCH, "fact values and period candidates recomputed from Silver", int(not matches_match)))

    match = tables[MATCH]
    event = tables[EVENT]
    count = match["candidate_count_num"]
    status = match["match_status_cd"]
    event_id = match["matched_license_event_id"]
    one = pc.equal(count, 1)
    many = pc.greater(count, 1)
    bad_state = pc.or_kleene(pc.not_equal(pc.is_valid(event_id), one),
                            pc.not_equal(pc.equal(status, "UNIQUE_MATCH"), one))
    bad_state = pc.or_kleene(bad_state, pc.not_equal(pc.equal(status, "MULTIPLE_MATCHES"), many))
    bad_state = pc.or_kleene(bad_state, pc.less(count, 0))
    no_establishment = pc.or_kleene(one, pc.equal(match["establishment_key"], UNKNOWN))
    checks.append(Check(MATCH, "candidate count and resolution status",
                        violation_count(pc.or_kleene(bad_state, pc.invert(no_establishment)))))

    selected = match.filter(pc.is_valid(event_id))
    selected_ids = pc.index_in(selected["matched_license_event_id"], value_set=event["license_event_key"])
    checks.append(Check(MATCH, f"FK matched event -> {EVENT}", selected_ids.null_count))
    selected_events = event.take(selected_ids)
    date_dim = tables["dim_date"]
    date_indices = pc.index_in(selected["date_key"], value_set=date_dim["date_key"])
    observed = pc.take(date_dim["calendar_dtm"], date_indices)
    linked = pc.and_kleene(pc.equal(selected["license_number_key"], selected_events["license_number_key"]),
                           pc.equal(selected["establishment_key"], selected_events["establishment_key"]))
    in_period = pc.and_kleene(pc.less_equal(selected_events["term_start_dtm"], observed),
                              pc.less_equal(observed, selected_events["term_end_dtm"]))
    checks.append(Check(MATCH, "selected event license, establishment and valid period",
                        violation_count(pc.invert(pc.and_kleene(linked, in_period)))))
    return checks


def write_validation(config, stage, checks):
    stream = StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=["table", "name", "violations", "detail"], lineterminator="\n")
    writer.writeheader()
    writer.writerows(asdict(check) for check in checks)
    failed = [check for check in checks if check.violations]
    for check in failed:
        print(f"FAIL {check.table} | {check.name} | {check.violations} | {check.detail}")
    print(f"{stage}: {len(checks) - len(failed)}/{len(checks)} checks passed.")
    with staging(config.reports, replace=True) as target:
        (target / f"validation_{stage}.csv").write_bytes(stream.getvalue().encode("utf-8"))
    return int(bool(failed))
