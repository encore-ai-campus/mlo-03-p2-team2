import json
from datetime import date
from pathlib import Path
from shutil import copyfile

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from src.ai_ready import build_inspection_training as pipeline
from src.ai_ready import inspection_training as training


PROJECT = Path(__file__).resolve().parents[2]
SOURCE_SHA = "a" * 64


def day(value):
    return date.fromisoformat(value)


def inspection(key, license_number, when, result, source_row):
    return {
        "inspection_key": key, "license_number_key": license_number,
        "inspection_dtm": day(when), "result_cd": result, "source_row_num": source_row,
    }


def recurrence(base, followup, code, repeat_flag, status="comparable"):
    return {
        "base_inspection_key": base["inspection_key"],
        "base_inspection_dtm": base["inspection_dtm"],
        "base_result_cd": base["result_cd"],
        "base_violation_parse_status_cd": "parsed",
        "license_number_key": base["license_number_key"],
        "followup_inspection_key": followup["inspection_key"] if followup else None,
        "followup_inspection_dtm": followup["inspection_dtm"] if followup else None,
        "followup_result_cd": followup["result_cd"] if followup else None,
        "followup_violation_parse_status_cd": "parsed" if followup else None,
        "days_to_followup_num": (followup["inspection_dtm"] - base["inspection_dtm"]).days if followup else None,
        "code_system_version": "2018-07-01",
        "violation_cd": code,
        "repeat_flag": repeat_flag,
        "comparison_status_cd": status,
    }


@pytest.fixture
def repository(tmp_path):
    paths = [pipeline.CONTRACT, pipeline.RECONCILIATION, pipeline.ORIGIN_03, pipeline.ORIGIN_04,
             *pipeline.CHECKSUMS, pipeline.INSPECTIONS, pipeline.VIOLATIONS, pipeline.QUARANTINE, pipeline.RECURRENCE]
    for relative in paths:
        (tmp_path / relative).parent.mkdir(parents=True, exist_ok=True)
    copyfile(PROJECT / pipeline.CONTRACT, tmp_path / pipeline.CONTRACT)

    old = inspection("old", "A", "2022-01-01", "FAIL", 1)
    prior = inspection("prior", "A", "2022-01-02", "FAIL", 2)
    same_day = inspection("same-day", "A", "2023-01-02", "NO ENTRY", 3)
    base = inspection("base", "A", "2023-01-02", "FAIL", 4)
    followup = inspection("followup", "A", "2023-01-04", "PASS W/ CONDITIONS", 5)
    crossing = inspection("crossing", "B", "2022-12-31", "PASS", 6)
    boundary = inspection("boundary", "B", "2023-01-01", "FAIL", 7)
    missing_license = inspection("missing", None, "2025-01-01", "PASS", 8)
    rows = [old, prior, same_day, base, followup, crossing, boundary, missing_license]
    source_records = [
        {"inspection_id": record["inspection_key"], "source_row_num": record["source_row_num"], "violation_code": code}
        for record, codes in ((old, ("55",)), (prior, ("47", "47")), (same_day, ("55",)),
                              (base, ("47", "55")), (followup, ("47",)), (crossing, ("47",)), (boundary, ("47",)))
        for code in codes
    ]
    pairs = [
        recurrence(base, followup, "47", True), recurrence(base, followup, "55", False),
        recurrence(crossing, boundary, "47", True), recurrence(boundary, None, "47", None, "no_followup"),
    ]
    pq.write_table(pa.Table.from_pylist(rows), tmp_path / pipeline.INSPECTIONS)
    pq.write_table(pa.Table.from_pylist(source_records), tmp_path / pipeline.VIOLATIONS)
    pq.write_table(pa.Table.from_pylist([{"inspection_id": "prior", "source_row_num": 2}]), tmp_path / pipeline.QUARANTINE)
    gold = pa.Table.from_pylist(pairs).replace_schema_metadata({
        "source_sha256": SOURCE_SHA, "violation_source": "domain02",
    })
    pq.write_table(gold, tmp_path / pipeline.RECURRENCE)
    for relative, value in (
        (pipeline.RECONCILIATION, {
            "status": "PASS", "issues": {}, "origin_sha256": SOURCE_SHA,
            "counts": {"bronze_inspections": len(rows), "accepted": len(source_records), "quarantined": 1},
        }),
        (pipeline.ORIGIN_03, {"sha256": SOURCE_SHA, "logical_row_count": len(rows)}),
        (pipeline.ORIGIN_04, {"entries": [{"table": "food_inspections", "source_sha256": SOURCE_SHA, "row_count": len(rows)}]}),
    ):
        (tmp_path / relative).write_text(json.dumps(value), encoding="utf-8")
    for manifest, files in pipeline.CHECKSUMS.items():
        (tmp_path / manifest).write_text(
            "".join(f"{pipeline.sha256(tmp_path / path)}  {path.as_posix()}\n" for path in files), encoding="utf-8",
        )
    return tmp_path


