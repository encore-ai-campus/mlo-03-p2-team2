"""Build the Violations analysis mart and an HTML report.

Run from the repository root: python -m src.domains.02_violation.build_analysis_mart
"""

from __future__ import annotations

from collections import Counter, defaultdict
import csv
from datetime import datetime, timezone
from html import escape
import hashlib
import json
import os
from pathlib import Path
import uuid

import pyarrow as pa
import pyarrow.parquet as pq

from src.bronze.paths import PROJECT_ROOT
from .gold import DIM_RELATIVE, FACT_RELATIVE, rows
from .profiling import BRONZE_RELATIVE, origin_snapshot, sha256
from .silver import SILVER_RELATIVE
from .reconciliation import ACCEPTED_RELATIVE, QUARANTINE_RELATIVE, REPORT_RELATIVE


MART_RELATIVE = Path("data/03_gold/02_violation/02_violations_analysis_mart.parquet")
HTML_RELATIVE = Path("reports/02_violation/violations_analysis.html")
LOG_RELATIVE = Path("logs/02_violation/violations_analysis_runs.jsonl")
MART_SCHEMA = pa.schema([
    pa.field("source_row_num", pa.int64(), nullable=False),
    pa.field("item_sequence_num", pa.int32(), nullable=False),
    pa.field("inspection_id", pa.string(), nullable=False),
    pa.field("facility_type", pa.string(), nullable=False),
    pa.field("inspection_result", pa.string(), nullable=False),
    pa.field("violation_key", pa.int32(), nullable=False),
    pa.field("violation_code", pa.string(), nullable=False),
    pa.field("violation_description", pa.string(), nullable=False),
    pa.field("violation_comments", pa.string(), nullable=False),
])
BRONZE_COLUMNS = ["Inspection ID", "Facility Type", "Results"]
FACT_COLUMNS = [
    "source_row_num", "item_sequence_num", "inspection_id", "violation_key", "violation_comments"
]
FAIL_VALUE = "Fail"
SHARED_CODE_MAP = PROJECT_ROOT / "metadata/data_dictionary/shared_code_map.csv"
TOP_N = 15
CHUNK = 20_000


def _publish(temp: Path, final: Path) -> None:
    if final.exists():
        if sha256(temp) != sha256(final):
            raise FileExistsError(f"Existing analysis output differs: {final}")
        temp.unlink()
    else:
        os.replace(temp, final)


