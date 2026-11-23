import csv
import hashlib
import json
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest


SCRIPTS = Path(__file__).resolve().parents[3] / "src" / "domains" / "04_license"
STAGES = ("01_bronze", "02_normalize", "03_quality", "04_modeling")
VALIDATORS = ("validate_bronze", "validate_silver", "validate_quality", "validate_gold")
LICENSE_COLUMNS = (
    "ID", "LICENSE ID", "LICENSE NUMBER", "ACCOUNT NUMBER", "SITE NUMBER",
    "LEGAL NAME", "DOING BUSINESS AS NAME", "ADDRESS", "CITY", "STATE", "ZIP CODE",
    "LICENSE CODE", "APPLICATION TYPE", "DATE ISSUED", "LICENSE STATUS",
    "LICENSE STATUS CHANGE DATE", "LICENSE TERM START DATE",
    "LICENSE TERM EXPIRATION DATE", "APPLICATION CREATED DATE",
)


def write_csv(path, columns, rows):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(columns)
        writer.writerows(rows)


@pytest.fixture
def project(tmp_path):
    data, reports = (tmp_path / name for name in ("data", "reports"))
    raw = data / "00_origin"
    raw.mkdir(parents=True)

    def license_row(key, number, start, end):
        return [
            "source-" + key, key, number, "10", "1", "Legal", "Shop",
            "Street", "Chicago", "IL", "01234", "1010", " RENEW ",
            "01/01/2024", "AAI", "", start, end, "",
        ]

    write_csv(raw / "business_licenses.csv", LICENSE_COLUMNS, [
        license_row("1", "111", "01/01/2024", "01/10/2024"),
        license_row("2", "111", "01/10/2024", "01/20/2024"),
        license_row("3", "222", "02/01/2024", "01/31/2024"),
        license_row("4", "", "bad", "01/31/2024"),
    ])
    write_csv(raw / "food_inspections.csv", (
        "Inspection ID", "License #", "Inspection Date", "Results",
    ), [
        ["101", "111", "01/01/2024", "Pass"],
        ["102", "111", "01/10/2024", "FAIL"],
        ["103", "111", "01/20/2024", "Pass"],
        ["104", "222", "02/01/2024", "Fail"],
        ["105", "333", "01/10/2024", "Pass"],
        ["106", "0", "01/10/2024", "Fail"],
        ["107", "111", "02/30/2024", "Pass"],
    ])
    return raw, data, reports


def execute(name, project, ok=True, extra=()):
    raw, data, reports = project
    completed = subprocess.run(
        [sys.executable, str(SCRIPTS / (name + ".py")),
         "--raw-dir", str(raw), "--data-dir", str(data), "--report-dir", str(reports),
         *extra],
        capture_output=True, encoding="utf-8", errors="replace",
    )
    if ok:
        assert completed.returncode == 0, completed.stdout + completed.stderr
    return completed


def snapshot(folder):
    return {p.relative_to(folder).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in folder.rglob("*") if p.is_file()}


@pytest.fixture
def shared_silver(tmp_path):
    folder = tmp_path / "shared_silver"
    folder.mkdir()
    licenses = folder / "business_licenses.parquet"
    inspections = folder / "food_inspections.parquet"
    day = date(2024, 1, 10)
    pq.write_table(pa.table({
        "license_event_key": ["0001"], "license_number_key": ["0111"],
        "account_key": ["010"], "site_key": ["01"], "issued_dtm": [day],
        "application_cd": ["RENEW"], "recorded_status_cd": ["AAI"],
        "term_start_dtm": [date(2024, 1, 1)], "term_end_dtm": [day],
        "status_change_dtm": pa.array([None], type=pa.date32()), "source_row_num": [99],
    }), licenses)
    pq.write_table(pa.table({
        "inspection_key": pa.array(["00101", "00102"], type=pa.large_string()),
        "license_number_key": ["0111", "0111"], "inspection_dtm": [day, date(2024, 1, 11)],
        "result_cd": ["PASS", "FAIL"], "source_row_num": [50, 51], "extra_column": [True, False],
    }), inspections)
    return licenses, inspections, tmp_path / "gold"


