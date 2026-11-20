"""Build the Violations star from accepted Silver only.

Run: python -m src.domains.02_violation.gold
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import uuid

import pyarrow as pa
import pyarrow.parquet as pq

from src.bronze.paths import PROJECT_ROOT
from .profiling import sha256
from .reconciliation import ACCEPTED_RELATIVE, QUARANTINE_RELATIVE, REPORT_RELATIVE


DIM_RELATIVE = Path("data/03_gold/02_violation/02_dim_violation.parquet")
FACT_RELATIVE = Path("data/03_gold/02_violation/02_fact_inspection_violation.parquet")
MAPPING_RELATIVE = Path("metadata/standards/02_violation/violations_gold_mapping.csv")
LOG_RELATIVE = Path("logs/02_violation/violations_gold_runs.jsonl")
DIM_SCHEMA = pa.schema([
    pa.field("violation_key", pa.int32(), nullable=False),
    pa.field("violation_code", pa.string(), nullable=False),
    pa.field("violation_description", pa.string(), nullable=False),
])
FACT_SCHEMA = pa.schema([
    pa.field("source_row_num", pa.int64(), nullable=False),
    pa.field("item_sequence_num", pa.int32(), nullable=False),
    pa.field("inspection_id", pa.string(), nullable=False),
    pa.field("violation_key", pa.int32(), nullable=False),
    pa.field("violation_comments", pa.string(), nullable=False),
    pa.field("source_violations_fragment", pa.string(), nullable=False),
])
CHUNK = 20_000


def rows(path: Path, columns: list[str] | None = None):
    for batch in pq.ParquetFile(path).iter_batches(batch_size=CHUNK, columns=columns):
        yield from batch.to_pylist()


def content_hash(path: Path) -> str:
    digest = hashlib.sha256()
    for row in rows(path):
        digest.update(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def dimension_members(accepted: Path) -> list[dict]:
    """Sort observed pairs, so keys never depend on input row order."""
    pairs = set()
    for row in rows(accepted, ["violation_code", "violation_description"]):
        pair = row["violation_code"], row["violation_description"]
        if not all(pair):
            raise ValueError("Accepted Silver contains a missing code/description")
        pairs.add(pair)
    return [dict(violation_key=i, violation_code=code, violation_description=description)
            for i, (code, description) in enumerate(sorted(pairs), start=1)]


def validate_inputs(root: Path) -> dict:
    accepted, quarantine, report_path = (root / path for path in
        (ACCEPTED_RELATIVE, QUARANTINE_RELATIVE, REPORT_RELATIVE))
    if not all(path.is_file() for path in (accepted, quarantine, report_path)):
        raise FileNotFoundError("Accepted Silver, quarantine, or reconciliation report missing")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if report["status"] != "PASS" or any(report["issues"].values()):
        raise ValueError("Silver reconciliation report failed")
    accepted_count = pq.ParquetFile(accepted).metadata.num_rows
    quarantine_count = pq.ParquetFile(quarantine).metadata.num_rows
    candidate_count = report["counts"]["candidate_fragments"]
    if accepted_count + quarantine_count != candidate_count:
        raise ValueError("Accepted + quarantine != candidate fragments")
    if accepted_count != report["counts"]["accepted"] or quarantine_count != report["counts"]["quarantined"]:
        raise ValueError("Current inputs differ from reconciliation report")
    if content_hash(accepted) != report["accepted_content_sha256"] or content_hash(quarantine) != report["quarantine_content_sha256"]:
        raise ValueError("Input content differs from reconciliation report")
    return {"accepted": accepted_count, "quarantined": quarantine_count, "candidate_fragments": candidate_count}


def _publish(temp: Path, final: Path) -> None:
    if final.exists():
        if sha256(temp) != sha256(final):
            raise FileExistsError(f"Existing Gold output differs: {final}")
        temp.unlink()
    else:
        os.replace(temp, final)


def build(root: Path = PROJECT_ROOT, output_root: Path | None = None) -> dict:
    root = Path(root)
    output_root = Path(output_root) if output_root is not None else root
    counts = validate_inputs(root)
    accepted = root / ACCEPTED_RELATIVE
    quarantine = root / QUARANTINE_RELATIVE
    protected = {str(path): sha256(path) for path in (accepted, quarantine)}
    started_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    members = dimension_members(accepted)
    pair_to_key = {(m["violation_code"], m["violation_description"]): m["violation_key"] for m in members}
    if len(pair_to_key) != len(members) or len({m["violation_key"] for m in members}) != len(members):
        raise ValueError("Duplicate dimension grain or surrogate key")
    code_descriptions = defaultdict(set)
    for m in members:
        code_descriptions[m["violation_code"]].add(m["violation_description"])
    dim_path, fact_path = output_root / DIM_RELATIVE, output_root / FACT_RELATIVE
    for path in (dim_path, fact_path):
        path.parent.mkdir(parents=True, exist_ok=True)
    token = uuid.uuid4().hex
    dim_temp = dim_path.with_name(dim_path.name + f".{token}.tmp")
    fact_temp = fact_path.with_name(fact_path.name + f".{token}.tmp")
    grain = set()
    fact_count = 0
    nulls = Counter()
    try:
        pq.write_table(pa.Table.from_pylist(members, schema=DIM_SCHEMA), dim_temp)
        with pq.ParquetWriter(fact_temp, FACT_SCHEMA) as writer:
            for batch in pq.ParquetFile(accepted).iter_batches(batch_size=CHUNK):
                output = []
                for row in batch.to_pylist():
                    identifier = (row["source_row_num"], row["item_sequence_num"])
                    if identifier in grain:
                        raise ValueError(f"Duplicate accepted fragment grain: {identifier}")
                    grain.add(identifier)
                    pair = row["violation_code"], row["violation_description"]
                    if pair not in pair_to_key or row["parsing_status"] != "PARSED":
                        raise ValueError(f"Invalid accepted fragment: {identifier}")
                    fact = {name: row[name] for name in FACT_SCHEMA.names if name != "violation_key"}
                    fact["violation_key"] = pair_to_key[pair]
                    for name, value in fact.items():
                        nulls[name] += value is None
                    if any(value is None for value in fact.values()):
                        raise ValueError(f"Null fact field: {identifier}")
                    output.append(fact)
                writer.write_table(pa.Table.from_pylist(output, schema=FACT_SCHEMA))
                fact_count += len(output)
        if fact_count != counts["accepted"]:
            raise ValueError("Silver to Fact row count mismatch")
        if pq.ParquetFile(dim_temp).schema_arrow != DIM_SCHEMA or pq.ParquetFile(fact_temp).schema_arrow != FACT_SCHEMA:
            raise ValueError("Gold schema mismatch")
        if pq.ParquetFile(fact_temp).metadata.num_rows != fact_count:
            raise ValueError("Fact metadata count mismatch")
        # A row-by-row reverse join validates all keys, code/description, comments and lineage.
        dim_by_key = {m["violation_key"]: (m["violation_code"], m["violation_description"]) for m in rows(dim_temp)}
        if len(dim_by_key) != len(members) or set(dim_by_key.values()) != set(pair_to_key):
            raise ValueError("Published dimension differs from accepted code-description pairs")
        orphan = changed = 0
        for source, fact in zip(rows(accepted), rows(fact_temp), strict=True):
            pair = dim_by_key.get(fact["violation_key"])
            orphan += pair is None
            changed += pair != (source["violation_code"], source["violation_description"])
            changed += any(fact[name] != source[name] for name in FACT_SCHEMA.names if name != "violation_key")
        if orphan or changed:
            raise ValueError(f"Gold reverse join mismatch: orphan={orphan}, changed={changed}")
        for path, digest in protected.items():
            if sha256(Path(path)) != digest:
                raise ValueError(f"Input changed: {path}")
        # Check both destinations before publishing either one.
        for temp, final in ((dim_temp, dim_path), (fact_temp, fact_path)):
            if final.exists() and sha256(temp) != sha256(final):
                raise FileExistsError(f"Existing Gold output differs: {final}")
        _publish(dim_temp, dim_path)
        _publish(fact_temp, fact_path)
        result = {
            "started_at_utc": started_at, "status": "PASS", "accepted": counts["accepted"],
            "quarantined": counts["quarantined"], "candidate_fragments": counts["candidate_fragments"],
            "dimension_rows": len(members), "fact_rows": fact_count, "codes": len(code_descriptions),
            "codes_with_multiple_descriptions": sum(len(v) > 1 for v in code_descriptions.values()),
            "duplicate_fact_grain": 0, "orphan_fk": orphan, "reverse_join_mismatch": changed,
            "fact_nulls": dict(nulls), "dimension_content_sha256": content_hash(dim_path),
            "fact_content_sha256": content_hash(fact_path), "dimension_schema": str(DIM_SCHEMA),
            "fact_schema": str(FACT_SCHEMA), "accepted_sha256": protected[str(accepted)],
            "quarantine_sha256": protected[str(quarantine)], "dimension_sha256": sha256(dim_path),
            "fact_sha256": sha256(fact_path),
        }
        log = root / LOG_RELATIVE
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(result, ensure_ascii=False) + "\n")
        return result
    finally:
        for temp in (dim_temp, fact_temp):
            temp.unlink(missing_ok=True)


if __name__ == "__main__":
    print(json.dumps(build(), ensure_ascii=False, indent=2))
