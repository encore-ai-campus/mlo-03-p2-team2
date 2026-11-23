"""Export the draft 05 handoff from one reconciled 02 run and matching 01 Silver."""

import argparse
from collections import Counter, defaultdict
from datetime import date
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import pyarrow as pa
import pyarrow.parquet as pq

from .profiling import sha256
from .reconciliation import ACCEPTED_RELATIVE, QUARANTINE_RELATIVE, REPORT_RELATIVE


INSPECTIONS = Path("data/02_silver/01_inspection/01_food_inspections.parquet")
INSPECTION_MANIFEST = INSPECTIONS.parent / "metadata/inspection_silver_manifest.json"
FRAGMENTS = {"accepted": ACCEPTED_RELATIVE, "quarantined": QUARANTINE_RELATIVE}
CODE_COLUMNS = ("inspection_key", "code_system_version", "violation_cd")
OBSERVATION_COLUMNS = ("inspection_key", "violation_observation_status")
SOURCE_START = date(2010, 1, 1)
PROCEDURE_CHANGE = date(2018, 7, 1)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def fingerprints(paths):
    return {role: {"path": str(path), "sha256": sha256(path)} for role, path in paths.items()}


def load_inspections(path):
    columns = ("inspection_key", "source_row_num", "inspection_dtm", "violations_text")
    rows = pq.read_table(path, columns=list(columns)).to_pylist()
    by_key = {}
    source_rows = set()
    for row in rows:
        key = row["inspection_key"]
        source_row = row["source_row_num"]
        require(isinstance(key, str) and key.strip() and key not in by_key,
                f"Empty or duplicate 01 inspection key: {key!r}")
        require(isinstance(source_row, int) and source_row > 0 and source_row not in source_rows,
                f"Invalid or duplicate 01 source row: {source_row!r}")
        source_rows.add(source_row)
        by_key[key] = row
    return by_key


def load_fragments(paths, inspections, counts, *, include_descriptions=False):
    accepted = defaultdict(dict)
    quarantined = set()
    columns = ["inspection_id", "source_row_num", "violation_code", "parsing_status"]
    for kind in FRAGMENTS:
        details = ["item_sequence_num", "violation_description"] if include_descriptions and kind == "accepted" else []
        with pq.ParquetFile(paths[kind]) as parquet:
            require(parquet.metadata.num_rows == counts[kind], f"02 {kind} row count differs from reconciliation")
            for batch in parquet.iter_batches(columns=[*columns, *details]):
                for row in batch.to_pylist():
                    key = row["inspection_id"]
                    require(key in inspections and inspections[key]["source_row_num"] == row["source_row_num"],
                            f"01 and 02 lineage differs for inspection {key!r}")
                    if kind == "quarantined":
                        quarantined.add(key)
                        continue
                    code = row["violation_code"]
                    require(row["parsing_status"] == "PARSED" and isinstance(code, str) and bool(code.strip()),
                            f"Invalid accepted code for inspection {key!r}")
                    sequence = row.get("item_sequence_num", 0)
                    earlier = accepted[key].get(code)
                    if earlier is None or sequence < earlier[0]:
                        accepted[key][code] = (sequence, row.get("violation_description"))
    return accepted, quarantined


def procedure_version(inspection_date):
    if inspection_date is None or inspection_date < SOURCE_START:
        return None
    if inspection_date < PROCEDURE_CHANGE:
        return "pre_2018_07_01"
    return "from_2018_07_01"


def build_rows(inspections, accepted, quarantined, *, include_descriptions=False):
    observations = []
    codes = []
    excluded = Counter({"inspections": 0, "distinct_code_rows": 0})
    for key, row in sorted(inspections.items(), key=lambda item: item[1]["source_row_num"]):
        approved = accepted.get(key, ())
        rejected = key in quarantined
        raw_present = bool((row["violations_text"] or "").strip())
        require(raw_present == bool(approved or rejected), f"Raw and fragment coverage differ for {key!r}")
        if not raw_present:
            status = "raw_missing"
        elif not approved:
            status = "unrecognized"
        elif rejected:
            status = "partial"
        else:
            status = "parsed"
        observations.append((key, status))
        era = procedure_version(row["inspection_dtm"])
        if era is None and approved:
            excluded.update(inspections=1, distinct_code_rows=len(approved))
        elif approved:
            for code in sorted(approved):
                row_key = (key, era, code)
                codes.append((*row_key, approved[code][1]) if include_descriptions else row_key)
    return codes, observations, dict(excluded)


def write_verified(directory, name, rows, columns):
    schema = pa.schema([pa.field(column, pa.string(), nullable=column == "description_text") for column in columns])
    arrays = tuple(zip(*rows, strict=True)) if rows else [[] for _ in columns]
    table = pa.Table.from_arrays(arrays, schema=schema)
    path = directory / name
    pq.write_table(table, path)
    require(pq.read_table(path).equals(table), f"Parquet round-trip differs for {name}")
    return {"rows": len(table), "sha256": sha256(path)}