def build_shared_gold(licenses, inspections, gold):
    return subprocess.run(
        [sys.executable, "-c", "from pathlib import Path; import sys; "
         "from modeling import build_gold_from_silver; "
         "build_gold_from_silver(*map(Path, sys.argv[1:]))",
         str(licenses), str(inspections), str(gold)],
        cwd=SCRIPTS, capture_output=True, encoding="utf-8", errors="replace",
    )


def test_gold_from_shared_silver_keeps_string_keys_and_match_semantics(shared_silver):
    before = snapshot(shared_silver[0].parent)
    result = build_shared_gold(*shared_silver)
    assert result.returncode == 0, result.stderr
    gold = shared_silver[2] / "04_license"
    fact = pq.read_table(gold / "04_fact_inspection_license_match.parquet")
    assert fact.schema.field("inspection_key").type == pa.string()
    assert fact.select(["inspection_key", "source_license_number", "matched_license_event_id",
                        "match_status_cd", "source_row_num"]).to_pylist() == [
        {"inspection_key": "00101", "source_license_number": "0111", "matched_license_event_id": "0001",
         "match_status_cd": "UNIQUE_MATCH", "source_row_num": 50},
        {"inspection_key": "00102", "source_license_number": "0111", "matched_license_event_id": None,
         "match_status_cd": "NO_VALID_PERIOD", "source_row_num": 51},
    ]
    assert len(list(gold.glob("04_*.parquet"))) == 5
    assert snapshot(shared_silver[0].parent) == before


@pytest.mark.parametrize("invalid_type", (None, pa.int64()))
def test_gold_rejects_invalid_shared_inspection_dates_before_writing(shared_silver, invalid_type):
    licenses, inspections, gold = shared_silver
    table = pq.read_table(inspections)
    if invalid_type is None:
        table = table.drop(["inspection_dtm"])
    else:
        table = table.set_column(table.schema.get_field_index("inspection_dtm"), "inspection_dtm",
                                 pa.array([1, 2], type=invalid_type))
    pq.write_table(table, inspections)
    result = build_shared_gold(licenses, inspections, gold)
    assert result.returncode != 0
    assert "food_inspections.parquet" in result.stderr and "inspection_dtm" in result.stderr
    assert not gold.exists()


@pytest.mark.parametrize("stage", ("01_bronze", "02_silver", "03_gold"))
def test_raw_directory_cannot_be_inside_an_output_stage(project, stage):
    _, data, _ = project
    result = execute("01_bronze", project, ok=False,
                     extra=("--raw-dir", str(data / stage / "raw")))
    assert result.returncode == 1
    assert "must not overlap" in result.stderr


def test_bronze_records_utc_provenance_and_verifies_existing_outputs(project):
    raw, data, _ = project
    output = data / "01_bronze" / "04_license"
    manifest = output / "ingestion_manifest.json"
    execute("01_bronze", project)
    original = manifest.read_bytes()
    records = json.loads(original)["entries"]
    assert {row["table"]: row["row_count"] for row in records} == {
        "business_licenses": 4, "food_inspections": 7,
    }
    for row in records:
        assert row["status"] == "created"
        for field in ("source_read_started_at_utc", "bronze_created_at_utc", "recorded_at_utc"):
            assert datetime.fromisoformat(row[field]).utcoffset() == timezone.utc.utcoffset(None)
        assert row["source_sha256"] == hashlib.sha256((raw / row["source_file"]).read_bytes()).hexdigest()
        assert row["bronze_sha256"] == hashlib.sha256((output / row["bronze_file"]).read_bytes()).hexdigest()
    execute("01_bronze", project)
    assert manifest.read_bytes() == original
    execute("validate_bronze", project)

    manifest.unlink()  # Simulate Parquet produced before provenance was implemented.
    outputs = snapshot(output)
    missing = execute("validate_bronze", project, ok=False)
    assert missing.returncode == 1
    assert "ingestion manifest" in missing.stdout
    execute("01_bronze", project)
    current = snapshot(output)
    assert all(current[path] == digest for path, digest in outputs.items())
    backfilled = json.loads(manifest.read_bytes())
    assert all(row["status"] == "verified_existing" and row["bronze_created_at_utc"] is None
               for row in backfilled["entries"])
    execute("validate_bronze", project)

    entry = backfilled["entries"][0]
    original_hash = entry["source_sha256"]
    entry["source_sha256"] = "0" * 64
    manifest.write_text(json.dumps(backfilled), encoding="utf-8")
    tampered = execute("validate_bronze", project, ok=False)
    assert tampered.returncode == 1
    assert "source_sha256" in tampered.stdout

    entry["source_sha256"] = original_hash
    entry["recorded_at_utc"] = "2026-11-20T10:00:00+09:00"
    manifest.write_text(json.dumps(backfilled), encoding="utf-8")
    wrong_zone = execute("validate_bronze", project, ok=False)
    assert wrong_zone.returncode == 1
    assert "Expected a UTC timestamp: recorded_at_utc" in wrong_zone.stdout


