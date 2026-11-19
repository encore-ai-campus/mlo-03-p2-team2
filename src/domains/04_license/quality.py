"""Comparable quality checks across Bronze and Silver."""

import csv
from collections import defaultdict
from dataclasses import dataclass
from io import StringIO

import pyarrow as pa
import pyarrow.compute as pc

from normalization import load_dictionary, trimmed, typed_dates, valid_identifier
from pipeline_io import ROW, parquet_batches


@dataclass(frozen=True)
class Rule:
    decision_id: str
    dimension: str
    description: str
    fields: tuple[str, ...]
    kind: str


RULES = {
    "business_licenses": (
        Rule("D04-DQ-01", "completeness", "Missing license number", ("license_number_key",), "missing"),
        Rule("D04-DQ-02", "validity", "Invalid license number", ("license_number_key",), "id"),
        Rule("D04-DQ-03", "completeness", "Missing term start", ("term_start_dtm",), "missing"),
        Rule("D04-DQ-04", "completeness", "Missing term expiration", ("term_end_dtm",), "missing"),
        Rule("D04-DQ-05", "validity", "Invalid term start date", ("term_start_dtm",), "date"),
        Rule("D04-DQ-06", "validity", "Invalid term expiration date", ("term_end_dtm",), "date"),
        Rule("D04-DQ-07", "consistency", "Expiration before term start", ("term_start_dtm", "term_end_dtm"), "order"),
        Rule("D04-DQ-08", "standardization", "Outer whitespace in application type", ("application_cd",), "space"),
        Rule("D04-DQ-09", "validity", "Status code requiring review", ("recorded_status_cd",), "status"),
    ),
    "food_inspections": (
        Rule("D04-DQ-10", "completeness", "Missing inspection license number", ("license_number_key",), "missing"),
        Rule("D04-DQ-11", "validity", "Invalid or excluded inspection license number", ("license_number_key",), "inspection_id"),
        Rule("D04-DQ-12", "completeness", "Missing inspection date", ("inspection_dtm",), "missing"),
        Rule("D04-DQ-13", "validity", "Invalid inspection date", ("inspection_dtm",), "date"),
    ),
}
CSV_REPORT = "quality_comparison.csv"
MD_REPORT = "품질 관리.md"


def dates(values):
    return typed_dates(trimmed(values)) if pa.types.is_string(values.type) else values


def violation_mask(rule, values):
    column = values[0]
    text = trimmed(column) if pa.types.is_string(column.type) else column

    if rule.kind == "missing":
        return pc.is_null(text)
    if rule.kind in {"id", "inspection_id"}:
        return pc.invert(valid_identifier(text, inspection=(rule.kind == "inspection_id")))
    if rule.kind == "date":
        return pc.and_(pc.is_valid(text), pc.is_null(dates(column)))
    if rule.kind == "order":
        return pc.less(dates(values[1]), dates(column))
    if rule.kind == "space":
        return pc.not_equal(column, pc.utf8_trim_whitespace(column))
    if rule.kind == "status":
        known = pa.array(["AAI", "AAC", "REV", "REA"])
        return pc.and_(pc.is_valid(text), pc.invert(pc.is_in(text, value_set=known)))
    raise ValueError(f"Unknown quality rule: {rule.kind}")


def measure(path, field_names, rules):
    row_count = 0
    counts = [0] * len(rules)
    examples = [[] for _ in rules]
    columns = [ROW, *dict.fromkeys(field_names[field] for rule in rules for field in rule.fields)]
    for batch in parquet_batches(path, columns=columns):
        row_count += batch.num_rows
        for index, rule in enumerate(rules):
            mask = pc.fill_null(violation_mask(rule, [batch[field_names[f]] for f in rule.fields]), False)
            counts[index] += pc.sum(mask).as_py() or 0
            limit = 3 - len(examples[index])
            if limit > 0:
                examples[index].extend(pc.filter(batch[ROW], mask)[:limit].to_pylist())
    return row_count, counts, examples


def compare(config):
    dictionary = load_dictionary(config.dictionary)
    results = []
    seen = set()
    for table, rules in RULES.items():
        source = {field.target_column: field.source_column for field in dictionary[table]}
        target = {name: name for name in source}
        before_rows, before, before_examples = measure(config.table("bronze", table), source, rules)
        after_rows, after, after_examples = measure(config.table("silver", table), target, rules)
        if before_rows != after_rows:
            raise ValueError(f"{table}: Bronze and Silver row counts differ.")
        for index, rule in enumerate(rules):
            if not rule.decision_id or rule.decision_id in seen:
                raise ValueError(f"Missing or duplicate decision ID: {rule.decision_id}")
            seen.add(rule.decision_id)
            results.append({
                "decision_id": rule.decision_id,
                "table": table,
                "dimension": rule.dimension,
                "rule": rule.description,
                "rows": before_rows,
                "bronze_violations": before[index],
                "bronze_percent": percent(before[index], before_rows),
                "bronze_examples": ", ".join(map(str, before_examples[index])),
                "silver_violations": after[index],
                "silver_percent": percent(after[index], after_rows),
                "silver_examples": ", ".join(map(str, after_examples[index])),
            })
    return results


def percent(bad, total):
    return f"{100 * bad / total:.4f}" if total else ""


def render_reports(results):
    stream = StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=list(results[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(results)
    lines = [
        "# Domain 04 품질 관리", "",
        "같은 원천 행을 Bronze와 Silver에서 비교합니다. 비율의 분모는 해당 테이블의 전체 행 수입니다.",
        "예시는 원천의 논리 레코드 순번입니다. 잘못된 값이 결측으로 바뀌면 결측 규칙에도 반영됩니다.",
        "기간 역전과 검토 대상 상태는 원천 이력을 추적할 수 있도록 Silver에 남깁니다.", "",
        "## 차원별 비교", "",
        "차원별 분모는 행 수를 해당 차원의 규칙 수만큼 합산한 검사 횟수입니다. 한 행이 두 규칙을 위반하면 두 건으로 집계합니다.", "",
        "| 테이블 | 차원 | 검사 횟수 | Bronze 위반 건수·비율 | Silver 위반 건수·비율 |",
        "| --- | --- | ---: | ---: | ---: |",
    ]
    totals = defaultdict(lambda: [0, 0, 0])
    for row in results:
        total = totals[row["table"], row["dimension"]]
        total[0] += row["rows"]
        total[1] += row["bronze_violations"]
        total[2] += row["silver_violations"]
    for (table, dimension), (total, bronze, silver) in sorted(totals.items()):
        lines.append(f"| {table} | {dimension} | {total} | {bronze} · {percent(bronze, total)} | "
                     f"{silver} · {percent(silver, total)} |")
    lines.extend([
        "", "## 규칙별 비교", "",
        "| 결정 ID | 테이블 | 차원 | 규칙 | 분모 | Bronze 건수·비율 | Bronze 순번 | Silver 건수·비율 | Silver 순번 |",
        "| --- | --- | --- | --- | ---: | ---: | --- | ---: | --- |",
    ])
    for row in results:
        lines.append(
            "| {decision_id} | {table} | {dimension} | {rule} | {rows} | "
            "{bronze_violations} · {bronze_percent} | {bronze_examples} | "
            "{silver_violations} · {silver_percent} | {silver_examples} |".format(**row)
        )
    lines.extend(["", "비율 열의 단위는 %이며, 분모가 0이면 비율은 공란입니다.", ""])
    return {CSV_REPORT: stream.getvalue().encode("utf-8"),
            MD_REPORT: "\n".join(lines).encode("utf-8")}
