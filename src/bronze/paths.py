"""Central paths and source contracts for Bronze."""

from dataclasses import dataclass
from pathlib import Path
import os


PROJECT_ROOT = Path(__file__).resolve().parents[2]
_raw_dir = Path(os.environ.get("CHICAGO_RAW_DIR", "data/00_origin"))
ORIGIN_ROOT = _raw_dir if _raw_dir.is_absolute() else PROJECT_ROOT / _raw_dir
BRONZE_ROOT = PROJECT_ROOT / "data" / "01_bronze"
RUN_LOG = PROJECT_ROOT / "logs" / "pipeline_runs.csv"


@dataclass(frozen=True)
class Source:
    name: str
    relative_path: str
    expected_rows: int
    format: str

    @property
    def path(self) -> Path:
        return ORIGIN_ROOT / self.relative_path

    @property
    def output(self) -> Path:
        return BRONZE_ROOT / self.name / f"{self.name}.parquet"


SOURCES = (
    Source("food_inspections", "food_inspections/food_inspections.csv", 318_627, "csv"),
    Source("business_licenses", "business_licenses/business_licenses.csv", 1_212_282, "csv"),
    Source("community_areas", "community_areas/community_areas.csv", 77, "csv"),
)
