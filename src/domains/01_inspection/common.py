"""Shared paths and definitions."""

from hashlib import file_digest
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[3]
if not __package__ and str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from src.silver.shared_dictionary import CODE_MAP, load_shared_columns


DOMAIN = "01_inspection"
SOURCE = Path("data/00_origin/food_inspections.csv")
BRONZE = Path("data/01_bronze") / DOMAIN
SILVER = Path("data/02_silver") / DOMAIN
GOLD = Path("data/03_gold") / DOMAIN
AI_READY = Path("data/ai_ready") / DOMAIN
REPORTS = Path("reports") / DOMAIN
TABLE = "01_food_inspections.parquet"
RULE_FLAGS = "01_inspection_rule_flags.parquet"
VALIDATED = "01_validated_inspections.parquet"
PERFORMANCE_DETAIL = "01_performance_detail.parquet"
INSPECTION_FIELDS = load_shared_columns(ROOT)["food_inspections"]
COLUMNS = {field["source_column"]: field["target_column"] for field in INSPECTION_FIELDS}
TRANSFORMS = {field["target_column"]: field["transform"] for field in INSPECTION_FIELDS}
DECISIONS = ("PASS", "PASS W/ CONDITIONS", "FAIL")
MIN_DECISIONS = 100
GRAIN = ["inspection_year_num", "inspection_month_num", "facility_type", "inspection_type", "risk_level_cd"]


def digest(path):
    with path.open("rb") as file:
        return file_digest(file, "sha256").hexdigest()


def write_table(frame, target):
    frame.to_parquet(target, index=False, compression="zstd")
