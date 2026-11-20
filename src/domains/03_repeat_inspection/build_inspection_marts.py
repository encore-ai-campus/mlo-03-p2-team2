import json
import re
import tempfile
from argparse import ArgumentParser
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from hashlib import file_digest
from itertools import islice
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from inspection_mart_report import build_report
from violation_inputs import load_domain02_violations


PROJECT = Path(__file__).resolve().parents[3]
DOMAIN = "03_repeat_inspection"
SILVER_DIR = PROJECT / "data" / "02_silver" / DOMAIN
GOLD_DIR = PROJECT / "data" / "03_gold" / DOMAIN
REPORT_DIR = PROJECT / "reports" / "runs" / DOMAIN
VIOLATION_START = date(2018, 7, 1)
REINSPECTION_MAX_DAYS = 30
COMPARABLE_RESULTS = {"FAIL", "PASS", "PASS W/ CONDITIONS"}
REINSPECTION_TYPE = re.compile(r"\bre[\s-]*inspection\b", re.IGNORECASE)
VIOLATION_PREFIX = re.compile(r"^\s*([1-9][0-9]*)\.\s+\S")

HISTORY_SCHEMA = pa.schema([
    ("inspection_key", pa.string()),
    ("license_number_key", pa.string()),
    ("inspection_dtm", pa.date32()),
    ("inspection_type", pa.string()),
    ("result_cd", pa.string()),
    ("source_row_num", pa.int64()),
    ("same_day_inspection_count", pa.int64()),
    ("previous_inspection_key", pa.string()),
    ("next_inspection_key", pa.string()),
    ("history_status_cd", pa.string()),
])
PAIR_FIELDS = [
    ("base_inspection_key", pa.string()),
    ("followup_inspection_key", pa.string()),
    ("license_number_key", pa.string()),
    ("base_inspection_dtm", pa.date32()),
    ("followup_inspection_dtm", pa.date32()),
    ("days_to_followup_num", pa.int64()),
    ("base_result_cd", pa.string()),
    ("followup_result_cd", pa.string()),
]
REPEAT_SCHEMA = pa.schema(PAIR_FIELDS + [
    ("code_system_version", pa.string()),
    ("violation_cd", pa.string()),
    ("repeat_flag", pa.bool_()),
    ("base_violation_parse_status_cd", pa.string()),
    ("followup_violation_parse_status_cd", pa.string()),
    ("comparison_status_cd", pa.string()),
])
REINSPECTION_SCHEMA = pa.schema(PAIR_FIELDS + [
    ("followup_inspection_type", pa.string()),
    ("reinspection_match_status_cd", pa.string()),
    ("reinspection_window_cd", pa.string()),
])


@dataclass(slots=True)
class Inspection:
    inspection_key: str
    license_number_key: str | None
    inspection_dtm: date | None
    inspection_type: str | None
    result_cd: str | None
    source_row_num: int


def parse_violations(text):
    if not text or not text.strip():
        return set(), "missing"
    codes = set()
    unparsed = False
    for part in text.split("|"):
        match = VIOLATION_PREFIX.match(part)
        if match:
            codes.add(match[1])
        else:
            unparsed = True
    if unparsed:
        return codes, "partial" if codes else "unparsed"
    return codes, "parsed"


def load_fact(fact):
    rows = []
    violations = {}
    keys = set()
    for batch in fact.iter_batches(columns=[*Inspection.__annotations__, "violations_text"]):
        for record in batch.to_pylist():
            text = record.pop("violations_text")
            row = Inspection(**record)
            if not row.inspection_key or row.inspection_key in keys:
                raise ValueError(f"Empty or duplicate inspection_key at source row {row.source_row_num}")
            keys.add(row.inspection_key)
            rows.append(row)
            if row.inspection_dtm and row.inspection_dtm >= VIOLATION_START:
                if row.result_cd in COMPARABLE_RESULTS:
                    violations[row.inspection_key] = parse_violations(text)
    return rows, violations


def group_history(rows):
    by_license = defaultdict(lambda: defaultdict(list))
    for row in rows:
        if row.license_number_key and row.inspection_dtm:
            by_license[row.license_number_key][row.inspection_dtm].append(row)
    return [sorted(days.items()) for days in by_license.values()]


