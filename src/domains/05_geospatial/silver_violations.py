"""위반 원문을 파싱해 점검별 관측 상태, 원문 토큰, 고유 코드 테이블을 생성한다.

절차 변경일 기준 구간과 원문 순번을 보존해 코드별 집계를 추적할 수 있다.
"""

from collections import Counter, defaultdict
from datetime import date
import re

import pyarrow as pa
import pyarrow.compute as pc


SOURCE_START = date(2010, 1, 1)
PROCEDURE_CHANGE = date(2018, 7, 1)
PRE_CHANGE = "pre_2018_07_01"
FROM_CHANGE = "from_2018_07_01"
SOURCE_URL = "https://catalog.data.gov/dataset/food-inspections"
NUMBERED_SEGMENT = re.compile(r"([0-9]{1,3})\.\s+(\S.*)", re.DOTALL)
COMMENT_MARKER = re.compile(r"(?:^|\s+)-\s+Comments:\s*", re.IGNORECASE)

KEY_FIELDS = [
    ("inspection_key", pa.string()),
    ("source_row_num", pa.int64()),
    ("batch_id", pa.string()),
    ("inspection_dtm", pa.date32()),
]
COMMON_FIELDS = KEY_FIELDS + [("code_system_version", pa.string())]
OBSERVATION_SCHEMA = pa.schema(COMMON_FIELDS + [
    ("violations_text", pa.string()),
    ("violation_observation_status", pa.string()),
    ("violation_token_count", pa.int64()),
    ("parsed_violation_token_count", pa.int64()),
    ("unrecognized_violation_token_count", pa.int64()),
    ("distinct_parsed_violation_code_count", pa.int64()),
    ("violation_code_occurrence_ready", pa.bool_()),
])
TOKEN_SCHEMA = pa.schema(COMMON_FIELDS + [
    ("violation_sequence", pa.int64()),
    ("raw_segment", pa.string()),
    ("violation_cd", pa.string()),
    ("description_text", pa.string()),
    ("comment_text", pa.string()),
    ("parse_status", pa.string()),
])
CODE_SCHEMA = pa.schema(COMMON_FIELDS + [
    ("violation_cd", pa.string()),
    ("first_violation_sequence", pa.int64()),
    ("violation_token_count", pa.int64()),
    ("description_text", pa.string()),
    ("violation_observation_status", pa.string()),
])


def procedure_version(inspection_date: date | None) -> str | None:
    # 같은 번호라도 절차 변경 전후의 코드는 별도 유형으로 관리한다.
    if inspection_date is None or inspection_date < SOURCE_START:
        return None
    if inspection_date < PROCEDURE_CHANGE:
        return PRE_CHANGE
    return FROM_CHANGE


def _parse_segment(segment: str) -> tuple[str | None, str | None, str | None, str]:
    trimmed = segment.strip()
    if not trimmed:
        return None, None, None, "empty_segment"
    match = NUMBERED_SEGMENT.fullmatch(trimmed)
    if not match:
        return None, None, None, "unrecognized"
    code, body = match.groups()
    description, *comments = COMMENT_MARKER.split(body, maxsplit=1)
    description = description.strip()
    if not any(character.isalpha() for character in description):
        return None, None, None, "unrecognized"
    comment = (comments[0].strip() or None) if comments else None
    return code, description, comment, "parsed"


def _record_batch(rows: list[tuple], schema: pa.Schema) -> pa.RecordBatch:
    columns = zip(*rows, strict=True) if rows else (() for _ in schema)
    arrays = [
        pa.array(values, type=field.type)
        for field, values in zip(schema, columns, strict=True)
    ]
    return pa.RecordBatch.from_arrays(arrays, schema=schema)