def _content_hash(path: Path) -> str:
    digest = hashlib.sha256()
    for row in rows(path):
        digest.update(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def _rank(counter: Counter, limit: int = TOP_N) -> list[tuple[object, int]]:
    return sorted(counter.items(), key=lambda item: (-item[1], str(item[0])))[:limit]


def _known_result_values() -> set[str]:
    with SHARED_CODE_MAP.open(encoding="utf-8-sig", newline="") as stream:
        return {row["source_value"] for row in csv.DictReader(stream)
                if row["dataset"] == "food_inspections" and row["source_column"] == "Results"}


def _bar_table(headers: list[str], records: list[list[object]], count_index: int) -> str:
    maximum = max((int(row[count_index]) for row in records), default=1)
    head = "".join(f"<th>{escape(header)}</th>" for header in headers)
    body = []
    for row in records:
        cells = []
        for index, value in enumerate(row):
            display = "(미기재)" if value == "" else str(value)
            if index == count_index:
                width = max(1, round(int(value) / maximum * 100))
                cells.append(f'<td class="number">{int(value):,}<div class="bar" style="width:{width}%"></div></td>')
            else:
                cells.append(f"<td>{escape(display)}</td>")
        body.append("<tr>" + "".join(cells) + "</tr>")
    return f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody></table>"


def _render_html(summary: dict) -> str:
    code_rows = [[code, count] for code, count in summary["top_codes"]]
    type_rows = [[code, description, count] for (code, description), count in summary["top_types"]]
    fail_rows = [[code, description, count] for (code, description), count in summary["top_fail_types"]]
    facility_rows = []
    for facility, total, leaders in summary["top_facilities"]:
        for rank, ((code, description), count) in enumerate(leaders, start=1):
            facility_rows.append([facility, total, rank, code, description, count])
    top_types = summary["top_types"]
    top_type_card = '<p class="note">정상 위반 기록이 없습니다.</p>'
    if top_types:
        (code, description), count = top_types[0]
        top_type_card = f'<div class="card"><b>{escape(code)} · {escape(description)}</b><div class="big">{count:,}</div></div>'
    fail_section = (_bar_table(['코드','설명','Fail 위반 건수'], fail_rows, 2)
                    if fail_rows else '<p class="note">Fail 점검에서 집계할 정상 위반 기록이 없습니다.</p>')
    return f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><title>Food Inspections 위반 유형 분석</title>
<style>
body{{font-family:Arial,'Malgun Gothic',sans-serif;margin:32px;color:#1f2937;max-width:1500px}}
h1,h2{{color:#16324f}} .cards{{display:flex;gap:16px;flex-wrap:wrap}} .card{{padding:18px;border:1px solid #dbe4ee;border-radius:10px;min-width:210px;background:#f8fafc}}
.big{{font-size:28px;font-weight:700}} table{{border-collapse:collapse;width:100%;margin:12px 0 32px}} th,td{{border:1px solid #dbe4ee;padding:8px;text-align:left;vertical-align:top}} th{{background:#eef4f8}} .number{{text-align:right;min-width:100px}} .bar{{height:5px;background:#3686b8;margin-top:4px;border-radius:3px}} .note{{color:#596579}}
</style></head><body>
<h1>Food Inspections ② 위반 유형 분석</h1>
<p class="note">Gold 정상 위반 조각만 사용했습니다. 위반 유형은 code-description 조합이며, 같은 코드의 서로 다른 설명을 합치지 않았습니다.</p>
<div class="cards"><div class="card">전체 정상 위반 건수<div class="big">{summary['total_violations']:,}</div></div>
<div class="card">Fail 점검 위반 건수<div class="big">{summary['fail_violations']:,}</div></div>
<div class="card">위반 코드 / 유형<div class="big">{summary['code_count']:,} / {summary['type_count']:,}</div></div></div>
<h2>1. 위반 코드별 빈도 TOP {TOP_N}</h2>{_bar_table(['위반 코드','위반 건수'], code_rows, 1)}
<h2>2. 시설 유형별 주요 위반</h2><p class="note">위반 건수가 많은 시설 유형 {TOP_N}개에서 유형별 상위 3건입니다. 빈 시설 유형은 미기재로 분리했습니다.</p>
{_bar_table(['시설 유형','시설 전체 위반','순위','코드','설명','위반 건수'], facility_rows, 5)}
<h2>3. 가장 빈번한 위반 유형</h2>{top_type_card}
{_bar_table(['코드','설명','위반 건수'], type_rows, 2)}
<h2>4. Fail 점검에서 자주 나타나는 위반</h2>{fail_section}
<p class="note">Mart grain: 정상 violation fragment 1건. 연결 키: Inspection ID(원천에서 유일성·NULL 검증 완료).</p>
</body></html>"""


def build(
    root: Path = PROJECT_ROOT, output_root: Path | None = None, *,
    bronze_path: Path | None = None, origin_root: Path | None = None,
) -> dict:
    root = Path(root)
    output_root = Path(output_root) if output_root is not None else root
    origin_root = origin_root or root
    origin_before = origin_snapshot(origin_root)
    paths = {
        "bronze": Path(bronze_path) if bronze_path is not None else root / BRONZE_RELATIVE,
        "silver": root / SILVER_RELATIVE, "accepted": root / ACCEPTED_RELATIVE,
        "quarantine": root / QUARANTINE_RELATIVE, "reconciliation": root / REPORT_RELATIVE,
        "dimension": root / DIM_RELATIVE, "fact": root / FACT_RELATIVE,
    }
    if not all(path.is_file() for path in paths.values()):
        missing = [str(path) for path in paths.values() if not path.is_file()]
        raise FileNotFoundError(missing)
    protected = {name: sha256(path) for name, path in paths.items() if name != "reconciliation"}
    reconciliation = json.loads(paths["reconciliation"].read_text(encoding="utf-8"))
    accepted_count = pq.ParquetFile(paths["accepted"]).metadata.num_rows
    quarantine_count = pq.ParquetFile(paths["quarantine"]).metadata.num_rows
    candidate_count = reconciliation["counts"]["candidate_fragments"]
    fact_count = pq.ParquetFile(paths["fact"]).metadata.num_rows
    if reconciliation["status"] != "PASS" or accepted_count + quarantine_count != candidate_count:
        raise ValueError("Accepted/quarantine reconciliation failed")
    if accepted_count != fact_count:
        raise ValueError("Accepted Silver and Gold Fact row counts differ")

    inspection = {}
    result_values = Counter()
    empty_facility_inspections = 0
    for row in rows(paths["bronze"], BRONZE_COLUMNS):
        inspection_id = row["Inspection ID"]
        if not inspection_id or inspection_id in inspection:
            raise ValueError(f"Bronze Inspection ID is null or duplicated: {inspection_id!r}")
        facility = row["Facility Type"]
        result = row["Results"] or ""
        if facility is None:
            raise ValueError(f"Bronze analysis attribute is NULL: {inspection_id}")
        inspection[inspection_id] = (facility, result)
        result_values[result] += 1
        empty_facility_inspections += facility == ""
    known_results = _known_result_values()
    missing_results = sum(count for value, count in result_values.items() if not value.strip())
    unknown_results = {value: count for value, count in sorted(result_values.items())
                       if value.strip() and value not in known_results}

    dimension = {}
    dimension_pairs = set()
    for row in rows(paths["dimension"]):
        key = row["violation_key"]
        pair = row["violation_code"], row["violation_description"]
        if key in dimension or pair in dimension_pairs or not all(pair):
            raise ValueError("Dimension PK/grain is duplicated or null")
        dimension[key] = pair
        dimension_pairs.add(pair)

    mart_path = output_root / MART_RELATIVE
    html_path = output_root / HTML_RELATIVE
    for path in (mart_path, html_path):
        path.parent.mkdir(parents=True, exist_ok=True)
    token = uuid.uuid4().hex
    mart_temp = mart_path.with_name(mart_path.name + f".{token}.tmp")
    html_temp = html_path.with_name(html_path.name + f".{token}.tmp")
    grain = set()
    code_counts = Counter()
    type_counts = Counter()
    fail_counts = Counter()
    facility_counts = defaultdict(Counter)
    facility_totals = Counter()
    orphan_inspection = orphan_dimension = mart_count = 0
    try:
        with pq.ParquetWriter(mart_temp, MART_SCHEMA) as writer:
            for batch in pq.ParquetFile(paths["fact"]).iter_batches(columns=FACT_COLUMNS, batch_size=CHUNK):
                output = []
                for fact in batch.to_pylist():
                    fact_grain = fact["source_row_num"], fact["item_sequence_num"]
                    if fact_grain in grain:
                        raise ValueError(f"Duplicate Fact grain: {fact_grain}")
                    grain.add(fact_grain)
                    attributes = inspection.get(fact["inspection_id"])
                    pair = dimension.get(fact["violation_key"])
                    orphan_inspection += attributes is None
                    orphan_dimension += pair is None
                    if attributes is None or pair is None:
                        continue
                    facility, result = attributes
                    code, description = pair
                    mart_row = {
                        "source_row_num": fact["source_row_num"],
                        "item_sequence_num": fact["item_sequence_num"],
                        "inspection_id": fact["inspection_id"], "facility_type": facility,
                        "inspection_result": result, "violation_key": fact["violation_key"],
                        "violation_code": code, "violation_description": description,
                        "violation_comments": fact["violation_comments"],
                    }
                    output.append(mart_row)
                    code_counts[code] += 1
                    type_counts[pair] += 1
                    facility_counts[facility][pair] += 1
                    facility_totals[facility] += 1
                    if result == FAIL_VALUE:
                        fail_counts[pair] += 1
                writer.write_table(pa.Table.from_pylist(output, schema=MART_SCHEMA))
                mart_count += len(output)
        if orphan_inspection or orphan_dimension or mart_count != fact_count:
            raise ValueError(f"Join mismatch: inspection={orphan_inspection}, dimension={orphan_dimension}, rows={mart_count}/{fact_count}")
        if pq.ParquetFile(mart_temp).schema_arrow != MART_SCHEMA:
            raise ValueError("Mart schema mismatch")
        summary = {
            "total_violations": mart_count, "fail_violations": sum(fail_counts.values()),
            "code_count": len(code_counts), "type_count": len(type_counts),
            "top_codes": _rank(code_counts), "top_types": _rank(type_counts),
            "top_fail_types": _rank(fail_counts),
            "top_facilities": [(facility, total, _rank(facility_counts[facility], 3))
                               for facility, total in _rank(facility_totals)],
        }
        html_temp.write_text(_render_html(summary), encoding="utf-8")
        for name, digest in protected.items():
            if sha256(paths[name]) != digest:
                raise ValueError(f"Protected input changed: {paths[name]}")
        origin_after = origin_snapshot(origin_root)
        if (origin_after["source_sha256"] != origin_before["source_sha256"]
                or origin_after["guard_sha256"] != origin_before["guard_sha256"]):
            raise ValueError("Protected Origin inputs changed during analysis")
        for temp, final in ((mart_temp, mart_path), (html_temp, html_path)):
            if final.exists() and sha256(temp) != sha256(final):
                raise FileExistsError(f"Existing analysis output differs: {final}")
        _publish(mart_temp, mart_path)
        _publish(html_temp, html_path)
        result = {
            "started_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "status": "PASS", "mart_rows": mart_count, "fact_rows": fact_count,
            "accepted_rows": accepted_count, "quarantine_rows": quarantine_count,
            "candidate_fragments": candidate_count, "inspection_rows": len(inspection),
            "inspection_id_duplicates": 0, "inspection_id_nulls": 0,
            "empty_facility_inspections": empty_facility_inspections,
            "observed_results": dict(sorted(result_values.items())), "fail_value": FAIL_VALUE,
            "fail_inspection_rows": result_values[FAIL_VALUE],
            "missing_inspection_result_rows": missing_results,
            "unknown_inspection_result_counts": unknown_results,
            "fail_violation_rows": summary["fail_violations"], "violation_codes": len(code_counts),
            "violation_types": len(type_counts), "orphan_inspection": orphan_inspection,
            "orphan_dimension": orphan_dimension, "unexpected_row_change": mart_count - fact_count,
            "duplicate_grain": 0, "mart_content_sha256": _content_hash(mart_path),
            "mart_sha256": sha256(mart_path), "html_sha256": sha256(html_path),
            "origin_sha256": origin_before["source_sha256"],
            "origin_guard_sha256": origin_before["guard_sha256"],
            "origin_storage_files": origin_before["storage_files"],
            "protected_sha256": protected,
            "top_code": list(summary["top_codes"][0]) if summary["top_codes"] else None,
            "top_type": [*summary["top_types"][0][0], summary["top_types"][0][1]] if summary["top_types"] else None,
            "top_fail_type": ([*summary["top_fail_types"][0][0], summary["top_fail_types"][0][1]]
                              if summary["top_fail_types"] else None),
        }
        log_path = root / LOG_RELATIVE
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(result, ensure_ascii=False) + "\n")
        return result
    finally:
        mart_temp.unlink(missing_ok=True)
        html_temp.unlink(missing_ok=True)


if __name__ == "__main__":
    print(json.dumps(build(), ensure_ascii=False, indent=2))