def history_rows(rows, histories):
    for days in sorted(histories, key=lambda history: history[0][1][0].license_number_key):
        for index, (_, same_day) in enumerate(days):
            previous = days[index - 1][1] if index else []
            following = days[index + 1][1] if index + 1 < len(days) else []
            for row in same_day:
                yield {
                    **{column: getattr(row, column) for column in Inspection.__annotations__},
                    "same_day_inspection_count": len(same_day),
                    "previous_inspection_key": previous[0].inspection_key if len(same_day) == len(previous) == 1 else None,
                    "next_inspection_key": following[0].inspection_key if len(same_day) == len(following) == 1 else None,
                    "history_status_cd": "dated" if len(same_day) == 1 else "ambiguous_same_day",
                }
    for row in rows:
        if not row.license_number_key or row.inspection_dtm is None:
            yield {
                **{column: getattr(row, column) for column in Inspection.__annotations__},
                "history_status_cd": "missing_license" if not row.license_number_key else "missing_date",
            }


def pair_record(base, followup):
    return {
        "base_inspection_key": base.inspection_key,
        "followup_inspection_key": followup.inspection_key if followup else None,
        "license_number_key": base.license_number_key,
        "base_inspection_dtm": base.inspection_dtm,
        "followup_inspection_dtm": followup.inspection_dtm if followup else None,
        "days_to_followup_num": (followup.inspection_dtm - base.inspection_dtm).days if followup else None,
        "base_result_cd": base.result_cd,
        "followup_result_cd": followup.result_cd if followup else None,
    }


def repeat_rows(histories, violations):
    for history in histories:
        comparable_days = []
        for day, rows in history:
            if day >= VIOLATION_START:
                comparable = [row for row in rows if row.result_cd in COMPARABLE_RESULTS]
                if comparable:
                    comparable_days.append(comparable)
        for index, same_day in enumerate(comparable_days):
            following = comparable_days[index + 1] if index + 1 < len(comparable_days) else []
            followup = following[0] if len(same_day) == len(following) == 1 else None
            followup_codes, followup_parse = violations[followup.inspection_key] if followup else (set(), None)
            for base in same_day:
                codes, base_parse = violations[base.inspection_key]
                status = "comparable"
                if len(same_day) > 1 or len(following) > 1:
                    status = "ambiguous_same_day"
                elif not followup:
                    status = "no_followup"
                elif base_parse != "parsed":
                    status = "base_violations_unconfirmed"
                elif followup_parse != "parsed":
                    status = "followup_violations_unconfirmed"
                for code in sorted(codes):
                    yield {
                        **pair_record(base, followup),
                        "code_system_version": VIOLATION_START.isoformat(),
                        "violation_cd": code,
                        "repeat_flag": code in followup_codes if status == "comparable" else None,
                        "base_violation_parse_status_cd": base_parse,
                        "followup_violation_parse_status_cd": followup_parse,
                        "comparison_status_cd": status,
                    }


def reinspection_rows(rows, histories, observation_end):
    matches = {}
    for history in histories:
        previous_failures = []
        for day, same_day in history:
            failures = [row for row in same_day if row.result_cd == "FAIL"]
            candidates = [row for row in same_day if REINSPECTION_TYPE.search(row.inspection_type or "")]
            if candidates and previous_failures and (
                1 <= (day - previous_failures[0].inspection_dtm).days <= REINSPECTION_MAX_DAYS
            ):
                other_failure = any(failure not in candidates for failure in failures)
                ambiguous = len(previous_failures) > 1 or len(candidates) > 1 or other_failure
                match = (None, "ambiguous_same_day") if ambiguous else (candidates[0], "matched")
                for base in previous_failures:
                    matches.setdefault(base.inspection_key, match)
            if candidates and failures:
                for base in failures:
                    if any(candidate.inspection_key != base.inspection_key for candidate in candidates):
                        matches.setdefault(base.inspection_key, (None, "ambiguous_same_day"))
            if failures:
                previous_failures = failures

    for base in rows:
        if base.result_cd != "FAIL":
            continue
        followup = None
        if not base.license_number_key:
            status = "missing_license"
        elif base.inspection_dtm is None:
            status = "missing_date"
        elif base.inspection_key in matches:
            followup, status = matches[base.inspection_key]
        elif (observation_end - base.inspection_dtm).days < REINSPECTION_MAX_DAYS:
            status = "insufficient_observation"
        else:
            status = "not_observed"
        record = pair_record(base, followup)
        yield {
            **record,
            "followup_inspection_type": followup.inspection_type if followup else None,
            "reinspection_match_status_cd": status,
            "reinspection_window_cd": "within_30_days" if followup else None,
        }


def write_parquet(path, schema, metadata, records):
    schema = schema.with_metadata(metadata)
    with pq.ParquetWriter(path, schema, compression="zstd") as writer:
        records = iter(records)
        while batch := list(islice(records, 10_000)):
            writer.write_table(pa.Table.from_pylist(batch, schema=schema))


