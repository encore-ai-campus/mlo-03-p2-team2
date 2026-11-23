"""Publish and validate the shared Gold dimensions and facts for all five domains."""

from argparse import ArgumentParser
from filecmp import cmp
from hashlib import file_digest
from pathlib import Path
from shutil import copyfile, copyfileobj
from tempfile import NamedTemporaryFile, TemporaryDirectory
from uuid import uuid4

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq


ROOT = Path(__file__).resolve().parents[2]
GOLD = ROOT / "data/03_gold"
UNKNOWN = "__unknown__"
INSPECTION_KEYS = {
    "facility_type": "facility_type_key",
    "inspection_type": "inspection_type_key",
    "risk_level": "risk_level_cd_key",
    "result": "result_cd_key",
}
LICENSE_KEYS = {"license": "license_number_key", "establishment": "establishment_key"}
VIOLATION_FACT = "02_fact_inspection_violation"
REPEAT_FACTS = {
    "03_fact_reinspection": "03_inspection_reinspection_mart",
    "03_fact_repeat_violation": "03_repeat_violation_mart",
}
REGIONAL_FACTS = {
    "inspection_area_period": (),
    "violation_coverage_area_period": ("code_system_version",),
    "violation_area_period": ("code_system_version", "violation_cd"),
}
REGION_KEYS = ("boundary_version", "community_area_num")
REGION_COLUMNS = (*REGION_KEYS, "community_area_name")


def deduplicate(table, keys):
    members = {}
    for row in table.to_pylist():
        key = tuple(row[column] for column in keys)
        if None in key:
            raise ValueError(f"Missing dimension key {keys}: {key}")
        if members.setdefault(key, row) != row:
            raise ValueError(f"Conflicting dimension attributes for {keys}: {key}")
    return pa.Table.from_pylist(list(members.values()), schema=table.schema)


def date_dimension(inspection, license_dates):
    inspection_days = set(inspection["inspection_dtm"].to_pylist())
    if None in inspection_days:
        raise ValueError("The inspection calendar contains a missing date")
    license_days = set()
    for record in license_dates.to_pylist():
        key, day = record["date_key"], record["calendar_dtm"]
        if key != (day.isoformat() if day else UNKNOWN):
            raise ValueError(f"License calendar date does not match its key: {key!r}")
        if day is not None:
            license_days.add(day)
    days = sorted(inspection_days | license_days)
    return pa.table({
        "date_key": pa.array([UNKNOWN, *(day.isoformat() for day in days)], pa.string()),
        "calendar_dtm": pa.array([None, *days], pa.date32()),
        "inspection_year_num": pa.array([None, *(day.year for day in days)], pa.int32()),
        "inspection_month_num": pa.array([None, *(day.month for day in days)], pa.int32()),
    }), len(inspection_days & license_days)


def verify_references(fact, references, name, nullable=()):
    for column, dimension_keys in references.items():
        values = fact[column]
        if (values.null_count and column not in nullable) or pc.any(
            pc.invert(pc.is_in(pc.unique(pc.drop_null(values)), dimension_keys))
        ).as_py():
            raise ValueError(f"Missing reference: {name}.{column}")


def verify_grain(table, keys, name, nullable=()):
    if any(table[key].null_count for key in keys if key not in nullable):
        raise ValueError(f"Missing fact key: {name}")
    if table.select(list(keys)).group_by(list(keys)).aggregate([]).num_rows != table.num_rows:
        raise ValueError(f"Duplicate fact grain: {name}")


def verify_fact(path, grain, references, nullable=()):
    fact = pq.read_table(path, columns=list(dict.fromkeys((*grain, *references))))
    verify_grain(fact, grain, path.name)
    verify_references(fact, references, path.name, nullable)
    return fact


def violation_fact(gold, scratch):
    fact = gold / "02_violation" / f"{VIOLATION_FACT}.parquet"
    if fact.is_file():
        return fact
    restored = scratch / fact.name
    with restored.open("wb") as output:
        for suffix in (".part-001", ".part-002"):
            with fact.with_suffix(f".parquet{suffix}").open("rb") as source:
                copyfileobj(source, output, length=1024 * 1024)
    return restored


