import csv
import hashlib
import subprocess
import sys
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
    raw, data, reports = (tmp_path / name for name in ("raw", "data", "reports"))
    raw.mkdir()

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
        for layer in ("bronze", "silver"):
            path = data / layer / "04_license" / (table + ".parquet")
            assert pq.ParquetFile(path).metadata.num_rows == expected

    path = data / "gold" / "facts" / "04_license" / "fact_inspection_license_match.parquet"
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
    result = pq.ParquetFile(data / "bronze" / "04_license" / "business_licenses.parquet").read()
    assert result.column_names == ["description", "row_id", "source_row_num"]
    assert result.to_pydict() == {
        "description": ["line 1\nline 2", ""], "row_id": ["0001", "0002"], "source_row_num": [1, 2],
    }
