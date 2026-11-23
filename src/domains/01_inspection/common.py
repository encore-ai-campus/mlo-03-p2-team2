"""Shared paths and definitions."""

from hashlib import file_digest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
DOMAIN = "01_inspection"
SOURCE = Path("data/00_origin/food_inspections.csv")
CODE_MAP = Path("metadata/data_dictionary/shared_code_map.csv")
BRONZE = Path("data/01_bronze") / DOMAIN
SILVER = Path("data/02_silver") / DOMAIN
GOLD = Path("data/03_gold") / DOMAIN
AI_READY = Path("data/ai_ready") / DOMAIN
REPORTS = Path("reports") / DOMAIN
TABLE = "01_food_inspections.parquet"
RULE_FLAGS = "01_inspection_rule_flags.parquet"
VALIDATED = "01_validated_inspections.parquet"
PERFORMANCE_DETAIL = "01_performance_detail.parquet"
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
    frame.to_parquet(target, index=False, compression="zstd")