def compact_violation_fact(source, target):
    # Preserve the source rows and schema while storing the shared fact as one Parquet.
    dictionary_columns = ["source_row_num", "item_sequence_num", "inspection_id", "violation_key"]
    with pq.ParquetFile(source) as original, pq.ParquetWriter(
        target, original.schema_arrow, compression="zstd", compression_level=9,
        use_dictionary=dictionary_columns,
    ) as writer:
        for batch in original.iter_batches(batch_size=100_000):
            writer.write_batch(batch)


def build_dimensions(gold, inspection_star, regional):
    license_dir = gold / "04_license"
    tables = {}
    for dimension, key in INSPECTION_KEYS.items():
        source = pq.read_table(inspection_star / f"01_dim_{dimension}.parquet")
        tables[dimension] = deduplicate(source, (key,))
    for dimension, key in LICENSE_KEYS.items():
        source = pq.read_table(license_dir / f"04_dim_{dimension}.parquet")
        tables[dimension] = deduplicate(source, (key,))
    establishments = tables["establishment"].filter(pc.not_equal(tables["establishment"]["establishment_key"], UNKNOWN))
    deduplicate(establishments, ("account_key", "site_key"))

    violations = pq.read_table(gold / "02_violation/02_dim_violation.parquet")
    tables["violation"] = deduplicate(violations, ("violation_key",))
    deduplicate(tables["violation"], ("violation_code", "violation_description"))

    inspection_dates = pq.read_table(inspection_star / "01_dim_date.parquet")
    license_dates = pq.read_table(license_dir / "04_dim_date.parquet")
    tables["date"], overlap = date_dimension(
        deduplicate(inspection_dates, ("inspection_dtm",)), deduplicate(license_dates, ("date_key",)),
    )
    regional_periods = pq.read_table(
        regional / "inspection_area_period.parquet", columns=[*REGION_COLUMNS, "community_area_match_status"],
    )
    assigned = regional_periods.filter(pc.equal(regional_periods["community_area_match_status"], "unique_area"))
    tables["community_area"] = deduplicate(assigned.select(REGION_COLUMNS), REGION_KEYS).sort_by(
        [(key, "ascending") for key in REGION_KEYS],
    )
    return tables, overlap


def validate_regional_facts(regional, dimension):
    areas = {tuple(row[key] for key in REGION_KEYS): row["community_area_name"] for row in dimension.to_pylist()}
    period_area = ("period_grain_cd", "period_start_dtm", "community_area_match_status", "community_area_num")
    for name, extra_keys in REGIONAL_FACTS.items():
        grain = (*period_area, *extra_keys)
        fact = pq.read_table(
            regional / f"{name}.parquet", columns=list(dict.fromkeys((*grain, *REGION_COLUMNS))),
        )
        verify_grain(fact, grain, name, nullable=("community_area_num",))
        metadata = (*REGION_COLUMNS, "community_area_match_status")
        for row in fact.select(metadata).group_by(list(metadata)).aggregate([]).to_pylist():
            if row["community_area_match_status"] == "unique_area":
                key = tuple(row[column] for column in REGION_KEYS)
                if key not in areas or row["community_area_name"] != areas[key]:
                    raise ValueError(f"Missing or inconsistent region in {name}: {key}")
            elif row["community_area_num"] is not None:
                raise ValueError(f"Unassigned region has an area number in {name}")


def validate_facts(facts, dimensions, regional):
    inspection = verify_fact(facts["01_fact_inspection"], ("inspection_key",), {
        "inspection_dtm": dimensions["date"]["calendar_dtm"],
        **{key: dimensions[name][key] for name, key in INSPECTION_KEYS.items()},
    })
    inspection_ids = inspection["inspection_key"]
    verify_fact(facts[VIOLATION_FACT], ("source_row_num", "item_sequence_num"), {
        "inspection_id": inspection_ids,
        "violation_key": dimensions["violation"]["violation_key"],
    })
    for name in REPEAT_FACTS:
        grain = ("base_inspection_key",)
        if name == "03_fact_repeat_violation":
            grain += ("code_system_version", "violation_cd")
        verify_fact(facts[name], grain, {
            "base_inspection_key": inspection_ids, "followup_inspection_key": inspection_ids,
        }, nullable=("followup_inspection_key",))

    license_references = {"date_key": dimensions["date"]["date_key"],
                          **{key: dimensions[name][key] for name, key in LICENSE_KEYS.items()}}
    events = verify_fact(facts["04_fact_license_event"], ("license_event_key",), license_references)
    verify_fact(facts["04_fact_inspection_license_match"], ("inspection_key",), {
        **license_references, "inspection_key": inspection_ids,
        "matched_license_event_id": events["license_event_key"],
    }, nullable=("matched_license_event_id",))
    validate_regional_facts(regional, dimensions["community_area"])


