"""공용 01 점검과 02 위반 산출물을 05 집계에 연결하고 키를 검증한다."""

import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from geographic_medallion import check, sha256_file


INSPECTION_FIELDS = {
    **dict.fromkeys(("inspection_key", "license_number_key", "result_cd", "risk_level_cd", "facility_type",
                     "inspection_type", "violations_text"), pa.string()),
    "inspection_dtm": pa.date32(),
    "latitude": pa.float64(),
    "longitude": pa.float64(),
    "source_row_num": pa.int64(),
}
CODE_FIELDS = dict.fromkeys(("inspection_key", "code_system_version", "violation_cd"), pa.string())
OBSERVATION_FIELDS = dict.fromkeys(("inspection_key", "violation_observation_status"), pa.string())
OBSERVATION_STATES = {"parsed", "partial", "unrecognized", "raw_missing"}
GOLD_INSPECTION_FIELDS = {
    name: INSPECTION_FIELDS[name]
    for name in ("inspection_key", "inspection_dtm", "result_cd", "facility_type", "inspection_type", "risk_level_cd")
}
AREA_FIELDS = {"community_area_num": pa.int64(), "community_area_name": pa.string()}
SHARED_SILVER_ARTIFACTS = {
    "inspection_community_areas.parquet", "inspection_geography.parquet", "quality_summary.json",
}


def shared_files(inspection_path, violations_dir):
    return {
        "inspection_silver": inspection_path,
        "violation_codes": violations_dir / "inspection_violation_codes.parquet",
        "violation_observations": violations_dir / "inspection_violation_observations.parquet",
    }


def shared_fingerprints(files):
    return {role: {"file": path.name, "sha256": sha256_file(path)} for role, path in files.items()}


def read_typed(path, required, optional=None):
    schema = pq.read_schema(path)
    fields = {**required, **{name: dtype for name, dtype in (optional or {}).items() if name in schema.names}}
    for name, dtype in fields.items():
        check(name in schema.names and (
            schema.field(name).type == dtype or (dtype == pa.string() and pa.types.is_large_string(schema.field(name).type))
        ), f"{path.name}: {name} must be {dtype}")
    table = pq.read_table(path, columns=list(fields))
    return table.cast(pa.schema(list(fields.items())))


def align_rows(table, name, keys):
    source = table[name]
    check(len(table) == len(keys) and source.null_count == 0 and pc.count_distinct(source).as_py() == len(table),
          f"Shared rows must contain one row per {name}")
    order = pc.index_in(keys, value_set=source)
    check(order.null_count == 0 and pc.count_distinct(order).as_py() == len(keys), f"Shared {name} values differ")
    return table.take(order)


def read_shared_violation_codes(path):
    codes = read_typed(path, CODE_FIELDS, {"description_text": pa.string()}).to_pandas()
    if "description_text" not in codes:
        codes["description_text"] = pd.Series(pd.NA, index=codes.index, dtype="string")
    return codes


def validate_inspection_silver(shared, local):
    # 입력의 행 순서와 무관하게 점검 ID로 공용 스키마와 동일 스냅샷의 값을 대조한다.
    key = shared["inspection_key"]
    valid = pc.and_(pc.is_valid(key), pc.not_equal(pc.utf8_trim_whitespace(key), ""))
    check(len(shared) == len(local) and pc.all(valid).as_py()
          and pc.count_distinct(key).as_py() == len(shared), "01 inspection keys must be complete and unique")
    order = pc.index_in(local["inspection_key"], value_set=key)
    check(order.null_count == 0, "01 and 05 inspection key sets differ")
    aligned = shared.take(order)
    for field in INSPECTION_FIELDS:
        check(aligned[field].combine_chunks().equals(local[field].combine_chunks()),
              f"01 inspection Silver differs from the source snapshot for {field}")
    return aligned


def attach_shared_violations(inspections, codes, observations):
    # 공유 관측 상태와 승인된 고유 코드로 집계 가능 분모를 다시 계산한다.
    by_key = inspections.set_index("inspection_key")
    seen = observations.set_index("inspection_key")["violation_observation_status"]
    check(seen.index.is_unique and len(seen) == len(by_key) and bool(by_key.index.isin(seen.index).all()),
          "02 observations must contain one row for each inspection key")
    seen = seen.reindex(by_key.index)
    check(bool(seen.isin(OBSERVATION_STATES).all()) and bool(
        seen.eq("raw_missing").eq(by_key["violation_observation_status"].eq("raw_missing")).all()
    ), "02 observation statuses disagree with the source text coverage")

    key_fields = list(CODE_FIELDS)
    check(bool(codes[key_fields].notna().all().all()) and bool(codes["violation_cd"].str.strip().ne("").all())
          and not codes.duplicated(key_fields).any(), "02 has a null, empty, or duplicate violation code key")
    check(bool(codes["inspection_key"].isin(by_key.index).all()), "02 has an unknown inspection key")
    era = codes["inspection_key"].map(by_key["code_system_version"])
    check(bool(codes["code_system_version"].eq(era).fillna(False).all()),
          "02 violation codes do not match the inspection procedure era")
    ready = by_key.index.isin(codes["inspection_key"])
    check(bool(seen.loc[ready].isin(["parsed", "partial"]).all()),
          "02 violation codes require a parsed or partial observation")
    return inspections.assign(violation_observation_status=seen.array, violation_code_occurrence_ready=ready)


def load_shared_inputs(silver_dir, inspections, files):
    shared = read_typed(files["inspection_silver"], INSPECTION_FIELDS)
    local = read_typed(silver_dir / "food_inspections.parquet", INSPECTION_FIELDS)
    aligned = validate_inspection_silver(shared, local)
    fields = set(INSPECTION_FIELDS).intersection(inspections).difference({"inspection_key"})
    inspections = inspections.set_index("inspection_key")
    common_values = aligned.select(["inspection_key", *sorted(fields)]).to_pandas().set_index("inspection_key")
    inspections.loc[:, sorted(fields)] = common_values.reindex(inspections.index)
    inspections = inspections.reset_index()

    codes = read_shared_violation_codes(files["violation_codes"])
    observations = read_typed(files["violation_observations"], OBSERVATION_FIELDS).to_pandas()
    inspections = attach_shared_violations(inspections, codes, observations)

    # 팀 코드의 점검·구간·코드 조합을 같은 원천에서 확인한 후보와 대조한다.
    candidates = pq.read_table(silver_dir / "inspection_violation_codes.parquet", columns=list(CODE_FIELDS)).to_pandas()
    check(pd.MultiIndex.from_frame(codes[list(CODE_FIELDS)]).isin(pd.MultiIndex.from_frame(candidates)).all(),
          "02 contains a violation code absent from the 05 source snapshot")
    return inspections, codes


def read_shared_geography(silver_dir, files, columns):
    shared = read_typed(files["inspection_silver"], GOLD_INSPECTION_FIELDS)
    derived = pq.read_table(silver_dir / "inspection_geography.parquet",
                            columns=["inspection_key", *[name for name in columns if name not in GOLD_INSPECTION_FIELDS]])
    aligned = align_rows(shared, "inspection_key", derived["inspection_key"])
    for name in aligned.column_names:
        if name != "inspection_key":
            derived = derived.append_column(name, aligned[name])
    return derived.select(columns).to_pandas()
