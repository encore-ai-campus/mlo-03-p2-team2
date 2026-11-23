"""Build and validate shared Gold dimensions from existing domain Gold tables."""

from argparse import ArgumentParser
from pathlib import Path
from shutil import copyfileobj
from tempfile import TemporaryDirectory

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


def verify_references(path, references):
    fact = pq.read_table(path, columns=list(references))
    for column, dimension_keys in references.items():
        values = fact[column]
        if values.null_count or pc.any(pc.invert(pc.is_in(pc.unique(values), dimension_keys))).as_py():
            raise ValueError(f"Missing dimension reference: {path.name}.{column}")
    print(f"{path.name}: verified {len(fact):,} fact rows")


def violation_fact(gold, scratch):
    fact = gold / "02_violation/02_fact_inspection_violation.parquet"
    if fact.is_file():
        return fact
    restored = scratch / fact.name
    with restored.open("wb") as output:
        for suffix in (".part-001", ".part-002"):
            with fact.with_suffix(f".parquet{suffix}").open("rb") as source:
                copyfileobj(source, output, length=1024 * 1024)
    return restored


def build(gold, inspection_star, output):
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

    output.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=output) as directory:
        scratch = Path(directory)
        verify_references(inspection_star / "01_fact_inspection.parquet", {
            "inspection_dtm": tables["date"]["calendar_dtm"],
            **{key: tables[name][key] for name, key in INSPECTION_KEYS.items()},
        })
        verify_references(violation_fact(gold, scratch), {"violation_key": tables["violation"]["violation_key"]})
        license_references = {"date_key": tables["date"]["date_key"],
                              **{key: tables[name][key] for name, key in LICENSE_KEYS.items()}}
        for name in ("fact_license_event", "fact_inspection_license_match"):
            verify_references(license_dir / f"04_{name}.parquet", license_references)
        for name, table in tables.items():
            pq.write_table(table, scratch / f"dim_{name}.parquet", compression="zstd")
        for name, table in sorted(tables.items()):
            filename = f"dim_{name}.parquet"
            (scratch / filename).replace(output / filename)
            print(f"{filename}: {len(table):,} rows")
    print(f"Shared calendar dates collapsed: {overlap:,}")


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--gold-dir", type=Path, default=GOLD)
    parser.add_argument("--inspection-star", type=Path, help="Domain 01 Gold star_schema directory")
    args = parser.parse_args()
    inspection_star = args.inspection_star or args.gold_dir / "01_inspection/analysis/star_schema"
    build(args.gold_dir, inspection_star, args.gold_dir / "dimensions")


if __name__ == "__main__":
    main()