def test_release_uses_only_earlier_history_and_observed_same_split_labels(repository):
    target = pipeline.build(repository)
    contract = pipeline.read_json(repository / pipeline.CONTRACT)
    failure, recurrence_spec = contract["datasets"].values()
    failure_rows = {row["inspection_key"]: row for row in pq.read_table(target / failure["file"]).to_pylist()}
    row = failure_rows["base"]
    assert len(failure_rows) == 7
    assert "same-day" not in failure_rows
    assert row["latest_prior_inspection_dtm"] == day("2022-01-02")
    assert row["prior_inspection_count_num"] == row["prior_fail_count_num"] == 1
    assert row["prior_code_observed_inspection_count_num"] == 1
    assert row["prior_fully_parsed_inspection_count_num"] == 0
    assert row["label_fail_flag"] is True
    assert "base_result_cd" not in row and "violation_cd" not in row
    assert failure_rows["crossing"]["split_cd"] == "train"
    assert failure_rows["followup"]["label_fail_flag"] is False
    assert failure_rows["missing"]["split_cd"] == "test"
    assert failure_rows["missing"]["prior_inspection_count_num"] is None

    recurrence_rows = pq.read_table(target / recurrence_spec["file"]).to_pylist()
    assert [(row["inspection_key"], row["violation_cd"], row["label_repeat_flag"],
             row["prior_same_code_inspection_count_num"]) for row in recurrence_rows] == [
        ("base", "47", True, 1), ("base", "55", False, 0),
    ]
    assert all(row["label_observed_dtm"] == day("2023-01-04") and row["split_cd"] == "validation"
               for row in recurrence_rows)
    summary = pipeline.read_json(target / pipeline.SUMMARY)
    assert summary["recurrence_input_status_counts"] == {
        "comparable": 3, "excluded_cross_split_label": 1, "no_followup": 1,
    }
    assert pipeline.build(repository, verify_only=True) == pipeline.build(repository) == target

    with (target / failure["file"]).open("ab") as stream:
        stream.write(b"changed")
    with pytest.raises(ValueError, match="artifact SHA-256 mismatch"):
        pipeline.build(repository, verify_only=True)


def test_rejects_input_from_different_published_snapshot(repository):
    with (repository / pipeline.VIOLATIONS).open("ab") as stream:
        stream.write(b"changed")
    with pytest.raises(ValueError, match="Published Parquet SHA-256 mismatch"):
        pipeline.build(repository)
    assert not (repository / pipeline.OUTPUT).exists()


def test_rejects_incorrect_label_and_code_history_respects_code_version(repository):
    rules = training.Rules.from_contract(pipeline.read_json(repository / pipeline.CONTRACT))
    inspections = pipeline.read_inspections(repository / pipeline.INSPECTIONS)
    codes, rejected = pipeline.read_codes(repository / pipeline.VIOLATIONS, repository / pipeline.QUARANTINE, inspections)
    label = next(pipeline.parquet_rows(repository / pipeline.RECURRENCE))
    with pytest.raises(ValueError, match="target and observed follow-up disagree"):
        training.load_recurrence_labels([dict(label, repeat_flag=False)], inspections, codes, rejected, rules)

    records = [training.Inspection("early", "A", day("2018-06-30"), "FAIL", 1),
               training.Inspection("late", "A", day("2018-07-02"), "FAIL", 2)]
    for record, history, counts in training.histories(records, {"early": {"47"}}, set(), rules):
        if record.key == "late":
            assert history["prior_code_observed_inspection_count_num"] == 1
            assert counts[("2018-07-01", "47")] == 0
            assert counts[("pre_2018-07-01", "47")] == 1
