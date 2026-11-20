import json
from collections import defaultdict

import pyarrow.parquet as pq


ACCEPTED = "data/02_silver/food_inspections/violations/inspection_violations_accepted.parquet"
QUARANTINE = "data/quarantine/food_inspections/violations/inspection_violations_quarantine.parquet"
RECONCILIATION = "reports/quality/violations_reconciliation.json"


def load_domain02_violations(root, source_sha, inspections, baseline):
    report = json.loads((root / RECONCILIATION).read_text(encoding="utf-8"))
    if report["status"] != "PASS" or any(report["issues"].values()):
        raise ValueError("Domain 02 violation reconciliation must pass")
    if not source_sha or report["origin_sha256"].lower() != source_sha.decode("ascii").lower():
        raise ValueError("Inspection Silver and Domain 02 must come from the same source SHA-256")

    source_rows = {row.inspection_key: row.source_row_num for row in inspections}
    codes = defaultdict(set)
    rejected = set()
    for kind, relative_path in (("accepted", ACCEPTED), ("quarantined", QUARANTINE)):
        parquet = pq.ParquetFile(root / relative_path)
        if parquet.metadata.num_rows != report["counts"][kind]:
            raise ValueError(f"Domain 02 {kind} row count differs from the reconciliation report")
        columns = ["inspection_id", "bronze_row_number", "violation_code", "parsing_status"]
        for batch in parquet.iter_batches(columns=columns):
            for record in batch.to_pylist():
                key = record["inspection_id"]
                if key not in source_rows or source_rows[key] != record["bronze_row_number"]:
                    raise ValueError(f"Domain 02 inspection lineage does not match Silver for {key!r}")
                if kind == "accepted":
                    code = record["violation_code"]
                    if record["parsing_status"] != "PARSED" or not isinstance(code, str) or not code.strip():
                        raise ValueError(f"Invalid accepted Domain 02 violation for {key!r}")
                    if key in baseline:
                        codes[key].add(code)
                elif key in baseline:
                    rejected.add(key)

    expected = {key for key, (_, status) in baseline.items() if status != "missing"}
    observed = codes.keys() | rejected
    if expected != observed:
        raise ValueError(
            "Domain 02 coverage differs from the nonblank Silver violations: "
            f"{len(expected - observed)} missing, {len(observed - expected)} unexpected inspections"
        )

    result = {}
    for key in baseline:
        accepted_codes = codes.get(key, set())
        if key in rejected:
            status = "partial" if accepted_codes else "unparsed"
        else:
            status = "parsed" if accepted_codes else "missing"
        result[key] = (accepted_codes, status)
    return result
