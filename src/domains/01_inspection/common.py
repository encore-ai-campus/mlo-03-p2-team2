"""Shared paths and definitions."""

from hashlib import file_digest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
DATA = ROOT / "data"
TABLE = "food_inspections.parquet"
COLUMNS = dict(zip(
    ["Inspection ID", "DBA Name", "AKA Name", "License #", "Facility Type",
     "Risk", "Address", "City", "State", "Zip", "Inspection Date",
     "Inspection Type", "Results", "Violations", "Latitude", "Longitude", "Location"],
    ["inspection_key", "dba_name", "aka_name", "license_number_key", "facility_type",
     "risk_level_cd", "address", "city", "state_cd", "zip_code", "inspection_dtm",
     "inspection_type", "result_cd", "violations_text", "latitude", "longitude", "location_text"],
    strict=True,
))
DECISIONS = ("PASS", "PASS W/ CONDITIONS", "FAIL")
MIN_DECISIONS = 100
GRAIN = ["inspection_year_num", "inspection_month_num", "facility_type", "inspection_type", "risk_level_cd"]


def digest(path):
    with path.open("rb") as file:
        return file_digest(file, "sha256").hexdigest()


def write_table(frame, target):
    frame.to_parquet(target, index=False)