def inspection_metadata(fact, fact_path, manifest_path):
    metadata = {
        key: value for key, value in (fact.schema_arrow.metadata or {}).items()
        if key in {b"source_sha256", b"snapshot_date", b"code_map"}
    }
    if manifest_path is not None:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        with fact_path.open("rb") as file:
            artifact_sha = file_digest(file, "sha256").hexdigest()
        if manifest["artifacts"].get(fact_path.name) != artifact_sha:
            raise ValueError("Inspection Silver SHA-256 differs from its manifest")
        if fact.metadata.num_rows != manifest["silver_rows"]:
            raise ValueError("Inspection Silver row count differs from its manifest")
        source_sha = manifest["source_sha256"].lower().encode("ascii")
        if metadata.get(b"source_sha256", source_sha).lower() != source_sha:
            raise ValueError("Inspection Silver source SHA-256 differs from its manifest")
        metadata[b"source_sha256"] = source_sha
        metadata[b"inspection_silver_sha256"] = artifact_sha.encode("ascii")
    return metadata


def build(fact_path, silver_dir, gold_dir, report_dir=None, *, domain02_root=None, inspection_manifest=None):
    fact = pq.ParquetFile(fact_path)
    metadata = inspection_metadata(fact, fact_path, inspection_manifest)
    rows, violations = load_fact(fact)
    observation_end = max(row.inspection_dtm for row in rows if row.inspection_dtm)
    histories = group_history(rows)
    baseline = None
    if domain02_root is not None:
        team_violations = load_domain02_violations(
            domain02_root, metadata.get(b"source_sha256"), rows, violations
        )
        eligible = repeated = 0
        for row in repeat_rows(histories, violations):
            flag = row["repeat_flag"]
            eligible += flag is not None
            repeated += flag is True
        baseline = (eligible, repeated)
        violations = team_violations
    metadata.update({
        b"violation_start": VIOLATION_START.isoformat().encode(),
        b"reinspection_early_cutoff_days": str(REINSPECTION_MAX_DAYS).encode(),
        b"observation_end": observation_end.isoformat().encode(),
    })
    silver_dir.mkdir(parents=True, exist_ok=True)
    gold_dir.mkdir(parents=True, exist_ok=True)
    if report_dir is None:
        report_dir = gold_dir
    report_dir.mkdir(parents=True, exist_ok=True)
    with (
        tempfile.TemporaryDirectory(dir=silver_dir) as staged_silver,
        tempfile.TemporaryDirectory(dir=gold_dir) as staged_gold,
        tempfile.TemporaryDirectory(dir=report_dir) as staged_report,
    ):
        history = Path(staged_silver) / "03_inspection_history.parquet"
        repeat = Path(staged_gold) / "03_repeat_violation_mart.parquet"
        reinspection = Path(staged_gold) / "03_inspection_reinspection_mart.parquet"
        report = Path(staged_report) / "inspection_analysis.html"
        write_parquet(history, HISTORY_SCHEMA, metadata, history_rows(rows, histories))
        repeat_metadata = {
            **metadata, b"violation_source": b"domain02" if baseline is not None else b"domain03_local",
        }
        write_parquet(repeat, REPEAT_SCHEMA, repeat_metadata, repeat_rows(histories, violations))
        write_parquet(reinspection, REINSPECTION_SCHEMA, metadata, reinspection_rows(rows, histories, observation_end))
        report.write_text(build_report(repeat, reinspection, observation_end, baseline=baseline), encoding="utf-8")
        history.replace(silver_dir / history.name)
        for path in (repeat, reinspection):
            path.replace(gold_dir / path.name)
        report.replace(report_dir / report.name)


def main():
    parser = ArgumentParser(description="Build inspection history and both analysis marts.")
    parser.add_argument("--fact", type=Path, help="Input inspection Silver Parquet")
    parser.add_argument("--inspection-manifest", type=Path, help="Domain 01 Silver provenance manifest")
    parser.add_argument("--silver-dir", type=Path)
    parser.add_argument("--gold-dir", type=Path)
    parser.add_argument("--report-dir", type=Path, help="Directory for the generated HTML report")
    parser.add_argument("--domain02-root", type=Path, help="Root containing Domain 02 Parquet and reconciliation report")
    args = parser.parse_args()
    team_mode = args.domain02_root is not None
    if team_mode and args.fact is None:
        parser.error("--domain02-root requires --fact with the inspection Silver path")
    silver_dir = args.silver_dir or SILVER_DIR
    gold_dir = args.gold_dir or GOLD_DIR
    report_dir = args.report_dir
    if report_dir is None and gold_dir == GOLD_DIR:
        report_dir = REPORT_DIR / "team" if team_mode else REPORT_DIR
    build(
        args.fact or SILVER_DIR / "03_food_inspections.parquet", silver_dir, gold_dir,
        report_dir, domain02_root=args.domain02_root, inspection_manifest=args.inspection_manifest,
    )


if __name__ == "__main__":
    main()