def regional_release(gold):
    releases = sorted((gold / "05_geospatial").glob("*/*/manifest.json"))
    if len(releases) != 1:
        raise ValueError("Specify --regional-gold with the Domain 05 Gold release directory")
    return releases[0].parent


def publish(target, *, table=None, source=None, link=False):
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_file():
        if table is not None and pq.read_table(target).equals(table):
            return
        if source is not None and (source.samefile(target) or cmp(source, target, shallow=False)):
            return

    if link:
        pending = target.with_name(f".{uuid4().hex}.tmp")
        try:
            pending.hardlink_to(source)
        except OSError:
            pass  # A separate output drive may not support links to the input.
        else:
            try:
                pending.replace(target)
            finally:
                pending.unlink(missing_ok=True)
            return

    # Stage files beside their destination so Windows inherits the shared folder permissions.
    with NamedTemporaryFile(dir=target.parent, delete=False) as stream:
        pending = Path(stream.name)
    try:
        if table is not None:
            pq.write_table(table, pending, compression="zstd")
        else:
            copyfile(source, pending)
        pending.replace(target)
    finally:
        pending.unlink(missing_ok=True)


def build(gold, inspection_star, regional, output):
    dimensions, overlap = build_dimensions(gold, inspection_star, regional)
    with TemporaryDirectory() as directory:
        scratch = Path(directory)
        compact = scratch / "compact" / f"{VIOLATION_FACT}.parquet"
        compact.parent.mkdir()
        compact_violation_fact(violation_fact(gold, scratch), compact)
        with compact.open("rb") as stream:
            digest = file_digest(stream, "sha256").hexdigest()
        checksum = compact.with_suffix(".parquet.sha256")
        checksum.write_text(f"{digest}  {compact.name}\n", encoding="ascii", newline="\n")
        facts = {
            "01_fact_inspection": inspection_star / "01_fact_inspection.parquet",
            VIOLATION_FACT: compact,
            **{name: gold / "03_repeat_inspection" / f"{source}.parquet" for name, source in REPEAT_FACTS.items()},
            **{f"04_{name}": gold / "04_license" / f"04_{name}.parquet"
               for name in ("fact_license_event", "fact_inspection_license_match")},
            **{f"05_fact_{name}": regional / f"{name}.parquet" for name in REGIONAL_FACTS},
        }
        validate_facts(facts, dimensions, regional)
        for name, table in sorted(dimensions.items()):
            publish(output / "dimensions" / f"dim_{name}.parquet", table=table)
            print(f"dim_{name}.parquet: {len(table):,} rows")
        for name, source in sorted(facts.items()):
            publish(output / "facts" / f"{name}.parquet", source=source, link=name.startswith(("03_", "05_")))
            with pq.ParquetFile(source) as parquet:
                print(f"{name}.parquet: {parquet.metadata.num_rows:,} rows")
        publish(output / "facts" / checksum.name, source=checksum)
    print(f"Published {len(dimensions)} dimensions and {len(facts)} facts under {output}")
    print(f"Shared calendar dates collapsed: {overlap:,}")


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--gold-dir", type=Path, default=GOLD)
    parser.add_argument("--inspection-star", type=Path, help="Domain 01 Gold star_schema directory")
    parser.add_argument("--regional-gold", type=Path, help="Domain 05 Gold release directory")
    parser.add_argument("--output-dir", type=Path, help="Directory for shared facts and dimensions (default: Gold directory)")
    args = parser.parse_args()
    inspection_star = args.inspection_star or args.gold_dir / "01_inspection/analysis/star_schema"
    regional = args.regional_gold or regional_release(args.gold_dir)
    build(args.gold_dir, inspection_star, regional, args.output_dir or args.gold_dir)


if __name__ == "__main__":
    main()