def test_all_stages_preserve_inputs_and_produce_reproducible_results(project):
    raw, data, reports = project
    raw_hashes = snapshot(raw)
    for stage in STAGES:
        execute(stage, project)
    first_output = snapshot(data), snapshot(reports)
    for stage in STAGES:
        execute(stage, project)
    assert (snapshot(data), snapshot(reports)) == first_output
    assert snapshot(raw) == raw_hashes

    for table, expected in [("business_licenses", 4), ("food_inspections", 7)]:
        for layer in ("01_bronze", "02_silver"):
            path = data / layer / "04_license" / f"04_{table}.parquet"
            assert pq.ParquetFile(path).metadata.num_rows == expected

    path = data / "03_gold" / "04_license" / "04_fact_inspection_license_match.parquet"
    rows = pq.ParquetFile(path).read().to_pylist()
    assert [row["candidate_count_num"] for row in rows] == [1, 2, 1, 0, 0, 0, 0]
    assert [row["match_status_cd"] for row in rows] == [
        "UNIQUE_MATCH", "MULTIPLE_MATCHES", "UNIQUE_MATCH", "NO_VALID_PERIOD",
        "NO_LICENSE_NUMBER_MATCH", "MISSING_LICENSE_NUMBER", "MISSING_INSPECTION_DATE",
    ]
    assert rows[1]["matched_license_event_id"] is None
    assert rows[0]["establishment_key"] == "10:1"
    assert rows[2]["matched_license_event_id"] == "2"
    assert "D04-DQ-" in next(reports.glob("*.md")).read_text(encoding="utf-8")
    for validator in VALIDATORS:
        execute(validator, project)

    fact = pq.ParquetFile(path).read()
    corrupt = fact.set_column(fact.schema.get_field_index("establishment_key"),
                              "establishment_key", pa.array(["bogus"] * len(fact)))
    pq.write_table(corrupt, path)
    result = execute("validate_gold", project, ok=False)
    assert result.returncode == 1
    assert "FK" in result.stdout


def test_bronze_uses_configured_workbook_sheet_and_columns(tmp_path):
    openpyxl = pytest.importorskip("openpyxl")
    raw, data, reports = (tmp_path / name for name in ("raw", "data", "reports"))
    raw.mkdir()
    workbook = openpyxl.Workbook()
    workbook.active.title = "unused"
    sheet = workbook.create_sheet("licenses")
    sheet.append(["row_id", "description", "omitted"])
    sheet.append(["0001", "line 1\nline 2", "value"])
    sheet.append(["0002", None, "value"])
    workbook.save(raw / "custom.xlsx")
    workbook.close()
    write_csv(raw / "inspections.csv", ["event"], [[1]])
    config = tmp_path / "sources.yaml"
    config.write_text(
        "raw_root_env: CHICAGO_RAW_DIR\n"
        "sources:\n"
        "  business_licenses:\n"
        "    file: custom.xlsx\n"
        "    format: xlsx\n"
        "    sheet: licenses\n"
        "    columns: [description, row_id]\n"
        "  food_inspections:\n"
        "    file: inspections.csv\n",
        encoding="utf-8",
    )
    original = snapshot(raw)
    project = raw, data, reports
    extra = ("--sources-config", str(config))
    execute("01_bronze", project, extra=extra)
    execute("validate_bronze", project, extra=extra)
    assert snapshot(raw) == original
    result = pq.ParquetFile(data / "01_bronze" / "04_license" / "04_business_licenses.parquet").read()
    assert result.column_names == ["description", "row_id", "source_row_num"]
    assert result.to_pydict() == {
        "description": ["line 1\nline 2", ""], "row_id": ["0001", "0002"], "source_row_num": [1, 2],
    }