def parse_violations(inspections: pa.Table) -> tuple[pa.Table, pa.Table, pa.Table, dict]:
    """Return observations, raw segments, unique observed code occurrences, and QA.

    A known era and an unambiguous inspection key are required for occurrence
    facts. Raw text and segment results remain available for every source row.
    """
    selected = inspections.select([name for name, _ in KEY_FIELDS] + ["violations_text"])
    if selected.schema.field("inspection_dtm").type != pa.date32():
        raise TypeError("inspection_dtm must be Arrow date32")
    key_counts = pc.value_counts(selected["inspection_key"])
    duplicate_keys = set(
        key_counts.field("values").filter(pc.greater(key_counts.field("counts"), 1)).to_pylist()
    )

    observation_batches = []
    token_batches = []
    code_batches = []
    observations_by_status = Counter(dict.fromkeys(("raw_missing", "parsed", "partial", "unrecognized"), 0))
    tokens_by_status = Counter(dict.fromkeys(("parsed", "unrecognized", "empty_segment"), 0))
    occurrence_rows_by_version = Counter(dict.fromkeys((PRE_CHANGE, FROM_CHANGE), 0))
    observed_codes_by_version = defaultdict(set)
    raw_present_without_era = 0
    parsed_without_comment = 0
    parsed_tokens_in_eligible_rows = 0
    eligible_observations = 0

    for batch in selected.to_batches(max_chunksize=8192):
        observations = []
        tokens = []
        occurrences = []
        for row in batch.to_pylist():
            inspection_key = row["inspection_key"]
            version = procedure_version(row["inspection_dtm"])
            metadata = tuple(row[name] for name, _ in KEY_FIELDS) + (version,)
            raw_text = row["violations_text"]
            if raw_text is None or not raw_text.strip():
                observations_by_status["raw_missing"] += 1
                observations.append(metadata + (raw_text, "raw_missing", None, None, None, None, False))
                continue

            raw_present_without_era += version is None
            # 파싱에 실패한 조각도 원문과 순번을 보존한다.
            segments = raw_text.split("|")
            parsed_count = 0
            codes = {}
            for sequence, segment in enumerate(segments, start=1):
                code, description, comment, status = _parse_segment(segment)
                tokens_by_status[status] += 1
                tokens.append(metadata + (sequence, segment, code, description, comment, status))
                if code is None:
                    continue
                parsed_count += 1
                parsed_without_comment += comment is None
                first_sequence, count, first_description = codes.get(code, (sequence, 0, description))
                codes[code] = (first_sequence, count + 1, first_description)

            unrecognized_count = len(segments) - parsed_count
            status = "parsed"
            if parsed_count == 0:
                status = "unrecognized"
            elif unrecognized_count:
                status = "partial"
            observations_by_status[status] += 1
            ready = (
                bool(codes)
                and version is not None
                and bool(inspection_key and inspection_key.strip())
                and inspection_key not in duplicate_keys
            )
            observations.append(metadata + (
                raw_text, status, len(segments), parsed_count, unrecognized_count, len(codes), ready,
            ))
            # 점검과 절차 구간 안에서 코드를 한 번만 기록한다.
            if ready:
                parsed_tokens_in_eligible_rows += parsed_count
                eligible_observations += 1
                occurrence_rows_by_version[version] += len(codes)
                observed_codes_by_version[version].update(codes)
                for code, (sequence, count, description) in codes.items():
                    occurrences.append(metadata + (code, sequence, count, description, status))

        observation_batches.append(_record_batch(observations, OBSERVATION_SCHEMA))
        token_batches.append(_record_batch(tokens, TOKEN_SCHEMA))
        code_batches.append(_record_batch(occurrences, CODE_SCHEMA))

    occurrence_rows = sum(occurrence_rows_by_version.values())
    summary = {
        "inspection_rows": len(inspections),
        "observation_status_counts": dict(observations_by_status),
        "token_rows": sum(tokens_by_status.values()),
        "token_parse_status_counts": dict(tokens_by_status),
        "parsed_tokens_without_comment_text": parsed_without_comment,
        "raw_present_without_code_system_version": raw_present_without_era,
        "inspection_rows_eligible_for_code_occurrence": eligible_observations,
        "parsed_tokens_without_eligible_inspection": tokens_by_status["parsed"] - parsed_tokens_in_eligible_rows,
        "repeated_code_tokens_within_eligible_inspection": parsed_tokens_in_eligible_rows - occurrence_rows,
        "code_occurrence_rows": occurrence_rows,
        "code_occurrence_rows_by_version": dict(occurrence_rows_by_version),
        "distinct_observed_codes_by_version": {
            version: len(observed_codes_by_version[version]) for version in occurrence_rows_by_version
        },
        "procedure_change_date": PROCEDURE_CHANGE.isoformat(),
        "procedure_source_url": SOURCE_URL,
        "description_provenance": "Text observed in the portal extract for each token",
    }
    return (
        pa.Table.from_batches(observation_batches, schema=OBSERVATION_SCHEMA),
        pa.Table.from_batches(token_batches, schema=TOKEN_SCHEMA),
        pa.Table.from_batches(code_batches, schema=CODE_SCHEMA),
        summary,
    )