def export_sample(root02, root01, output, *, inspection_path=None, inspection_manifest=None):
    """Project reconciled violations using legacy or explicitly supplied inspection Silver."""
    require(not output.exists(), f"Sample destination already exists: {output}")
    include_descriptions = inspection_path is not None
    inputs = {
        "inspection_silver": Path(inspection_path) if inspection_path is not None else root01 / INSPECTIONS,
        "inspection_manifest": (Path(inspection_manifest) if inspection_manifest is not None
                                else root01 / INSPECTION_MANIFEST),
        "reconciliation": root02 / REPORT_RELATIVE,
        **{kind: root02 / path for kind, path in FRAGMENTS.items()},
    }
    provenance = fingerprints(inputs)
    manifest = json.loads(inputs["inspection_manifest"].read_text(encoding="utf-8"))
    report = json.loads(inputs["reconciliation"].read_text(encoding="utf-8"))
    counts = report["counts"]
    require(report["status"] == "PASS" and not any(report["issues"].values()), "02 reconciliation must pass")
    require(manifest["source_sha256"] == report["origin_sha256"], "01 and 02 source SHA-256 differ")
    artifact_key = inputs["inspection_silver"].name if inspection_path is not None else INSPECTIONS.as_posix()
    require(manifest["artifacts"].get(artifact_key) == provenance["inspection_silver"]["sha256"],
            "01 Silver SHA-256 differs from its manifest")
    require(counts["accepted"] + counts["quarantined"] == counts["candidate_fragments"],
            "02 fragment counts do not reconcile")

    inspections = load_inspections(inputs["inspection_silver"])
    require(len(inspections) == manifest["silver_rows"] == counts["bronze_inspections"],
            "01 Silver and 02 Bronze row counts differ")
    accepted, quarantined = load_fragments(inputs, inspections, counts, include_descriptions=include_descriptions)
    codes, observations, excluded = build_rows(inspections, accepted, quarantined,
                                               include_descriptions=include_descriptions)
    statuses = {key: status for key, status in observations}
    status_counts = Counter(statuses.values())
    require(len(statuses) == len(observations) and statuses.keys() == inspections.keys(),
            "Observations must contain exactly one row for every inspection key")
    require(status_counts["raw_missing"] == counts["empty_inspections"]
            and len(statuses) - status_counts["raw_missing"] == counts["nonblank_inspections"],
            "Observation coverage does not reconcile with 02 Bronze")
    require(len({row[:3] for row in codes}) == len(codes), "Duplicate inspection, procedure era and code")
    require(all(statuses.get(row[0]) in {"parsed", "partial"} for row in codes),
            "Code rows must reference parsed or partial observations")
    require(len(codes) + excluded["distinct_code_rows"] == sum(map(len, accepted.values())),
            "Distinct approved code rows do not reconcile")
    require(fingerprints(inputs) == provenance, "An input artifact changed during export")
    if inspection_path is not None:
        root = root02.resolve()
        for role, path in inputs.items():
            resolved = path.resolve()
            if resolved.is_relative_to(root):
                provenance[role]["path"] = resolved.relative_to(root).as_posix()

    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=output.parent) as temporary:
        stage = Path(temporary) / "sample"
        stage.mkdir()
        code_columns = (*CODE_COLUMNS, "description_text") if include_descriptions else CODE_COLUMNS
        artifacts = {
            "inspection_violation_codes.parquet": write_verified(
                stage, "inspection_violation_codes.parquet", codes, code_columns,
            ),
            "inspection_violation_observations.parquet": write_verified(
                stage, "inspection_violation_observations.parquet", observations, OBSERVATION_COLUMNS,
            ),
        }
        verification = {
            "status": "PASS",
            "schema": "02-to-05-draft-v1",
            "source_sha256": report["origin_sha256"],
            "inputs": provenance,
            "source_counts": counts,
            "observation_counts": dict(sorted(status_counts.items())),
            "code_counts_by_version": dict(sorted(Counter(row[1] for row in codes).items())),
            "excluded_without_procedure_version": excluded,
            "duplicate_code_keys": 0,
            "duplicate_observation_keys": 0,
            "orphan_code_rows": 0,
            "artifacts": artifacts,
        }
        (stage / "verification.json").write_text(json.dumps(verification, indent=2) + "\n", encoding="utf-8")
        stage.rename(output)
    return verification


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--domain02-root", type=Path, required=True)
    parser.add_argument("--domain01-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    result = export_sample(args.domain02_root, args.domain01_root, args.output_dir)
    for name, info in result["artifacts"].items():
        print(f"{name}: {info['rows']:,} rows, SHA-256 {info['sha256']}")


if __name__ == "__main__":
    main()