def test_gold_rejects_plausible_but_incorrect_fact_values(project):
    _, data, _ = project
    for stage in STAGES:
        execute(stage, project)
    facts = data / "03_gold" / "04_license"
    match = facts / "04_fact_inspection_license_match.parquet"
    events = facts / "04_fact_license_event.parquet"
    mutations = (
        (match, 1, {"candidate_count_num": 9}),
        (match, 3, {"match_status_cd": "NO_LICENSE_NUMBER_MATCH"}),
        (match, 0, {"match_status_cd": "NO_VALID_PERIOD", "candidate_count_num": 0,
                    "matched_license_event_id": None, "establishment_key": "__unknown__"}),
        (match, 1, {"result_cd": "PASS", "date_key": "2024-01-01"}),
        (events, 3, {"recorded_status_cd": "OTHER"}),
    )
    accepted = []
    for path, index, changes in mutations:
        original = path.read_bytes()
        fact = pq.read_table(path)
        rows = fact.to_pylist()
        rows[index].update(changes)
        try:
            pq.write_table(pa.Table.from_pylist(rows, schema=fact.schema), path)
            result = execute("validate_gold", project, ok=False)
            if result.returncode != 1 or "recomputed from Silver" not in result.stdout:
                accepted.append((changes, result.stdout, result.stderr))
        finally:
            path.write_bytes(original)
    assert not accepted


def test_incoming_rows_flow_to_gold_and_preserve_original_snapshots(project, tmp_path):
    raw, _, _ = project
    incoming = tmp_path / "incoming"
    incoming.mkdir()
    inspections = incoming / "food_inspections.csv"
    columns = ["Results", "Inspection Date", "License #", "Inspection ID"]
    rows = [["Fail", "01/10/2024", "333", "105"], ["Fail", "01/10/2024", "111", "108"]]
    write_csv(inspections, columns, rows)
    with (raw / "business_licenses.csv").open(encoding="utf-8", newline="") as stream:
        data_rows = csv.reader(stream)
        next(data_rows)
        event = next(data_rows)
    event[:3] = ["source-5", "5", "333"]
    write_csv(incoming / "business_licenses.csv", LICENSE_COLUMNS, [event])
    before = snapshot(raw), snapshot(incoming)
    combined = tmp_path / "combined"
    options = ("--delta-dir", str(incoming), "--combined-raw-dir", str(combined))
    execute("run_pipeline", project, extra=options)
    assert (snapshot(raw), snapshot(incoming)) == before

    manifest = json.loads((combined / "merge_manifest.json").read_bytes())
    for entry in manifest["entries"]:
        assert entry["inserted_rows"] == 1
        assert entry["result_sha256"] == snapshot(combined)[entry["file"]]
    assert next(entry for entry in manifest["entries"] if entry["table"] == "food_inspections")["updated_rows"] == 1
    updated_project = combined, *project[1:]
    execute("run_pipeline", updated_project, extra=("--start-at", "silver"))
    execute("run_pipeline", updated_project, extra=("--validate-only",))
    _, data, _ = project
    fact = pq.read_table(data / "03_gold/04_license/04_fact_inspection_license_match.parquet")
    matches = {row["inspection_key"]: row for row in fact.to_pylist()}
    assert matches["105"]["matched_license_event_id"] == "5"
    assert matches["105"]["result_cd"] == "FAIL"
    assert matches["108"]["candidate_count_num"] == 2

    compared = snapshot(combined)
    write_csv(inspections, columns, rows + [["Pass", "01/10/2024", "333", "105"]])
    failed = execute("run_pipeline", project, ok=False, extra=options)
    assert failed.returncode == 1 and "conflicting incoming rows" in failed.stderr
    assert snapshot(combined) == compared
